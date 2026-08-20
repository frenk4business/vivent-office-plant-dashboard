from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from vivent_dashboard.cache import load_cache, save_cache
from vivent_dashboard.mock_data import create_mock_data, inject_test_water_alert
from vivent_dashboard.ui import POWER_OFF_COMMAND, _water_alert_message


class DashboardTests(unittest.TestCase):
    def test_cache_roundtrip(self):
        expected = create_mock_data()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.json"
            save_cache(path, expected)
            actual = load_cache(path)
        self.assertEqual(actual, expected)

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


if __name__ == "__main__":
    unittest.main()
