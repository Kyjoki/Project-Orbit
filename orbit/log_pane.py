"""Reusable log viewer with search and copy controls."""

from pathlib import Path

from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)


class LogPane(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск в логах")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._query_changed)
        self.search.returnPressed.connect(self.find_next)
        self.match_count = QLabel("")
        self.match_count.setObjectName("smallCaption")
        previous = QPushButton("↑")
        previous.setToolTip("Предыдущее совпадение")
        previous.clicked.connect(self.find_previous)
        following = QPushButton("↓")
        following.setToolTip("Следующее совпадение")
        following.clicked.connect(self.find_next)
        self.copy_button = QPushButton("Копировать")
        self.copy_button.setToolTip("Скопировать показанные логи")
        self.copy_button.clicked.connect(self.copy_text)
        self.save_button = QPushButton("Сохранить в файл")
        self.save_button.setToolTip("Выбрать файл для сохранения показанных логов")
        self.save_button.clicked.connect(self.save_text)
        self.save_button.setEnabled(False)
        controls.addWidget(self.search, 1)
        controls.addWidget(self.match_count)
        controls.addWidget(previous)
        controls.addWidget(following)
        controls.addWidget(self.copy_button)
        controls.addWidget(self.save_button)
        layout.addLayout(controls)
        self.viewer = QPlainTextEdit()
        self.viewer.setReadOnly(True)
        self.viewer.setMaximumBlockCount(5000)
        layout.addWidget(self.viewer, 1)

    def set_text(self, value: str) -> None:
        self.viewer.setPlainText(value)
        self.save_button.setEnabled(bool(value))
        if self.search.text():
            self._query_changed()
        else:
            self.viewer.moveCursor(QTextCursor.MoveOperation.End)

    def append(self, value: str) -> None:
        if not value:
            return
        previous = self.viewer.textCursor()
        cursor = self.viewer.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(value)
        self.save_button.setEnabled(True)
        if self.search.text():
            self.viewer.setTextCursor(previous)
            self._update_match_count()
        else:
            self.viewer.setTextCursor(cursor)
            self.viewer.ensureCursorVisible()

    def _update_match_count(self) -> None:
        query = self.search.text()
        matches = self.viewer.toPlainText().casefold().count(query.casefold()) if query else 0
        self.match_count.setText(f"{matches} найдено" if query else "")

    def _query_changed(self, *_):
        self._update_match_count()
        if self.search.text():
            cursor = self.viewer.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.viewer.setTextCursor(cursor)
            self.viewer.find(self.search.text())

    def find_next(self):
        query = self.search.text()
        if not query:
            return
        if not self.viewer.find(query):
            cursor = self.viewer.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.viewer.setTextCursor(cursor)
            self.viewer.find(query)

    def find_previous(self):
        query = self.search.text()
        if not query:
            return
        backward = QTextDocument.FindFlag.FindBackward
        if not self.viewer.find(query, backward):
            cursor = self.viewer.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.viewer.setTextCursor(cursor)
            self.viewer.find(query, backward)

    def copy_text(self):
        QApplication.clipboard().setText(self.viewer.toPlainText())

    def save_text(self):
        content = self.viewer.toPlainText()
        if not content:
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Сохранить логи", "orbit-log.txt",
                                                   "Текстовые файлы (*.txt);;Все файлы (*)")
        if not filename:
            return
        try:
            Path(filename).write_text(content, encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Не удалось сохранить логи", str(exc))
