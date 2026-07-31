from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)

from services.ollama.ollama_service import OllamaService
from services.ollama.personalities import build_system_prompt, generate_personality_preview


class PersonalityPreviewWorker(QThread):
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, *, model: str, message: str, settings: dict[str, object]) -> None:
        super().__init__()
        self.model = model
        self.message = message
        self.settings = dict(settings)

    def run(self) -> None:
        try:
            answer = generate_personality_preview(
                OllamaService(timeout=30.0),
                model=self.model,
                message=self.message,
                settings=self.settings,
            )
            if not answer:
                raise RuntimeError("Ollama no generó ninguna respuesta.")
            self.succeeded.emit(answer)
        except Exception as error:
            self.failed.emit(str(error))


class PersonalityDialog(QDialog):
    def __init__(
        self,
        *,
        model: str,
        language: str,
        custom_name: str,
        custom_prompt: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.model = model
        self.language = language
        self.worker: PersonalityPreviewWorker | None = None
        self.setObjectName("voiceDialog")
        self.setWindowTitle("Editar personalidad")
        self.setModal(True)
        self.setMinimumSize(680, 720)

        self.name_edit = QLineEdit(custom_name)
        self.name_edit.setObjectName("voiceCombo")
        self.instructions_edit = QTextEdit()
        self.instructions_edit.setObjectName("voicePreviewText")
        self.instructions_edit.setPlainText(custom_prompt)
        self.instructions_edit.setMinimumHeight(120)
        self.preview_prompt = QTextEdit()
        self.preview_prompt.setObjectName("voicePreviewText")
        self.preview_prompt.setReadOnly(True)
        self.preview_prompt.setMinimumHeight(120)
        self.test_message = QLineEdit("Hola PandaIA, ¿cómo estás?")
        self.test_message.setObjectName("voiceCombo")
        self.answer_area = QTextEdit()
        self.answer_area.setObjectName("voicePreviewText")
        self.answer_area.setReadOnly(True)
        self.answer_area.setMinimumHeight(90)
        self.status_label = QLabel("Lista para probar la personalidad.")
        self.status_label.setObjectName("voiceStatus")
        self.test_button = QPushButton("Probar personalidad")
        self.test_button.setObjectName("voicePreviewButton")
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setObjectName("voiceSecondaryButton")
        self.save_button = QPushButton("Guardar personalidad")
        self.save_button.setObjectName("voiceSaveButton")

        self._build_ui()
        self._connect_signals()
        self.update_prompt_preview()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(12)
        title = QLabel("Personalidad personalizada")
        title.setObjectName("voiceDialogTitle")
        subtitle = QLabel("Define cómo debe expresarse PandaIA y pruébala sin reproducir voz.")
        subtitle.setObjectName("voiceDialogSubtitle")
        separator = QFrame()
        separator.setObjectName("voiceDialogSeparator")
        separator.setFixedHeight(1)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(separator)
        for label_text, widget in (
            ("Nombre visible", self.name_edit),
            ("Instrucciones", self.instructions_edit),
            ("Vista previa del system prompt", self.preview_prompt),
            ("Mensaje de prueba", self.test_message),
        ):
            layout.addWidget(QLabel(label_text))
            layout.addWidget(widget)
        layout.addWidget(self.test_button)
        layout.addWidget(self.status_label)
        layout.addWidget(QLabel("Respuesta de Ollama"))
        layout.addWidget(self.answer_area)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)

    def _connect_signals(self) -> None:
        self.name_edit.textChanged.connect(self.update_prompt_preview)
        self.instructions_edit.textChanged.connect(self.update_prompt_preview)
        self.test_button.clicked.connect(self.test_personality)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.validate_and_accept)

    def settings(self) -> dict[str, object]:
        return {
            "personality": "Personalizada",
            "language": self.language,
            "custom_personality_name": self.name_edit.text().strip(),
            "custom_personality_prompt": self.instructions_edit.toPlainText().strip(),
        }

    def update_prompt_preview(self) -> None:
        self.preview_prompt.setPlainText(build_system_prompt(self.settings()))

    def test_personality(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        if not self.model.strip():
            self.status_label.setText("Selecciona un modelo de Ollama disponible.")
            return
        message = self.test_message.text().strip()
        if not message:
            self.status_label.setText("Escribe un mensaje de prueba.")
            return
        if not self._valid_custom_fields():
            return
        self.set_busy(True)
        self.status_label.setText("Generando respuesta…")
        self.answer_area.clear()
        self.worker = PersonalityPreviewWorker(
            model=self.model, message=message, settings=self.settings()
        )
        self.worker.succeeded.connect(self.preview_succeeded)
        self.worker.failed.connect(self.preview_failed)
        self.worker.finished.connect(self.preview_finished)
        self.worker.start()

    def preview_succeeded(self, answer: str) -> None:
        self.answer_area.setPlainText(answer)
        self.status_label.setText("Prueba completada.")

    def preview_failed(self, message: str) -> None:
        self.status_label.setText(f"No se pudo probar: {message}")

    def preview_finished(self) -> None:
        self.set_busy(False)
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None

    def validate_and_accept(self) -> None:
        if self._valid_custom_fields():
            self.accept()

    def _valid_custom_fields(self) -> bool:
        if not self.name_edit.text().strip():
            self.status_label.setText("El nombre de la personalidad es obligatorio.")
            return False
        if not self.instructions_edit.toPlainText().strip():
            self.status_label.setText("Las instrucciones son obligatorias.")
            return False
        return True

    def set_busy(self, busy: bool) -> None:
        for widget in (
            self.name_edit, self.instructions_edit, self.test_message,
            self.test_button, self.cancel_button, self.save_button,
        ):
            widget.setDisabled(busy)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.status_label.setText("Espera a que termine la prueba en curso.")
            event.ignore()
            return
        event.accept()
