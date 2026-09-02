from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class WaterAlert:
    plant_name: str
    water_score: float
    low_hours: float
    last_seen: datetime | None


@dataclass(frozen=True)
class PlantStatus:
    plant_name: str
    health_score: float | None
    status: str
    main_issue: str
    water_score: float | None
    activity_score: float | None
    nutrient_score: float | None
    last_seen: datetime | None
    activity_calibrating: bool = False


@dataclass(frozen=True)
class PlantOfWeek:
    plant_name: str
    league_score: float
    previous_period_score: float | None
    score_change: float | None
    data_completeness: float
    online_coverage: float | None
    week_start: datetime
    week_end: datetime
    badge: str
    is_final: bool = False
    plant_key: str | None = None
    channel_id: str | None = None


@dataclass(frozen=True)
class HallOfFameEntry:
    plant_key: str
    plant_name: str
    wins: int
    last_win: datetime
    average_winning_score: float


@dataclass(frozen=True)
class HistoricalWinner:
    week_start: datetime
    week_end: datetime
    plant_key: str
    plant_name: str
    league_score: float


@dataclass(frozen=True)
class DashboardData:
    water_alerts: list[WaterAlert]
    plants: list[PlantStatus]
    fetched_at: datetime
    plant_of_week: PlantOfWeek | None = None
    hall_of_fame: list[HallOfFameEntry] = field(default_factory=list)
    recent_winners: list[HistoricalWinner] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["fetched_at"] = self.fetched_at.isoformat()
        for item in result["water_alerts"]:
            if item["last_seen"] is not None:
                item["last_seen"] = item["last_seen"].isoformat()
        for item in result["plants"]:
            if item["last_seen"] is not None:
                item["last_seen"] = item["last_seen"].isoformat()
        winner = result.get("plant_of_week")
        if winner is not None:
            winner["week_start"] = winner["week_start"].isoformat()
            winner["week_end"] = winner["week_end"].isoformat()
        for item in result["hall_of_fame"]:
            item["last_win"] = item["last_win"].isoformat()
        for item in result["recent_winners"]:
            item["week_start"] = item["week_start"].isoformat()
            item["week_end"] = item["week_end"].isoformat()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "DashboardData":
        alerts = [
            WaterAlert(**{**item, "last_seen": _datetime(item.get("last_seen"))})
            for item in value.get("water_alerts", [])
        ]
        plants = [
            PlantStatus(**{**item, "last_seen": _datetime(item.get("last_seen"))})
            for item in value.get("plants", [])
        ]
        winner_value = value.get("plant_of_week")
        winner = None
        if winner_value:
            winner = PlantOfWeek(
                **{
                    **winner_value,
                    "week_start": _datetime(winner_value["week_start"]),
                    "week_end": _datetime(winner_value["week_end"]),
                }
            )
        hall_of_fame = [
            HallOfFameEntry(**{**item, "last_win": _datetime(item["last_win"])})
            for item in value.get("hall_of_fame", [])
        ]
        recent_winners = [
            HistoricalWinner(
                **{
                    **item,
                    "week_start": _datetime(item["week_start"]),
                    "week_end": _datetime(item["week_end"]),
                }
            )
            for item in value.get("recent_winners", [])
        ]
        return cls(
            alerts,
            plants,
            _datetime(value["fetched_at"]) or datetime.now().astimezone(),
            winner,
            hall_of_fame,
            recent_winners,
        )


def _datetime(value: str | datetime | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)
