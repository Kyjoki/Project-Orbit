import tempfile
import unittest
from pathlib import Path

from orbit.models import Command, Link, Project
from orbit.storage import ProjectStore


class ProjectStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.store = ProjectStore(Path(self.temp.name) / "orbit.db")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_project_and_commands_survive_reopen(self):
        project = Project(
            name="Site", folder="C:/work/site", description="Public site",
            repository_url="https://example.com/repo", site_url="https://example.com",
            editor_command="code", commands=[Command(name="Frontend", command="npm run dev")],
            links=[Link(title="Документация", url="https://example.com/docs")],
        )
        saved = self.store.save(project)
        self.store.close()
        self.store = ProjectStore(Path(self.temp.name) / "orbit.db")
        loaded = self.store.get(saved.id)
        self.assertEqual(loaded.name, "Site")
        self.assertEqual(loaded.commands[0].command, "npm run dev")
        self.assertEqual(loaded.site_url, "https://example.com")
        self.assertEqual(loaded.links[0].url, "https://example.com/docs")

    def test_project_type_is_persisted(self):
        saved = self.store.save(Project(name="Bot", folder="C:/bot", kind="Бот"))
        self.assertEqual(self.store.get(saved.id).kind, "Бот")

    def test_github_username_setting_survives_reopen(self):
        self.store.set_setting("github_username", "Kyjoki")
        self.store.close()
        self.store = ProjectStore(Path(self.temp.name) / "orbit.db")
        self.assertEqual(self.store.get_setting("github_username"), "Kyjoki")

    def test_selected_git_branches_survive_restart_and_project_deletion(self):
        project = self.store.save(Project(name="Argus", folder="C:/argus"))
        self.store.set_project_branches(project.id, ["feat/pretest-check", "main", "main"])
        self.store.close()
        self.store = ProjectStore(Path(self.temp.name) / "orbit.db")
        self.assertEqual(self.store.get_project_branches(project.id), ["feat/pretest-check", "main"])
        self.store.delete(project.id)
        self.assertEqual(self.store.get_project_branches(project.id), [])

    def test_old_database_gets_project_type_column(self):
        import sqlite3
        legacy_path = Path(self.temp.name) / "legacy.db"
        db = sqlite3.connect(legacy_path)
        db.execute("CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL, folder TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', repository_url TEXT NOT NULL DEFAULT '', site_url TEXT NOT NULL DEFAULT '', editor_command TEXT NOT NULL DEFAULT 'code')")
        db.execute("INSERT INTO projects(name, folder) VALUES('Old', 'C:/old')")
        db.commit()
        db.close()
        legacy = ProjectStore(legacy_path)
        try:
            self.assertEqual(legacy.list_projects()[0].kind, "Другое")
        finally:
            legacy.close()

    def test_update_replaces_commands_and_delete_cascades(self):
        saved = self.store.save(Project(name="Bot", folder="C:/bot", commands=[Command("Old", "old")]))
        saved.commands = [Command("Backend", "python main.py")]
        self.store.save(saved)
        self.assertEqual([c.name for c in self.store.get(saved.id).commands], ["Backend"])
        self.store.delete(saved.id)
        self.assertEqual(self.store.list_projects(), [])

    def test_rejects_empty_name_folder_and_command(self):
        for project in (
            Project(name=" ", folder="C:/x"),
            Project(name="A", folder=" "),
            Project(name="A", folder="C:/x", commands=[Command("Run", " ")]),
        ):
            with self.subTest(project=project), self.assertRaises(ValueError):
                self.store.save(project)


if __name__ == "__main__":
    unittest.main()
