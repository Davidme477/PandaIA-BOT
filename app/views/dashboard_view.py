import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)
from services.ollama.ollama_service import OllamaService, OllamaServiceError
from services.live.runtime_controls import stop_button_enabled
from services.tiktok.live_state import LiveStats, format_count, format_elapsed

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
        self.activity_placeholder: QLabel | None = None
        self.stat_labels: dict[str, QLabel] = {}
        self.voice_name_label: QLabel | None = None
        self.voice_language_label: QLabel | None = None
        self.voice_engine_label: QLabel | None = None
        self.voice_details_label: QLabel | None = None
        self.stop_button: QPushButton | None = None

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
        self.load_voice_settings()
        self.connect_dashboard_signals()

    def create_statistics(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("statisticsPanel")
        frame.setFixedHeight(105)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(22, 12, 22, 12)
        layout.setSpacing(0)

        stats = [
            ("viewers", "👥", "Espectadores", "0"),
            ("likes", "♥", "Me gusta", "0"),
            ("gifts", "🎁", "Regalos", "0"),
            ("comments", "▣", "Comentarios", "0"),
            ("elapsed", "◷", "Tiempo conectado", "00:00:00"),
        ]
        for index, (key, icon, name, value) in enumerate(stats):
            item = QWidget()
            row = QHBoxLayout(item)
            row.setContentsMargins(12, 0, 12, 0)
            row.setSpacing(14)
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
            self.stat_labels[key] = value_label
            texts_layout.addWidget(name_label)
            texts_layout.addWidget(value_label)
            row.addWidget(icon_label)
            row.addWidget(texts)
            layout.addWidget(item, 1)
            if index < len(stats) - 1:
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
        self.personality_combo.addItems([
            "Amigable, divertida y carismática",
            "Profesional",
            "Entusiasta",
        ])
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
        visual = QLabel("🎙️     〰〰〰〰〰")
        visual.setObjectName("voiceVisual")
        visual.setAlignment(Qt.AlignmentFlag.AlignCenter)
        visual.setFixedHeight(115)
        self.voice_name_label = QLabel("Voz:  Dora")
        self.voice_language_label = QLabel("Idioma:  Español")
        self.voice_engine_label = QLabel("Motor:  Kokoro")
        self.voice_details_label = QLabel("Velocidad: 1.00x · Volumen: 100%")
        layout.addWidget(visual)
        layout.addWidget(self.voice_name_label)
        layout.addWidget(self.voice_language_label)
        layout.addWidget(self.voice_engine_label)
        layout.addWidget(self.voice_details_label)
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
        tooltips = {
            "respond_comments": "Permite que PandaIA responda comentarios del live.",
            "read_gifts": "Agradece los regalos reales usando IA y voz.",
            "use_memory": "Recuerda el contexto reciente de cada usuario durante este live.",
            "automatic_responses": "Responde a todos los comentarios; desactivado, solo menciones y preguntas.",
            "autonomous_mode": "Permite intervenciones breves después de un periodo sin actividad.",
        }
        for key, text in controls:
            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            toggle = QPushButton("●")
            toggle.setObjectName("toggleButton")
            toggle.setCheckable(True)
            toggle.setChecked(True)
            toggle.setFixedSize(43, 25)
            toggle.setToolTip(tooltips[key])
            self.control_toggles[key] = toggle
            row.addWidget(QLabel(text))
            row.addStretch()
            row.addWidget(toggle)
            layout.addWidget(row_widget)
        layout.addStretch()
        self.stop_button = QPushButton("Detener BOT")
        self.stop_button.setObjectName("dangerButton")
        self.stop_button.setFixedHeight(50)
        self.stop_button.setToolTip("Desconecta el live y cancela las respuestas pendientes.")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_bot_requested.emit)
        layout.addWidget(self.stop_button)
        return card

    def apply_connection_state(self, state: str, _message: str) -> None:
        if self.stop_button is not None:
            self.stop_button.setEnabled(stop_button_enabled(state))

    def create_activity_card(self) -> QFrame:
        card = self.create_panel("Actividad Reciente")
        layout = card.layout()
        self.activity_layout = layout
        self.activity_placeholder = QLabel("Aún no hay actividad")
        self.activity_placeholder.setObjectName("activityEmpty")
        layout.addWidget(self.activity_placeholder)
        layout.addStretch()
        return card

    def build_activity_row(self, icon: str, title: str, user: str, amount: str) -> QWidget:
        widget = QWidget()
        widget.setObjectName("activityRow")
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 10, 0, 10)
        icon_label = QLabel(icon)
        icon_label.setObjectName("activityIcon")
        icon_label.setFixedWidth(48)
        text_box = QWidget()
        text_layout = QVBoxLayout(text_box)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.addWidget(QLabel(title))
        user_label = QLabel(user)
        user_label.setObjectName("activityUser")
        text_layout.addWidget(user_label)
        amount_label = QLabel(amount)
        amount_label.setObjectName("activityAmount")
        row.addWidget(icon_label)
        row.addWidget(text_box, 1)
        row.addWidget(amount_label)
        return widget

    def add_activity(self, icon: str, title: str, user: str, amount: str = "") -> None:
        if self.activity_layout is None:
            return
        if self.activity_placeholder is not None:
            self.activity_layout.removeWidget(self.activity_placeholder)
            self.activity_placeholder.hide()
        self.activity_layout.insertWidget(
            2,
            self.build_activity_row(icon, title, user, amount),
        )
        rows = []
        for index in range(self.activity_layout.count()):
            widget = self.activity_layout.itemAt(index).widget()
            if widget is not None and widget.objectName() == "activityRow":
                rows.append(widget)
        for old in rows[4:]:
            self.activity_layout.removeWidget(old)
            old.deleteLater()

    def set_live_stats(self, stats: LiveStats) -> None:
        values = {
            "viewers": format_count(stats.viewers),
            "likes": format_count(stats.likes),
            "gifts": format_count(stats.gifts),
            "comments": format_count(stats.comments),
            "elapsed": format_elapsed(stats.elapsed_seconds),
        }
        for key, value in values.items():
            label = self.stat_labels.get(key)
            if label is not None:
                label.setText(value)

    def reset_live_session(self) -> None:
        self.set_live_stats(LiveStats())
        if self.activity_layout is None:
            return
        for index in reversed(range(self.activity_layout.count())):
            widget = self.activity_layout.itemAt(index).widget()
            if widget is not None and widget.objectName() == "activityRow":
                self.activity_layout.removeWidget(widget)
                widget.deleteLater()
        if self.activity_placeholder is not None:
            self.activity_placeholder.show()
            if self.activity_layout.indexOf(self.activity_placeholder) < 0:
                self.activity_layout.insertWidget(2, self.activity_placeholder)

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
                lambda checked, current_key=key:
                    self.handle_setting_change(current_key, checked)
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
            index = self.model_combo.findText(saved_model)
            self.model_combo.setCurrentIndex(index if index >= 0 else 0)
        self.set_combo_value(
            self.personality_combo,
            str(dashboard.get("personality", "Amigable, divertida y carismática")),
        )
        self.set_combo_value(
            self.language_combo,
            str(dashboard.get("language", "Español")),
        )
        for key, toggle in self.control_toggles.items():
            toggle.setChecked(bool(dashboard.get(key, True)))

    def save_dashboard_settings(self) -> None:
        if not all((self.model_combo, self.personality_combo, self.language_combo)):
            return
        data = self.read_settings()
        dashboard = {
            "model": self.model_combo.currentText(),
            "personality": self.personality_combo.currentText(),
            "language": self.language_combo.currentText(),
        }
        for key, toggle in self.control_toggles.items():
            dashboard[key] = toggle.isChecked()
        data["dashboard"] = dashboard
        self.write_settings(data)

    def load_voice_settings(self) -> None:
        tts = self.read_settings().get("tts", {})
        self.set_voice_info(
            str(tts.get("display_name", "Dora")),
            str(tts.get("language", "Español")),
            str(tts.get("engine", "kokoro")),
            float(tts.get("speed", 1.0)),
            float(tts.get("volume", 1.0)),
        )

    def set_voice_info(
        self,
        display_name: str,
        language: str,
        engine: str,
        speed: float,
        volume: float,
    ) -> None:
        if self.voice_name_label:
            self.voice_name_label.setText(f"Voz:  {display_name}")
        if self.voice_language_label:
            self.voice_language_label.setText(f"Idioma:  {language}")
        if self.voice_engine_label:
            self.voice_engine_label.setText(f"Motor:  {engine.title()}")
        if self.voice_details_label:
            self.voice_details_label.setText(
                f"Velocidad: {speed:.2f}x · Volumen: {round(volume * 100)}%"
            )

    @staticmethod
    def set_combo_value(combo: QComboBox | None, value: str) -> None:
        if combo is not None:
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

    @staticmethod
    def write_settings(data: dict) -> None:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(data, indent=4, ensure_ascii=False),
            encoding="utf-8",
        )
