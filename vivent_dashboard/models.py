from __future__ import annotations

from dataclasses import asdict, dataclass
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


@dataclass(frozen=True)
class DashboardData:
    water_alerts: list[WaterAlert]
    plants: list[PlantStatus]
    fetched_at: datetime
    plant_of_week: PlantOfWeek | None = None

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
        return cls(
            alerts,
            plants,
            _datetime(value["fetched_at"]) or datetime.now().astimezone(),
            winner,
        )


def _datetime(value: str | datetime | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)
