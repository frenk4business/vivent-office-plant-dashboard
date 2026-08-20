# Vivent Office Plants Dashboard

Native fullscreen Raspberry Pi dashboard built with Python 3 and PySide6/Qt 6.
Version 1 shows **Plants Need Water** and **Plant Squad** and refreshes every five
minutes.

The application is designed as a kiosk dashboard for the Vivent Biosignals
office in Zeist.

## Project goal

The goal of this project is to turn plant biosignal data into a clear,
always-visible office overview. Colleagues can immediately see which plants may
need attention, while the dashboard remains simple enough to run unattended on
a wall-mounted Raspberry Pi display.

The screen combines a prominent multilingual water alert with a compact health
overview for all monitored office plants. It is intentionally independent of a
browser-based dashboard so the installation can start automatically and keep
working as a dedicated kiosk.

## What I built

I created and configured the complete office dashboard installation:

- a native fullscreen PySide6 interface for Raspberry Pi;
- a live plant-health and water-alert overview;
- read-only data access, local caching and a clear offline state;
- mock data and automated tests for development without production access;
- an official Vivent Biosignals branded header;
- a two-step safe shutdown button for the Pi and display;
- a system timer that safely shuts down the installation every day at 17:00;
- improved, high-contrast health percentages for readability at a distance.

## Public demo and private data connector

This public repository contains the complete kiosk interface, mock data,
offline cache, automated tests and Raspberry Pi service configuration. Run it
with `--mock` to explore the dashboard without credentials or production data.

The production data connector is deliberately kept outside this repository.
It contains deployment-specific database integration, internal metric names
and scoring rules. The launcher automatically uses that private connector when
it is installed locally; otherwise it starts the safe mock-data version.

## Runtime packages

Installed from Debian packages:

```text
python3-pyside6.qtcore
python3-pyside6.qtgui
python3-pyside6.qtwidgets
```

## Local checks

```bash
python3 -m unittest discover -s tests -v
QT_QPA_PLATFORM=offscreen python3 -m vivent_dashboard --mock --screenshot /tmp/vivent-dashboard.png
```

No `.env`, production connector, channel mapping or production dataset is
included in the public source tree.

The user service is installed as `vivent-dashboard.service`. It waits for the
Wayland session, runs fullscreen, and is restarted by systemd after a crash.
Application logs are available with:

```bash
journalctl --user -u vivent-dashboard.service
```

The fullscreen UI has a two-step **PI + DISPLAY UIT** button. The first press
arms it for eight seconds; the second press requests a clean system power-off.
The system timer `vivent-office-poweroff.timer` provides an independent daily
fallback at 17:00. It deliberately uses `Persistent=false`, so booting the Pi
after 17:00 does not immediately replay a missed shutdown.

## Branding

The dashboard uses the official Vivent Biosignals logo published on the
[Vivent media-assets page](https://vivent-biosignals.com/media-assets/). The
Vivent name and logo remain the property of their respective owner.
