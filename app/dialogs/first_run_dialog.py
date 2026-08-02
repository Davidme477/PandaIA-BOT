from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from core.first_run import collect_first_run_diagnostics, complete_first_run


class FirstRunDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Primer inicio de PandaIA")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        title = QLabel("PandaIA está lista para configurarse")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        report = collect_first_run_diagnostics()
        statuses = (
            ("Carpetas y permisos", report["writable"]),
            ("Ollama y modelos", report["ollama"]),
            ("Windows SAPI", report["windows_sapi"]),
            ("Kokoro", report["kokoro"]),
            ("Puerto local del overlay", report["overlay_port"]),
        )
        for name, ok in statuses:
            label = QLabel(f"{'✓' if ok else '•'} {name}: {'disponible' if ok else 'opcional o pendiente'}")
            label.setWordWrap(True)
            layout.addWidget(label)
        models = report.get("ollama_models") or []
        model_text = ", ".join(models) if models else "ninguno detectado; sugerido: qwen3:4b"
        model_label = QLabel(f"Modelos de Ollama: {model_text}")
        model_label.setWordWrap(True)
        layout.addWidget(model_label)
        note = QLabel("Spotify, Telegram, Cloudflare y Ollama pueden configurarse después. Omitirlos no impide abrir PandaIA.")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Entrar a PandaIA")
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def accept(self) -> None:
        complete_first_run()
        super().accept()
