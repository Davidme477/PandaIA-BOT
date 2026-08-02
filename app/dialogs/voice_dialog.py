from __future__ import annotations

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSlider,
    QTextEdit, QVBoxLayout, QWidget,
)

from services.tts.voice_manager import VoiceManager, get_voice_manager


DEFAULT_TEXT = "Hola, soy PandaIA. Gracias por acompañarme en este directo."


class VoicePreviewWorker(QThread):
    preview_ready = Signal(str)
    preview_failed = Signal(str)

    def __init__(self, *, manager: VoiceManager, engine: str, text: str, voice: str, speed: float, volume: float) -> None:
        super().__init__()
        self.manager = manager
        self.engine = engine
        self.text = text
        self.voice = voice
        self.speed = speed
        self.volume = volume

    def run(self) -> None:
        try:
            result = self.manager.preview(
                engine=self.engine,
                text=self.text,
                voice=self.voice,
                speed=self.speed,
                volume=self.volume,
            )
            self.preview_ready.emit(result)
        except Exception as error:
            self.preview_failed.emit(str(error))


class VoiceDialog(QDialog):
    def __init__(
        self,
        *,
        current_engine: str = "kokoro",
        current_voice: str = "ef_dora",
        current_speed: float = 1.0,
        current_volume: float = 1.0,
        manager: VoiceManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.setObjectName("voiceDialog")
        self.setWindowTitle("Administrador de Voces")
        self.setModal(True)
        self.setMinimumSize(520, 500)
        self._set_screen_safe_initial_size(680, 700)

        self.manager = manager or get_voice_manager()
        self.worker: VoicePreviewWorker | None = None

        self.engine_combo = QComboBox()
        self.engine_combo.setObjectName("voiceCombo")
        self.voice_combo = QComboBox()
        self.voice_combo.setObjectName("voiceCombo")

        self.description_label = QLabel()
        self.description_label.setObjectName("voiceDescription")
        self.description_label.setWordWrap(True)

        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setObjectName("voiceSlider")
        self.speed_slider.setRange(50, 200)
        self.speed_slider.setValue(max(50, min(200, round(current_speed * 100))))
        self.speed_value = QLabel()
        self.speed_value.setObjectName("voiceValue")

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setObjectName("voiceSlider")
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(max(0, min(100, round(current_volume * 100))))
        self.volume_value = QLabel()
        self.volume_value.setObjectName("voiceValue")

        self.preview_text = QTextEdit()
        self.preview_text.setObjectName("voicePreviewText")
        self.preview_text.setPlainText(DEFAULT_TEXT)
        self.preview_text.setMinimumHeight(120)
        self.preview_text.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self.status_label = QLabel("Lista para probar una voz.")
        self.status_label.setObjectName("voiceStatus")
        self.status_label.setWordWrap(True)

        self.preview_button = QPushButton("▶  Probar voz")
        self.preview_button.setObjectName("voicePreviewButton")
        self.preview_button.setFixedHeight(48)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setObjectName("voiceSecondaryButton")
        self.cancel_button.setMinimumWidth(125)
        self.cancel_button.setFixedHeight(46)

        self.save_button = QPushButton("Guardar voz")
        self.save_button.setObjectName("voiceSaveButton")
        self.save_button.setMinimumWidth(145)
        self.save_button.setFixedHeight(46)

        self.build_ui()
        self.load_engines(current_engine)
        self.connect_signals()
        self.load_voices(current_voice)
        self.update_values()

    def build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("voiceDialogScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("voiceDialogContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(16)

        title = QLabel("Administrador de Voces")
        title.setObjectName("voiceDialogTitle")
        subtitle = QLabel("Selecciona un motor, elige una voz y escúchala antes de guardar.")
        subtitle.setObjectName("voiceDialogSubtitle")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)

        separator = QFrame()
        separator.setObjectName("voiceDialogSeparator")
        separator.setFixedHeight(1)
        layout.addWidget(separator)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(15)
        grid.setColumnStretch(1, 1)

        grid.addWidget(self.make_label("Motor de voz"), 0, 0)
        grid.addWidget(self.engine_combo, 0, 1)
        grid.addWidget(self.make_label("Voz"), 1, 0)
        grid.addWidget(self.voice_combo, 1, 1)
        grid.addWidget(self.make_label("Descripción"), 2, 0)
        grid.addWidget(self.description_label, 2, 1)

        speed_box = QWidget()
        speed_layout = QHBoxLayout(speed_box)
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.addWidget(self.speed_slider, 1)
        speed_layout.addWidget(self.speed_value)

        volume_box = QWidget()
        volume_layout = QHBoxLayout(volume_box)
        volume_layout.setContentsMargins(0, 0, 0, 0)
        volume_layout.addWidget(self.volume_slider, 1)
        volume_layout.addWidget(self.volume_value)

        grid.addWidget(self.make_label("Velocidad"), 3, 0)
        grid.addWidget(speed_box, 3, 1)
        grid.addWidget(self.make_label("Volumen"), 4, 0)
        grid.addWidget(volume_box, 4, 1)
        layout.addLayout(grid)

        layout.addWidget(self.make_label("Texto de prueba"))
        layout.addWidget(self.preview_text)
        layout.addWidget(self.status_label)
        layout.addWidget(self.preview_button)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(content)
        root.addWidget(self.scroll_area, 1)

        self.actions_widget = QWidget()
        self.actions_widget.setObjectName("voiceDialogActions")
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 8, 0, 0)
        actions.addStretch()
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.save_button)
        self.actions_widget.setLayout(actions)
        root.addWidget(self.actions_widget)

    def _set_screen_safe_initial_size(self, width: int, height: int) -> None:
        available = self.screen().availableGeometry()
        self.setMinimumSize(
            min(self.minimumWidth(), max(1, available.width() - 20)),
            min(self.minimumHeight(), max(1, available.height() - 20)),
        )
        safe_width = max(self.minimumWidth(), min(width, available.width() - 40))
        safe_height = max(self.minimumHeight(), min(height, available.height() - 40))
        self.setMaximumHeight(max(self.minimumHeight(), available.height() - 20))
        self.resize(safe_width, safe_height)

    @staticmethod
    def make_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("voiceFieldLabel")
        return label

    def load_engines(self, current_engine: str) -> None:
        selected = 0
        for index, engine in enumerate(self.manager.list_engines()):
            label = engine.display_name if engine.available else f"{engine.display_name} · No disponible"
            self.engine_combo.addItem(label, engine.code)
            item = self.engine_combo.model().item(index)
            if item is not None:
                item.setEnabled(engine.available)
            if engine.code == current_engine and engine.available:
                selected = index
        self.engine_combo.setCurrentIndex(selected)

    def load_voices(self, preferred_voice: str = "") -> None:
        self.voice_combo.clear()
        try:
            voices = self.manager.list_voices(self.selected_engine())
        except Exception as error:
            self.description_label.setText(str(error))
            return

        selected = 0
        for index, voice in enumerate(voices):
            self.voice_combo.addItem(f"{voice.display_name} · {voice.gender}", voice.code)
            if voice.code == preferred_voice:
                selected = index

        enabled = self.voice_combo.count() > 0
        self.voice_combo.setEnabled(enabled)
        self.preview_button.setEnabled(enabled)
        self.save_button.setEnabled(enabled)

        if enabled:
            self.voice_combo.setCurrentIndex(selected)
            self.update_description()
        else:
            self.description_label.setText("Este motor no tiene voces disponibles.")

    def connect_signals(self) -> None:
        self.engine_combo.currentIndexChanged.connect(lambda: self.load_voices())
        self.voice_combo.currentIndexChanged.connect(self.update_description)
        self.speed_slider.valueChanged.connect(self.update_values)
        self.volume_slider.valueChanged.connect(self.update_values)
        self.preview_button.clicked.connect(self.preview_voice)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)

    def selected_engine(self) -> str:
        return str(self.engine_combo.currentData())

    def selected_voice_code(self) -> str:
        return str(self.voice_combo.currentData())

    def selected_speed(self) -> float:
        return self.speed_slider.value() / 100.0

    def selected_volume(self) -> float:
        return self.volume_slider.value() / 100.0

    def selected_settings(self) -> dict[str, object]:
        engine = self.selected_engine()
        voice = self.manager.get_voice(engine, self.selected_voice_code())
        return {
            "engine": engine,
            "voice": voice.code,
            "display_name": voice.display_name,
            "language": voice.language,
            "gender": voice.gender,
            "style": voice.style,
            "speed": self.selected_speed(),
            "volume": self.selected_volume(),
        }

    def update_description(self) -> None:
        if self.voice_combo.count() == 0:
            return
        try:
            voice = self.manager.get_voice(self.selected_engine(), self.selected_voice_code())
            self.description_label.setText(f"{voice.language} · {voice.style}")
        except Exception as error:
            self.description_label.setText(str(error))

    def update_values(self) -> None:
        self.speed_value.setText(f"{self.selected_speed():.2f}x")
        self.volume_value.setText(f"{round(self.selected_volume() * 100)}%")

    def preview_voice(self) -> None:
        text = self.preview_text.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Texto vacío", "Escribe una frase para probar la voz.")
            return
        if self.worker is not None and self.worker.isRunning():
            return

        self.set_busy(True)
        self.status_label.setText("Generando y reproduciendo la vista previa...")
        self.worker = VoicePreviewWorker(
            manager=self.manager,
            engine=self.selected_engine(),
            text=text,
            voice=self.selected_voice_code(),
            speed=self.selected_speed(),
            volume=self.selected_volume(),
        )
        self.worker.preview_ready.connect(self.preview_ready)
        self.worker.preview_failed.connect(self.preview_error)
        self.worker.finished.connect(self.preview_finished)
        self.worker.start()

    def set_busy(self, busy: bool) -> None:
        for widget in (
            self.preview_button, self.save_button, self.cancel_button,
            self.engine_combo, self.voice_combo, self.speed_slider,
            self.volume_slider, self.preview_text,
        ):
            widget.setDisabled(busy)

    def preview_ready(self, result: str) -> None:
        self.status_label.setText(f"Vista previa finalizada: {result}")

    def preview_error(self, message: str) -> None:
        self.status_label.setText(message)
        QMessageBox.critical(self, "Error del motor de voz", message)

    def preview_finished(self) -> None:
        self.set_busy(False)
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None
