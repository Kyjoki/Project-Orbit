"""Choose which remote branches appear in Orbit and switch explicitly."""

from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QProgressBar, QPushButton, QVBoxLayout)

from .branches import (BranchError, current_branch, delete_local_branch,
                       list_local_branches, origin_url, remote_branch_heads,
                       switch_branch)
from .branch_status import compare_branch_heads


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
            if self.action == "list":
                heads = remote_branch_heads(self.folder)
                result = (heads, list_local_branches(self.folder),
                          compare_branch_heads(origin_url(self.folder), heads))
            elif self.action == "switch":
                result = switch_branch(self.folder, self.branch)
            else:
                result = delete_local_branch(self.folder, self.branch)
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
        self.local_branches: set[str] = set()
        self.main_status: dict[str, str] = {}
        self.worker: BranchTask | None = None
        try:
            self.active_branch = current_branch(folder)
        except BranchError:
            self.active_branch = ""
        self.setWindowTitle("Ветки проекта")
        self.resize(740, 490)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        heading = QLabel("Ветки Git")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        explanation = QLabel(
            "«В main: да» — коммиты ветки уже есть в main на GitHub; «нет» — есть новые "
            "коммиты. «Не скачана» — ветка есть на GitHub, но ещё не занимает место на "
            "компьютере. Галочка слева добавляет ветку в список для тестирования. "
            "Переключение меняет код в этой же папке и не запускает команды."
        )
        explanation.setWordWrap(True)
        explanation.setObjectName("muted")
        layout.addWidget(explanation)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.branches = QListWidget()
        self.branches.setAlternatingRowColors(True)
        self.branches.currentItemChanged.connect(self._update_buttons)
        self.branches.itemChanged.connect(self._update_buttons)
        layout.addWidget(self.branches, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        list_buttons = QHBoxLayout()
        self.refresh_button = QPushButton("Обновить список")
        self.refresh_button.clicked.connect(self.refresh)
        self.save_button = QPushButton("Сохранить список")
        self.save_button.clicked.connect(self.save_selection)
        self.switch_button = QPushButton("Загрузить и переключить")
        self.switch_button.setObjectName("primary")
        self.switch_button.clicked.connect(self.start_switch)
        self.delete_button = QPushButton("Удалить локальную ветку")
        self.delete_button.clicked.connect(self.start_delete)
        self.close_button = QPushButton("Закрыть")
        self.close_button.clicked.connect(self.reject)
        for button in (self.refresh_button, self.save_button):
            list_buttons.addWidget(button)
        list_buttons.addStretch()
        layout.addLayout(list_buttons)
        action_buttons = QHBoxLayout()
        for button in (self.switch_button, self.delete_button, self.close_button):
            action_buttons.addWidget(button)
        layout.addLayout(action_buttons)
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
            location = ("Текущая (на компьютере)" if name == self.active_branch else
                        "На компьютере" if name in self.local_branches else "Не скачана")
            state = self.main_status.get(name, "unknown")
            main = {"merged": "В main: да", "unmerged": "В main: нет"}.get(
                state, "В main: ? (не проверено)")
            label = f"{name}  ·  {main}  ·  {location}"
            item = QListWidgetItem(label)
            item.setToolTip("В main — сравнение коммитов с main на GitHub. После squash-merge "
                            "изменения могут присутствовать в main, хотя исходные коммиты не вошли. "
                            "«Не скачана» означает, что локальной ветки нет; на GitHub она есть.")
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
        self.delete_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.worker = BranchTask(action, self.folder, branch, self)
        self.worker.result_ready.connect(self._task_result)
        self.worker.failed.connect(self._task_error)
        self.worker.finished.connect(self._task_finished)
        self.worker.start()

    def refresh(self):
        self.status.setText("Получаю ветки и сравниваю их коммиты с main на GitHub…")
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

    def start_delete(self):
        branch = self._selected_branch()
        if (not branch or branch not in self.local_branches or
                branch == self.active_branch or branch in {"main", "master"}):
            return
        self.status.setText(f"Удаляю локальную ветку {branch}…")
        self._start_task("delete", branch)

    def _task_result(self, action: str, result):
        if action == "list":
            checked = self._checked_names()
            remote, local, main_status = result
            self.remote_branches = set(remote)
            self.local_branches = set(local)
            self.main_status = main_status
            self._populate(checked)
            unknown = sum(state == "unknown" for state in main_status.values())
            note = f" Не удалось проверить: {unknown}." if unknown else ""
            self.status.setText(f"Текущая ветка: {self.active_branch or 'не выбрана'}."
                                f"{note} Отметьте нужные ветки и сохраните список.")
        elif action == "switch":
            self.active_branch = result
            self.local_branches.add(result)
            selected = self._checked_names() | {result}
            self.included = selected
            self.save_callback(sorted(selected, key=str.casefold))
            self._populate(selected)
            self.status.setText(f"Текущая ветка: {result}. Команды проекта не запускались.")
            self.branch_switched.emit(result)
        else:
            self.local_branches.discard(result)
            selected = self._checked_names() - {result}
            self.included = selected
            self.save_callback(sorted(selected, key=str.casefold))
            self._populate(selected)
            self.status.setText(f"Локальная ветка {result} удалена. На GitHub она осталась.")

    def _task_error(self, action: str, message: str):
        prefix = {"list": "Не удалось получить ветки: ",
                  "switch": "Переключение остановлено: ",
                  "delete": "Удаление остановлено: "}[action]
        self.status.setText(prefix + message)

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
        self.delete_button.setEnabled(self.worker is None
                                      and self._selected_branch() in self.local_branches
                                      and self._selected_branch() != self.active_branch
                                      and self._selected_branch() not in {"main", "master"})

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
