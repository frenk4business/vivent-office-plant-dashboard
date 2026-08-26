from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .cache import load_cache, save_cache
from .mock_data import create_mock_data, inject_test_water_alert
from .ui import DashboardWindow


DEFAULT_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Vivent Office Plants native dashboard")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--windowed", action="store_true", help="Do not enter fullscreen")
    parser.add_argument("--mock", action="store_true", help="Use built-in demonstration data")
    parser.add_argument("--test-water-alert", action="store_true", help="Show a clearly marked synthetic water alert")
    parser.add_argument("--check-data", action="store_true", help="Fetch once, print a summary, and exit")
    parser.add_argument(
        "--sync-channels",
        action="store_true",
        help="Discover new active trial sensors, update the local channel list, and exit",
    )
    parser.add_argument("--screenshot", type=Path, help="Save a UI screenshot and exit")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    test_water_alert = args.test_water_alert or os.environ.get("VIVENT_TEST_WATER_ALERT") == "1"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.mock:
        if args.sync_channels:
            logging.error("Channel synchronization is unavailable in mock mode")
            return 2
        data = create_mock_data()
        fetch = create_mock_data
        refresh_seconds = 300
        cached = data
    else:
        try:
            from vivent_dashboard_private.config import load_config
            from vivent_dashboard_private.repository import DashboardRepository
        except ImportError:
            logging.error(
                "The production data connector is not included in the public "
                "dashboard package; use --mock or install a private connector"
            )
            return 2
        try:
            config = load_config(args.env_file)
        except Exception as exc:
            logging.error("Configuration error: %s", exc)
            return 2
        repository = DashboardRepository(config)

        if args.sync_channels:
            try:
                from vivent_dashboard_private.channel_sync import synchronize_channels

                result = synchronize_channels(config, repository)
            except Exception as exc:
                logging.error("Channel synchronization failed: %s", exc)
                return 1
            changes = []
            if result.added:
                changes.append(f"added {', '.join(result.added)}")
            if result.renamed:
                changes.append(f"renamed {', '.join(result.renamed)}")
            summary = "; ".join(changes) if changes else "no changes"
            print(f"Channel sync OK via {result.source}: {result.total} plants; {summary}")
            return 0

        def fetch():
            current = repository.fetch()
            save_cache(config.cache_file, current)
            return inject_test_water_alert(current) if test_water_alert else current

        refresh_seconds = config.refresh_seconds
        cached = load_cache(config.cache_file)
        if cached and test_water_alert:
            cached = inject_test_water_alert(cached)

    if args.check_data:
        try:
            checked = fetch()
        except Exception as exc:
            logging.error("Data check failed: %s", exc)
            return 1
        print(f"Data OK: {len(checked.plants)} plants, {len(checked.water_alerts)} water alerts")
        return 0

    app = QApplication(sys.argv)
    app.setApplicationName("Vivent Office Plants")
    window = DashboardWindow(fetch, cached, refresh_seconds, fullscreen=not args.windowed and not args.screenshot)
    window.show_dashboard()
    if args.screenshot:
        def capture() -> None:
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            window.grab().save(str(args.screenshot))
            app.quit()
        QTimer.singleShot(1200, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
