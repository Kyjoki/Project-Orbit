import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    QApplication = None


@unittest.skipUnless(QApplication is not None, "Install PySide6 to run UI tests")
class LogPaneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_search_and_copy_visible_log(self):
        from orbit.log_pane import LogPane

        pane = LogPane()
        pane.set_text("first line\nerror happened\nlast line\n")
        pane.search.setText("error")
        self.assertIn("1 найдено", pane.match_count.text())
        self.assertEqual(pane.viewer.textCursor().selectedText(), "error")
        pane.copy_button.click()
        self.assertEqual(self.app.clipboard().text(), pane.viewer.toPlainText())
        pane.close()
        pane.deleteLater()
        self.app.processEvents()
        from PySide6.QtCore import QCoreApplication, QEvent
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_save_requires_explicit_file_choice(self):
        from orbit.log_pane import LogPane

        pane = LogPane()
        pane.set_text("[2026-10-10 12:00:00] hello\n")
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            destination = Path(directory) / "chosen.txt"
            with patch("orbit.log_pane.QFileDialog.getSaveFileName", return_value=("", "")):
                pane.save_button.click()
            self.assertFalse(destination.exists())
            with patch("orbit.log_pane.QFileDialog.getSaveFileName", return_value=(str(destination), "Text files (*.txt)")):
                pane.save_button.click()
            self.assertEqual(destination.read_text(encoding="utf-8"), pane.viewer.toPlainText())
        pane.close()
        pane.deleteLater()
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
