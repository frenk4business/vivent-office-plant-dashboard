from __future__ import annotations

from datetime import datetime, timedelta
import logging
from pathlib import Path
import subprocess
import threading
from typing import Callable

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedLayout,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .models import DashboardData, PlantStatus


LOG = logging.getLogger(__name__)
GREEN = "#2f855a"
BRIGHT_GREEN = "#48a868"
DARK = "#17352a"
MUTED = "#64736c"
AMBER = "#d89b2b"
RED = "#cf4b4b"
LIGHT_BG = "#f3f7f4"
CARD_BG = "#ffffff"
POWER_OFF_COMMAND = ["/usr/bin/systemctl", "poweroff", "--no-wall", "--no-ask-password"]
LOGO_PATH = Path(__file__).with_name("assets") / "vivent-logo.png"
LOGO_CROP = (225, 56, 1459, 966)


class RefreshSignals(QObject):
    success = Signal(object)
    failure = Signal(str)
    shutdown_failure = Signal(str)


def _official_logo() -> QPixmap:
    logo = QPixmap(str(LOGO_PATH))
    if logo.isNull():
        return logo
    # The official media asset includes transparent padding around the logo.
    return logo.copy(*LOGO_CROP)


class LogoWidget(QLabel):
    def __init__(self, compact: bool = False) -> None:
        super().__init__()
        width, height = (124, 64) if compact else (150, 94)
        self.setFixedSize(width, height)
        self.setAlignment(Qt.AlignCenter)
        logo = _official_logo()
        if logo.isNull():
            LOG.warning("Could not load Vivent logo from %s", LOGO_PATH)
            self.setText("Vivent Biosignals")
            return

        self.setPixmap(logo.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))


class WatermarkTable(QTableWidget):
    def __init__(self, rows: int, columns: int) -> None:
        super().__init__(rows, columns)
        self.watermark = _official_logo()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self.watermark.isNull():
            return

        if self.rowCount():
            last_row = self.rowCount() - 1
            blank_top = self.rowViewportPosition(last_row) + self.rowHeight(last_row) + 12
        else:
            blank_top = 12
        available_height = self.viewport().height() - blank_top - 12
        if available_height < 80:
            return

        maximum_width = min(340, int(self.viewport().width() * 0.32))
        maximum_height = min(230, int(available_height * 0.78))
        logo = self.watermark.scaled(
            maximum_width,
            maximum_height,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        x = (self.viewport().width() - logo.width()) // 2
        y = blank_top + (available_height - logo.height()) // 2
        painter = QPainter(self.viewport())
        painter.setOpacity(0.10)
        painter.drawPixmap(x, y, logo)


class DashboardWindow(QMainWindow):
    def __init__(
        self,
        fetch_data: Callable[[], DashboardData],
        initial_data: DashboardData | None,
        refresh_seconds: int,
        fullscreen: bool = True,
    ) -> None:
        super().__init__()
        self.fetch_data = fetch_data
        self.last_data = initial_data
        self.fullscreen = fullscreen
        self.compact = fullscreen
        self.refreshing = False
        self.signals = RefreshSignals()
        self.signals.success.connect(self._refresh_succeeded)
        self.signals.failure.connect(self._refresh_failed)
        self.signals.shutdown_failure.connect(self._shutdown_failed)
        self.shutdown_armed = False
        self.setWindowTitle("Vivent Office Plants – Zeist")
        self.setMinimumSize(1024, 600 if self.compact else 650)
        self.setStyleSheet(self._stylesheet(self.compact))
        self._build_ui()
        if initial_data:
            self.render(initial_data, offline=True, message="Cached data – connecting…")
        else:
            self.connection_label.setText("Connecting to plant sensors…")
        self.timer = QTimer(self)
        self.timer.setInterval(refresh_seconds * 1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        QTimer.singleShot(200, self.refresh)
        QTimer.singleShot(3000, lambda: QApplication.setOverrideCursor(QCursor(Qt.BlankCursor)))

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(
            20,
            6 if self.compact else 10,
            20,
            8 if self.compact else 14,
        )
        root_layout.setSpacing(6 if self.compact else 10)

        header = QHBoxLayout()
        header.addWidget(LogoWidget(self.compact))
        title_box = QVBoxLayout()
        title = QLabel("Office Plants")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Zeist  •  Live plant health")
        subtitle.setObjectName("subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()
        self.connection_label = QLabel("Starting…")
        self.connection_label.setObjectName("connection")
        self.connection_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header.addWidget(self.connection_label)
        root_layout.addLayout(header)

        self.water_card = self._card()
        self.water_card.setProperty("waterAlert", False)
        water_layout = QVBoxLayout(self.water_card)
        water_layout.setContentsMargins(
            16,
            5 if self.compact else 8,
            16,
            5 if self.compact else 8,
        )
        water_layout.setSpacing(3 if self.compact else 5)
        water_header = QHBoxLayout()
        water_title = QLabel("Plants Need Water")
        water_title.setObjectName("sectionTitle")
        self.water_summary = QLabel()
        self.water_summary.setObjectName("waterSummary")
        self.water_summary.setAlignment(Qt.AlignRight)
        water_header.addWidget(water_title)
        water_header.addStretch()
        water_header.addWidget(self.water_summary)
        water_layout.addLayout(water_header)
        self.water_alert_banner = QLabel()
        self.water_alert_banner.setObjectName("waterAlertBanner")
        self.water_alert_banner.setWordWrap(True)
        self.water_alert_banner.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.water_alert_banner.hide()
        water_layout.addWidget(self.water_alert_banner)
        self.water_table = self._table(["Plant", "Water", "Low status", "Last measurement"])
        self.water_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        water_layout.addWidget(self.water_table)
        warning = QLabel(
            "Controleer eerst of de aarde droog is • Check that the soil is dry first • "
            "Comprueba primero que la tierra esté seca"
        )
        warning.setObjectName("warning")
        warning.setWordWrap(True)
        water_layout.addWidget(warning)
        root_layout.addWidget(self.water_card, 0)

        squad_card = self._card()
        self.squad_stack = QStackedLayout(squad_card)
        self.squad_stack.setContentsMargins(0, 0, 0, 0)

        squad_page = QWidget()
        squad_page.setStyleSheet("background: transparent;")
        squad_layout = QVBoxLayout(squad_page)
        squad_layout.setContentsMargins(
            16,
            5 if self.compact else 8,
            16,
            6 if self.compact else 10,
        )
        squad_layout.setSpacing(3 if self.compact else 5)
        squad_header = QHBoxLayout()
        squad_title = QLabel("Plant Squad")
        squad_title.setObjectName("sectionTitle")
        self.squad_count = QLabel()
        self.squad_count.setObjectName("muted")
        squad_header.addWidget(squad_title)
        squad_header.addStretch()
        squad_header.addWidget(self.squad_count)
        squad_layout.addLayout(squad_header)
        self.squad_table = self._table(
            ["Plant", "Health", "Status", "Main issue", "Water", "Activity", "Nutrients", "Updated"],
            watermark=True,
        )
        squad_layout.addWidget(self.squad_table)
        self.squad_stack.addWidget(squad_page)

        history_page = QWidget()
        history_page.setObjectName("historyPage")
        history_layout = QVBoxLayout(history_page)
        history_layout.setContentsMargins(
            16,
            5 if self.compact else 8,
            16,
            6 if self.compact else 10,
        )
        history_layout.setSpacing(3 if self.compact else 5)
        history_header = QHBoxLayout()
        history_title = QLabel("★  Plant van de Week — Historie")
        history_title.setObjectName("sectionTitle")
        self.history_summary = QLabel()
        self.history_summary.setObjectName("historySummary")
        self.history_close = QPushButton("SLUITEN  ×")
        self.history_close.setObjectName("historyClose")
        self.history_close.setMinimumSize(105, 32)
        self.history_close.setCursor(Qt.PointingHandCursor)
        self.history_close.clicked.connect(self._hide_history)
        history_header.addWidget(history_title)
        history_header.addStretch()
        history_header.addWidget(self.history_summary)
        history_header.addWidget(self.history_close)
        history_layout.addLayout(history_header)
        self.history_table = self._table(
            ["#", "Plant", "Gewonnen", "Laatste winst", "Gem. winscore"]
        )
        history_layout.addWidget(self.history_table)
        self.history_recent = QLabel()
        self.history_recent.setObjectName("historyRecent")
        self.history_recent.setWordWrap(True)
        history_layout.addWidget(self.history_recent)
        self.squad_stack.addWidget(history_page)
        self.history_timer = QTimer(self)
        self.history_timer.setSingleShot(True)
        self.history_timer.setInterval(20_000)
        self.history_timer.timeout.connect(self._hide_history)
        root_layout.addWidget(squad_card, 1)

        self.potw_card = self._card()
        self.potw_card.setObjectName("plantOfWeek")
        potw_layout = QHBoxLayout(self.potw_card)
        potw_layout.setContentsMargins(18, 8, 18, 8)
        potw_layout.setSpacing(12)

        potw_heading = QVBoxLayout()
        potw_heading.setSpacing(1)
        potw_title_row = QHBoxLayout()
        potw_title_row.setSpacing(6)
        potw_title = QLabel("★  PLANT VAN DE WEEK")
        potw_title.setObjectName("potwTitle")
        self.history_button = QPushButton("HISTORIE")
        self.history_button.setObjectName("historyButton")
        self.history_button.setMinimumSize(85, 32)
        self.history_button.setCursor(Qt.PointingHandCursor)
        self.history_button.clicked.connect(self._show_history)
        self.potw_period = QLabel()
        self.potw_period.setObjectName("potwPeriod")
        potw_title_row.addWidget(potw_title)
        potw_title_row.addWidget(self.history_button)
        potw_title_row.addStretch()
        potw_heading.addLayout(potw_title_row)
        potw_heading.addWidget(self.potw_period)
        potw_layout.addLayout(potw_heading)

        self.potw_name = QLabel()
        self.potw_name.setObjectName("potwName")
        self.potw_name.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.potw_name.setWordWrap(True)
        potw_layout.addWidget(self.potw_name, 1)

        self.potw_badge = QLabel()
        self.potw_badge.setObjectName("potwBadge")
        self.potw_badge.setAlignment(Qt.AlignCenter)
        potw_layout.addWidget(self.potw_badge)

        self.potw_score = QLabel()
        self.potw_score.setObjectName("potwScore")
        self.potw_score.setAlignment(Qt.AlignCenter)
        potw_layout.addWidget(self.potw_score)

        self.potw_meta = QLabel()
        self.potw_meta.setObjectName("potwMeta")
        self.potw_meta.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.potw_meta.setWordWrap(True)
        self.potw_meta.setMinimumWidth(195)
        self.potw_meta.setMaximumWidth(215)
        potw_layout.addWidget(self.potw_meta)
        self.potw_card.setFixedHeight(62 if self.compact else 72)
        root_layout.addWidget(self.potw_card, 0)

        footer = QHBoxLayout()
        footer.addStretch()
        shutdown_schedule = QLabel("Automatisch uit om 17:00")
        shutdown_schedule.setObjectName("shutdownSchedule")
        footer.addWidget(shutdown_schedule)
        self.shutdown_button = QPushButton("PI + DISPLAY UIT")
        self.shutdown_button.setObjectName("shutdownButton")
        self.shutdown_button.setMinimumSize(175, 36)
        self.shutdown_button.setCursor(Qt.PointingHandCursor)
        self.shutdown_button.clicked.connect(self._request_shutdown)
        footer.addWidget(self.shutdown_button)
        root_layout.addLayout(footer)

        self.setCentralWidget(root)

    @staticmethod
    def _card() -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 7)
        shadow.setColor(QColor(20, 70, 45, 28))
        card.setGraphicsEffect(shadow)
        return card

    @staticmethod
    def _table(headers: list[str], watermark: bool = False) -> QTableWidget:
        table = WatermarkTable(0, len(headers)) if watermark else QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.setFocusPolicy(Qt.NoFocus)
        table.setSelectionMode(QAbstractItemView.NoSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        return table

    def refresh(self) -> None:
        if self.refreshing:
            return
        self.refreshing = True
        self.connection_label.setText("Refreshing plant data…")

        def work() -> None:
            try:
                self.signals.success.emit(self.fetch_data())
            except Exception as exc:
                LOG.exception("Dashboard refresh failed")
                self.signals.failure.emit(str(exc))

        threading.Thread(target=work, name="dashboard-refresh", daemon=True).start()

    def _refresh_succeeded(self, data: DashboardData) -> None:
        self.refreshing = False
        self.last_data = data
        self.render(data, offline=False)

    def _refresh_failed(self, message: str) -> None:
        self.refreshing = False
        LOG.warning("Keeping last successful data visible: %s", message)
        if self.last_data:
            self.render(self.last_data, offline=True, message="Connection temporarily unavailable")
        else:
            self.connection_label.setText("No connection – waiting to retry")
            self.connection_label.setStyleSheet(f"color: {AMBER};")
            self.water_summary.setText("No cached data available")

    def render(self, data: DashboardData, offline: bool, message: str = "") -> None:
        if offline:
            self.connection_label.setText(f"●  {message}  •  {_relative(data.fetched_at)}")
            self.connection_label.setStyleSheet(f"color: {AMBER};")
        else:
            self.connection_label.setText(f"●  Live  •  updated {data.fetched_at:%H:%M}")
            self.connection_label.setStyleSheet(f"color: {GREEN};")
        self._render_water(data)
        self._render_squad(data)
        self._render_plant_of_week(data)
        self._render_history(data)

    def _render_water(self, data: DashboardData) -> None:
        alerts = data.water_alerts
        has_alert = bool(alerts)
        self.water_card.setProperty("waterAlert", has_alert)
        self.water_card.style().unpolish(self.water_card)
        self.water_card.style().polish(self.water_card)
        self.water_card.update()
        self.water_alert_banner.setVisible(has_alert)
        if has_alert:
            self.water_summary.setText(f"⚠  {len(alerts)} WATERALARM{'EN' if len(alerts) != 1 else ''}")
            self.water_summary.setStyleSheet(f"color: {RED}; font-size: 15px; font-weight: 900;")
            self.water_alert_banner.setText(_water_alert_message(alerts))
        else:
            self.water_summary.setText("Geen wateralarm • No water alert • Sin alerta de riego")
            self.water_summary.setStyleSheet(f"color: {GREEN};")
        row_count = max(1, len(alerts))
        self.water_table.setRowCount(row_count)
        table_header_height = 28 if self.compact else 32
        table_row_height = 27 if self.compact else 31
        self.water_table.setFixedHeight(
            table_header_height + row_count * (table_row_height + 1)
        )
        if not alerts:
            self.water_table.setItem(0, 0, _item("No plants need water", bold=True, color=GREEN))
            for column in range(1, 4):
                self.water_table.setItem(0, column, _item("—", color=MUTED))
        else:
            for row, alert in enumerate(alerts):
                self.water_table.setItem(row, 0, _item(alert.plant_name, bold=True))
                self.water_table.setItem(row, 1, _item(f"{alert.water_score:.0f}%", color=RED if alert.water_score < 20 else AMBER))
                self.water_table.setItem(row, 2, _item(f"≥ {alert.low_hours:g} h", bold=True, color=RED))
                self.water_table.setItem(row, 3, _item(_relative(alert.last_seen), color=MUTED))
        for row in range(row_count):
            self.water_table.setRowHeight(row, table_row_height)

    def _render_squad(self, data: DashboardData) -> None:
        self.squad_count.setText(f"{len(data.plants)} monitored plants")
        self.squad_table.setRowCount(len(data.plants))
        for row, plant in enumerate(data.plants):
            self.squad_table.setItem(row, 0, _item(plant.plant_name, bold=True))
            self.squad_table.setCellWidget(row, 1, _health_bar(plant.health_score))
            self.squad_table.setItem(row, 2, _item(plant.status, bold=True, color=_status_color(plant.status)))
            self.squad_table.setItem(row, 3, _item(plant.main_issue, color=_issue_color(plant)))
            self.squad_table.setItem(row, 4, _item(_percent(plant.water_score), color=_score_color(plant.water_score)))
            activity = "Calibrating" if plant.activity_calibrating else _percent(plant.activity_score)
            activity_color = AMBER if plant.activity_calibrating else _score_color(plant.activity_score)
            self.squad_table.setItem(row, 5, _item(activity, color=activity_color))
            self.squad_table.setItem(row, 6, _item(_percent(plant.nutrient_score), color=_score_color(plant.nutrient_score)))
            self.squad_table.setItem(row, 7, _item(_relative(plant.last_seen), color=MUTED))
            self.squad_table.setRowHeight(row, 30 if self.compact else 34)
        header = self.squad_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)

    def _render_plant_of_week(self, data: DashboardData) -> None:
        winner = data.plant_of_week
        if winner is None:
            current = datetime.now().astimezone()
            start = (current - timedelta(days=current.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            end = start + timedelta(days=7) - timedelta(seconds=1)
            self.potw_period.setText(f"{_week_label(start, end)}  •  TUSSENSTAND")
            self.potw_name.setText("Nog niet genoeg data")
            self.potw_badge.setText("MIN. DATA NODIG")
            self.potw_score.setText("—")
            self.potw_meta.setText("Wacht op voldoende geldige weekdata")
            return

        state = "EINDSTAND" if winner.is_final else "TUSSENSTAND"
        self.potw_period.setText(f"{_week_label(winner.week_start, winner.week_end)}  •  {state}")
        self.potw_name.setText(winner.plant_name)
        self.potw_badge.setText(winner.badge.upper())
        self.potw_score.setText(f"{winner.league_score:.0f}%")
        if winner.score_change is None:
            change = "geen vorige week"
        elif winner.score_change > 0:
            points = abs(round(winner.score_change))
            change = f"↑ {points} {'punt' if points == 1 else 'punten'} vs. vorige week"
        elif winner.score_change < 0:
            points = abs(round(winner.score_change))
            change = f"↓ {points} {'punt' if points == 1 else 'punten'} vs. vorige week"
        else:
            change = "– gelijk aan vorige week"
        coverage = _percent(winner.online_coverage)
        self.potw_meta.setText(
            f"{change}\nData {winner.data_completeness:.0f}%  •  online {coverage}"
        )

    def _render_history(self, data: DashboardData) -> None:
        entries = data.hall_of_fame
        completed = sum(entry.wins for entry in entries)
        self.history_summary.setText(
            f"{completed} {'weekwinnaar' if completed == 1 else 'weekwinnaars'}"
        )
        self.history_table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            self.history_table.setItem(row, 0, _item(str(row + 1), bold=True, color=AMBER))
            self.history_table.setItem(row, 1, _item(entry.plant_name, bold=True))
            self.history_table.setItem(
                row, 2, _item(f"{entry.wins}×", bold=True, color=GREEN)
            )
            self.history_table.setItem(
                row, 3, _item(_short_date(entry.last_win), color=MUTED)
            )
            self.history_table.setItem(
                row, 4, _item(f"{entry.average_winning_score:.0f}%", color=AMBER)
            )
            self.history_table.setRowHeight(row, 31 if self.compact else 36)
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        if data.recent_winners:
            recent = "   •   ".join(
                f"W{winner.week_start.isocalendar().week}: {winner.plant_name} ({winner.league_score:.0f}%)"
                for winner in data.recent_winners[:4]
            )
            self.history_recent.setText(f"LAATSTE WINNAARS   {recent}")
        else:
            self.history_recent.setText(
                "Nog geen afgesloten week vastgelegd — de actuele week blijft een tussenstand."
            )

    def _show_history(self) -> None:
        self.squad_stack.setCurrentIndex(1)
        self.history_timer.start()

    def _hide_history(self) -> None:
        self.history_timer.stop()
        self.squad_stack.setCurrentIndex(0)

    def _request_shutdown(self) -> None:
        if not self.shutdown_armed:
            self.shutdown_armed = True
            self.shutdown_button.setText("BEVESTIG: ALLES UIT")
            self.shutdown_button.setProperty("armed", True)
            self.shutdown_button.style().unpolish(self.shutdown_button)
            self.shutdown_button.style().polish(self.shutdown_button)
            QTimer.singleShot(8000, self._disarm_shutdown)
            return

        self.shutdown_armed = False
        self.shutdown_button.setEnabled(False)
        self.shutdown_button.setText("VEILIG UITSCHAKELEN…")
        self.connection_label.setText("Pi en display worden uitgeschakeld…")
        self.connection_label.setStyleSheet(f"color: {RED}; font-weight: 800;")

        def power_off() -> None:
            try:
                subprocess.run(
                    POWER_OFF_COMMAND,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
            except Exception as exc:
                self.signals.shutdown_failure.emit(str(exc))

        threading.Thread(target=power_off, name="dashboard-poweroff", daemon=True).start()

    def _disarm_shutdown(self) -> None:
        if not self.shutdown_armed:
            return
        self.shutdown_armed = False
        self.shutdown_button.setText("PI + DISPLAY UIT")
        self.shutdown_button.setProperty("armed", False)
        self.shutdown_button.style().unpolish(self.shutdown_button)
        self.shutdown_button.style().polish(self.shutdown_button)

    def _shutdown_failed(self, message: str) -> None:
        LOG.error("Power-off request failed: %s", message)
        self.shutdown_button.setEnabled(True)
        self.shutdown_button.setText("UITZETTEN MISLUKT — OPNIEUW")
        self.shutdown_button.setProperty("armed", False)
        self.shutdown_button.style().unpolish(self.shutdown_button)
        self.shutdown_button.style().polish(self.shutdown_button)
        self.connection_label.setText("Uitschakelen mislukt")
        self.connection_label.setStyleSheet(f"color: {RED}; font-weight: 800;")

    def show_dashboard(self) -> None:
        if self.fullscreen:
            self.showFullScreen()
        else:
            self.resize(1440, 900)
            self.show()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape and self.squad_stack.currentIndex() == 1:
            self._hide_history()
            return
        if not self.fullscreen or (event.modifiers() & Qt.ControlModifier and event.modifiers() & Qt.ShiftModifier and event.key() == Qt.Key_Q):
            super().keyPressEvent(event)

    @staticmethod
    def _stylesheet(compact: bool = False) -> str:
        base_font = 11 if compact else 12
        section_font = 16 if compact else 18
        table_padding = "3px 5px" if compact else "4px 6px"
        header_padding = "4px" if compact else "6px"
        warning_padding = "3px 7px" if compact else "5px 9px"
        shutdown_padding = "6px 16px" if compact else "7px 16px"
        return f"""
            QMainWindow, QWidget {{ background: {LIGHT_BG}; color: {DARK}; font-family: 'DejaVu Sans'; font-size: {base_font}px; }}
            QFrame#card {{ background: {CARD_BG}; border: 1px solid #dfe9e2; border-radius: 16px; }}
            QFrame#card[waterAlert="true"] {{ background: #fff4f4; border: 4px solid {RED}; }}
            QFrame#plantOfWeek {{ background: #fff9e7; border: 2px solid #e6c25c; border-radius: 14px; }}
            QLabel#pageTitle {{ color: {DARK}; font-size: 24px; font-weight: 700; }}
            QLabel#subtitle {{ color: {MUTED}; font-size: 12px; }}
            QLabel#sectionTitle {{ color: {DARK}; font-size: {section_font}px; font-weight: 700; }}
            QLabel#connection {{ font-size: 11px; font-weight: 600; padding: 6px; }}
            QLabel#waterSummary {{ font-size: 12px; font-weight: 700; }}
            QLabel#waterAlertBanner {{ color: white; background: {RED}; border: 2px solid #a82929; border-radius: 10px; padding: 10px 14px; font-size: 13px; font-weight: 800; }}
            QLabel#warning {{ color: #6e5a26; background: #fff8e6; border-radius: 7px; padding: {warning_padding}; font-size: 10px; }}
            QLabel#muted {{ color: {MUTED}; }}
            QLabel#potwTitle {{ color: #9b6b00; font-size: 12px; font-weight: 900; }}
            QLabel#potwPeriod {{ color: {MUTED}; font-size: 9px; font-weight: 700; }}
            QLabel#potwName {{ color: {DARK}; font-size: 16px; font-weight: 800; }}
            QLabel#potwBadge {{ color: #8a5b00; background: #ffedaf; border: 1px solid #e4bf50; border-radius: 8px; padding: 5px 9px; font-size: 10px; font-weight: 900; }}
            QLabel#potwScore {{ color: #9b6b00; background: white; border: 2px solid #e6c25c; border-radius: 9px; padding: 5px 10px; font-size: 20px; font-weight: 900; }}
            QLabel#potwMeta {{ color: {MUTED}; font-size: 9px; font-weight: 600; }}
            QLabel#historySummary {{ color: {MUTED}; font-size: 10px; font-weight: 700; }}
            QLabel#historyRecent {{ color: {MUTED}; background: #fff9e7; border: 1px solid #ead68f; border-radius: 7px; padding: 6px 9px; font-size: 9px; font-weight: 700; }}
            QPushButton#historyButton {{ color: #8a5b00; background: white; border: 1px solid #e4bf50; border-radius: 7px; padding: 5px 10px; font-size: 10px; font-weight: 900; }}
            QPushButton#historyButton:hover {{ background: #ffedaf; }}
            QPushButton#historyClose {{ color: #8a5b00; background: #fff9e7; border: 1px solid #e4bf50; border-radius: 7px; padding: 5px 10px; font-size: 10px; font-weight: 900; }}
            QLabel#shutdownSchedule {{ color: {MUTED}; font-size: 10px; padding-right: 4px; }}
            QPushButton#shutdownButton {{ color: {RED}; background: white; border: 2px solid {RED}; border-radius: 9px; padding: {shutdown_padding}; font-size: 12px; font-weight: 800; }}
            QPushButton#shutdownButton:hover {{ background: #fff0f0; }}
            QPushButton#shutdownButton[armed="true"] {{ color: white; background: {RED}; border: 2px solid #a82929; }}
            QPushButton#shutdownButton:disabled {{ color: white; background: {MUTED}; border-color: {MUTED}; }}
            QTableWidget {{ background: transparent; alternate-background-color: #f7faf8; border: none; color: {DARK}; }}
            QTableWidget::item {{ padding: {table_padding}; border-bottom: 1px solid #e8efea; }}
            QHeaderView::section {{ background: #edf4ef; color: {MUTED}; border: none; border-bottom: 1px solid #d9e6dd; padding: {header_padding}; font-size: 9px; font-weight: 700; text-transform: uppercase; }}
            QScrollBar:vertical {{ background: transparent; width: 8px; }}
            QScrollBar::handle:vertical {{ background: #b7cabd; border-radius: 4px; min-height: 25px; }}
            QProgressBar {{ border: none; background: #e7eee9; border-radius: 6px; min-width: 78px; min-height: 18px; }}
            QProgressBar::chunk {{ border-radius: 6px; background: {BRIGHT_GREEN}; }}
        """


def _item(text: str, bold: bool = False, color: str | None = None) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    if bold:
        font = item.font()
        font.setBold(True)
        item.setFont(font)
    if color:
        item.setForeground(QColor(color))
    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    return item


def _water_alert_message(alerts) -> str:
    test_prefix = ""
    if any(alert.plant_name.startswith("TEST —") for alert in alerts):
        test_prefix = (
            "=== TEST • NIET WATER GEVEN • DO NOT WATER • NO REGAR ===\n"
        )
    plants = "  •  ".join(
        f"{alert.plant_name}: {alert.water_score:.0f}%"
        for alert in alerts
    )
    return (
        test_prefix +
        "⚠  WATER NODIG / NEEDS WATER / NECESITA AGUA  ⚠\n"
        f"▼  AANHOUDEND LAAG / SUSTAINED LOW / BAJO PROLONGADO   •   {plants}\n"
        "NL aarde → water indien droog   |   EN soil → water if dry   |   ES tierra → regar si seca"
    )


def _health_bar(value: float | None) -> QWidget:
    container = QWidget()
    container.setStyleSheet("background: transparent;")
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(7)

    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setTextVisible(False)
    bar.setFixedSize(78, 20)

    percentage = QLabel()
    percentage.setFixedSize(54, 24)
    percentage.setAlignment(Qt.AlignCenter)
    if value is None:
        bar.setValue(0)
        percentage.setText("No data")
        color = "#a5aaa7"
    else:
        bar.setValue(round(value))
        percentage.setText(f"{value:.0f}%")
        color = _score_color(value)

    bar.setStyleSheet(f"QProgressBar::chunk {{ background: {color}; }}")
    percentage.setStyleSheet(
        f"color: {DARK}; background: white; border: 2px solid {color}; "
        "border-radius: 6px; font-weight: 900; font-size: 12px;"
    )
    layout.addWidget(bar)
    layout.addWidget(percentage)
    return container


def _status_color(status: str) -> str:
    return {
        "Critical": RED,
        "Needs attention": AMBER,
        "Healthy": GREEN,
        "Thriving": "#16834f",
        "Offline": "#8b938f",
        "Insufficient data": "#8b938f",
    }.get(status, MUTED)


def _issue_color(plant: PlantStatus) -> str:
    return GREEN if plant.main_issue == "Within target" else _status_color(plant.status)


def _score_color(value: float | None) -> str:
    if value is None:
        return "#8b938f"
    if value < 30:
        return RED
    if value < 50:
        return AMBER
    return GREEN


def _percent(value: float | None) -> str:
    return "No recent data" if value is None else f"{value:.0f}%"


def _week_label(start: datetime, end: datetime) -> str:
    months = (
        "jan", "feb", "mrt", "apr", "mei", "jun",
        "jul", "aug", "sep", "okt", "nov", "dec",
    )
    week = start.isocalendar().week
    if start.year == end.year and start.month == end.month:
        period = f"{start.day}–{end.day} {months[start.month - 1]} {start.year}"
    elif start.year == end.year:
        period = (
            f"{start.day} {months[start.month - 1]}–"
            f"{end.day} {months[end.month - 1]} {start.year}"
        )
    else:
        period = (
            f"{start.day} {months[start.month - 1]} {start.year}–"
            f"{end.day} {months[end.month - 1]} {end.year}"
        )
    return f"Week {week}  •  {period}"


def _short_date(value: datetime) -> str:
    months = (
        "jan", "feb", "mrt", "apr", "mei", "jun",
        "jul", "aug", "sep", "okt", "nov", "dec",
    )
    return f"W{value.isocalendar().week} • {value.day} {months[value.month - 1]}"


def _relative(value: datetime | None) -> str:
    if value is None:
        return "No data"
    current = datetime.now(value.tzinfo) if value.tzinfo else datetime.now()
    seconds = max(0, int((current - value).total_seconds()))
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"
