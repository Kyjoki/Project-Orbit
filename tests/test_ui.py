import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    QApplication = None


@unittest.skipUnless(QApplication is not None, "Install PySide6 to run UI tests")
class WindowSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from orbit.main_window import MainWindow
        from orbit.models import Command, Project
        from orbit.storage import ProjectStore

        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.store = ProjectStore(Path(self.temp.name) / "ui.db")
        self.project = self.store.save(Project(
            name="Example Site", kind="Веб-сайт", folder=str(Path.cwd()),
            commands=[Command("Frontend", f'"{sys.executable}" -u -c "print(42)"')],
        ))
        self.window = MainWindow(self.store)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        from PySide6.QtCore import QCoreApplication, QEvent

        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.temp.cleanup()

    def test_cards_filter_and_detail_navigation(self):
        self.assertEqual(len(self.window.project_grid.items), 1)
        self.window.search.setText("missing")
        self.assertEqual(len(self.window.project_grid.items), 0)
        self.window.search.setText("example")
        self.window.open_project(self.project.id)
        self.assertEqual(self.window.detail_title.text(), "Example Site")
        self.assertEqual(len(self.window.command_controls), 1)

    def test_sidebar_buttons_have_equal_width(self):
        sizes = {(button.minimumWidth(), button.maximumWidth())
                 for button in self.window.nav_buttons.values()}
        self.assertEqual(sizes, {(68, 68)})

    def test_project_card_shows_local_site_and_api_states(self):
        from PySide6.QtWidgets import QLabel, QPushButton
        from orbit.project_card import ProjectCard

        card = ProjectCard(self.project, "running", [
            ("Сайт", "online", "http://127.0.0.1:5173"),
            ("API", "offline", "http://127.0.0.1:8010/docs"),
        ])
        plain_card = ProjectCard(self.project, "running")
        card.show()
        plain_card.show()
        self.app.processEvents()
        captions = " ".join(label.text() for label in card.findChildren(QLabel))
        self.assertIn("Сайт: доступен", captions)
        self.assertIn("API: недоступен", captions)
        self.assertEqual(card.height(), plain_card.height())
        card_run = next(button for button in card.findChildren(QPushButton) if button.text() == "Остановить")
        plain_run = next(button for button in plain_card.findChildren(QPushButton) if button.text() == "Остановить")
        self.assertEqual(card_run.y(), plain_run.y())
        card.close()
        card.deleteLater()
        plain_card.close()
        plain_card.deleteLater()
        self.app.processEvents()

    def test_project_update_is_explicit_and_uses_project_folder(self):
        from unittest.mock import patch

        self.window.open_project(self.project.id)
        self.assertTrue(self.window.update_button.isEnabled())
        with patch("orbit.main_window.GitUpdateDialog") as dialog:
            self.window.update_project()
        dialog.assert_called_once()
        self.assertEqual(dialog.call_args.args[0], Path(self.project.folder))
        self.assertFalse(self.window.processes.is_running(self.project.commands[0].id))

    def test_update_dialog_runs_git_outside_ui_thread(self):
        from unittest.mock import patch
        from orbit.git_update import GitUpdateResult
        from orbit.git_update_dialog import GitUpdateDialog

        dialog = GitUpdateDialog(Path(self.project.folder), self.window)

        def slow_update(_folder):
            time.sleep(0.2)
            return GitUpdateResult("old", "new")

        with patch("orbit.git_update_dialog.update_repository", side_effect=slow_update):
            started = time.monotonic()
            dialog.start_update()
            self.assertLess(time.monotonic() - started, 0.1)
            deadline = time.monotonic() + 5
            while dialog.worker is not None and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.01)
        self.assertIsNone(dialog.worker)
        self.assertIn("обновлено", dialog.status.text())
        dialog.close()
        dialog.deleteLater()
        self.app.processEvents()

    def test_command_output_reaches_log_view(self):
        command = self.project.commands[0]
        self.window.open_project(self.project.id)
        self.window.start_command(command.id, command.command, self.project.folder)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and "42" not in self.window.detail_log.toPlainText():
            self.app.processEvents()
            time.sleep(0.02)
        self.assertIn("42", self.window.detail_log.toPlainText())
        self.assertRegex(self.window.detail_log.toPlainText(), r"\[\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\] 42")
        self.assertFalse((Path(self.temp.name) / "logs").exists())

    def test_logs_are_memory_only_and_old_log_files_are_not_loaded(self):
        from orbit.main_window import MainWindow
        from orbit.storage import ProjectStore

        command_id = self.project.commands[0].id
        old_logs = Path(self.temp.name) / "logs"
        old_logs.mkdir(exist_ok=True)
        (old_logs / f"{command_id}.log").write_text("legacy log\n", encoding="utf-8")
        self.window.logs[command_id] = "[2026-10-10 12:00:00] current session\n"
        self.window.close()
        self.store = ProjectStore(Path(self.temp.name) / "ui.db")
        self.window = MainWindow(self.store)
        self.window.open_project(self.project.id)
        self.assertEqual(self.window.detail_log.toPlainText(), "")
        self.assertEqual((old_logs / f"{command_id}.log").read_text(encoding="utf-8"), "legacy log\n")

    def test_project_form_keeps_type_and_custom_link(self):
        from orbit.project_dialog import ProjectDialog

        dialog = ProjectDialog(self.project)
        dialog.add_link("Документация", "https://example.com/docs")
        dialog.validate_and_accept()
        result = dialog.result_project()
        self.assertEqual(result.kind, "Веб-сайт")
        self.assertEqual(result.links[0].title, "Документация")
        dialog.close()
        dialog.deleteLater()
        self.app.processEvents()

    def test_user_stop_is_not_shown_as_error(self):
        command = self.project.commands[0]
        self.window.start_command(command.id, f'"{sys.executable}" -u -c "import time; time.sleep(10)"',
                                  self.project.folder)
        self.window.stop_command(command.id)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.app.processEvents()
            if not self.window.processes.is_running(command.id):
                break
            time.sleep(0.02)
        self.app.processEvents()
        self.assertEqual(self.window._project_status(self.project), "stopped")

    def test_github_import_adds_local_project_without_starting_commands(self):
        from orbit.github import GithubRepository

        folder = Path(self.temp.name) / "remote-site"
        folder.mkdir()
        (folder / "package.json").write_text('{"scripts":{"dev":"vite"}}', encoding="utf-8")
        repo = GithubRepository.from_payload("Kyjoki/remote-site", "Imported site")
        self.window._finish_github_import(repo, folder)
        saved = next(project for project in self.store.list_projects() if project.name == "remote-site")
        self.assertEqual(saved.repository_url, "https://github.com/Kyjoki/remote-site")
        self.assertEqual(saved.commands[0].command, "npm run dev")
        self.assertFalse(self.window.processes.is_running(saved.commands[0].id))

    def test_github_browser_loads_repositories_without_blocking_window(self):
        from unittest.mock import patch
        from orbit.github import GithubRepository
        from orbit.github_dialog import GithubDialog

        repo = GithubRepository.from_payload("Kyjoki/example", "Sample")
        dialog = GithubDialog("", str(Path(self.temp.name)), set(), self.window)
        dialog.username.setText("Kyjoki")
        with patch("orbit.github_dialog.list_public_repositories", return_value=[repo]):
            dialog.refresh()
            deadline = time.monotonic() + 5
            while dialog.worker is not None and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.01)
        self.assertEqual(dialog.repo_list.count(), 1)
        dialog.repo_list.setCurrentRow(0)
        self.assertTrue(dialog.import_button.isEnabled())
        dialog.close()
        dialog.deleteLater()
        self.app.processEvents()
        from PySide6.QtCore import QCoreApplication, QEvent
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == "__main__":
    unittest.main()
