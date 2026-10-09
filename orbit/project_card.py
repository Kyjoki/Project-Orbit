from PySide6.QtCore import QSize, Signal, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QToolButton, QVBoxLayout

from . import icons
from .models import Project


TYPE_ICONS = {
    "Веб-сайт": "globe", "API": "server", "Бот": "bot",
    "Расширение": "box", "Приложение": "layout", "Другое": "folder",
}
STATUS_LABELS = {"running": "Работает", "stopped": "Остановлен", "error": "Ошибка"}


class ProjectCard(QFrame):
    open_requested = Signal(int)
    toggle_requested = Signal(int)
    edit_requested = Signal(int)
    delete_requested = Signal(int)

    def __init__(self, project: Project, status: str,
                 health: list[tuple[str, str, str]] | None = None, parent=None):
        super().__init__(parent)
        health = health or []
        self.project_id = project.id
        self.setObjectName("projectCard")
        self.setMinimumWidth(285)
        self.setFixedHeight(225)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        top = QHBoxLayout()
        icon = QLabel()
        icon.setObjectName("iconTile")
        icon.setFixedSize(38, 38)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(icons.pixmap(TYPE_ICONS.get(project.kind, "folder"), "#8B7CFF", 21))
        top.addWidget(icon)
        title_column = QVBoxLayout()
        name = QLabel(project.name)
        name.setObjectName("cardTitle")
        name.setToolTip(project.name)
        kind = QLabel(project.kind)
        kind.setObjectName("muted")
        title_column.addWidget(name)
        title_column.addWidget(kind)
        top.addLayout(title_column, 1)
        layout.addLayout(top)
        description = QLabel(project.description or "Описание не указано")
        description.setObjectName("muted")
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignTop)
        description.setFixedHeight(34)
        layout.addWidget(description)
        badge = QLabel("●  " + STATUS_LABELS.get(status, "Остановлен"))
        badge.setObjectName("statusBadge")
        badge.setProperty("state", status)
        badge.setFixedWidth(112)
        layout.addWidget(badge)
        labels = {"online": "доступен", "offline": "недоступен", "checking": "проверка"}
        health_text = "   ·   ".join(f"{name}: {labels.get(state, 'проверка')}" for name, state, _ in health)
        health_label = QLabel(health_text)
        health_label.setObjectName("smallCaption")
        health_label.setWordWrap(True)
        health_label.setFixedHeight(27)
        health_label.setToolTip("\n".join(url for _, _, url in health))
        layout.addWidget(health_label)
        actions = QHBoxLayout()
        run = QPushButton("Остановить" if status == "running" else "Запустить")
        run.setObjectName("danger" if status == "running" else "primary")
        run.setIcon(icons.icon("stop" if status == "running" else "play", "#FFFFFF", 15))
        run.setEnabled(bool(project.commands))
        run.clicked.connect(lambda: self.toggle_requested.emit(self.project_id))
        open_button = QPushButton("Открыть")
        open_button.setIcon(icons.icon("external", "#E7E9EF", 15))
        open_button.clicked.connect(lambda: self.open_requested.emit(self.project_id))
        more = QToolButton()
        more.setObjectName("moreButton")
        more.setIcon(icons.icon("more", "#98A0B0", 17))
        more.setIconSize(QSize(17, 17))
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(more)
        menu.addAction("Редактировать", lambda: self.edit_requested.emit(self.project_id))
        menu.addAction("Логи", lambda: self.open_requested.emit(self.project_id))
        menu.addSeparator()
        menu.addAction("Удалить…", lambda: self.delete_requested.emit(self.project_id))
        more.setMenu(menu)
        actions.addWidget(run)
        actions.addWidget(open_button)
        actions.addStretch()
        actions.addWidget(more)
        layout.addLayout(actions)
