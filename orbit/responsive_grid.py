from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QWidget


class ResponsiveGrid(QWidget):
    def __init__(self, min_width: int = 310, spacing: int = 14, parent=None):
        super().__init__(parent)
        self.min_width = min_width
        self.spacing = spacing
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(spacing)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.items: list[QWidget] = []
        self.columns = 0

    def set_items(self, items: list[QWidget]) -> None:
        for widget in self.items:
            self.grid.removeWidget(widget)
            widget.hide()
            widget.deleteLater()
        self.items = items
        self._layout_items()

    def _layout_items(self) -> None:
        while self.grid.count():
            self.grid.takeAt(0)
        columns = max(1, min(4, (max(self.width(), self.min_width) + self.spacing) //
                             (self.min_width + self.spacing)))
        for column in range(4):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)
        for index, widget in enumerate(self.items):
            self.grid.addWidget(widget, index // columns, index % columns)
        self.columns = columns

    def resizeEvent(self, event):
        super().resizeEvent(event)
        columns = max(1, min(4, (self.width() + self.spacing) //
                             (self.min_width + self.spacing)))
        if columns != self.columns:
            self._layout_items()
