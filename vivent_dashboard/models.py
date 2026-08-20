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
class DashboardData:
    water_alerts: list[WaterAlert]
    plants: list[PlantStatus]
    fetched_at: datetime

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["fetched_at"] = self.fetched_at.isoformat()
        for item in result["water_alerts"]:
            if item["last_seen"] is not None:
                item["last_seen"] = item["last_seen"].isoformat()
        for item in result["plants"]:
            if item["last_seen"] is not None:
                item["last_seen"] = item["last_seen"].isoformat()
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
        return cls(alerts, plants, _datetime(value["fetched_at"]) or datetime.now().astimezone())


def _datetime(value: str | datetime | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)
