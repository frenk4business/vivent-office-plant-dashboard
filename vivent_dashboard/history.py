from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import sqlite3

from .models import HallOfFameEntry, HistoricalWinner


@dataclass(frozen=True)
class FinalizedWeek:
    week_start: datetime
    week_end: datetime
    plant_key: str | None
    channel_id: str | None
    plant_name: str | None
    league_score: float | None
    data_completeness: float | None
    online_coverage: float | None
    finalized_at: datetime


class PlantOfWeekHistory:
    """Small local ledger of immutable, completed Plant-of-the-Week results."""

    def __init__(self, path: Path):
        self.path = path
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS weekly_results (
                    week_start TEXT PRIMARY KEY,
                    week_end TEXT NOT NULL,
                    plant_key TEXT,
                    channel_id TEXT,
                    plant_name TEXT,
                    league_score REAL,
                    data_completeness REAL,
                    online_coverage REAL,
                    finalized_at TEXT NOT NULL
                )
                """
            )
        os.chmod(self.path, 0o600)

    def has_week(self, week_start: datetime) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM weekly_results WHERE week_start = ?",
                (week_start.isoformat(),),
            ).fetchone()
        return row is not None

    def record(self, result: FinalizedWeek) -> bool:
        """Record a completed week once; returns False if it was already finalized."""
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO weekly_results (
                    week_start, week_end, plant_key, channel_id, plant_name,
                    league_score, data_completeness, online_coverage, finalized_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.week_start.isoformat(),
                    result.week_end.isoformat(),
                    result.plant_key,
                    result.channel_id,
                    result.plant_name,
                    result.league_score,
                    result.data_completeness,
                    result.online_coverage,
                    result.finalized_at.isoformat(),
                ),
            )
        return cursor.rowcount == 1

    def backup(self, created_at: datetime | None = None) -> Path:
        timestamp = (created_at or datetime.now().astimezone()).strftime(
            "%Y%m%dT%H%M%S%f"
        )
        destination = self.path.with_name(
            f"{self.path.stem}.backup-{timestamp}{self.path.suffix}"
        )
        with self._connect() as source:
            with sqlite3.connect(destination) as target:
                source.backup(target)
        os.chmod(destination, 0o600)
        return destination

    def replace_from(
        self,
        week_start: datetime,
        results: list[FinalizedWeek],
    ) -> int:
        """Atomically replace finalized results from a competition week onward."""
        if not results:
            raise ValueError("History replacement requires at least one completed week")
        starts = [result.week_start for result in results]
        if len(set(starts)) != len(starts):
            raise ValueError("History replacement contains duplicate week starts")
        if any(start < week_start for start in starts):
            raise ValueError("History replacement contains a pre-competition week")
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM weekly_results WHERE week_start >= ?",
                (week_start.isoformat(),),
            )
            connection.executemany(
                """
                INSERT INTO weekly_results (
                    week_start, week_end, plant_key, channel_id, plant_name,
                    league_score, data_completeness, online_coverage, finalized_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        result.week_start.isoformat(),
                        result.week_end.isoformat(),
                        result.plant_key,
                        result.channel_id,
                        result.plant_name,
                        result.league_score,
                        result.data_completeness,
                        result.online_coverage,
                        result.finalized_at.isoformat(),
                    )
                    for result in sorted(results, key=lambda item: item.week_start)
                ],
            )
        return len(results)

    def migrate_plant_key(self, channel_id: str, plant_key: str) -> int:
        """Attach older sensor-keyed wins when a stable Plant ID becomes available."""
        if plant_key == channel_id:
            return 0
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE weekly_results
                SET plant_key = ?
                WHERE channel_id = ? AND plant_key = ?
                """,
                (plant_key, channel_id, channel_id),
            )
        return cursor.rowcount

    def discard_before(self, week_start: datetime) -> int:
        """Remove results from before the official competition start."""
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM weekly_results WHERE week_start < ?",
                (week_start.isoformat(),),
            )
        return cursor.rowcount

    def hall_of_fame(self) -> list[HallOfFameEntry]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                WITH totals AS (
                    SELECT plant_key, COUNT(*) AS wins,
                           MAX(week_start) AS last_win,
                           AVG(league_score) AS average_score
                    FROM weekly_results
                    WHERE plant_key IS NOT NULL
                    GROUP BY plant_key
                )
                SELECT t.plant_key, w.plant_name, t.wins, t.last_win, t.average_score
                FROM totals t
                JOIN weekly_results w
                  ON w.plant_key = t.plant_key AND w.week_start = t.last_win
                ORDER BY t.wins DESC, t.average_score DESC, t.last_win DESC,
                         w.plant_name COLLATE NOCASE
                """
            ).fetchall()
        return [
            HallOfFameEntry(
                plant_key=row["plant_key"],
                plant_name=row["plant_name"],
                wins=row["wins"],
                last_win=datetime.fromisoformat(row["last_win"]),
                average_winning_score=row["average_score"],
            )
            for row in rows
        ]

    def recent_winners(self, limit: int = 5) -> list[HistoricalWinner]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT week_start, week_end, plant_key, plant_name, league_score
                FROM weekly_results
                WHERE plant_key IS NOT NULL
                ORDER BY week_start DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            HistoricalWinner(
                week_start=datetime.fromisoformat(row["week_start"]),
                week_end=datetime.fromisoformat(row["week_end"]),
                plant_key=row["plant_key"],
                plant_name=row["plant_name"],
                league_score=row["league_score"],
            )
            for row in rows
        ]

    def finalized_week_starts(self) -> set[datetime]:
        with self._connect() as connection:
            rows = connection.execute("SELECT week_start FROM weekly_results").fetchall()
        return {datetime.fromisoformat(row["week_start"]) for row in rows}
