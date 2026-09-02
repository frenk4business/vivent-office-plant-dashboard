from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import tempfile


@dataclass(frozen=True)
class ActivityReset:
    reset_at: datetime
    calibration_until: datetime


class ActivityResetRegistry:
    """Local record of electrode resets that start a new Activity baseline."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, datetime]:
        """Return baseline start times for compatibility with older callers."""
        return {
            channel_id: reset.reset_at
            for channel_id, reset in self.load_records().items()
        }

    def load_records(self) -> dict[str, ActivityReset]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid Activity reset registry in {self.path}")
        records: dict[str, ActivityReset] = {}
        for channel_id, value in payload.items():
            if isinstance(value, dict):
                try:
                    reset_at = datetime.fromisoformat(str(value["reset_at"]))
                    calibration_until = datetime.fromisoformat(
                        str(value["calibration_until"])
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Invalid Activity reset for {channel_id} in {self.path}"
                    ) from exc
            else:
                # Legacy format: the value itself was the reset timestamp.
                reset_at = datetime.fromisoformat(str(value))
                calibration_until = reset_at + timedelta(days=7)
            records[str(channel_id)] = ActivityReset(
                reset_at=reset_at,
                calibration_until=calibration_until,
            )
        return records

    def record(self, channel_id: str, reset_at: datetime) -> None:
        records = self.load_records()
        records[channel_id] = ActivityReset(
            reset_at=reset_at,
            calibration_until=reset_at + timedelta(days=7),
        )
        self._write(records)

    def end_calibration(self, channel_id: str, ended_at: datetime) -> ActivityReset:
        records = self.load_records()
        try:
            current = records[channel_id]
        except KeyError as exc:
            raise ValueError(f"No Activity reset is registered for {channel_id}") from exc
        updated = ActivityReset(current.reset_at, ended_at)
        records[channel_id] = updated
        self._write(records)
        return updated

    def _write(self, records: dict[str, ActivityReset]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            delete=False,
        ) as temporary:
            json.dump(
                {
                    key: {
                        "reset_at": value.reset_at.isoformat(),
                        "calibration_until": value.calibration_until.isoformat(),
                    }
                    for key, value in sorted(records.items())
                },
                temporary,
                indent=2,
            )
            temporary.write("\n")
            temporary_path = Path(temporary.name)
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, self.path)
