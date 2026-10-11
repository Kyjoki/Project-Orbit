import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import QApplication, QListWidget, QListWidgetItem
except ImportError:
    QApplication = None


@unittest.skipUnless(QApplication is not None, "Install PySide6 to run UI tests")
class ThemeTests(unittest.TestCase):
    def test_alternating_list_rows_keep_dark_theme_contrast(self):
        from orbit.theme import apply_theme

        app = QApplication.instance() or QApplication([])
        apply_theme(app)
        rows = QListWidget()
        rows.setAlternatingRowColors(True)
        rows.addItems(["first", "second"])
        alternate = rows.palette().color(QPalette.ColorRole.AlternateBase)
        text = rows.palette().color(QPalette.ColorRole.Text)
        self.assertLess(alternate.lightness(), 100)
        self.assertGreater(text.lightness() - alternate.lightness(), 90)


if __name__ == "__main__":
    unittest.main()
