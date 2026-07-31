from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QSizePolicy, QWidget


WIDE_BREAKPOINT = 1180
MEDIUM_BREAKPOINT = 720


def columns_for_width(
    width: int,
    *,
    wide_columns: int,
    medium_columns: int = 2,
    narrow_columns: int = 1,
) -> int:
    if width >= WIDE_BREAKPOINT:
        return wide_columns
    if width >= MEDIUM_BREAKPOINT:
        return min(wide_columns, medium_columns)
    return min(wide_columns, narrow_columns)


class ResponsiveGrid(QWidget):
    """Reubica los mismos widgets al cambiar el ancho, sin duplicarlos."""

    def __init__(
        self,
        *,
        wide_columns: int,
        medium_columns: int = 2,
        narrow_columns: int = 1,
        spacing: int = 16,
    ) -> None:
        super().__init__()
        self.wide_columns = wide_columns
        self.medium_columns = medium_columns
        self.narrow_columns = narrow_columns
        self.widgets: list[QWidget] = []
        self.current_columns = 0
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(spacing)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def add_responsive_widget(self, widget: QWidget) -> None:
        if widget not in self.widgets:
            self.widgets.append(widget)
        self.reflow(force=True)

    def reflow(self, *, force: bool = False) -> None:
        columns = columns_for_width(
            self.width(),
            wide_columns=self.wide_columns,
            medium_columns=self.medium_columns,
            narrow_columns=self.narrow_columns,
        )
        if not force and columns == self.current_columns:
            return
        self.current_columns = columns
        for index, widget in enumerate(self.widgets):
            self.grid.addWidget(widget, index // columns, index % columns)
        for column in range(self.wide_columns):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.reflow()
