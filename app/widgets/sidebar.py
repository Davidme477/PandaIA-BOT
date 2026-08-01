from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class Sidebar(QWidget):
    page_selected = Signal(int)

    def __init__(self) -> None:
        super().__init__()

        self.setObjectName("sidebar")
        self.setMinimumWidth(190)
        self.setMaximumWidth(245)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        self.buttons: list[QPushButton] = []
        self.menu_items: list[tuple[str, str]] = []
        self.compact = False

        self.build_interface()

    def build_interface(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)

        self.menu_items = [
            ("⌂", "Panel Principal"),
            ("◉", "Conexión TikTok"),
            ("✿", "IA & Personalidad"),
            ("◖", "Voces (TTS)"),
            ("▣", "Memoria"),
            ("☷", "Comandos"),
            ("♢", "Regalos & Animaciones"),
            ("⚙", "Configuración"),
            ("▤", "Registros (Logs)"),
        ]

        for index, (icon, text) in enumerate(self.menu_items):
            button = QPushButton(f"{icon}    {text}")
            button.setObjectName("sidebarButton")
            button.setCheckable(True)
            button.setMinimumHeight(46)
            button.setCursor(Qt.CursorShape.PointingHandCursor)

            button.clicked.connect(
                lambda checked, current=index:
                self.select_page(current)
            )

            if index == 0:
                button.setChecked(True)

            self.buttons.append(button)
            layout.addWidget(button)

        layout.addStretch()
        self.profile = self.create_profile()
        layout.addWidget(self.profile)

    def set_compact(self, compact: bool) -> None:
        if compact == self.compact:
            return
        self.compact = compact
        self.setProperty("compact", compact)
        self.setMinimumWidth(64 if compact else 190)
        self.setMaximumWidth(76 if compact else 245)
        for button, (icon, text) in zip(self.buttons, self.menu_items):
            button.setText(icon if compact else f"{icon}    {text}")
            button.setToolTip(text)
        self.profile.setVisible(not compact)
        self.style().unpolish(self); self.style().polish(self)

    def select_page(self, page_index: int) -> None:
        for index, button in enumerate(self.buttons):
            button.setChecked(index == page_index)

        self.page_selected.emit(page_index)

    def create_profile(self) -> QFrame:
        card = QFrame()
        card.setObjectName("profileCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 18, 12, 18)
        layout.setSpacing(8)

        panda = QLabel("🐼")
        panda.setObjectName("profilePanda")
        panda.setAlignment(Qt.AlignmentFlag.AlignCenter)

        name = QLabel(
            '<span style="color:#ffffff;">Panda</span>'
            '<span style="color:#a855f7;">IA</span>'
        )
        name.setObjectName("profileName")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setWordWrap(True)

        version = QLabel("Versión 1.0.0")
        version.setObjectName("profileVersion")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setWordWrap(True)

        layout.addWidget(panda)
        layout.addWidget(name)
        layout.addWidget(version)

        return card
