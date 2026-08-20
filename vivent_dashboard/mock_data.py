from datetime import datetime, timedelta

from .models import DashboardData, PlantStatus, WaterAlert


def create_mock_data() -> DashboardData:
    now = datetime.now().astimezone()
    return DashboardData(
        water_alerts=[
            WaterAlert("Anthurium Meeting Room", 18, 17.5, now - timedelta(minutes=8)),
            WaterAlert("Pachira Lounge", 34, 22.25, now - timedelta(minutes=12)),
        ],
        plants=[
            PlantStatus("Anthurium Meeting Room", 27, "Critical", "Low Water Status", 18, 52, 47, now - timedelta(minutes=8)),
            PlantStatus("Pachira Lounge", 46, "Needs attention", "Low Water Status", 34, 61, 55, now - timedelta(minutes=12)),
            PlantStatus("Strelitzia Entrance", 78, "Thriving", "Within target", 28, 82, 76, now - timedelta(minutes=4)),
            PlantStatus("Strawberry Kitchen", 63, "Healthy", "Within target", 67, 64, 58, now - timedelta(minutes=16)),
            PlantStatus("Anthurium Window", None, "Offline", "Sensor offline", None, None, None, now - timedelta(hours=2, minutes=5)),
        ],
        fetched_at=now,
    )


def inject_test_water_alert(data: DashboardData) -> DashboardData:
    plant_name = data.plants[0].plant_name if data.plants else "Testplant"
    test_alert = WaterAlert(
        f"TEST — {plant_name}",
        32,
        16.25,
        datetime.now().astimezone(),
    )
    return DashboardData([test_alert, *data.water_alerts], data.plants, data.fetched_at)
