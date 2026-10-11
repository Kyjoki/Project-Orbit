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
              patch("orbit.branch_dialog.remote_branch_heads",
                    side_effect=lambda _folder: (time.sleep(0.15), {"main": "a" * 40,
                                                                  "feat/pretest-check": "b" * 40})[1]),
              patch("orbit.branch_dialog.origin_url", return_value="https://github.com/x/y.git"),
              patch("orbit.branch_dialog.compare_branch_heads", return_value={
                  "main": "merged", "feat/pretest-check": "unmerged"}),
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

    def test_delete_downloaded_branch_removes_it_from_saved_choices(self):
        from orbit.branch_dialog import BranchDialog

        saved = []
        with (patch("orbit.branch_dialog.current_branch", return_value="main"),
              patch("orbit.branch_dialog.remote_branch_heads",
                    return_value={"feat/pretest-check": "b" * 40, "main": "a" * 40}),
              patch("orbit.branch_dialog.origin_url", return_value="https://github.com/x/y.git"),
              patch("orbit.branch_dialog.compare_branch_heads", return_value={
                  "main": "merged", "feat/pretest-check": "unmerged"}),
              patch("orbit.branch_dialog.list_local_branches",
                    return_value=["feat/pretest-check", "main"]),
              patch("orbit.branch_dialog.delete_local_branch",
                    return_value="feat/pretest-check") as remove):
            dialog = BranchDialog(Path.cwd(), ["main", "feat/pretest-check"], saved.append)
            self._wait_for_worker(dialog)
            feature = next(dialog.branches.item(index) for index in range(dialog.branches.count())
                           if dialog.branches.item(index).data(Qt.ItemDataRole.UserRole) == "feat/pretest-check")
            dialog.branches.setCurrentItem(feature)
            self.assertTrue(dialog.delete_button.isEnabled())
            dialog.start_delete()
            self._wait_for_worker(dialog)
            remove.assert_called_once()
            self.assertEqual(saved[-1], ["main"])
            feature = next(dialog.branches.item(index) for index in range(dialog.branches.count())
                           if dialog.branches.item(index).data(Qt.ItemDataRole.UserRole) == "feat/pretest-check")
            self.assertFalse(feature.checkState() == Qt.CheckState.Checked)
            dialog.close()
            dialog.deleteLater()
            self.app.processEvents()

    def test_merged_branch_has_visible_main_badge(self):
        from orbit.branch_dialog import BranchDialog

        with (patch("orbit.branch_dialog.current_branch", return_value="main"),
              patch("orbit.branch_dialog.remote_branch_heads",
                    return_value={"main": "a" * 40, "feat/done": "b" * 40}),
              patch("orbit.branch_dialog.origin_url", return_value="https://github.com/x/y.git"),
              patch("orbit.branch_dialog.list_local_branches", return_value=["main", "feat/done"]),
              patch("orbit.branch_dialog.compare_branch_heads", return_value={
                  "main": "merged", "feat/done": "merged"})):
            dialog = BranchDialog(Path.cwd(), ["main", "feat/done"], lambda _: None)
            self._wait_for_worker(dialog)
            feature = next(dialog.branches.item(index) for index in range(dialog.branches.count())
                           if dialog.branches.item(index).data(Qt.ItemDataRole.UserRole) == "feat/done")
            self.assertIn("В main: да", feature.text())
            dialog.close()
            dialog.deleteLater()
            self.app.processEvents()

    def test_each_branch_shows_main_and_download_state_separately(self):
        from orbit.branch_dialog import BranchDialog

        with (patch("orbit.branch_dialog.current_branch", return_value="feat/current"),
              patch("orbit.branch_dialog.remote_branch_heads", return_value={
                  "main": "a" * 40, "feat/current": "b" * 40,
                  "feat/merged": "c" * 40, "feat/new": "d" * 40,
                  "feat/unclear": "e" * 40}),
              patch("orbit.branch_dialog.origin_url", return_value="https://github.com/x/y.git"),
              patch("orbit.branch_dialog.compare_branch_heads", return_value={
                  "main": "merged", "feat/current": "unmerged",
                  "feat/merged": "merged", "feat/new": "unmerged",
                  "feat/unclear": "unknown"}),
              patch("orbit.branch_dialog.list_local_branches", return_value=["main", "feat/current"])):
            dialog = BranchDialog(Path.cwd(), ["main"], lambda _: None)
            self._wait_for_worker(dialog)
            labels = {dialog.branches.item(i).data(Qt.ItemDataRole.UserRole): dialog.branches.item(i).text()
                      for i in range(dialog.branches.count())}
            self.assertIn("В main: да", labels["feat/merged"])
            self.assertIn("Не скачана", labels["feat/merged"])
            self.assertIn("В main: нет", labels["feat/new"])
            self.assertIn("В main: ?", labels["feat/unclear"])
            self.assertIn("Текущая", labels["feat/current"])
            self.assertIn("В main: нет", labels["feat/current"])
            dialog.close()
            dialog.deleteLater()
            self.app.processEvents()
