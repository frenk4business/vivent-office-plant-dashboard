from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest

from vivent_dashboard.cache import load_cache, save_cache
from vivent_dashboard.history import FinalizedWeek, PlantOfWeekHistory
from vivent_dashboard.mock_data import create_mock_data, inject_test_water_alert
from vivent_dashboard.signal_quality import ActivityReset, ActivityResetRegistry
from vivent_dashboard.ui import POWER_OFF_COMMAND, _water_alert_message, _week_label


class DashboardTests(unittest.TestCase):
    def test_cache_roundtrip(self):
        expected = create_mock_data()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.json"
            save_cache(path, expected)
            actual = load_cache(path)
        self.assertEqual(actual, expected)

    def test_cache_from_before_history_and_calibration_remains_compatible(self):
        payload = create_mock_data().to_dict()
        payload.pop("hall_of_fame")
        payload.pop("recent_winners")
        for plant in payload["plants"]:
            plant.pop("activity_calibrating")

        from vivent_dashboard.models import DashboardData

        restored = DashboardData.from_dict(payload)
        self.assertEqual(restored.hall_of_fame, [])
        self.assertEqual(restored.recent_winners, [])
        self.assertTrue(
            all(not plant.activity_calibrating for plant in restored.plants)
        )

    def test_water_alert_is_trilingual_and_explicit(self):
        alert = create_mock_data().water_alerts[:1]
        message = _water_alert_message(alert)
        self.assertIn("AANHOUDEND LAAG", message)
        self.assertIn("SUSTAINED LOW", message)
        self.assertIn("NL aarde", message)
        self.assertIn("EN soil", message)
        self.assertIn("ES tierra", message)

    def test_synthetic_alert_is_clearly_marked(self):
        data = inject_test_water_alert(create_mock_data())
        message = _water_alert_message(data.water_alerts)
        self.assertIn("TEST • NIET WATER GEVEN • DO NOT WATER • NO REGAR", message)

    def test_poweroff_uses_systemd_without_a_shell(self):
        self.assertEqual(
            POWER_OFF_COMMAND,
            ["/usr/bin/systemctl", "poweroff", "--no-wall", "--no-ask-password"],
        )

    def test_week_label_runs_from_monday_through_sunday(self):
        start = datetime.fromisoformat("2026-08-17T00:00:00+02:00")
        end = datetime.fromisoformat("2026-08-23T23:59:59+02:00")
        self.assertEqual(_week_label(start, end), "Week 34  •  17–23 aug 2026")

    def test_history_records_a_completed_week_only_once(self):
        start = datetime.fromisoformat("2026-08-17T00:00:00")
        with tempfile.TemporaryDirectory() as directory:
            history = PlantOfWeekHistory(Path(directory) / "history.sqlite3")
            result = FinalizedWeek(
                start,
                start + timedelta(days=7) - timedelta(seconds=1),
                "plant-1",
                "sensor-1",
                "Anthurium",
                81,
                100,
                95,
                datetime.fromisoformat("2026-08-24T08:05:00+02:00"),
            )
            self.assertTrue(history.record(result))
            self.assertFalse(history.record(result))
            self.assertEqual(history.hall_of_fame()[0].wins, 1)
            self.assertEqual(history.path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(history.path.parent.stat().st_mode & 0o777, 0o700)

    def test_history_finalizes_a_week_without_an_eligible_winner(self):
        start = datetime.fromisoformat("2026-08-17T00:00:00")
        with tempfile.TemporaryDirectory() as directory:
            history = PlantOfWeekHistory(Path(directory) / "history.sqlite3")
            result = FinalizedWeek(
                start,
                start + timedelta(days=7) - timedelta(seconds=1),
                None,
                None,
                None,
                None,
                None,
                None,
                datetime.fromisoformat("2026-08-24T08:05:00+02:00"),
            )

            self.assertTrue(history.record(result))
            self.assertFalse(history.record(result))
            self.assertEqual(history.finalized_week_starts(), {start})
            self.assertEqual(history.hall_of_fame(), [])
            self.assertEqual(history.recent_winners(), [])

    def test_history_rebuild_is_atomic_and_keeps_a_backup(self):
        start = datetime.fromisoformat("2026-07-20T00:00:00")
        finalized_at = datetime.fromisoformat("2026-07-27T08:05:00+02:00")
        with tempfile.TemporaryDirectory() as directory:
            history = PlantOfWeekHistory(Path(directory) / "history.sqlite3")
            original = FinalizedWeek(
                start,
                start + timedelta(days=7) - timedelta(seconds=1),
                "plant-old",
                "sensor-old",
                "Old winner",
                61,
                100,
                90,
                finalized_at,
            )
            replacement = FinalizedWeek(
                start,
                start + timedelta(days=7) - timedelta(seconds=1),
                "plant-new",
                "sensor-new",
                "New winner",
                72,
                100,
                95,
                finalized_at,
            )
            history.record(original)
            backup_path = history.backup(finalized_at)
            self.assertEqual(backup_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(history.replace_from(start, [replacement]), 1)
            self.assertEqual(history.hall_of_fame()[0].plant_name, "New winner")
            self.assertEqual(
                PlantOfWeekHistory(backup_path).hall_of_fame()[0].plant_name,
                "Old winner",
            )

            with self.assertRaisesRegex(ValueError, "duplicate week starts"):
                history.replace_from(start, [replacement, replacement])
            self.assertEqual(history.hall_of_fame()[0].plant_name, "New winner")

    def test_history_scoreboard_aggregates_by_stable_plant_key(self):
        start = datetime.fromisoformat("2026-08-03T00:00:00")
        with tempfile.TemporaryDirectory() as directory:
            history = PlantOfWeekHistory(Path(directory) / "history.sqlite3")
            for offset, name, score in (
                (0, "Oude naam", 70),
                (7, "Nieuwe naam", 90),
            ):
                week = start + timedelta(days=offset)
                history.record(
                    FinalizedWeek(
                        week,
                        week + timedelta(days=7) - timedelta(seconds=1),
                        "same-plant-id",
                        f"sensor-{offset}",
                        name,
                        score,
                        100,
                        95,
                        datetime.now().astimezone(),
                    )
                )
            entry = history.hall_of_fame()[0]
            self.assertEqual(entry.plant_name, "Nieuwe naam")
            self.assertEqual(entry.wins, 2)
            self.assertEqual(entry.average_winning_score, 80)
            self.assertEqual(len(history.recent_winners()), 2)

    def test_history_migrates_sensor_key_to_new_plant_id(self):
        start = datetime.fromisoformat("2026-08-03T00:00:00")
        with tempfile.TemporaryDirectory() as directory:
            history = PlantOfWeekHistory(Path(directory) / "history.sqlite3")
            history.record(
                FinalizedWeek(
                    start,
                    start + timedelta(days=7) - timedelta(seconds=1),
                    "sensor-1",
                    "sensor-1",
                    "Plant",
                    75,
                    100,
                    95,
                    datetime.now().astimezone(),
                )
            )
            self.assertEqual(history.migrate_plant_key("sensor-1", "plant-uuid"), 1)
            self.assertEqual(history.hall_of_fame()[0].plant_key, "plant-uuid")

    def test_history_discards_results_before_competition_start(self):
        start = datetime.fromisoformat("2026-07-13T00:00:00")
        with tempfile.TemporaryDirectory() as directory:
            history = PlantOfWeekHistory(Path(directory) / "history.sqlite3")
            for offset in (0, 7):
                week = start + timedelta(days=offset)
                history.record(
                    FinalizedWeek(
                        week,
                        week + timedelta(days=7) - timedelta(seconds=1),
                        "plant-1",
                        "sensor-1",
                        "Plant",
                        75,
                        100,
                        95,
                        datetime.now().astimezone(),
                    )
                )
            removed = history.discard_before(datetime.fromisoformat("2026-07-20"))
            self.assertEqual(removed, 1)
            self.assertEqual(history.hall_of_fame()[0].wins, 1)

    def test_activity_reset_registry_roundtrip_and_permissions(self):
        reset_at = datetime.fromisoformat("2026-08-26T10:15:00+02:00")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "activity-resets.json"
            registry = ActivityResetRegistry(path)
            registry.record("sensor-1", reset_at)
            self.assertEqual(registry.load(), {"sensor-1": reset_at})
            self.assertEqual(
                registry.load_records(),
                {
                    "sensor-1": ActivityReset(
                        reset_at,
                        reset_at + timedelta(days=7),
                    )
                },
            )
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)

    def test_activity_calibration_can_end_without_changing_baseline(self):
        reset_at = datetime.fromisoformat("2026-08-26T10:15:00+02:00")
        ended_at = datetime.fromisoformat("2026-09-02T07:35:00+02:00")
        with tempfile.TemporaryDirectory() as directory:
            registry = ActivityResetRegistry(Path(directory) / "activity-resets.json")
            registry.record("sensor-1", reset_at)
            updated = registry.end_calibration("sensor-1", ended_at)
            self.assertEqual(updated, ActivityReset(reset_at, ended_at))
            self.assertEqual(registry.load(), {"sensor-1": reset_at})
            self.assertEqual(registry.load_records(), {"sensor-1": updated})

    def test_activity_reset_registry_reads_legacy_timestamp_format(self):
        reset_at = datetime.fromisoformat("2026-08-26T10:15:00+02:00")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "activity-resets.json"
            path.write_text(
                '{"sensor-1": "2026-08-26T10:15:00+02:00"}\n',
                encoding="utf-8",
            )
            registry = ActivityResetRegistry(path)
            self.assertEqual(
                registry.load_records(),
                {
                    "sensor-1": ActivityReset(
                        reset_at,
                        reset_at + timedelta(days=7),
                    )
                },
            )

    def test_activity_reset_registry_preserves_other_sensors(self):
        first = datetime.fromisoformat("2026-08-26T10:15:00+02:00")
        second = datetime.fromisoformat("2026-08-27T09:00:00+02:00")
        with tempfile.TemporaryDirectory() as directory:
            registry = ActivityResetRegistry(Path(directory) / "activity-resets.json")
            registry.record("sensor-1", first)
            registry.record("sensor-2", second)
            self.assertEqual(
                registry.load(),
                {"sensor-1": first, "sensor-2": second},
            )


if __name__ == "__main__":
    unittest.main()
