"""Replay recorded LD2410 frames through the detector, outside of HA.

Run as a module, per docs/spec/10-interfaces.md §3::

    uv run python -m custom_components.smart_ld2410.replay \\
        --db PATH --sensor ID --from TS --to TS \\
        [--params overrides.json] [--emit episodes|states|frames]
        [--k K] [--window S] [--enter SCORE] [--exit SCORE] [--hold S]
        [--freeze-hold S] [--min-mad MAD] [--support-tau S] [--csv out.csv]

``--from``/``--to`` accept either epoch seconds or an ISO 8601 timestamp
(naive timestamps are assumed UTC); both default to the full range of
recorded frames. Every ``DetectorConfig`` knob is exposed as a flag;
omitted flags fall back to the dataclass defaults, or to ``--params``
(a JSON object of overrides) when given -- explicit flags win over
``--params``.

Determinism requirement (§3): identical DB + params always produce
byte-identical output, since neither the detector nor this harness reads the
wall clock -- ``--emit`` selects *what* is printed, not how it's computed.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from .algo.detector import Detector
from .algo.types import DetectorConfig, DetectorOutput, Frame
from .store import FrameStore

if TYPE_CHECKING:
    from _csv import _writer as CsvWriter

EmitMode = Literal["episodes", "states", "frames"]


def _parse_ts(value: str) -> float:
    """Parse a timestamp given as epoch seconds or ISO 8601 (naive == UTC)."""
    try:
        return float(value)
    except ValueError:
        pass
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.timestamp()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m custom_components.smart_ld2410.replay", description=__doc__
    )
    parser.add_argument("--db", type=Path, required=True, help="Path to frames.db")
    parser.add_argument("--sensor", dest="sensor_id", type=str, required=True, help="Sensor id")
    parser.add_argument(
        "--from", dest="from_ts", type=str, default=None,
        help="Range start, inclusive (epoch seconds or ISO 8601; default: earliest frame)",
    )
    parser.add_argument(
        "--to", dest="to_ts", type=str, default=None,
        help="Range end, exclusive (epoch seconds or ISO 8601; default: unbounded)",
    )
    parser.add_argument(
        "--emit", choices=("episodes", "states", "frames"), default="states",
        help="What to print to stdout (default: states)",
    )
    parser.add_argument(
        "--params", type=Path, default=None,
        help="JSON object of DetectorConfig field overrides; explicit flags below win over these",
    )
    parser.add_argument("--k", type=float, default=None, help="Exceedance threshold: median + k*MAD")
    parser.add_argument(
        "--window", dest="baseline_window_s", type=float, default=None,
        help="Baseline rolling window, seconds",
    )
    parser.add_argument(
        "--enter", dest="enter_score", type=float, default=None,
        help="Aggregate score required to enter occupied",
    )
    parser.add_argument(
        "--exit", dest="exit_score", type=float, default=None,
        help="Score below which the exit hold timer runs",
    )
    parser.add_argument(
        "--hold", dest="hold_s", type=float, default=None,
        help="Seconds occupied is held once score drops below --exit",
    )
    parser.add_argument(
        "--freeze-hold", dest="freeze_hold_s", type=float, default=None,
        help="Seconds baseline adaptation stays frozen after occupancy ends",
    )
    parser.add_argument("--min-mad", dest="min_mad", type=float, default=None, help="MAD floor")
    parser.add_argument(
        "--support-tau", dest="support_tau_s", type=float, default=None,
        help="Time constant for the neighbour-elevation support test, seconds",
    )
    parser.add_argument(
        "--csv", type=Path, default=None,
        help="Also write per-frame ts,score,confidence,occupied,device_occupancy to this CSV path",
    )
    return parser


def _config_from_args(args: argparse.Namespace) -> DetectorConfig:
    config = DetectorConfig()
    if args.params is not None:
        overrides = json.loads(args.params.read_text())
        config = replace(config, **overrides)
    flag_overrides = {
        name: value
        for name, value in (
            ("k", args.k),
            ("baseline_window_s", args.baseline_window_s),
            ("enter_score", args.enter_score),
            ("exit_score", args.exit_score),
            ("hold_s", args.hold_s),
            ("freeze_hold_s", args.freeze_hold_s),
            ("min_mad", args.min_mad),
            ("support_tau_s", args.support_tau_s),
        )
        if value is not None
    }
    return replace(config, **flag_overrides)


class _EpisodeAccumulator:
    """Segments contiguous occupied runs into episode-shaped summaries.

    Best-effort: fields that only a later phase's episode detector can
    produce (label, label_source, label_conf, centroid_vel) are left at
    their contract-default/unknown value here.
    """

    def __init__(self) -> None:
        self._t0: float | None = None
        self._peak_residual = 0.0
        self._gate_lo: int | None = None
        self._gate_hi: int | None = None
        self._still_frame_count = 0
        self._frame_count = 0
        self._t_last = 0.0

    def update(self, frame: Frame, output: DetectorOutput) -> tuple[float, ...] | None:
        """Feed one frame's output; returns a closed episode row when one just ended."""
        closed = None
        if output.occupied:
            if self._t0 is None:
                self._t0 = frame.ts_utc
                self._peak_residual = 0.0
                self._gate_lo = None
                self._gate_hi = None
                self._still_frame_count = 0
                self._frame_count = 0
            self._peak_residual = max(self._peak_residual, output.score)
            if output.active_gates:
                lo, hi = min(output.active_gates), max(output.active_gates)
                self._gate_lo = lo if self._gate_lo is None else min(self._gate_lo, lo)
                self._gate_hi = hi if self._gate_hi is None else max(self._gate_hi, hi)
            still_dominant = sum(output.residuals_still) >= sum(output.residuals_move)
            self._still_frame_count += int(still_dominant)
            self._frame_count += 1
            self._t_last = frame.ts_utc
        elif self._t0 is not None:
            closed = self._close()
        return closed

    def finish(self) -> tuple[float, ...] | None:
        if self._t0 is not None:
            return self._close()
        return None

    def _close(self) -> tuple[float, ...]:
        still_frac = self._still_frame_count / self._frame_count if self._frame_count else 0.0
        row = (
            self._t0,
            self._t_last,
            self._peak_residual,
            self._gate_lo if self._gate_lo is not None else 0,
            self._gate_hi if self._gate_hi is not None else 0,
            still_frac,
        )
        self._t0 = None
        return row


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if not args.db.exists():
        # FrameStore.__init__ creates the schema read-write on any path
        # handed to it, so without this check a typo'd path would silently
        # produce a fresh, empty database instead of erroring.
        parser.error(f"no such database file: {args.db}")

    config = _config_from_args(args)

    start_utc = _parse_ts(args.from_ts) if args.from_ts else 0.0
    end_utc = _parse_ts(args.to_ts) if args.to_ts else float("inf")
    emit: EmitMode = args.emit

    store = FrameStore(args.db)
    detector = Detector(config)

    csv_writer: CsvWriter | None = None
    csv_file = args.csv.open("w", newline="") if args.csv is not None else None
    if csv_file is not None:
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(["ts_utc", "score", "confidence", "occupied", "device_occupancy"])

    stdout = csv.writer(sys.stdout)
    if emit == "frames":
        stdout.writerow(["ts", "ts_mono", "move", "still", "distance_cm", "device_occ"])
    elif emit == "states":
        stdout.writerow(["ts", "score", "confidence", "occupied", "active_gates"])
    else:
        stdout.writerow(["t0", "t1", "peak_residual", "gate_lo", "gate_hi", "still_frac"])

    episodes = _EpisodeAccumulator()
    total_frames = 0

    try:
        for frame in store.iter_frames(args.sensor_id, start_utc, end_utc):
            output = detector.process(frame)
            total_frames += 1

            if emit == "frames":
                stdout.writerow(
                    [
                        f"{frame.ts_utc:.3f}",
                        f"{frame.ts_mono:.3f}",
                        "|".join(str(v) for v in frame.move_gates),
                        "|".join(str(v) for v in frame.still_gates),
                        frame.target_distance_cm,
                        int(frame.device_occupancy),
                    ]
                )
            elif emit == "states":
                stdout.writerow(
                    [
                        f"{frame.ts_utc:.3f}",
                        f"{output.score:.4f}",
                        f"{output.confidence:.4f}",
                        int(output.occupied),
                        "|".join(str(g) for g in output.active_gates),
                    ]
                )
            else:
                closed = episodes.update(frame, output)
                if closed is not None:
                    t0, t1, peak_residual, gate_lo, gate_hi, still_frac = closed
                    stdout.writerow(
                        [f"{t0:.3f}", f"{t1:.3f}", f"{peak_residual:.4f}", gate_lo, gate_hi, f"{still_frac:.4f}"]
                    )

            if csv_writer is not None:
                csv_writer.writerow(
                    [
                        f"{frame.ts_utc:.3f}",
                        f"{output.score:.4f}",
                        f"{output.confidence:.4f}",
                        int(output.occupied),
                        int(frame.device_occupancy),
                    ]
                )
    finally:
        if csv_file is not None:
            csv_file.close()

    if emit == "episodes":
        closed = episodes.finish()
        if closed is not None:
            t0, t1, peak_residual, gate_lo, gate_hi, still_frac = closed
            stdout.writerow(
                [f"{t0:.3f}", f"{t1:.3f}", f"{peak_residual:.4f}", gate_lo, gate_hi, f"{still_frac:.4f}"]
            )

    print(f"# frames replayed: {total_frames}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
