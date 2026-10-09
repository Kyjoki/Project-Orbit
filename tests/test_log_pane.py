import os
import unittest

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


if __name__ == "__main__":
    unittest.main()
