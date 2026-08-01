from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from app.widgets.responsive_grid import layout_mode


class Header(QWidget):
    """Encabezado adaptable; los controles de ventana pertenecen a Windows."""

    def __init__(self, _main_window=None) -> None:
        super().__init__()
        self.setObjectName("header")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.status_labels: dict[str, QLabel] = {}
        self.status_titles: dict[str, QLabel] = {}
        self.status_cards: list[QFrame] = []
        self.current_mode = ""
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(16, 10, 16, 10)
        self.grid.setSpacing(8)
        self.brand = self.create_brand()
        self.actions = QWidget(); actions = QHBoxLayout(self.actions); actions.setContentsMargins(0, 0, 0, 0)
        actions.addWidget(self.create_action("⚙", "Ajustes")); actions.addWidget(self.create_action("?", "Ayuda"))
        for values in (("bot", "Estado del BOT", "DESCONECTADO"), ("tiktok", "TikTok Live", "DESCONECTADO"),
                       ("ollama", "Ollama (IA)", "NO VERIFICADO"), ("tts", "Kokoro TTS", "NO INSTALADO")):
            self.status_cards.append(self.create_status_card(*values))
        self.set_available_width(1600)

    def set_available_width(self, width: int) -> None:
        mode = layout_mode(width)
        if mode == self.current_mode:
            return
        self.current_mode = mode
        while self.grid.count():
            self.grid.takeAt(0)
        for column in range(6): self.grid.setColumnStretch(column, 0)
        compact = mode == "narrow"
        self.brand.setProperty("compact", compact)
        if mode == "wide":
            self.grid.addWidget(self.brand, 0, 0)
            for index, card in enumerate(self.status_cards, 1): self.grid.addWidget(card, 0, index)
            self.grid.addWidget(self.actions, 0, 5)
            self.grid.setColumnStretch(0, 2)
        else:
            self.grid.addWidget(self.brand, 0, 0, 1, 2 if compact else 3)
            self.grid.addWidget(self.actions, 0, 2 if compact else 3, 1, 1)
            columns = 2 if compact else 4
            for column in range(columns): self.grid.setColumnStretch(column, 1)
            for index, card in enumerate(self.status_cards):
                self.grid.addWidget(card, 1 + index // columns, index % columns)
        for card in self.status_cards:
            card.setProperty("compact", compact); card.setToolTip(
                f"{self.status_titles[next(key for key, value in self.status_labels.items() if value.parent() is card)].text()}"
            )
        self.updateGeometry()

    def create_brand(self) -> QWidget:
        brand = QWidget(); brand.setObjectName("headerBrand")
        layout = QHBoxLayout(brand); layout.setContentsMargins(0, 0, 8, 0); layout.setSpacing(8)
        logo = QLabel("🐼"); logo.setObjectName("logo"); logo.setAlignment(Qt.AlignmentFlag.AlignCenter); logo.setFixedSize(58, 58)
        text = QWidget(); text_layout = QVBoxLayout(text); text_layout.setContentsMargins(0, 4, 0, 4); text_layout.setSpacing(2)
        title = QLabel('<span style="color:#a855f7;">PandaIA</span> <span style="color:#ffffff;">BOT</span>'); title.setObjectName("brandTitle")
        subtitle = QLabel("Tu asistente IA para TikTok Live"); subtitle.setObjectName("brandSubtitle"); subtitle.setWordWrap(True)
        text_layout.addWidget(title); text_layout.addWidget(subtitle); layout.addWidget(logo); layout.addWidget(text)
        return brand

    def create_status_card(self, key: str, title_text: str, status_text: str) -> QFrame:
        card = QFrame(); card.setObjectName("headerStatusCard"); card.setMinimumWidth(142)
        layout = QVBoxLayout(card); layout.setContentsMargins(12, 8, 12, 8); layout.setSpacing(3)
        title = QLabel(title_text); title.setObjectName("statusCardTitle")
        status = QLabel(status_text); status.setObjectName("statusRed"); status.setMinimumWidth(118)
        title.setToolTip(title_text); status.setToolTip(status_text)
        self.status_titles[key] = title; self.status_labels[key] = status
        layout.addWidget(title); layout.addWidget(status); return card

    def create_action(self, icon: str, text: str) -> QWidget:
        container = QWidget(); layout = QVBoxLayout(container); layout.setContentsMargins(2, 0, 2, 0); layout.setSpacing(1)
        button = QPushButton(icon); button.setObjectName("headerIconButton"); button.setFixedSize(34, 34); button.setToolTip(text)
        label = QLabel(text); label.setObjectName("headerButtonText"); label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignCenter); layout.addWidget(label); return container

    def set_bot_status(self, text: str, object_name: str) -> None: self.set_status("bot", text, object_name)
    def set_tiktok_status(self, text: str, object_name: str) -> None: self.set_status("tiktok", text, object_name)
    def set_ollama_status(self, text: str, object_name: str) -> None: self.set_status("ollama", text, object_name)

    def set_tts_status(self, text: str, object_name: str, engine_name: str) -> None:
        self.status_titles["tts"].setText(f"{engine_name} TTS"); self.set_status("tts", text, object_name)

    def set_status(self, key: str, text: str, object_name: str) -> None:
        label = self.status_labels[key]; label.setText(text); label.setToolTip(text); label.setObjectName(object_name)
        label.style().unpolish(label); label.style().polish(label); label.update()
