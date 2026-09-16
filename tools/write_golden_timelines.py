"""Rewrite the golden occupancy timelines under tests/fixtures/golden.

Run after a deliberate behaviour change; the diff is the change's evidence.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from custom_components.smart_ld2410.algo.harness import (  # noqa: E402
    replay,
    sensor_ids,
    timeline_rows,
)
from custom_components.smart_ld2410.algo.types import ALL_STAGES  # noqa: E402

RECORDINGS = ROOT / "tests" / "fixtures" / "recordings"
GOLDEN = ROOT / "tests" / "fixtures" / "golden"


def main() -> int:
    """Replay every fixture at default tuning and write its timeline."""
    GOLDEN.mkdir(parents=True, exist_ok=True)
    for recording in sorted(RECORDINGS.glob("*.db")):
        timelines = {
            sensor_id: timeline_rows(replay(recording, sensor_id, stages=ALL_STAGES))
            for sensor_id in sensor_ids(recording)
        }
        (GOLDEN / f"{recording.stem}.json").write_text(
            json.dumps(timelines, indent=2) + "\n"
        )
        print(f"{recording.stem}: {sum(len(rows) for rows in timelines.values())} events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
