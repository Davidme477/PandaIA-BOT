from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QWidget,
)


class Footer(QScrollArea):
    def __init__(self) -> None:
        super().__init__()

        self.setObjectName("bottomBar")
        self.setWidgetResizable(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(55)
        self.setMaximumHeight(72)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.build_interface()

    def build_interface(self) -> None:
        content = QWidget()
        content.setObjectName("footerContent")
        layout = QHBoxLayout(content)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)

        layout.addWidget(QLabel("⚙  CPU: 18%"))
        layout.addWidget(self.create_separator())
        layout.addWidget(QLabel("▦  RAM: 2.1 GB / 8 GB"))
        layout.addWidget(self.create_separator())

        internet = QLabel(
            "◉  Internet: "
            "<span style='color:#22c55e;'>Estable</span>"
        )
        layout.addWidget(internet)

        layout.addStretch()

        automatic_save = QLabel(
            "●  Guardado automático: "
            "<span style='color:#22c55e;'>Activado</span>"
        )
        layout.addWidget(automatic_save)

        layout.addWidget(self.create_separator())
        layout.addWidget(QLabel("◷  Hora: 20:45:30"))
        self.setWidget(content)

    def create_separator(self) -> QFrame:
        separator = QFrame()
        separator.setObjectName("bottomSeparator")
        separator.setFixedSize(1, 24)

        return separator
