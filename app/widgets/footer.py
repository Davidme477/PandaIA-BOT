from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QLabel, QSizePolicy, QWidget

from app.widgets.responsive_grid import layout_mode


class Footer(QWidget):
    def __init__(self) -> None:
        super().__init__(); self.setObjectName("bottomBar")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.grid = QGridLayout(self); self.grid.setContentsMargins(12, 8, 12, 8); self.grid.setSpacing(8)
        self.labels = [
            QLabel("⚙  CPU: 18%"), QLabel("▦  RAM: 2.1 GB / 8 GB"),
            QLabel("◉  Internet: <span style='color:#22c55e;'>Estable</span>"),
            QLabel("●  Guardado automático: <span style='color:#22c55e;'>Activado</span>"),
            QLabel("◷  Hora: 20:45:30"),
        ]
        self.current_mode = ""; self.set_available_width(1600)

    def set_available_width(self, width: int) -> None:
        mode = layout_mode(width)
        if mode == self.current_mode: return
        self.current_mode = mode
        while self.grid.count(): self.grid.takeAt(0)
        columns = 5 if mode == "wide" else 3 if mode == "medium" else 2
        for index, label in enumerate(self.labels):
            label.setToolTip(label.text()); self.grid.addWidget(label, index // columns, index % columns)
        for column in range(columns): self.grid.setColumnStretch(column, 1)
        self.updateGeometry()
