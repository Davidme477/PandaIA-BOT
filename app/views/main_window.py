from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.views.dashboard_view import DashboardView
from app.views.tiktok_view import TikTokView
from app.widgets.footer import Footer
from app.widgets.header import Header
from app.widgets.sidebar import Sidebar
from core.app_controller import AppController


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("PandaIA BOT")
        self.setMinimumSize(1400, 800)
        self.resize(1600, 900)

        self.pages = QStackedWidget()
        self.sidebar = Sidebar()
        self.controller = AppController(self)

        self.build_interface()
        self.connect_signals()

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

        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(16, 12, 16, 12)
        body_layout.setSpacing(16)

        self.dashboard_view = DashboardView()
        self.tiktok_view = TikTokView()

        self.pages.setObjectName("contentStack")
        self.pages.addWidget(self.dashboard_view)
        self.pages.addWidget(self.tiktok_view)

        body_layout.addWidget(self.sidebar)
        body_layout.addWidget(self.pages, 1)

        root_layout.addWidget(body, 1)

        self.footer = Footer()
        root_layout.addWidget(self.footer)

    def connect_signals(self) -> None:
        # Navegación lateral
        self.sidebar.page_selected.connect(
            self.change_page
        )

        # Conexión y desconexión de TikTok
        self.tiktok_view.connect_requested.connect(
            self.controller.connect_all
        )

        self.tiktok_view.disconnect_requested.connect(
            self.controller.disconnect_all
        )

        # Controles del panel principal
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

        # Estados superiores
        self.controller.bot_status_changed.connect(
            self.header.set_bot_status
        )

        self.controller.tiktok_status_changed.connect(
            self.header.set_tiktok_status
        )

        self.controller.ollama_status_changed.connect(
            self.header.set_ollama_status
        )

        self.controller.kokoro_status_changed.connect(
            self.header.set_kokoro_status
        )

        # Estado de la pantalla de TikTok
        self.controller.connection_state_changed.connect(
            self.tiktok_view.apply_connection_state
        )

        # Actividad reciente de TikTok
        self.controller.activity_received.connect(
            self.dashboard_view.add_activity
        )

    def change_page(self, page_index: int) -> None:
        if page_index < self.pages.count():
            self.pages.setCurrentIndex(page_index)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.controller.shutdown()
        event.accept()