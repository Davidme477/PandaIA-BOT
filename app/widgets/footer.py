from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QWidget,
)


class Footer(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.setObjectName("bottomBar")
        self.setFixedHeight(55)

        self.build_interface()

    def build_interface(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(28, 0, 28, 0)
        layout.setSpacing(22)

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

    def create_separator(self) -> QFrame:
        separator = QFrame()
        separator.setObjectName("bottomSeparator")
        separator.setFixedSize(1, 24)

        return separator