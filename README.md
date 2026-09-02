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
- a local Hall of Fame with immutable completed-week winners and a scoreboard;
- read-only data access, local caching and a clear offline state;
- mock data and automated tests for development without production access;
- an official Vivent Biosignals branded header;
- a two-step safe shutdown button for the Pi and display;
- a system timer that safely shuts down the installation every day at 17:00;
- a daily trial synchronization that discovers newly added active sensors;
- a layout optimized for the wall display's 1024 × 600 resolution;
- high-contrast health percentages for readability at a distance.

## Dashboard sections

### Plants Need Water

Shows only water scores below 30% that remain continuously low for more than
four hours. A gap between measurements of more than 30 minutes restarts that
period. Scores from 30% through 39% remain visible as an early `Low Water
Status` warning in Plant Squad, but do not trigger the prominent alert. The
alert and safety instruction are presented in Dutch, English and Spanish so
colleagues can first check whether the soil is actually dry.

### Plant Squad

Shows the latest health status, main issue, water, plant activity and nutrient
score for every monitored plant. Missing or stale measurements are clearly
marked instead of being treated as healthy data.

### Plant van de Week

Highlights the strongest eligible plant for the current Monday-to-Sunday
period. The card displays the current score, change compared with the previous
week, data completeness and online coverage. Production scoring rules remain in
the private connector and are not published in this repository. The current
week is explicitly shown as a provisional standing.

The compact **HISTORIE** button temporarily replaces the Plant Squad table with
the Hall of Fame. It shows wins, the latest win and average winning score per
plant, plus recent weekly winners. It closes automatically after twenty
seconds, with the close button, or with Escape.

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

The `vivent-channel-sync.timer` checks the configured trial once per day at
approximately 08:05. New active sensors are appended to the local channel list
and appear at the next five-minute dashboard refresh. Existing entries are not
removed and manually assigned names are preserved. When metadata names are
unavailable, a new sensor receives a temporary generated name until metadata
becomes reachable.

On the first successful data refresh after 08:05 on Monday, the previous
Monday-to-Sunday winner is finalized exactly once. This short delay gives the
metrics pipeline time to settle. Completed results are stored outside the repository in
`~/.local/state/vivent-dashboard/plant-of-week-history.sqlite3` with mode 600.
The stable Plant ID is used when available, with the sensor ID as fallback. An
initial production installation can fill all available completed weeks with:

```bash
python3 -m vivent_dashboard --backfill-history
```

To recalculate every completed competition week after a scoring or trial-scope
correction, use the atomic rebuild command. It creates a mode-600 SQLite backup
next to the live ledger before replacing any results:

```bash
python3 -m vivent_dashboard --rebuild-history
```

The office competition starts with the week of 20 July 2026. Earlier trial
weeks are deliberately excluded from both the Hall of Fame and backfills.

After an electrode has been reinserted, its old flat signal must not be used as
an Activity reference. Register the maintenance timestamp locally with:

```bash
python3 -m vivent_dashboard --record-activity-reset CHANNEL_ID \
  --reset-at 2026-08-26T10:15:00+02:00
```

For seven days the dashboard shows Activity as calibrating, calculates Health
from Water and Nutrients only, and excludes the plant from Plant of the Week.
Afterwards, Activity uses only measurements recorded after the reset.

If the signal has stabilized earlier and the plant should rejoin immediately,
end only the calibration period while preserving the original baseline start:

```bash
python3 -m vivent_dashboard --end-activity-calibration CHANNEL_ID
```

All Water, Activity, Nutrient, Health and Plant-of-the-Week measurements are
clamped to each sensor's start and optional stop time in the configured trial.
If a physical sensor ID was used in another trial, those measurements cannot
enter the current trial's scores or historical backfills.

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
