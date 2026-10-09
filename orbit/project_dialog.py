from pathlib import Path

from PySide6.QtCore import QUrl

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget, QComboBox,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from .models import Command, Link, Project, PROJECT_KINDS


class ProjectDialog(QDialog):
    def __init__(self, project: Project | None = None, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Редактировать проект" if project else "Новый проект")
        self.resize(680, 700)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(project.name if project else "")
        self.kind = QComboBox()
        self.kind.addItems(PROJECT_KINDS)
        self.kind.setCurrentText(project.kind if project else "Другое")
        self.folder = QLineEdit(project.folder if project else "")
        browse = QPushButton("Обзор…")
        browse.clicked.connect(self.browse_folder)
        folder_row = QWidget()
        folder_layout = QHBoxLayout(folder_row)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.addWidget(self.folder)
        folder_layout.addWidget(browse)
        self.description = QTextEdit(project.description if project else "")
        self.description.setFixedHeight(72)
        self.repo = QLineEdit(project.repository_url if project else "")
        self.site = QLineEdit(project.site_url if project else "")
        self.editor = QLineEdit(project.editor_command if project else "code")
        self.editor.setPlaceholderText("code")
        form.addRow("Название *", self.name)
        form.addRow("Тип", self.kind)
        form.addRow("Локальная папка *", folder_row)
        form.addRow("Описание", self.description)
        form.addRow("Репозиторий", self.repo)
        form.addRow("Сайт", self.site)
        form.addRow("Команда редактора", self.editor)
        layout.addLayout(form)
        layout.addWidget(QLabel("Команды запуска"))
        self.commands = QTableWidget(0, 2)
        self.commands.setHorizontalHeaderLabels(["Название", "Команда"])
        self.commands.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.commands.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        if project:
            for command in project.commands:
                self.add_command(command.name, command.command)
        layout.addWidget(self.commands)
        row = QHBoxLayout()
        add = QPushButton("+ Команда")
        remove = QPushButton("− Удалить команду")
        add.clicked.connect(lambda: self.add_command())
        remove.clicked.connect(self.remove_command)
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch()
        layout.addLayout(row)
        layout.addWidget(QLabel("Дополнительные ссылки"))
        self.links = QTableWidget(0, 2)
        self.links.setHorizontalHeaderLabels(["Название", "URL"])
        self.links.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.links.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.links.setFixedHeight(120)
        if project:
            for link in project.links:
                self.add_link(link.title, link.url)
        layout.addWidget(self.links)
        link_row = QHBoxLayout()
        add_link = QPushButton("+ Ссылка")
        remove_link = QPushButton("− Удалить ссылку")
        add_link.clicked.connect(lambda: self.add_link())
        remove_link.clicked.connect(self.remove_link)
        link_row.addWidget(add_link)
        link_row.addWidget(remove_link)
        link_row.addStretch()
        layout.addLayout(link_row)
        self.error = QLabel("")
        self.error.setObjectName("error")
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку проекта", self.folder.text())
        if folder:
            self.folder.setText(folder)

    def add_command(self, name: str = "", command: str = ""):
        index = self.commands.rowCount()
        self.commands.insertRow(index)
        self.commands.setItem(index, 0, QTableWidgetItem(name))
        self.commands.setItem(index, 1, QTableWidgetItem(command))

    def remove_command(self):
        row = self.commands.currentRow()
        if row >= 0:
            self.commands.removeRow(row)

    def add_link(self, title: str = "", url: str = ""):
        index = self.links.rowCount()
        self.links.insertRow(index)
        self.links.setItem(index, 0, QTableWidgetItem(title))
        self.links.setItem(index, 1, QTableWidgetItem(url))

    def remove_link(self):
        row = self.links.currentRow()
        if row >= 0:
            self.links.removeRow(row)

    def validate_and_accept(self):
        if not self.name.text().strip() or not self.folder.text().strip():
            self.error.setText("Заполните название и папку.")
            return
        if not Path(self.folder.text().strip()).is_dir():
            self.error.setText("Указанная папка не существует.")
            return
        for row in range(self.commands.rowCount()):
            if not self.commands.item(row, 0).text().strip() or not self.commands.item(row, 1).text().strip():
                self.error.setText("Заполните название и текст каждой команды.")
                return
        for row in range(self.links.rowCount()):
            title = self.links.item(row, 0).text().strip()
            url = self.links.item(row, 1).text().strip()
            if not title or QUrl(url).scheme().lower() not in ("http", "https"):
                self.error.setText("Укажите название и URL http(s) для каждой ссылки.")
                return
        self.accept()

    def result_project(self) -> Project:
        commands = [Command(self.commands.item(i, 0).text().strip(),
                            self.commands.item(i, 1).text().strip())
                    for i in range(self.commands.rowCount())]
        links = [Link(self.links.item(i, 0).text().strip(), self.links.item(i, 1).text().strip())
                 for i in range(self.links.rowCount())]
        return Project(
            id=self.project.id if self.project else None,
            name=self.name.text().strip(), folder=self.folder.text().strip(), kind=self.kind.currentText(),
            description=self.description.toPlainText().strip(),
            repository_url=self.repo.text().strip(), site_url=self.site.text().strip(),
            editor_command=self.editor.text().strip() or "code", commands=commands, links=links,
        )
