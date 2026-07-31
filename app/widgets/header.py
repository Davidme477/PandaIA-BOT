from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class Header(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()

        self.main_window = main_window
        self.setObjectName("header")
        self.setFixedHeight(105)

        self.status_labels: dict[str, QLabel] = {}
        self.status_titles: dict[str, QLabel] = {}

        self.build_interface()

    def build_interface(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(28, 14, 26, 14)
        layout.setSpacing(12)

        layout.addWidget(self.create_brand())

        layout.addWidget(
            self.create_status_card(
                "bot",
                "Estado del BOT",
                "DESCONECTADO",
                "statusRed",
            )
        )

        layout.addWidget(
            self.create_status_card(
                "tiktok",
                "TikTok Live",
                "DESCONECTADO",
                "statusRed",
            )
        )

        layout.addWidget(
            self.create_status_card(
                "ollama",
                "Ollama (IA)",
                "NO VERIFICADO",
                "statusRed",
            )
        )

        layout.addWidget(
            self.create_status_card(
                "tts",
                "Kokoro TTS",
                "NO INSTALADO",
                "statusRed",
            )
        )

        layout.addStretch()

        layout.addWidget(self.create_action("•••", "Minimizar"))
        layout.addWidget(self.create_action("⚙", "Ajustes"))
        layout.addWidget(self.create_action("?", "Ayuda"))

        minimize_button = QPushButton("—")
        minimize_button.setObjectName("windowButton")
        minimize_button.setFixedSize(48, 48)
        minimize_button.clicked.connect(
            self.main_window.showMinimized
        )

        close_button = QPushButton("×")
        close_button.setObjectName("closeButton")
        close_button.setFixedSize(48, 48)
        close_button.clicked.connect(self.main_window.close)

        layout.addWidget(minimize_button)
        layout.addWidget(close_button)

    def create_brand(self) -> QWidget:
        brand = QWidget()

        layout = QHBoxLayout(brand)
        layout.setContentsMargins(0, 0, 20, 0)
        layout.setSpacing(12)

        logo = QLabel("🐼")
        logo.setObjectName("logo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(70, 70)

        text_container = QWidget()

        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 6, 0, 6)
        text_layout.setSpacing(2)

        title = QLabel(
            '<span style="color:#a855f7;">PandaIA</span> '
            '<span style="color:#ffffff;">BOT</span>'
        )
        title.setObjectName("brandTitle")

        subtitle = QLabel(
            "Tu asistente IA para TikTok Live"
        )
        subtitle.setObjectName("brandSubtitle")

        text_layout.addWidget(title)
        text_layout.addWidget(subtitle)

        layout.addWidget(logo)
        layout.addWidget(text_container)

        return brand

    def create_status_card(
        self,
        key: str,
        title_text: str,
        status_text: str,
        object_name: str,
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("headerStatusCard")
        card.setFixedSize(145, 70)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(5)

        title = QLabel(title_text)
        title.setObjectName("statusCardTitle")

        status = QLabel(status_text)
        status.setObjectName(object_name)

        self.status_labels[key] = status
        self.status_titles[key] = title

        layout.addWidget(title)
        layout.addWidget(status)

        return card

    def create_action(
        self,
        icon: str,
        text: str,
    ) -> QWidget:
        container = QWidget()
        container.setFixedSize(74, 72)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        button = QPushButton(icon)
        button.setObjectName("headerIconButton")
        button.setFixedSize(38, 38)

        label = QLabel(text)
        label.setObjectName("headerButtonText")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(button)
        layout.addWidget(label)

        return container

    def set_bot_status(
        self,
        text: str,
        object_name: str,
    ) -> None:
        self.set_status(
            "bot",
            text,
            object_name,
        )

    def set_tiktok_status(
        self,
        text: str,
        object_name: str,
    ) -> None:
        self.set_status(
            "tiktok",
            text,
            object_name,
        )

    def set_ollama_status(
        self,
        text: str,
        object_name: str,
    ) -> None:
        self.set_status(
            "ollama",
            text,
            object_name,
        )

    def set_tts_status(
        self,
        text: str,
        object_name: str,
        engine_name: str,
    ) -> None:
        self.status_titles["tts"].setText(f"{engine_name} TTS")
        self.set_status(
            "tts",
            text,
            object_name,
        )

    def set_status(
        self,
        key: str,
        text: str,
        object_name: str,
    ) -> None:
        label = self.status_labels[key]

        label.setText(text)
        label.setObjectName(object_name)

        label.style().unpolish(label)
        label.style().polish(label)
        label.update()
