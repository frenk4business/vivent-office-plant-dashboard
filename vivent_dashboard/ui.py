from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
import subprocess
import threading
from typing import Callable

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QPixmap
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


class RefreshSignals(QObject):
    success = Signal(object)
    failure = Signal(str)
    shutdown_failure = Signal(str)


class LogoWidget(QLabel):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(150, 94)
        self.setAlignment(Qt.AlignCenter)
        logo = QPixmap(str(LOGO_PATH))
        if logo.isNull():
            LOG.warning("Could not load Vivent logo from %s", LOGO_PATH)
            self.setText("Vivent Biosignals")
            return

        # The official media asset includes transparent padding around the logo.
        logo = logo.copy(225, 56, 1459, 966)
        self.setPixmap(logo.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))


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
        self.refreshing = False
        self.signals = RefreshSignals()
        self.signals.success.connect(self._refresh_succeeded)
        self.signals.failure.connect(self._refresh_failed)
        self.signals.shutdown_failure.connect(self._shutdown_failed)
        self.shutdown_armed = False
        self.setWindowTitle("Vivent Office Plants – Zeist")
        self.setMinimumSize(1024, 650)
        self.setStyleSheet(self._stylesheet())
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
        root_layout.setContentsMargins(20, 10, 20, 14)
        root_layout.setSpacing(10)

        header = QHBoxLayout()
        header.addWidget(LogoWidget())
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
        water_layout.setContentsMargins(16, 8, 16, 8)
        water_layout.setSpacing(5)
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
        squad_layout = QVBoxLayout(squad_card)
        squad_layout.setContentsMargins(16, 8, 16, 10)
        squad_layout.setSpacing(5)
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
            ["Plant", "Health", "Status", "Main issue", "Water", "Activity", "Nutrients", "Updated"]
        )
        squad_layout.addWidget(self.squad_table)
        root_layout.addWidget(squad_card, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        shutdown_schedule = QLabel("Automatisch uit om 17:00")
        shutdown_schedule.setObjectName("shutdownSchedule")
        footer.addWidget(shutdown_schedule)
        self.shutdown_button = QPushButton("PI + DISPLAY UIT")
        self.shutdown_button.setObjectName("shutdownButton")
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
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
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
        self.water_table.setFixedHeight(32 + row_count * 32)
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
            self.water_table.setRowHeight(row, 31)

    def _render_squad(self, data: DashboardData) -> None:
        self.squad_count.setText(f"{len(data.plants)} monitored plants")
        self.squad_table.setRowCount(len(data.plants))
        for row, plant in enumerate(data.plants):
            self.squad_table.setItem(row, 0, _item(plant.plant_name, bold=True))
            self.squad_table.setCellWidget(row, 1, _health_bar(plant.health_score))
            self.squad_table.setItem(row, 2, _item(plant.status, bold=True, color=_status_color(plant.status)))
            self.squad_table.setItem(row, 3, _item(plant.main_issue, color=_issue_color(plant)))
            self.squad_table.setItem(row, 4, _item(_percent(plant.water_score), color=_score_color(plant.water_score)))
            self.squad_table.setItem(row, 5, _item(_percent(plant.activity_score), color=_score_color(plant.activity_score)))
            self.squad_table.setItem(row, 6, _item(_percent(plant.nutrient_score), color=_score_color(plant.nutrient_score)))
            self.squad_table.setItem(row, 7, _item(_relative(plant.last_seen), color=MUTED))
            self.squad_table.setRowHeight(row, 34)
        header = self.squad_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)

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
        if not self.fullscreen or (event.modifiers() & Qt.ControlModifier and event.modifiers() & Qt.ShiftModifier and event.key() == Qt.Key_Q):
            super().keyPressEvent(event)

    @staticmethod
    def _stylesheet() -> str:
        return f"""
            QMainWindow, QWidget {{ background: {LIGHT_BG}; color: {DARK}; font-family: 'DejaVu Sans'; font-size: 12px; }}
            QFrame#card {{ background: {CARD_BG}; border: 1px solid #dfe9e2; border-radius: 16px; }}
            QFrame#card[waterAlert="true"] {{ background: #fff4f4; border: 4px solid {RED}; }}
            QLabel#pageTitle {{ color: {DARK}; font-size: 24px; font-weight: 700; }}
            QLabel#subtitle {{ color: {MUTED}; font-size: 12px; }}
            QLabel#sectionTitle {{ color: {DARK}; font-size: 18px; font-weight: 700; }}
            QLabel#connection {{ font-size: 11px; font-weight: 600; padding: 6px; }}
            QLabel#waterSummary {{ font-size: 12px; font-weight: 700; }}
            QLabel#waterAlertBanner {{ color: white; background: {RED}; border: 2px solid #a82929; border-radius: 10px; padding: 10px 14px; font-size: 13px; font-weight: 800; }}
            QLabel#warning {{ color: #6e5a26; background: #fff8e6; border-radius: 7px; padding: 5px 9px; font-size: 10px; }}
            QLabel#muted {{ color: {MUTED}; }}
            QLabel#shutdownSchedule {{ color: {MUTED}; font-size: 10px; padding-right: 4px; }}
            QPushButton#shutdownButton {{ color: {RED}; background: white; border: 2px solid {RED}; border-radius: 9px; padding: 7px 14px; font-size: 11px; font-weight: 800; }}
            QPushButton#shutdownButton:hover {{ background: #fff0f0; }}
            QPushButton#shutdownButton[armed="true"] {{ color: white; background: {RED}; border: 2px solid #a82929; }}
            QPushButton#shutdownButton:disabled {{ color: white; background: {MUTED}; border-color: {MUTED}; }}
            QTableWidget {{ background: transparent; alternate-background-color: #f7faf8; border: none; color: {DARK}; }}
            QTableWidget::item {{ padding: 4px 6px; border-bottom: 1px solid #e8efea; }}
            QHeaderView::section {{ background: #edf4ef; color: {MUTED}; border: none; border-bottom: 1px solid #d9e6dd; padding: 6px; font-size: 9px; font-weight: 700; text-transform: uppercase; }}
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
