"""Main window: overview, searchable project cards, details, and live logs."""

import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QStackedWidget,
    QToolButton, QVBoxLayout, QWidget,
)

from . import icons
from .github import GithubRepository, suggest_commands
from .github_dialog import GithubDialog
from .git_update_dialog import GitUpdateDialog
from .models import PROJECT_KINDS, Project
from .processes import ProcessManager
from .project_card import ProjectCard
from .project_dialog import ProjectDialog
from .project_filters import filter_projects
from .responsive_grid import ResponsiveGrid
from .storage import ProjectStore


NAVIGATION = (("overview", "Обзор", "layout"), ("projects", "Проекты", "folder"),
              ("logs", "Логи", "file-text"), ("settings", "Настройки", "sliders"))


def make_label(text: str, object_name: str = "") -> QLabel:
    result = QLabel(text)
    if object_name:
        result.setObjectName(object_name)
    return result


class MainWindow(QMainWindow):
    def __init__(self, store: ProjectStore):
        super().__init__()
        self.store = store
        self.processes = ProcessManager()
        self.logs: dict[int, str] = {}
        self.exit_codes: dict[int, int] = {}
        self.user_stopped_ids: set[int] = set()
        self.detail_project_id: int | None = None
        self.detail_command_id: int | None = None
        self.log_command_id: int | None = None
        self.command_controls: dict[int, tuple[QLabel, QPushButton, QPushButton]] = {}
        self.setWindowTitle("Project Orbit")
        self.setWindowIcon(QIcon(icons.logo_pixmap(48)))
        self.resize(1280, 800)
        self.setMinimumSize(900, 600)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._build_sidebar(layout)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.pages = {
            "overview": self._build_overview_page(),
            "projects": self._build_projects_page(),
            "logs": self._build_logs_page(),
            "settings": self._build_settings_page(),
            "detail": self._build_detail_page(),
        }
        for page in self.pages.values():
            self.stack.addWidget(page)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.add_project)
        for index, (key, _, _) in enumerate(NAVIGATION, start=1):
            QShortcut(QKeySequence(f"Ctrl+{index}"), self,
                      activated=lambda page=key: self.show_page(page))
        self._refresh_all()
        self.show_page("projects")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.process_events)
        self.timer.start(50)

    def _build_sidebar(self, root_layout: QHBoxLayout) -> None:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(84)
        column = QVBoxLayout(sidebar)
        column.setContentsMargins(8, 16, 8, 12)
        column.setSpacing(7)
        logo = QLabel()
        logo.setPixmap(icons.logo_pixmap(34))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setToolTip("Project Orbit")
        column.addWidget(logo)
        column.addSpacing(16)
        self.nav_buttons: dict[str, QToolButton] = {}
        for key, title, icon_name in NAVIGATION:
            button = QToolButton()
            button.setObjectName("nav")
            button.setText(title)
            button.setIcon(icons.icon(icon_name, "#98A0B0", 22, on="#FFFFFF"))
            button.setIconSize(QSize(22, 22))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setCheckable(True)
            button.setFixedWidth(68)
            button.setFixedHeight(62)
            button.clicked.connect(lambda _, page=key: self.show_page(page))
            self.nav_buttons[key] = button
            column.addWidget(button)
        column.addStretch()
        root_layout.addWidget(sidebar)

    def _page(self, title: str, subtitle: str, action: QPushButton | None = None):
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(28, 23, 28, 24)
        column.setSpacing(17)
        header = QHBoxLayout()
        texts = QVBoxLayout()
        texts.setSpacing(1)
        texts.addWidget(make_label(title, "title"))
        texts.addWidget(make_label(subtitle, "muted"))
        header.addLayout(texts)
        header.addStretch()
        if action:
            header.addWidget(action)
        column.addLayout(header)
        return page, column

    def _scroll_content(self, column: QVBoxLayout):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        content = QVBoxLayout(host)
        content.setContentsMargins(0, 0, 5, 12)
        content.setSpacing(16)
        scroll.setWidget(host)
        column.addWidget(scroll, 1)
        return content

    def _make_add_button(self) -> QPushButton:
        button = QPushButton("+ Добавить проект")
        button.setObjectName("primary")
        button.clicked.connect(self.add_project)
        return button

    def _project_actions(self) -> QWidget:
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        github = QPushButton("Из GitHub")
        github.clicked.connect(self.import_from_github)
        row.addWidget(github)
        row.addWidget(self._make_add_button())
        return host

    def _build_projects_page(self) -> QWidget:
        page, column = self._page("Проекты", "Все ваши проекты в одном месте", self._project_actions())
        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по названию, описанию, папке")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icons.icon("search", "#768093", 16), QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(self._refresh_project_cards)
        self.type_filter = QComboBox()
        self.type_filter.addItem("Все типы", None)
        for kind in PROJECT_KINDS:
            self.type_filter.addItem(kind, kind)
        self.type_filter.currentIndexChanged.connect(self._refresh_project_cards)
        self.state_filter = QComboBox()
        for label, value in (("Все состояния", None), ("Работает", "running"),
                             ("Остановлен", "stopped"), ("Ошибка", "error")):
            self.state_filter.addItem(label, value)
        self.state_filter.currentIndexChanged.connect(self._refresh_project_cards)
        self.result_count = make_label("", "smallCaption")
        filters.addWidget(self.search, 1)
        filters.addWidget(self.type_filter)
        filters.addWidget(self.state_filter)
        filters.addWidget(self.result_count)
        column.addLayout(filters)
        content = self._scroll_content(column)
        self.project_grid = ResponsiveGrid()
        content.addWidget(self.project_grid)
        self.project_empty = make_label("Пока нет проектов. Нажмите «Добавить проект», чтобы начать.", "muted")
        self.project_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.project_empty.setMinimumHeight(190)
        content.addWidget(self.project_empty)
        content.addStretch()
        return page

    def _build_overview_page(self) -> QWidget:
        page, column = self._page("Обзор", "Ваши проекты и процессы", self._make_add_button())
        stats = QHBoxLayout()
        self.stat_projects = self._stat_card("Проектов", stats)
        self.stat_running = self._stat_card("Запущено процессов", stats)
        self.stat_errors = self._stat_card("Ошибок", stats)
        column.addLayout(stats)
        column.addWidget(make_label("Проекты", "sectionTitle"))
        content = self._scroll_content(column)
        self.overview_grid = ResponsiveGrid()
        content.addWidget(self.overview_grid)
        self.overview_empty = make_label("Добавьте первый проект, чтобы увидеть его здесь.", "muted")
        self.overview_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.overview_empty.setMinimumHeight(180)
        content.addWidget(self.overview_empty)
        content.addStretch()
        return page

    def _stat_card(self, title: str, row: QHBoxLayout) -> QLabel:
        card = QFrame()
        card.setObjectName("statCard")
        content = QVBoxLayout(card)
        value = make_label("0", "title")
        content.addWidget(value)
        content.addWidget(make_label(title, "muted"))
        row.addWidget(card, 1)
        return value

    def _build_logs_page(self) -> QWidget:
        page, column = self._page("Логи", "Вывод команд в текущем сеансе")
        self.log_selector = QComboBox()
        self.log_selector.currentIndexChanged.connect(self._choose_global_log)
        column.addWidget(self.log_selector)
        self.global_log = QPlainTextEdit()
        self.global_log.setReadOnly(True)
        self.global_log.setMaximumBlockCount(2000)
        column.addWidget(self.global_log, 1)
        return page

    def _build_settings_page(self) -> QWidget:
        page, column = self._page("Настройки", "Хранение данных и поведение приложения")
        section = QFrame()
        section.setObjectName("detailSection")
        body = QVBoxLayout(section)
        body.addWidget(make_label("Данные", "sectionTitle"))
        path = make_label(str(self.store.path), "muted")
        path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.addWidget(path)
        body.addWidget(make_label("Команды запускаются только по нажатию. При выходе активные процессы останавливаются.", "muted"))
        column.addWidget(section)
        future = QFrame()
        future.setObjectName("detailSection")
        future_body = QVBoxLayout(future)
        future_body.addWidget(make_label("Планируется", "sectionTitle"))
        future_body.addWidget(make_label("Мониторинг сайтов и ИИ-анализ ошибок будут добавлены в следующих версиях.", "muted"))
        column.addWidget(future)
        github_section = QFrame()
        github_section.setObjectName("detailSection")
        github_body = QVBoxLayout(github_section)
        github_body.addWidget(make_label("GitHub", "sectionTitle"))
        github_body.addWidget(make_label("Публичные репозитории доступны по имени пользователя. Для приватных нужен вход через GitHub CLI.", "muted"))
        github_button = QPushButton("Открыть импорт")
        github_button.clicked.connect(self.import_from_github)
        github_body.addWidget(github_button, 0, Qt.AlignmentFlag.AlignLeft)
        column.addWidget(github_section)
        update_section = QFrame()
        update_section.setObjectName("detailSection")
        update_body = QVBoxLayout(update_section)
        update_body.addWidget(make_label("Обновление Orbit", "sectionTitle"))
        update_body.addWidget(make_label("После публикации кода на GitHub закройте приложение и выполните .\\update.bat в папке Orbit.", "muted"))
        column.addWidget(update_section)
        column.addStretch()
        return page

    def _build_detail_page(self) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(28, 23, 28, 24)
        column.setSpacing(14)
        back = QPushButton("← Проекты")
        back.clicked.connect(lambda: self.show_page("projects"))
        column.addWidget(back, 0, Qt.AlignmentFlag.AlignLeft)
        heading = QHBoxLayout()
        texts = QVBoxLayout()
        self.detail_title = make_label("", "title")
        self.detail_description = make_label("", "muted")
        self.detail_description.setWordWrap(True)
        texts.addWidget(self.detail_title)
        texts.addWidget(self.detail_description)
        heading.addLayout(texts, 1)
        edit = QPushButton("Изменить")
        edit.clicked.connect(lambda: self.edit_project(self.detail_project_id))
        delete = QPushButton("Удалить")
        delete.clicked.connect(lambda: self.delete_project(self.detail_project_id))
        heading.addWidget(edit)
        heading.addWidget(delete)
        column.addLayout(heading)
        links = QHBoxLayout()
        self.folder_button = self._detail_button("Папка", self.open_folder)
        self.editor_button = self._detail_button("Редактор", self.open_editor)
        self.repo_button = self._detail_button("Репозиторий", lambda: self.open_link("repository_url"))
        self.update_button = self._detail_button("Обновить код", self.update_project)
        self.site_button = self._detail_button("Сайт", lambda: self.open_link("site_url"))
        for button in (self.folder_button, self.editor_button, self.repo_button,
                       self.update_button, self.site_button):
            links.addWidget(button)
        links.addStretch()
        column.addLayout(links)
        self.extra_links_host = QWidget()
        self.extra_links_layout = QHBoxLayout(self.extra_links_host)
        self.extra_links_layout.setContentsMargins(0, 0, 0, 0)
        column.addWidget(self.extra_links_host)
        column.addWidget(make_label("Команды", "sectionTitle"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(160)
        host = QWidget()
        self.command_layout = QVBoxLayout(host)
        self.command_layout.setContentsMargins(0, 0, 5, 0)
        self.command_layout.addStretch()
        scroll.setWidget(host)
        column.addWidget(scroll, 2)
        self.detail_log_title = make_label("Логи — выберите команду", "sectionTitle")
        column.addWidget(self.detail_log_title)
        self.detail_log = QPlainTextEdit()
        self.detail_log.setReadOnly(True)
        self.detail_log.setMaximumBlockCount(2000)
        column.addWidget(self.detail_log, 3)
        return page

    def _detail_button(self, title: str, handler) -> QPushButton:
        button = QPushButton(title)
        button.clicked.connect(handler)
        return button

    def show_page(self, key: str) -> None:
        self.stack.setCurrentWidget(self.pages[key])
        checked = "projects" if key == "detail" else key
        for name, button in self.nav_buttons.items():
            button.setChecked(name == checked)

    def _project_status(self, project: Project) -> str:
        if any(self.processes.is_running(command.id) for command in project.commands):
            return "running"
        if any(self.exit_codes.get(command.id, 0) != 0 for command in project.commands):
            return "error"
        return "stopped"

    def _new_card(self, project: Project) -> ProjectCard:
        card = ProjectCard(project, self._project_status(project))
        card.open_requested.connect(self.open_project)
        card.toggle_requested.connect(self.toggle_project)
        card.edit_requested.connect(self.edit_project)
        card.delete_requested.connect(self.delete_project)
        return card

    def _refresh_project_cards(self, *_):
        projects = self.store.list_projects()
        statuses = {project.id: self._project_status(project) for project in projects}
        visible = filter_projects(projects, self.search.text(), self.type_filter.currentData(),
                                  self.state_filter.currentData(), statuses)
        self.project_grid.set_items([self._new_card(project) for project in visible])
        self.project_grid.setVisible(bool(visible))
        self.project_empty.setText("Пока нет проектов. Нажмите «Добавить проект», чтобы начать." if not projects
                                   else "Ничего не найдено. Измените поиск или фильтры.")
        self.project_empty.setVisible(not visible)
        self.result_count.setText(f"Найдено: {len(visible)} из {len(projects)}" if projects else "")

    def _refresh_overview(self):
        projects = self.store.list_projects()
        self.stat_projects.setText(str(len(projects)))
        self.stat_running.setText(str(sum(self.processes.is_running(c.id) for p in projects for c in p.commands)))
        self.stat_errors.setText(str(sum(self._project_status(p) == "error" for p in projects)))
        self.overview_grid.set_items([self._new_card(project) for project in projects[:4]])
        self.overview_grid.setVisible(bool(projects))
        self.overview_empty.setVisible(not projects)

    def _refresh_log_selector(self):
        current = self.log_command_id
        self.log_selector.blockSignals(True)
        self.log_selector.clear()
        for project in self.store.list_projects():
            for command in project.commands:
                self.log_selector.addItem(f"{project.name} · {command.name}", command.id)
                if command.id == current:
                    self.log_selector.setCurrentIndex(self.log_selector.count() - 1)
        if self.log_selector.currentIndex() < 0 and self.log_selector.count():
            self.log_selector.setCurrentIndex(0)
        self.log_selector.blockSignals(False)
        self._choose_global_log()

    def _refresh_all(self):
        self._refresh_project_cards()
        self._refresh_overview()
        self._refresh_log_selector()
        if self.detail_project_id is not None:
            self._fill_detail()

    def _choose_global_log(self, *_):
        self.log_command_id = self.log_selector.currentData()
        self.global_log.setPlainText(self.logs.get(self.log_command_id, ""))
        self.global_log.moveCursor(QTextCursor.MoveOperation.End)

    def open_project(self, project_id: int):
        if self.store.get(project_id):
            self.detail_project_id = project_id
            self._fill_detail()
            self.show_page("detail")

    def _fill_detail(self):
        project = self.store.get(self.detail_project_id)
        if not project:
            self.detail_project_id = None
            self.show_page("projects")
            return
        self.detail_title.setText(project.name)
        self.detail_description.setText(f"{project.kind}  ·  {project.folder}\n{project.description or 'Описание не указано'}")
        self.repo_button.setEnabled(bool(project.repository_url))
        self.update_button.setEnabled((Path(project.folder) / ".git").exists()
                                      and not any(self.processes.is_running(c.id) for c in project.commands))
        self.update_button.setToolTip("Получить только новые изменения через Git")
        self.site_button.setEnabled(bool(project.site_url))
        while self.extra_links_layout.count():
            item = self.extra_links_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.extra_links_host.setVisible(bool(project.links))
        if project.links:
            self.extra_links_layout.addWidget(make_label("Ссылки:", "muted"))
            for link in project.links:
                button = QPushButton(link.title)
                button.clicked.connect(lambda _, url=link.url: self.open_url(url))
                self.extra_links_layout.addWidget(button)
            self.extra_links_layout.addStretch()
        while self.command_layout.count() > 1:
            item = self.command_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.command_controls.clear()
        if not project.commands:
            empty = make_label("Команд пока нет. Добавьте их через «Изменить».", "muted")
            self.command_layout.insertWidget(0, empty)
        for command in project.commands:
            row = QFrame()
            row.setObjectName("detailSection")
            cells = QHBoxLayout(row)
            labels = QVBoxLayout()
            labels.addWidget(make_label(command.name, "cardTitle"))
            labels.addWidget(make_label(command.command, "muted"))
            cells.addLayout(labels, 1)
            status = make_label("")
            view = QPushButton("Логи")
            run = QPushButton("Запустить")
            stop = QPushButton("Остановить")
            view.clicked.connect(lambda _, c=command: self.select_detail_log(c.id, c.name))
            run.clicked.connect(lambda _, c=command, p=project: self.start_command(c.id, c.command, p.folder))
            stop.clicked.connect(lambda _, c=command: self.stop_command(c.id))
            for widget in (status, view, run, stop):
                cells.addWidget(widget)
            self.command_layout.insertWidget(self.command_layout.count() - 1, row)
            self.command_controls[command.id] = status, run, stop
            self._refresh_command_control(command.id)
        if self.detail_command_id not in {c.id for c in project.commands}:
            self.detail_command_id = project.commands[0].id if project.commands else None
        selected = next((c for c in project.commands if c.id == self.detail_command_id), None)
        self.select_detail_log(selected.id, selected.name) if selected else self.select_detail_log(None, "")

    def select_detail_log(self, command_id: int | None, name: str):
        self.detail_command_id = command_id
        self.detail_log_title.setText(f"Логи · {name}" if name else "Логи — выберите команду")
        self.detail_log.setPlainText(self.logs.get(command_id, ""))
        self.detail_log.moveCursor(QTextCursor.MoveOperation.End)

    def _refresh_command_control(self, command_id: int):
        widgets = self.command_controls.get(command_id)
        if not widgets:
            return
        status, run, stop = widgets
        running = self.processes.is_running(command_id)
        code = self.exit_codes.get(command_id, 0)
        status.setText("● Работает" if running else "● Ошибка" if code else "○ Остановлена")
        status.setStyleSheet("color: #3DD598" if running else "color: #FF6B6B" if code else "color: #98A0B0")
        run.setEnabled(not running)
        stop.setEnabled(running)

    def add_project(self):
        dialog = ProjectDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            project = self.store.save(dialog.result_project())
            self._refresh_all()
            self.open_project(project.id)

    def import_from_github(self):
        default_folder = str(Path.home() / "Documents" / "Projects")
        dialog = GithubDialog(
            self.store.get_setting("github_username", "Kyjoki"),
            self.store.get_setting("github_folder", default_folder),
            {project.repository_url for project in self.store.list_projects() if project.repository_url}, self,
        )
        dialog.username_changed.connect(lambda username: self.store.set_setting("github_username", username))
        dialog.repository_imported.connect(self._finish_github_import)
        dialog.exec()
        if dialog.parent_folder.text().strip():
            self.store.set_setting("github_folder", dialog.parent_folder.text().strip())

    def _finish_github_import(self, repo: GithubRepository, folder: Path):
        for project in self.store.list_projects():
            if project.repository_url.rstrip("/").lower() == repo.html_url.lower():
                self.open_project(project.id)
                return
        commands = suggest_commands(folder)
        kind = "Бот" if (folder / "bot.py").is_file() else "Веб-сайт" if (folder / "package.json").is_file() else "Другое"
        project = self.store.save(Project(
            name=repo.name, folder=str(folder), kind=kind, description=repo.description,
            repository_url=repo.html_url, site_url=repo.homepage, commands=commands,
        ))
        self._refresh_all()
        self.open_project(project.id)

    def update_project(self):
        project = self._detail_project()
        if not project:
            return
        if any(self.processes.is_running(c.id) for c in project.commands):
            QMessageBox.warning(self, "Команды запущены", "Остановите команды проекта перед обновлением кода.")
            return
        if not (Path(project.folder) / ".git").exists():
            QMessageBox.warning(self, "Git-репозиторий не найден", "В папке проекта нет локального Git-репозитория.")
            return
        dialog = GitUpdateDialog(Path(project.folder), self)
        dialog.exec()

    def edit_project(self, project_id: int | None):
        project = self.store.get(project_id) if project_id is not None else None
        if not project:
            return
        if any(self.processes.is_running(c.id) for c in project.commands):
            QMessageBox.warning(self, "Команды запущены", "Остановите команды перед редактированием проекта.")
            return
        dialog = ProjectDialog(project, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.store.save(dialog.result_project())
            self._refresh_all()

    def delete_project(self, project_id: int | None):
        project = self.store.get(project_id) if project_id is not None else None
        if not project:
            return
        if QMessageBox.question(self, "Удалить проект", f"Удалить «{project.name}» из Project Orbit?\nФайлы проекта сохранятся.") != QMessageBox.StandardButton.Yes:
            return
        for command in project.commands:
            self.processes.stop(command.id)
            self.logs.pop(command.id, None)
            self.exit_codes.pop(command.id, None)
        self.store.delete(project.id)
        if self.detail_project_id == project.id:
            self.detail_project_id = None
            self.show_page("projects")
        self._refresh_all()

    def toggle_project(self, project_id: int):
        project = self.store.get(project_id)
        if not project:
            return
        if any(self.processes.is_running(c.id) for c in project.commands):
            for command in project.commands:
                self.stop_command(command.id)
        else:
            for command in project.commands:
                self.start_command(command.id, command.command, project.folder)

    def start_command(self, command_id: int, command: str, folder: str):
        try:
            self.processes.start(command_id, command, folder)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Не удалось запустить команду", str(exc))
            return
        self.exit_codes.pop(command_id, None)
        self.user_stopped_ids.discard(command_id)
        self._refresh_all()

    def stop_command(self, command_id: int):
        if self.processes.is_running(command_id):
            self.user_stopped_ids.add(command_id)
        try:
            self.processes.stop(command_id)
        except OSError as exc:
            self.user_stopped_ids.discard(command_id)
            QMessageBox.warning(self, "Не удалось остановить команду", str(exc))
        self._refresh_all()

    def process_events(self):
        state_changed = False
        for event in self.processes.drain_events():
            if event.kind == "started":
                self.logs[event.command_id] = f"[Запущено: {event.text}]\n"
                self.exit_codes.pop(event.command_id, None)
                state_changed = True
            elif event.kind == "output":
                self.logs[event.command_id] = (self.logs.get(event.command_id, "") + event.text)[-200_000:]
            elif event.kind == "finished":
                manually_stopped = event.command_id in self.user_stopped_ids
                self.user_stopped_ids.discard(event.command_id)
                self.exit_codes[event.command_id] = 0 if manually_stopped else int(event.text)
                ending = "[Остановлено пользователем]" if manually_stopped else f"[Завершено, код {event.text}]"
                self.logs[event.command_id] = (self.logs.get(event.command_id, "") +
                                               f"\n{ending}\n")[-200_000:]
                state_changed = True
            for selected_id, view in ((self.detail_command_id, self.detail_log),
                                      (self.log_command_id, self.global_log)):
                if event.command_id != selected_id:
                    continue
                if event.kind == "started":
                    view.setPlainText(self.logs[event.command_id])
                elif event.kind == "output":
                    view.moveCursor(QTextCursor.MoveOperation.End)
                    view.insertPlainText(event.text)
                elif event.kind == "finished":
                    view.appendPlainText(f"\n{ending}")
                view.moveCursor(QTextCursor.MoveOperation.End)
        if state_changed:
            self._refresh_all()

    def _detail_project(self) -> Project | None:
        return self.store.get(self.detail_project_id) if self.detail_project_id is not None else None

    def open_folder(self):
        project = self._detail_project()
        if project:
            if not Path(project.folder).is_dir():
                QMessageBox.warning(self, "Папка не найдена", project.folder)
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(project.folder))))

    def open_editor(self):
        project = self._detail_project()
        if not project:
            return
        try:
            if os.name == "nt":
                subprocess.Popen(["cmd.exe", "/d", "/s", "/c", f'{project.editor_command} "{project.folder}"'],
                                 creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            else:
                subprocess.Popen(f'{project.editor_command} "{project.folder}"', shell=True)
        except OSError as exc:
            QMessageBox.warning(self, "Не удалось открыть редактор", str(exc))

    def open_link(self, field: str):
        project = self._detail_project()
        if not project:
            return
        url = getattr(project, field)
        if url:
            self.open_url(url)

    def open_url(self, url: str):
        parsed = QUrl(url)
        if parsed.scheme().lower() not in ("http", "https"):
            QMessageBox.warning(self, "Некорректная ссылка", "Используйте ссылку http:// или https://.")
        elif not QDesktopServices.openUrl(parsed):
            QMessageBox.warning(self, "Не удалось открыть ссылку", url)

    def closeEvent(self, event):
        self.timer.stop()
        self.processes.stop_all()
        self.store.close()
        super().closeEvent(event)
