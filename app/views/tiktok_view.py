from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from app.widgets.responsive_grid import ResponsiveGrid
from config.settings_store import read_settings, write_settings_atomic


CONFIG_FILE = Path("config/settings.json")


class TikTokView(QScrollArea):
    connect_requested = Signal(str)
    disconnect_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.connection_state = "disconnected"
        self.build_interface()
        self.load_settings()

    def build_interface(self) -> None:
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        title = QLabel("Conexión a TikTok Live")
        title.setObjectName("pageTitle")

        subtitle = QLabel(
            "Ingresa el nombre de usuario de la cuenta que realizará el Live."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)

        root.addWidget(title)
        root.addWidget(subtitle)

        columns = ResponsiveGrid(wide_columns=2, medium_columns=2)
        columns.add_responsive_widget(self.create_account_panel())
        columns.add_responsive_widget(self.create_information_panel())

        root.addWidget(columns)
        root.addWidget(self.create_connection_panel())
        root.addStretch()
        self.setWidget(content)

    def create_account_panel(self) -> QFrame:
        panel = self.create_panel("Cuenta de TikTok")
        layout = panel.layout()

        label = QLabel("Usuario de TikTok")
        label.setObjectName("fieldLabel")

        self.username_input = QLineEdit()
        self.username_input.setObjectName("usernameInput")
        self.username_input.setPlaceholderText("@nombre_de_usuario")
        self.username_input.setClearButtonEnabled(True)
        self.username_input.setFixedHeight(48)

        helper = QLabel(
            "Puedes escribir el usuario con o sin el símbolo @."
        )
        helper.setObjectName("helperText")
        helper.setWordWrap(True)

        self.remember_checkbox = QCheckBox("Recordar usuario")
        self.remember_checkbox.setChecked(True)

        self.save_button = QPushButton("Guardar usuario")
        self.save_button.setObjectName("primaryButton")
        self.save_button.setFixedHeight(50)
        self.save_button.clicked.connect(self.save_settings)

        self.save_message = QLabel("")
        self.save_message.setObjectName("successMessage")
        self.save_message.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(label)
        layout.addWidget(self.username_input)
        layout.addWidget(helper)
        layout.addSpacing(10)
        layout.addWidget(self.remember_checkbox)
        layout.addStretch()
        layout.addWidget(self.save_button)
        layout.addWidget(self.save_message)

        return panel

    def create_information_panel(self) -> QFrame:
        panel = self.create_panel("Información de conexión")
        layout = panel.layout()

        self.current_user_value = QLabel("Sin usuario")
        self.current_user_value.setObjectName("informationValue")

        self.connection_value = QLabel("Desconectado")
        self.connection_value.setObjectName("connectionDisconnected")

        self.last_connection_value = QLabel("--")
        self.last_connection_value.setObjectName("informationValue")

        self.live_time_value = QLabel("00:00:00")
        self.live_time_value.setObjectName("informationValue")

        for label, value in [
            ("Usuario configurado", self.current_user_value),
            ("Estado actual", self.connection_value),
            ("Última conexión", self.last_connection_value),
            ("Tiempo conectado", self.live_time_value),
        ]:
            layout.addWidget(self.create_information_row(label, value))

        layout.addStretch()
        return panel

    def create_connection_panel(self) -> QFrame:
        panel = self.create_panel("Estado de conexión")
        panel.setMinimumHeight(260)
        layout = panel.layout()

        self.status_circle = QLabel("●")
        self.status_circle.setObjectName("largeStatusDisconnected")
        self.status_circle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status_title = QLabel("Desconectado")
        self.status_title.setObjectName("connectionTitle")
        self.status_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status_description = QLabel(
            "Escribe y guarda tu usuario de TikTok para continuar."
        )
        self.status_description.setObjectName("pageSubtitle")
        self.status_description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_description.setWordWrap(True)

        self.connect_button = QPushButton("Conectar")
        self.connect_button.setObjectName("primaryButton")
        self.connect_button.setFixedHeight(52)
        self.connect_button.clicked.connect(self.handle_connection_click)

        layout.addStretch()
        layout.addWidget(self.status_circle)
        layout.addWidget(self.status_title)
        layout.addWidget(self.status_description)
        layout.addSpacing(12)
        layout.addWidget(self.connect_button)
        layout.addStretch()

        return panel

    def create_panel(self, title_text: str) -> QFrame:
        panel = QFrame()
        panel.setObjectName("tiktokPanel")
        panel.setMinimumHeight(280)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        title = QLabel(title_text)
        title.setObjectName("panelTitle")

        separator = QFrame()
        separator.setObjectName("horizontalSeparator")
        separator.setFixedHeight(1)

        layout.addWidget(title)
        layout.addWidget(separator)
        return panel

    def create_information_row(
        self,
        label_text: str,
        value_widget: QLabel,
    ) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(10)

        label = QLabel(label_text)
        label.setObjectName("informationLabel")
        label.setWordWrap(True)
        value_widget.setWordWrap(True)

        layout.addWidget(label)
        layout.addStretch()
        layout.addWidget(value_widget)
        return row

    def normalize_username(self, username: str) -> str:
        username = username.strip().replace(" ", "")
        if not username:
            return ""
        return username if username.startswith("@") else f"@{username}"

    def save_settings(self) -> None:
        username = self.normalize_username(self.username_input.text())

        if not username:
            self.show_save_message(
                "Escribe un nombre de usuario.",
                is_error=True,
            )
            return

        self.username_input.setText(username)
        self.current_user_value.setText(username)
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

        data = read_settings(CONFIG_FILE)
        data["tiktok"] = {
            "username": username,
            "remember_user": self.remember_checkbox.isChecked(),
        }

        try:
            write_settings_atomic(CONFIG_FILE, data)
            self.show_save_message(
                "Usuario guardado correctamente.",
                is_error=False,
            )
            self.status_description.setText(
                f"Usuario preparado para conectarse: {username}"
            )
        except OSError as error:
            self.show_save_message(
                f"No se pudo guardar: {error}",
                is_error=True,
            )

    def load_settings(self) -> None:
        if not CONFIG_FILE.exists():
            return

        try:
            data = read_settings(CONFIG_FILE)
            tiktok_data = data.get("tiktok", {})
            username = tiktok_data.get("username", "")
            remember_user = tiktok_data.get("remember_user", True)

            self.remember_checkbox.setChecked(remember_user)

            if remember_user and username:
                self.username_input.setText(username)
                self.current_user_value.setText(username)
                self.status_description.setText(
                    f"Usuario preparado para conectarse: {username}"
                )

        except OSError:
            self.show_save_message(
                "No se pudo leer la configuración guardada.",
                is_error=True,
            )

    def handle_connection_click(self) -> None:
        if self.connection_state in {"connecting", "disconnecting"}:
            return

        if self.connection_state == "connected":
            self.disconnect_requested.emit()
            return

        username = self.normalize_username(self.username_input.text())

        if not username:
            self.show_save_message(
                "Primero escribe tu usuario de TikTok.",
                is_error=True,
            )
            return

        self.username_input.setText(username)
        self.current_user_value.setText(username)
        self.connect_requested.emit(username)

    def apply_connection_state(self, state: str, message: str) -> None:
        self.connection_state = state

        if state == "connecting":
            self.connection_value.setText("Conectando...")
            self.status_title.setText("Conectando...")
            self.status_description.setText(message)
            self.connect_button.setText("Conectando...")
            self.connect_button.setEnabled(False)

        elif state == "connected":
            username = self.normalize_username(self.username_input.text())
            self.connection_value.setText("Conectado")
            self.connection_value.setObjectName("connectionConnected")
            self.status_circle.setObjectName("largeStatusConnected")
            self.status_title.setText(f"Conectado a {username}")
            self.status_description.setText(message)
            self.connect_button.setText("Desconectar")
            self.connect_button.setObjectName("dangerButton")
            self.connect_button.setEnabled(True)
            self.last_connection_value.setText(
                datetime.now().strftime("%d/%m/%Y %H:%M")
            )

        elif state == "disconnecting":
            self.connection_value.setText("Desconectando...")
            self.status_title.setText("Desconectando...")
            self.status_description.setText(message)
            self.connect_button.setText("Desconectando...")
            self.connect_button.setEnabled(False)

        elif state == "error":
            self.connection_value.setText("Error")
            self.connection_value.setObjectName("connectionDisconnected")
            self.status_circle.setObjectName("largeStatusDisconnected")
            self.status_title.setText("No se pudo conectar")
            self.status_description.setText(message)
            self.connect_button.setText("Conectar")
            self.connect_button.setObjectName("primaryButton")
            self.connect_button.setEnabled(True)

        else:
            self.connection_state = "disconnected"
            self.connection_value.setText("Desconectado")
            self.connection_value.setObjectName("connectionDisconnected")
            self.status_circle.setObjectName("largeStatusDisconnected")
            self.status_title.setText("Desconectado")
            self.status_description.setText(message)
            self.connect_button.setText("Conectar")
            self.connect_button.setObjectName("primaryButton")
            self.connect_button.setEnabled(True)

        self.refresh_style(self.connection_value)
        self.refresh_style(self.status_circle)
        self.refresh_style(self.connect_button)

    def show_save_message(self, message: str, *, is_error: bool) -> None:
        self.save_message.setText(message)
        self.save_message.setObjectName(
            "errorMessage" if is_error else "successMessage"
        )
        self.refresh_style(self.save_message)

    @staticmethod
    def refresh_style(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()
