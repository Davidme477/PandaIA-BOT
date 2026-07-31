from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from services.tts.kokoro_service import (
    KokoroService,
    VoiceOption,
)


PREVIEW_FILE = Path("temp/kokoro/voice_preview.wav")
DEFAULT_TEXT = (
    "Hola, soy PandaIA. Gracias por acompañarme en este directo."
)


class VoicePreviewWorker(QThread):
    preview_ready = Signal(str)
    preview_failed = Signal(str)

    def __init__(
        self,
        *,
        text: str,
        voice: str,
        speed: float,
        volume: float,
    ) -> None:
        super().__init__()
        self.text = text
        self.voice = voice
        self.speed = speed
        self.volume = volume

    def run(self) -> None:
        try:
            path = KokoroService().save_wav(
                text=self.text,
                output_path=PREVIEW_FILE,
                voice=self.voice,
                speed=self.speed,
                volume=self.volume,
            )

            if sys.platform == "win32":
                import winsound

                winsound.PlaySound(
                    str(path.resolve()),
                    winsound.SND_FILENAME,
                )

            self.preview_ready.emit(str(path))

        except Exception as error:
            self.preview_failed.emit(str(error))


class VoiceDialog(QDialog):
    def __init__(
        self,
        *,
        current_voice: str = "ef_dora",
        current_speed: float = 1.0,
        current_volume: float = 1.0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.setObjectName("voiceDialog")
        self.setWindowTitle("Administrador de Voces")
        self.setModal(True)
        self.setMinimumSize(620, 610)
        self.resize(680, 650)

        self.service = KokoroService()
        self.voices = self.service.list_voices()
        self.worker: VoicePreviewWorker | None = None

        self.voice_combo = QComboBox()
        self.voice_combo.setObjectName("voiceCombo")

        self.description_label = QLabel()
        self.description_label.setObjectName("voiceDescription")
        self.description_label.setWordWrap(True)

        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setObjectName("voiceSlider")
        self.speed_slider.setRange(50, 200)
        self.speed_slider.setValue(
            max(50, min(200, round(current_speed * 100)))
        )

        self.speed_value = QLabel()
        self.speed_value.setObjectName("voiceValue")

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setObjectName("voiceSlider")
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(
            max(0, min(100, round(current_volume * 100)))
        )

        self.volume_value = QLabel()
        self.volume_value.setObjectName("voiceValue")

        self.preview_text = QTextEdit()
        self.preview_text.setObjectName("voicePreviewText")
        self.preview_text.setPlainText(DEFAULT_TEXT)
        self.preview_text.setMinimumHeight(120)
        self.preview_text.setMaximumHeight(145)

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
        self.load_voices(current_voice)
        self.connect_signals()
        self.update_values()

    def build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 26, 28, 26)
        root.setSpacing(18)

        title = QLabel("Administrador de Voces")
        title.setObjectName("voiceDialogTitle")

        subtitle = QLabel(
            "Selecciona una voz, ajusta la velocidad y el volumen, "
            "y escúchala antes de guardar."
        )
        subtitle.setObjectName("voiceDialogSubtitle")
        subtitle.setWordWrap(True)

        root.addWidget(title)
        root.addWidget(subtitle)

        separator = QFrame()
        separator.setObjectName("voiceDialogSeparator")
        separator.setFixedHeight(1)
        root.addWidget(separator)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(15)
        grid.setColumnStretch(1, 1)

        grid.addWidget(self.make_label("Voz"), 0, 0)
        grid.addWidget(self.voice_combo, 0, 1)

        grid.addWidget(self.make_label("Descripción"), 1, 0)
        grid.addWidget(self.description_label, 1, 1)

        speed_box = QWidget()
        speed_layout = QHBoxLayout(speed_box)
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.setSpacing(12)
        speed_layout.addWidget(self.speed_slider, 1)
        speed_layout.addWidget(self.speed_value)

        volume_box = QWidget()
        volume_layout = QHBoxLayout(volume_box)
        volume_layout.setContentsMargins(0, 0, 0, 0)
        volume_layout.setSpacing(12)
        volume_layout.addWidget(self.volume_slider, 1)
        volume_layout.addWidget(self.volume_value)

        grid.addWidget(self.make_label("Velocidad"), 2, 0)
        grid.addWidget(speed_box, 2, 1)

        grid.addWidget(self.make_label("Volumen"), 3, 0)
        grid.addWidget(volume_box, 3, 1)

        root.addLayout(grid)

        root.addWidget(self.make_label("Texto de prueba"))
        root.addWidget(self.preview_text)
        root.addWidget(self.status_label)
        root.addWidget(self.preview_button)

        root.addStretch()

        actions = QHBoxLayout()
        actions.setSpacing(12)
        actions.addStretch()
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.save_button)

        root.addLayout(actions)

    @staticmethod
    def make_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("voiceFieldLabel")
        return label

    def load_voices(self, current_voice: str) -> None:
        selected = 0

        for index, voice in enumerate(self.voices):
            self.voice_combo.addItem(
                f"{voice.display_name} · {voice.gender}",
                voice.code,
            )

            if voice.code == current_voice:
                selected = index

        self.voice_combo.setCurrentIndex(selected)
        self.update_description()

    def connect_signals(self) -> None:
        self.voice_combo.currentIndexChanged.connect(
            self.update_description
        )
        self.speed_slider.valueChanged.connect(self.update_values)
        self.volume_slider.valueChanged.connect(self.update_values)
        self.preview_button.clicked.connect(self.preview_voice)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)

    def selected_voice_code(self) -> str:
        return str(self.voice_combo.currentData())

    def selected_voice(self) -> VoiceOption:
        return self.service.get_voice(self.selected_voice_code())

    def selected_speed(self) -> float:
        return self.speed_slider.value() / 100.0

    def selected_volume(self) -> float:
        return self.volume_slider.value() / 100.0

    def selected_settings(self) -> dict[str, object]:
        voice = self.selected_voice()

        return {
            "engine": "kokoro",
            "voice": voice.code,
            "display_name": voice.display_name,
            "language": voice.language,
            "gender": voice.gender,
            "style": voice.style,
            "speed": self.selected_speed(),
            "volume": self.selected_volume(),
        }

    def update_description(self) -> None:
        voice = self.selected_voice()
        self.description_label.setText(
            f"{voice.language} · {voice.style}"
        )

    def update_values(self) -> None:
        self.speed_value.setText(f"{self.selected_speed():.2f}x")
        self.volume_value.setText(
            f"{round(self.selected_volume() * 100)}%"
        )

    def preview_voice(self) -> None:
        text = self.preview_text.toPlainText().strip()

        if not text:
            QMessageBox.warning(
                self,
                "Texto vacío",
                "Escribe una frase para probar la voz.",
            )
            return

        if self.worker is not None and self.worker.isRunning():
            return

        self.set_busy(True)
        self.status_label.setText(
            "Generando y reproduciendo la vista previa..."
        )

        self.worker = VoicePreviewWorker(
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
        self.preview_button.setDisabled(busy)
        self.save_button.setDisabled(busy)
        self.cancel_button.setDisabled(busy)
        self.voice_combo.setDisabled(busy)
        self.speed_slider.setDisabled(busy)
        self.volume_slider.setDisabled(busy)
        self.preview_text.setDisabled(busy)

    def preview_ready(self, path: str) -> None:
        self.status_label.setText(
            f"Vista previa finalizada: {path}"
        )

    def preview_error(self, message: str) -> None:
        self.status_label.setText(message)
        QMessageBox.critical(
            self,
            "Error de Kokoro",
            message,
        )

    def preview_finished(self) -> None:
        self.set_busy(False)

        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None