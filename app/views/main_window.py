from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent, QResizeEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.views.dashboard_view import DashboardView
from app.views.tiktok_view import TikTokView
from app.views.gifts_view import GiftsView
from app.views.settings_view import SettingsView
from app.widgets.footer import Footer
from app.widgets.header import Header
from app.widgets.sidebar import Sidebar
from core.app_controller import AppController


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("PandaIA BOT")
        self.setMinimumSize(900, 650)
        self.resize(1600, 900)

        self.pages = QStackedWidget()
        self.sidebar = Sidebar()
        self.controller = AppController(self)
        self.resize_timer = QTimer(self); self.resize_timer.setSingleShot(True); self.resize_timer.setInterval(60)
        self.resize_timer.timeout.connect(self.apply_responsive_layout)

        self.build_interface()
        self.connect_signals()
        self.controller.publish_initial_state()

    def build_interface(self) -> None:
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.header = Header(self)
        root_layout.addWidget(self.header)

        body = QWidget()
        body.setObjectName("mainBody")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(16, 12, 16, 12)
        body_layout.setSpacing(16)

        self.dashboard_view = DashboardView()
        self.tiktok_view = TikTokView()
        self.gifts_view = GiftsView(self.controller.spotify_runtime, self.controller.cloudflare_tunnel)
        self.settings_view = SettingsView(self.controller.watchdog_settings)

        self.pages.setObjectName("contentStack")
        self.page_by_sidebar = [
            self.dashboard_view, self.tiktok_view,
            self.placeholder("IA & Personalidad", "Configura la IA desde el Panel Principal."),
            self.placeholder("Voces (TTS)", "Administra la voz desde el Panel Principal."),
            self.placeholder("Memoria", "El monitor de memoria está disponible en el Panel Principal."),
            self.placeholder("Comandos", "/mensaje → conversar con PandaIA.\na/artista canción → solicitar música."),
            self.gifts_view,
            self.settings_view,
            self.placeholder("Registros (Logs)", "Los registros de la sesión aparecerán aquí."),
        ]
        for page in self.page_by_sidebar: self.pages.addWidget(page)

        body_layout.addWidget(self.sidebar)
        body_layout.addWidget(self.pages, 1)

        root_layout.addWidget(body, 1)

        self.footer = Footer()
        root_layout.addWidget(self.footer)

    def connect_signals(self) -> None:
        self.sidebar.page_selected.connect(self.change_page)
        self.tiktok_view.connect_requested.connect(
            self.controller.connect_all
        )
        self.tiktok_view.disconnect_requested.connect(
            self.controller.disconnect_all
        )

        self.dashboard_view.stop_bot_requested.connect(
            self.controller.disconnect_all
        )
        self.dashboard_view.setting_changed.connect(
            self.controller.update_dashboard_setting
        )
        self.dashboard_view.edit_personality_requested.connect(
            self.controller.edit_personality
        )
        self.dashboard_view.change_voice_requested.connect(
            self.controller.change_voice
        )

        self.controller.bot_status_changed.connect(
            self.header.set_bot_status
        )
        self.controller.tiktok_status_changed.connect(
            self.header.set_tiktok_status
        )
        self.controller.ollama_status_changed.connect(
            self.header.set_ollama_status
        )
        self.controller.tts_status_changed.connect(
            self.header.set_tts_status
        )
        self.controller.connection_state_changed.connect(
            self.tiktok_view.apply_connection_state
        )
        self.controller.connection_state_changed.connect(
            self.dashboard_view.apply_connection_state
        )
        self.controller.activity_received.connect(
            self.dashboard_view.add_activity
        )
        self.controller.live_stats_changed.connect(
            self.dashboard_view.set_live_stats
        )
        self.controller.live_session_reset.connect(
            self.dashboard_view.reset_live_session
        )
        self.controller.memory_changed.connect(
            self.dashboard_view.set_memory_snapshot
        )
        self.controller.voice_settings_changed.connect(
            self.dashboard_view.set_voice_info
        )
        self.controller.dashboard_settings_changed.connect(
            self.dashboard_view.apply_dashboard_settings
        )
        self.gifts_view.settings_changed.connect(self.controller.update_gifts_settings)
        watchdog = self.controller.live_watchdog
        self.settings_view.settings_changed.connect(self.controller.update_watchdog_settings)
        self.settings_view.save_token_requested.connect(watchdog.save_token)
        self.settings_view.detect_chat_requested.connect(watchdog.detect_chat)
        self.settings_view.test_telegram_requested.connect(watchdog.test_telegram)
        self.settings_view.disconnect_telegram_requested.connect(watchdog.disconnect_telegram)
        self.settings_view.test_alarm_requested.connect(watchdog.test_alarm)
        self.settings_view.simulate_warning_requested.connect(watchdog.simulate_warning)
        self.settings_view.stop_alarm_requested.connect(watchdog.stop_alarm)
        self.settings_view.open_studio_requested.connect(self.controller.open_live_studio)
        watchdog.status_changed.connect(self.settings_view.apply_status)
        watchdog.alert_logged.connect(self.settings_view.add_alert)
        watchdog.banner_changed.connect(self.settings_view.set_banner)
        watchdog.banner_changed.connect(self.show_watchdog_attention)
        watchdog.telegram_changed.connect(self.settings_view.set_telegram)

    @staticmethod
    def placeholder(title: str, message: str) -> QScrollArea:
        scroll = QScrollArea(); scroll.setObjectName("contentScroll"); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget(); content.setObjectName("mainContent"); layout = QVBoxLayout(content); layout.setContentsMargins(8, 8, 8, 8)
        heading = QLabel(title); heading.setObjectName("pageTitle"); text = QLabel(message); text.setObjectName("pageSubtitle"); text.setWordWrap(True)
        layout.addWidget(heading); layout.addWidget(text); layout.addStretch(); scroll.setWidget(content); return scroll

    def change_page(self, page_index: int) -> None:
        if 0 <= page_index < self.pages.count(): self.pages.setCurrentIndex(page_index)

    def show_watchdog_attention(self, visible: bool, _text: str) -> None:
        self.setWindowTitle("⚠ TikTok requiere atención — PandaIA BOT" if visible else "PandaIA BOT")
        if visible: QApplication.alert(self, 0)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event); self.resize_timer.start()

    def apply_responsive_layout(self) -> None:
        content_width = self.pages.width()
        compact_sidebar = self.width() < 1180
        self.sidebar.set_compact(compact_sidebar)
        QTimer.singleShot(0, lambda: self._apply_content_width(self.pages.width()))

    def _apply_content_width(self, width: int) -> None:
        self.header.set_available_width(width)
        self.footer.set_available_width(width)
        for view in (self.dashboard_view, self.tiktok_view, self.gifts_view, self.settings_view):
            if hasattr(view, "set_available_width"): view.set_available_width(width)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.dashboard_view.shutdown_workers()
        self.gifts_view.shutdown_workers()
        self.controller.shutdown()
        event.accept()
