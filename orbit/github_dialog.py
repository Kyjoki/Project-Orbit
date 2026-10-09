"""Non-blocking GitHub repository browser and importer."""

import os
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path

from PySide6.QtCore import QThread, Qt, QTimer, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QProgressBar,
    QPushButton, QVBoxLayout,
)

from .github import GithubError, GithubRepository, clone_repository, list_authenticated_repositories, list_public_repositories


class ImportCancelled(Exception):
    pass


class GithubTask(QThread):
    result_ready = Signal(object)
    failed = Signal(str)

    def __init__(self, action: str, username: str = "", repo: GithubRepository | None = None,
                 parent_folder: Path | None = None, parent=None):
        super().__init__(parent)
        self.action = action
        self.username = username
        self.repo = repo
        self.parent_folder = parent_folder
        self.cancelled = threading.Event()
        self.process: subprocess.Popen | None = None

    def cancel(self):
        self.cancelled.set()

    def _run_command(self, args, **kwargs):
        timeout = kwargs.get("timeout", 600)
        options = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
                   else {"start_new_session": True})
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding="utf-8", errors="replace", **options)
        self.process = process
        deadline = time.monotonic() + timeout
        try:
            while True:
                if self.cancelled.is_set():
                    if process.poll() is None:
                        if os.name == "nt":
                            from .windows_process_tree import terminate_tree
                            terminate_tree(process.pid)
                        else:
                            os.killpg(process.pid, signal.SIGTERM)
                    process.communicate()
                    raise ImportCancelled()
                if time.monotonic() > deadline:
                    process.kill()
                    process.communicate()
                    raise subprocess.TimeoutExpired(args, timeout)
                try:
                    stdout, stderr = process.communicate(timeout=0.25)
                    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
                except subprocess.TimeoutExpired:
                    continue
        finally:
            self.process = None

    def run(self):
        try:
            if self.action == "public":
                result = list_public_repositories(self.username, cancelled=self.cancelled.is_set)
            elif self.action == "authenticated":
                result = list_authenticated_repositories(self.username, run=self._run_command)
            elif self.action == "clone":
                result = (self.repo, clone_repository(self.repo, self.parent_folder, run=self._run_command))
            else:
                raise GithubError("Неизвестное действие GitHub.")
            if not self.cancelled.is_set():
                self.result_ready.emit(result)
        except ImportCancelled:
            pass
        except (GithubError, FileExistsError, OSError, subprocess.TimeoutExpired) as exc:
            if not self.cancelled.is_set():
                self.failed.emit(str(exc))


class GithubDialog(QDialog):
    repository_imported = Signal(object, object)
    username_changed = Signal(str)

    def __init__(self, username: str, parent_folder: str, existing_urls: set[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Импорт из GitHub")
        self.resize(690, 620)
        self.existing_urls = {url.rstrip("/").lower() for url in existing_urls}
        self.repositories: list[GithubRepository] = []
        self.worker: GithubTask | None = None
        self.close_when_finished = False
        self.import_succeeded = False
        layout = QVBoxLayout(self)
        layout.setSpacing(11)
        layout.addWidget(QLabel("Выберите репозиторий. Он будет скачан только после нажатия «Импортировать»."))
        account_row = QHBoxLayout()
        self.username = QLineEdit(username)
        self.username.setPlaceholderText("Имя пользователя GitHub")
        self.mode = QComboBox()
        self.mode.addItem("Публичные", "public")
        self.mode.addItem("Публичные и приватные (gh)", "authenticated")
        account_row.addWidget(self.username, 1)
        account_row.addWidget(self.mode)
        layout.addLayout(account_row)
        source_row = QHBoxLayout()
        self.refresh_button = QPushButton("Обновить список")
        self.refresh_button.clicked.connect(self.refresh)
        self.login_button = QPushButton("Войти в GitHub")
        self.login_button.clicked.connect(self.open_login)
        source_row.addWidget(self.refresh_button)
        source_row.addWidget(self.login_button)
        source_row.addStretch()
        layout.addLayout(source_row)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск среди найденных репозиториев")
        self.search.textChanged.connect(self._populate_list)
        layout.addWidget(self.search)
        self.repo_list = QListWidget()
        self.repo_list.currentItemChanged.connect(self._update_import_button)
        layout.addWidget(self.repo_list, 1)
        destination_row = QHBoxLayout()
        destination_row.addWidget(QLabel("Скачать в:"))
        self.parent_folder = QLineEdit(parent_folder)
        browse = QPushButton("Обзор…")
        browse.clicked.connect(self.browse_parent)
        destination_row.addWidget(self.parent_folder, 1)
        destination_row.addWidget(browse)
        layout.addLayout(destination_row)
        self.status = QLabel("После импорта проект появится в Orbit. Команды запуска можно изменить в его карточке.")
        self.status.setWordWrap(True)
        self.status.setObjectName("muted")
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Закрыть")
        cancel.clicked.connect(self.reject)
        self.import_button = QPushButton("Импортировать")
        self.import_button.setObjectName("primary")
        self.import_button.clicked.connect(self.import_selected)
        self.import_button.setEnabled(False)
        buttons.addWidget(cancel)
        buttons.addWidget(self.import_button)
        layout.addLayout(buttons)
        if username:
            QTimer.singleShot(0, self.refresh)

    def selected_repo(self) -> GithubRepository | None:
        item = self.repo_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def browse_parent(self):
        folder = QFileDialog.getExistingDirectory(self, "Папка для GitHub проектов", self.parent_folder.text())
        if folder:
            self.parent_folder.setText(folder)

    def refresh(self):
        username = self.username.text().strip()
        if not username:
            self.status.setText("Укажите имя пользователя GitHub.")
            return
        self.username_changed.emit(username)
        self._start_task(GithubTask(self.mode.currentData(), username=username, parent=self),
                         "Получаю список репозиториев…")

    def _start_task(self, worker: GithubTask, message: str):
        if self.worker is not None:
            return
        self.worker = worker
        self.status.setText(message)
        self.progress.show()
        self.refresh_button.setEnabled(False)
        self.import_button.setEnabled(False)
        worker.result_ready.connect(self._handle_result)
        worker.failed.connect(self._handle_error)
        worker.finished.connect(self._task_finished)
        worker.start()

    def _handle_result(self, result):
        if isinstance(result, list):
            self.repositories = result
            self._populate_list()
            self.status.setText(f"Найдено репозиториев: {len(result)}. Выберите один для импорта.")
        else:
            repo, path = result
            self.repository_imported.emit(repo, path)
            self.import_succeeded = True
            self.close_when_finished = True

    def _handle_error(self, message: str):
        self.status.setText(message)

    def _task_finished(self):
        worker = self.worker
        self.worker = None
        if worker:
            worker.wait()
            worker.deleteLater()
        self.progress.hide()
        self.refresh_button.setEnabled(True)
        self._update_import_button()
        if self.close_when_finished:
            self.close_when_finished = False
            if self.import_succeeded:
                super().accept()
            else:
                super().reject()

    def _populate_list(self, *_):
        query = self.search.text().strip().casefold()
        current = self.selected_repo()
        current_name = current.full_name if current else ""
        self.repo_list.clear()
        for repo in self.repositories:
            if query and query not in f"{repo.full_name} {repo.description}".casefold():
                continue
            suffix = " · приватный" if repo.private else ""
            if repo.html_url.lower() in self.existing_urls:
                suffix += " · уже добавлен"
            item = QListWidgetItem(f"{repo.full_name}{suffix}\n{repo.description or 'Без описания'}")
            item.setData(Qt.ItemDataRole.UserRole, repo)
            self.repo_list.addItem(item)
            if repo.full_name == current_name:
                self.repo_list.setCurrentItem(item)
        self._update_import_button()

    def _update_import_button(self, *_):
        repo = self.selected_repo()
        self.import_button.setEnabled(self.worker is None and repo is not None
                                      and repo.html_url.lower() not in self.existing_urls)

    def import_selected(self):
        repo = self.selected_repo()
        if not repo:
            return
        folder = self.parent_folder.text().strip()
        if not folder:
            self.status.setText("Выберите папку для проектов.")
            return
        parent = Path(folder).expanduser()
        self._start_task(GithubTask("clone", repo=repo, parent_folder=parent, parent=self),
                         f"Скачиваю {repo.full_name} в {parent}…")

    def open_login(self):
        if shutil.which("gh") is None:
            QApplication.clipboard().setText("winget install --id GitHub.cli -e")
            QMessageBox.information(self, "GitHub CLI нужен для приватных репозиториев",
                                    "Команда установки скопирована в буфер обмена:\n"
                                    "winget install --id GitHub.cli -e\n\n"
                                    "После установки выполните в PowerShell: gh auth login")
            QDesktopServices.openUrl(QUrl("https://cli.github.com/"))
            return
        if os.name == "nt":
            subprocess.Popen(["cmd.exe", "/k", "gh auth login --web"],
                             creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            QMessageBox.information(self, "Вход в GitHub", "Выполните `gh auth login --web` в терминале.")

    def reject(self):
        if self.worker is not None and self.worker.isRunning():
            self.close_when_finished = True
            self.worker.cancel()
            self.status.setText("Отменяю операцию…")
            return
        super().reject()

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            self.close_when_finished = True
            self.worker.cancel()
            self.status.setText("Отменяю операцию…")
            event.ignore()
            return
        super().closeEvent(event)
