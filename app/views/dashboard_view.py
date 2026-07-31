import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


from services.ollama.ollama_service import OllamaService, OllamaServiceError


CONFIG_FILE = Path("config/settings.json")


class DashboardView(QScrollArea):
    setting_changed = Signal(str, object)
    stop_bot_requested = Signal()
    edit_personality_requested = Signal()
    change_voice_requested = Signal()

    def __init__(self) -> None:
        super().__init__()

        self.setObjectName("contentScroll")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        self.model_combo: QComboBox | None = None
        self.personality_combo: QComboBox | None = None
        self.language_combo: QComboBox | None = None
        self.control_toggles: dict[str, QPushButton] = {}
        self.activity_layout: QVBoxLayout | None = None

        content = QWidget()
        content.setObjectName("mainContent")

        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(self.create_statistics())

        cards = QHBoxLayout()
        cards.setSpacing(16)

        cards.addWidget(self.create_ai_card(), 1)
        cards.addWidget(self.create_voice_card(), 1)
        cards.addWidget(self.create_controls_card(), 1)
        cards.addWidget(self.create_activity_card(), 1)

        layout.addLayout(cards)
        layout.addWidget(self.create_memory_panel())
        layout.addStretch()

        self.setWidget(content)

        self.load_ollama_models()
        self.load_dashboard_settings()
        self.connect_dashboard_signals()

    def create_statistics(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("statisticsPanel")
        frame.setFixedHeight(105)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(22, 12, 22, 12)
        layout.setSpacing(0)

        statistics = [
            ("👥", "Espectadores", "12,582"),
            ("♥", "Me gusta", "45,231"),
            ("🎁", "Regalos", "3,421"),
            ("▣", "Comentarios", "1,284"),
            ("◷", "Tiempo en vivo", "01:25:30"),
        ]

        for index, data in enumerate(statistics):
            icon, name, value = data

            item = QWidget()
            item_layout = QHBoxLayout(item)
            item_layout.setContentsMargins(12, 0, 12, 0)
            item_layout.setSpacing(14)

            icon_label = QLabel(icon)
            icon_label.setObjectName("statIcon")

            texts = QWidget()
            texts_layout = QVBoxLayout(texts)
            texts_layout.setContentsMargins(0, 0, 0, 0)
            texts_layout.setSpacing(5)

            name_label = QLabel(name)
            name_label.setObjectName("statName")

            value_label = QLabel(value)
            value_label.setObjectName("statValue")

            texts_layout.addWidget(name_label)
            texts_layout.addWidget(value_label)

            item_layout.addWidget(icon_label)
            item_layout.addWidget(texts)

            layout.addWidget(item, 1)

            if index < len(statistics) - 1:
                separator = QFrame()
                separator.setObjectName("verticalSeparator")
                separator.setFixedWidth(1)
                layout.addWidget(separator)

        return frame

    def create_ai_card(self) -> QFrame:
        card = self.create_panel("IA & Personalidad")
        layout = card.layout()

        layout.addWidget(QLabel("Modelo IA (Ollama)"))

        self.model_combo = QComboBox()
        layout.addWidget(self.model_combo)

        layout.addWidget(QLabel("Personalidad"))

        self.personality_combo = QComboBox()
        self.personality_combo.addItems(
            [
                "Amigable, divertida y carismática",
                "Profesional",
                "Entusiasta",
            ]
        )
        layout.addWidget(self.personality_combo)

        layout.addWidget(QLabel("Idioma"))

        self.language_combo = QComboBox()
        self.language_combo.addItems(["Español", "Inglés", "Portugués"])
        layout.addWidget(self.language_combo)

        layout.addStretch()

        button = QPushButton("Editar Personalidad")
        button.setObjectName("primaryButton")
        button.setFixedHeight(50)
        button.clicked.connect(self.edit_personality_requested.emit)

        layout.addWidget(button)

        return card

    def create_voice_card(self) -> QFrame:
        card = self.create_panel("Voz Actual (TTS)")
        layout = card.layout()

        visual = QLabel("👩🏻     〰〰〰〰〰")
        visual.setObjectName("voiceVisual")
        visual.setAlignment(Qt.AlignmentFlag.AlignCenter)
        visual.setFixedHeight(115)

        layout.addWidget(visual)
        layout.addWidget(QLabel("Voz:  Emma (ES)"))
        layout.addWidget(QLabel("Idioma:  Español"))
        layout.addWidget(QLabel("Emoción:  Feliz ●"))
        layout.addStretch()

        button = QPushButton("Cambiar Voz")
        button.setObjectName("primaryButton")
        button.setFixedHeight(50)
        button.clicked.connect(self.change_voice_requested.emit)

        layout.addWidget(button)

        return card

    def create_controls_card(self) -> QFrame:
        card = self.create_panel("Controles del BOT")
        layout = card.layout()

        controls = [
            ("respond_comments", "Responder a comentarios"),
            ("read_gifts", "Leer regalos en voz alta"),
            ("use_memory", "Usar memoria"),
            ("automatic_responses", "Respuestas automáticas"),
            ("autonomous_mode", "Modo IA Autónomo"),
        ]

        for key, text in controls:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)

            toggle = QPushButton("●")
            toggle.setObjectName("toggleButton")
            toggle.setCheckable(True)
            toggle.setChecked(True)
            toggle.setFixedSize(43, 25)

            self.control_toggles[key] = toggle

            row_layout.addWidget(QLabel(text))
            row_layout.addStretch()
            row_layout.addWidget(toggle)

            layout.addWidget(row)

        layout.addStretch()

        stop_button = QPushButton("Detener BOT")
        stop_button.setObjectName("dangerButton")
        stop_button.setFixedHeight(50)
        stop_button.clicked.connect(self.stop_bot_requested.emit)

        layout.addWidget(stop_button)

        return card

    def create_activity_card(self) -> QFrame:
        card = self.create_panel("Actividad Reciente")
        layout = card.layout()
        self.activity_layout = layout

        activities = [
            ("🌪", "Regalo Tornado", "@CarlosTikTok", "x1"),
            ("🦁", "Regalo León", "@Maria_23", "x5"),
            ("👤", "Nuevo Seguidor", "@Alex_Oficial", ""),
            ("🎁", "Regalo TikTok Universe", "@SofiLive", "x1"),
        ]

        for icon, title, user, amount in activities:
            row = QWidget()
            row.setObjectName("activityRow")

            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 10, 0, 10)

            icon_label = QLabel(icon)
            icon_label.setObjectName("activityIcon")
            icon_label.setFixedWidth(48)

            text_container = QWidget()
            text_layout = QVBoxLayout(text_container)
            text_layout.setContentsMargins(0, 0, 0, 0)

            text_layout.addWidget(QLabel(title))

            user_label = QLabel(user)
            user_label.setObjectName("activityUser")
            text_layout.addWidget(user_label)

            amount_label = QLabel(amount)
            amount_label.setObjectName("activityAmount")

            row_layout.addWidget(icon_label)
            row_layout.addWidget(text_container, 1)
            row_layout.addWidget(amount_label)

            layout.addWidget(row)

        layout.addStretch()

        return card

    def add_activity(
        self,
        icon: str,
        title: str,
        user: str,
        amount: str = "",
    ) -> None:
        if self.activity_layout is None:
            return

        row = QWidget()
        row.setObjectName("activityRow")

        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 10, 0, 10)

        icon_label = QLabel(icon)
        icon_label.setObjectName("activityIcon")
        icon_label.setFixedWidth(48)

        text_container = QWidget()
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)

        title_label = QLabel(title)
        text_layout.addWidget(title_label)

        user_label = QLabel(user)
        user_label.setObjectName("activityUser")
        text_layout.addWidget(user_label)

        amount_label = QLabel(amount)
        amount_label.setObjectName("activityAmount")

        row_layout.addWidget(icon_label)
        row_layout.addWidget(text_container, 1)
        row_layout.addWidget(amount_label)

        self.activity_layout.insertWidget(2, row)

        activity_rows: list[QWidget] = []

        for index in range(self.activity_layout.count()):
            item = self.activity_layout.itemAt(index)
            widget = item.widget()

            if (
                widget is not None
                and widget.objectName() == "activityRow"
            ):
                activity_rows.append(widget)

        for old_row in activity_rows[4:]:
            self.activity_layout.removeWidget(old_row)
            old_row.deleteLater()

    def create_panel(self, title_text: str) -> QFrame:
        panel = QFrame()
        panel.setObjectName("dashboardCard")
        panel.setMinimumHeight(410)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(14)

        title = QLabel(title_text)
        title.setObjectName("panelTitle")

        separator = QFrame()
        separator.setObjectName("horizontalSeparator")
        separator.setFixedHeight(1)

        layout.addWidget(title)
        layout.addWidget(separator)

        return panel

    def create_memory_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("memoryPanel")
        panel.setFixedHeight(130)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 16, 22, 18)
        layout.setSpacing(12)

        title = QLabel("Memoria del BOT")
        title.setObjectName("panelTitle")

        fields = QHBoxLayout()
        fields.setSpacing(12)

        values = [
            "Nombre del streamer:   Alex",
            "Tema del live:   Charlando y jugando",
            "Recuerda a:   Seguidores frecuentes",
            "Última interacción:   hace 2 min",
        ]

        for value in values:
            label = QLabel(value)
            label.setObjectName("memoryField")
            label.setMinimumHeight(42)
            fields.addWidget(label)

        layout.addWidget(title)
        layout.addLayout(fields)

        return panel

    def load_ollama_models(self) -> None:
        if self.model_combo is None:
            return

        self.model_combo.clear()

        try:
            models = OllamaService(timeout=5.0).list_models()
        except OllamaServiceError:
            self.model_combo.addItem("Ollama no disponible")
            self.model_combo.setEnabled(False)
            return

        if not models:
            self.model_combo.addItem("No hay modelos instalados")
            self.model_combo.setEnabled(False)
            return

        self.model_combo.setEnabled(True)
        self.model_combo.addItems(models)

    def connect_dashboard_signals(self) -> None:
        if self.model_combo is not None:
            self.model_combo.currentTextChanged.connect(
                lambda value: self.handle_setting_change("model", value)
            )

        if self.personality_combo is not None:
            self.personality_combo.currentTextChanged.connect(
                lambda value: self.handle_setting_change("personality", value)
            )

        if self.language_combo is not None:
            self.language_combo.currentTextChanged.connect(
                lambda value: self.handle_setting_change("language", value)
            )

        for key, toggle in self.control_toggles.items():
            toggle.toggled.connect(
                lambda checked, current_key=key: self.handle_setting_change(
                    current_key,
                    checked,
                )
            )

    def handle_setting_change(self, key: str, value: object) -> None:
        self.save_dashboard_settings()
        self.setting_changed.emit(key, value)

    def load_dashboard_settings(self) -> None:
        data = self.read_settings()
        dashboard = data.get("dashboard", {})

        saved_model = str(dashboard.get("model", "")).strip()

        if (
            self.model_combo is not None
            and self.model_combo.isEnabled()
            and self.model_combo.count() > 0
        ):
            saved_index = self.model_combo.findText(saved_model)

            if saved_index >= 0:
                self.model_combo.setCurrentIndex(saved_index)
            else:
                self.model_combo.setCurrentIndex(0)
                dashboard["model"] = self.model_combo.currentText()
                data["dashboard"] = dashboard
                CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
                CONFIG_FILE.write_text(
                    json.dumps(data, indent=4, ensure_ascii=False),
                    encoding="utf-8",
                )
        self.set_combo_value(
            self.personality_combo,
            dashboard.get(
                "personality",
                "Amigable, divertida y carismática",
            ),
        )
        self.set_combo_value(
            self.language_combo,
            dashboard.get("language", "Español"),
        )

        for key, toggle in self.control_toggles.items():
            toggle.setChecked(bool(dashboard.get(key, True)))

    def save_dashboard_settings(self) -> None:
        data = self.read_settings()

        dashboard = {
            "model": self.model_combo.currentText(),
            "personality": self.personality_combo.currentText(),
            "language": self.language_combo.currentText(),
        }

        for key, toggle in self.control_toggles.items():
            dashboard[key] = toggle.isChecked()

        data["dashboard"] = dashboard

        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(data, indent=4, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def set_combo_value(combo: QComboBox | None, value: str) -> None:
        if combo is None:
            return

        index = combo.findText(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    @staticmethod
    def read_settings() -> dict:
        if not CONFIG_FILE.exists():
            return {}

        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}