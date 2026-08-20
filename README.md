# Vivent Office Plants Dashboard

Native fullscreen Raspberry Pi dashboard built with Python 3 and PySide6/Qt 6.
It shows **Plants Need Water**, **Plant Squad** and a weekly plant champion, and
refreshes automatically every five minutes.

The application is designed as a kiosk dashboard for the Vivent Biosignals
office in Zeist.

## Project goal

The goal of this project is to turn plant biosignal data into a clear,
always-visible office overview. Colleagues can immediately see which plants may
need attention, while the dashboard remains simple enough to run unattended on
a wall-mounted Raspberry Pi display.

The screen combines a prominent multilingual water alert, a compact health
overview for all monitored office plants and a **Plant van de Week** card. It is
intentionally independent of a browser-based dashboard so the installation can
start automatically and keep working as a dedicated kiosk.

## What I built

I created and configured the complete office dashboard installation:

- a native fullscreen PySide6 interface for Raspberry Pi;
- a live plant-health and water-alert overview;
- a weekly plant champion with score, trend, data completeness and online
  coverage;
- read-only data access, local caching and a clear offline state;
- mock data and automated tests for development without production access;
- an official Vivent Biosignals branded header;
- a two-step safe shutdown button for the Pi and display;
- a system timer that safely shuts down the installation every day at 17:00;
- a layout optimized for the wall display's 1024 × 600 resolution;
- high-contrast health percentages for readability at a distance.

## Dashboard sections

### Plants Need Water

Shows only sustained low-water conditions. The alert and safety instruction are
presented in Dutch, English and Spanish so colleagues can first check whether
the soil is actually dry.

### Plant Squad

Shows the latest health status, main issue, water, plant activity and nutrient
score for every monitored plant. Missing or stale measurements are clearly
marked instead of being treated as healthy data.

### Plant van de Week

Highlights the strongest eligible plant for the current Monday-to-Sunday
period. The card displays the current score, change compared with the previous
week, data completeness and online coverage. Production scoring rules remain in
the private connector and are not published in this repository.

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

## Run the public demo

From the repository root:

```bash
python3 -m vivent_dashboard --mock
```

Useful development modes:

```bash
# Open in a normal desktop window
python3 -m vivent_dashboard --mock --windowed

# Render a deterministic screenshot without opening a window
QT_QPA_PLATFORM=offscreen python3 -m vivent_dashboard \
  --mock --screenshot /tmp/vivent-dashboard.png

# Display a clearly marked synthetic water alarm
python3 -m vivent_dashboard --mock --test-water-alert
```

## Local checks

```bash
python3 -m unittest discover -s tests -v
QT_QPA_PLATFORM=offscreen python3 -m vivent_dashboard --mock --screenshot /tmp/vivent-dashboard.png
```

No `.env`, production connector, channel mapping or production dataset is
included in the public source tree.

## Raspberry Pi kiosk operation

The included user service waits for the Wayland session, starts the dashboard
fullscreen and restarts it after a crash. The launcher uses the production
connector when it is installed locally and otherwise falls back to the safe
mock dashboard.

Application logs are available with:

```bash
journalctl --user -u vivent-dashboard.service
```

The fullscreen UI has a two-step **PI + DISPLAY UIT** button. The first press
arms it for eight seconds; the second press requests a clean system power-off.
The system timer `vivent-office-poweroff.timer` provides an independent daily
fallback at 17:00. It deliberately uses `Persistent=false`, so booting the Pi
after 17:00 does not immediately replay a missed shutdown.

## Privacy and repository contents

The following deployment-specific files are intentionally ignored by Git:

- `.env` credentials;
- `channels.json` production channel mappings;
- `vivent_dashboard_private/` database integration and scoring rules;
- `last-success.json` cached production measurements.

Never commit these files or production screenshots containing plant or employee
names.

## Branding

The dashboard uses the official Vivent Biosignals logo published on the
[Vivent media-assets page](https://vivent-biosignals.com/media-assets/). The
Vivent name and logo remain the property of their respective owner.
