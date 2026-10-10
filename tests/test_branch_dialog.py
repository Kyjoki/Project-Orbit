import os
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
except ImportError:
    QApplication = None


@unittest.skipUnless(QApplication is not None, "Install PySide6 to run UI tests")
class BranchDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _wait_for_worker(self, dialog):
        deadline = time.monotonic() + 5
        while dialog.worker is not None and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertIsNone(dialog.worker)

    def test_refresh_save_and_switch_selected_branch_without_blocking_ui(self):
        from orbit.branch_dialog import BranchDialog

        saved = []
        with (patch("orbit.branch_dialog.current_branch", return_value="main"),
              patch("orbit.branch_dialog.list_remote_branches",
                    side_effect=lambda _folder: (time.sleep(0.15), ["main", "feat/pretest-check"])[1]),
              patch("orbit.branch_dialog.switch_branch", return_value="feat/pretest-check")):
            started = time.monotonic()
            dialog = BranchDialog(Path.cwd(), ["main"], saved.append)
            self.assertLess(time.monotonic() - started, 0.1)
            self._wait_for_worker(dialog)
            self.assertEqual(dialog.branches.count(), 2)
            feature = next(dialog.branches.item(index) for index in range(dialog.branches.count())
                           if dialog.branches.item(index).data(Qt.ItemDataRole.UserRole) == "feat/pretest-check")
            dialog.branches.setCurrentItem(feature)
            self.assertFalse(dialog.switch_button.isEnabled())
            feature.setCheckState(Qt.CheckState.Checked)
            self.assertTrue(dialog.switch_button.isEnabled())
            dialog.save_selection()
            self.assertEqual(saved[-1], ["feat/pretest-check", "main"])
            feature = next(dialog.branches.item(index) for index in range(dialog.branches.count())
                           if dialog.branches.item(index).data(Qt.ItemDataRole.UserRole) == "feat/pretest-check")
            dialog.branches.setCurrentItem(feature)
            dialog.start_switch()
            self._wait_for_worker(dialog)
            self.assertEqual(dialog.active_branch, "feat/pretest-check")
            self.assertEqual(saved[-1], ["feat/pretest-check", "main"])
            dialog.close()
            dialog.deleteLater()
            self.app.processEvents()
            from PySide6.QtCore import QCoreApplication, QEvent
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
