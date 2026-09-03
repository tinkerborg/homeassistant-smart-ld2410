#!/usr/bin/env python3
"""Replay recorded LD2410 frames through the detector, outside of HA.

    uv run python scripts/replay.py <db> <sensor_id> [--start ISO] [--end ISO]
        [--k K] [--window S] [--enter SCORE] [--exit SCORE] [--hold S]
        [--freeze-hold S] [--min-mad MAD] [--support-tau S] [--csv out.csv]

Every ``DetectorConfig`` knob is exposed as a flag; omitted flags fall back
to the dataclass defaults. Deterministic: same DB + same flags always produce
identical output, since the detector never reads the wall clock.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from _csv import _writer as CsvWriter

# Run as a plain script (not `-m`), so the repo root -- parent of
# custom_components/ -- isn't on sys.path by default. Add it before
# importing the integration package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.smart_ld2410.algo.detector import Detector  # noqa: E402
from custom_components.smart_ld2410.algo.types import DetectorConfig, Frame  # noqa: E402
from custom_components.smart_ld2410.store import FrameStore  # noqa: E402


def _parse_iso_utc(value: str) -> float:
    """Parse an ISO 8601 timestamp to epoch seconds, assuming UTC if naive."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.timestamp()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db", type=Path, help="Path to frames.db")
    parser.add_argument("sensor_id", type=str, help="Sensor id (BT address) to replay")
    parser.add_argument("--start", type=str, default=None, help="ISO 8601 start (inclusive)")
    parser.add_argument("--end", type=str, default=None, help="ISO 8601 end (exclusive)")
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
        help="Write per-frame ts_utc,score,confidence,occupied,device_occupancy to this CSV path",
    )
    return parser


def _config_from_args(args: argparse.Namespace) -> DetectorConfig:
    overrides = {
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
    return DetectorConfig(**overrides)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if not args.db.exists():
        # FrameStore.__init__ creates the schema read-write on any path
        # handed to it, so without this check a typo'd path would silently
        # produce a fresh, empty database instead of erroring.
        parser.error(f"no such database file: {args.db}")

    config = _config_from_args(args)

    start_utc = _parse_iso_utc(args.start) if args.start else 0.0
    end_utc = _parse_iso_utc(args.end) if args.end else float("inf")

    store = FrameStore(args.db)
    detector = Detector(config)

    csv_writer: CsvWriter | None = None
    csv_file = args.csv.open("w", newline="") if args.csv is not None else None
    if csv_file is not None:
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(["ts_utc", "score", "confidence", "occupied", "device_occupancy"])

    total_frames = 0
    detector_transitions = 0
    device_transitions = 0
    detector_occupied_s = 0.0
    device_occupied_s = 0.0
    agreement_count = 0

    prev_frame: Frame | None = None
    prev_detector_occupied: bool | None = None
    prev_device_occupied: bool | None = None

    try:
        for frame in store.iter_frames(args.sensor_id, start_utc, end_utc):
            output = detector.process(frame)
            total_frames += 1

            if prev_frame is not None:
                dt = max(0.0, frame.ts_mono - prev_frame.ts_mono)
                if prev_detector_occupied:
                    detector_occupied_s += dt
                if prev_device_occupied:
                    device_occupied_s += dt

            ts = datetime.fromtimestamp(frame.ts_utc, tz=UTC).isoformat()

            if prev_detector_occupied is not None and output.occupied != prev_detector_occupied:
                detector_transitions += 1
                state = "OCCUPIED" if output.occupied else "VACANT"
                print(
                    f"{ts}  detector -> {state:8s} score={output.score:.2f} "
                    f"confidence={output.confidence:.2f} active_gates={list(output.active_gates)}"
                )
            if prev_device_occupied is not None and frame.device_occupancy != prev_device_occupied:
                device_transitions += 1
                state = "OCCUPIED" if frame.device_occupancy else "VACANT"
                print(f"{ts}  device   -> {state:8s}")

            if output.occupied == frame.device_occupancy:
                agreement_count += 1

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

            prev_frame = frame
            prev_detector_occupied = output.occupied
            prev_device_occupied = frame.device_occupancy
    finally:
        if csv_file is not None:
            csv_file.close()

    print()
    print(f"frames replayed:      {total_frames}")
    if total_frames:
        print(f"agreement:            {100.0 * agreement_count / total_frames:.1f}%")
    print(f"detector transitions: {detector_transitions}  time occupied: {detector_occupied_s:.1f}s")
    print(f"device transitions:   {device_transitions}  time occupied: {device_occupied_s:.1f}s")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
