"""Choose which remote branches appear in Orbit and switch explicitly."""

from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QProgressBar, QPushButton, QVBoxLayout)

from .branches import BranchError, current_branch, list_remote_branches, switch_branch


class BranchTask(QThread):
    result_ready = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self, action: str, folder: Path, branch: str = "", parent=None):
        super().__init__(parent)
        self.action = action
        self.folder = folder
        self.branch = branch

    def run(self):
        try:
            result = (list_remote_branches(self.folder) if self.action == "list"
                      else switch_branch(self.folder, self.branch))
            self.result_ready.emit(self.action, result)
        except BranchError as exc:
            self.failed.emit(self.action, str(exc))


class BranchDialog(QDialog):
    branch_switched = Signal(str)

    def __init__(self, folder: Path, included: list[str], save_callback, parent=None):
        super().__init__(parent)
        self.folder = folder
        self.save_callback = save_callback
        self.included = set(included)
        self.remote_branches: set[str] = set()
        self.worker: BranchTask | None = None
        try:
            self.active_branch = current_branch(folder)
        except BranchError:
            self.active_branch = ""
        self.setWindowTitle("Ветки проекта")
        self.resize(560, 440)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        heading = QLabel("Ветки Git")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        explanation = QLabel(
            "Отметьте ветки, между которыми хотите переключаться. Переключение меняет код "
            "в этой же папке и не запускает команды. При локальных правках переключение остановится."
        )
        explanation.setWordWrap(True)
        explanation.setObjectName("muted")
        layout.addWidget(explanation)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.branches = QListWidget()
        self.branches.currentItemChanged.connect(self._update_buttons)
        self.branches.itemChanged.connect(self._update_buttons)
        layout.addWidget(self.branches, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        buttons = QHBoxLayout()
        self.refresh_button = QPushButton("Обновить список")
        self.refresh_button.clicked.connect(self.refresh)
        self.save_button = QPushButton("Сохранить список")
        self.save_button.clicked.connect(self.save_selection)
        self.switch_button = QPushButton("Переключить")
        self.switch_button.setObjectName("primary")
        self.switch_button.clicked.connect(self.start_switch)
        self.close_button = QPushButton("Закрыть")
        self.close_button.clicked.connect(self.reject)
        for button in (self.refresh_button, self.save_button, self.switch_button, self.close_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self._populate(self.included | ({self.active_branch} if self.active_branch else set()))
        self.refresh()

    def _checked_names(self) -> set[str]:
        return {self.branches.item(index).data(Qt.ItemDataRole.UserRole)
                for index in range(self.branches.count())
                if self.branches.item(index).checkState() == Qt.CheckState.Checked}

    def _selected_branch(self) -> str:
        item = self.branches.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else ""

    def _populate(self, checked: set[str]):
        selected = self._selected_branch()
        names = self.remote_branches | self.included | checked
        if self.active_branch:
            names.add(self.active_branch)
        self.branches.blockSignals(True)
        self.branches.clear()
        for name in sorted(names, key=str.casefold):
            label = name + ("  ·  текущая" if name == self.active_branch else "")
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if name in checked or name == self.active_branch
                               else Qt.CheckState.Unchecked)
            self.branches.addItem(item)
            if name == selected:
                self.branches.setCurrentItem(item)
        self.branches.blockSignals(False)
        self._update_buttons()

    def _start_task(self, action: str, branch: str = ""):
        if self.worker is not None:
            return
        self.progress.show()
        self.refresh_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.switch_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.worker = BranchTask(action, self.folder, branch, self)
        self.worker.result_ready.connect(self._task_result)
        self.worker.failed.connect(self._task_error)
        self.worker.finished.connect(self._task_finished)
        self.worker.start()

    def refresh(self):
        self.status.setText("Получаю названия веток из GitHub…")
        self._start_task("list")

    def save_selection(self):
        selected = self._checked_names()
        if self.active_branch:
            selected.add(self.active_branch)
        self.included = selected
        self.save_callback(sorted(selected, key=str.casefold))
        self.status.setText("Список веток сохранён. Код проекта не менялся.")
        self._populate(selected)

    def start_switch(self):
        branch = self._selected_branch()
        if not branch or branch == self.active_branch or branch not in self._checked_names():
            return
        self.status.setText(f"Переключаю на {branch}…")
        self._start_task("switch", branch)

    def _task_result(self, action: str, result):
        if action == "list":
            checked = self._checked_names()
            self.remote_branches = set(result)
            self._populate(checked)
            self.status.setText(f"Текущая ветка: {self.active_branch or 'не выбрана'}. "
                                "Отметьте нужные ветки и сохраните список.")
        else:
            self.active_branch = result
            selected = self._checked_names() | {result}
            self.included = selected
            self.save_callback(sorted(selected, key=str.casefold))
            self._populate(selected)
            self.status.setText(f"Текущая ветка: {result}. Команды проекта не запускались.")
            self.branch_switched.emit(result)

    def _task_error(self, action: str, message: str):
        self.status.setText(("Не удалось получить ветки: " if action == "list"
                             else "Переключение остановлено: ") + message)

    def _task_finished(self):
        worker = self.worker
        self.worker = None
        if worker:
            worker.wait()
            worker.deleteLater()
        self.progress.hide()
        self.refresh_button.setEnabled(True)
        self.save_button.setEnabled(True)
        self.close_button.setEnabled(True)
        self._update_buttons()

    def _update_buttons(self, *_):
        self.switch_button.setEnabled(self.worker is None
                                      and bool(self._selected_branch())
                                      and self._selected_branch() in self._checked_names()
                                      and self._selected_branch() != self.active_branch)

    def reject(self):
        if self.worker is not None:
            self.status.setText("Дождитесь завершения операции Git.")
            return
        super().reject()

    def closeEvent(self, event):
        if self.worker is not None:
            self.status.setText("Дождитесь завершения операции Git.")
            event.ignore()
            return
        super().closeEvent(event)
