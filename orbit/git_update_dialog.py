"""Responsive progress window for an explicitly requested Git update."""

from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout

from .git_update import GitUpdateError, update_repository


class GitUpdateTask(QThread):
    result_ready = Signal(object)
    failed = Signal(str)

    def __init__(self, folder: Path, parent=None):
        super().__init__(parent)
        self.folder = folder

    def run(self):
        try:
            self.result_ready.emit(update_repository(self.folder))
        except GitUpdateError as exc:
            self.failed.emit(str(exc))


class GitUpdateDialog(QDialog):
    def __init__(self, folder: Path, parent=None):
        super().__init__(parent)
        self.folder = folder
        self.worker: GitUpdateTask | None = None
        self.setWindowTitle("Обновить локальный проект")
        self.resize(510, 205)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        heading = QLabel("Получить последние изменения")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        explanation = QLabel(
            "Git скачает только недостающие изменения в эту папку. "
            "Локальные правки останутся без изменений; при их наличии обновление остановится. "
            "Команды проекта автоматически не запустятся."
        )
        explanation.setWordWrap(True)
        explanation.setObjectName("muted")
        layout.addWidget(explanation)
        self.status = QLabel(str(folder))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.close_button = QPushButton("Закрыть")
        self.close_button.clicked.connect(self.reject)
        self.update_button = QPushButton("Обновить")
        self.update_button.setObjectName("primary")
        self.update_button.clicked.connect(self.start_update)
        buttons.addWidget(self.close_button)
        buttons.addWidget(self.update_button)
        layout.addLayout(buttons)

    def start_update(self):
        if self.worker is not None:
            return
        self.status.setText("Получаю изменения из GitHub…")
        self.progress.show()
        self.update_button.setEnabled(False)
        self.close_button.setEnabled(False)
        worker = GitUpdateTask(self.folder, self)
        self.worker = worker
        worker.result_ready.connect(self._show_result)
        worker.failed.connect(self._show_error)
        worker.finished.connect(self._task_finished)
        worker.start()

    def _show_result(self, result):
        self.status.setText(
            f"Готово: обновлено до {result.after[:10]}. Перезапустите команды проекта при необходимости."
            if result.changed else "Уже установлена последняя версия."
        )

    def _show_error(self, message: str):
        self.status.setText("Обновление остановлено: " + message)

    def _task_finished(self):
        worker = self.worker
        self.worker = None
        if worker:
            worker.wait()
            worker.deleteLater()
        self.progress.hide()
        self.update_button.setEnabled(True)
        self.close_button.setEnabled(True)

    def reject(self):
        if self.worker is not None:
            self.status.setText("Дождитесь завершения обновления Git.")
            return
        super().reject()

    def closeEvent(self, event):
        if self.worker is not None:
            self.status.setText("Дождитесь завершения обновления Git.")
            event.ignore()
            return
        super().closeEvent(event)
