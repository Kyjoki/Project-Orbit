import sqlite3
from pathlib import Path

from .models import Command, Link, Project


class ProjectStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, folder TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'Другое',
                description TEXT NOT NULL DEFAULT '', repository_url TEXT NOT NULL DEFAULT '',
                site_url TEXT NOT NULL DEFAULT '', editor_command TEXT NOT NULL DEFAULT 'code'
            );
            CREATE TABLE IF NOT EXISTS commands (
                id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                name TEXT NOT NULL, command TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                title TEXT NOT NULL, url TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY, value TEXT NOT NULL
            );
        """)
        columns = {row["name"] for row in self.db.execute("PRAGMA table_info(projects)")}
        if "kind" not in columns:
            with self.db:
                self.db.execute("ALTER TABLE projects ADD COLUMN kind TEXT NOT NULL DEFAULT 'Другое'")

    def save(self, project: Project) -> Project:
        if not project.name.strip() or not project.folder.strip():
            raise ValueError("Укажите название и папку проекта.")
        if any(not c.name.strip() or not c.command.strip() for c in project.commands):
            raise ValueError("У каждой команды должны быть название и строка запуска.")
        if any(not link.title.strip() or not link.url.strip() for link in project.links):
            raise ValueError("У каждой ссылки должны быть название и адрес.")
        values = (project.name.strip(), project.folder.strip(), project.kind.strip() or "Другое", project.description,
                  project.repository_url.strip(), project.site_url.strip(), project.editor_command.strip())
        with self.db:
            if project.id is None:
                cursor = self.db.execute("""INSERT INTO projects
                    (name, folder, kind, description, repository_url, site_url, editor_command)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""", values)
                project.id = cursor.lastrowid
            else:
                cursor = self.db.execute("""UPDATE projects SET name=?, folder=?, kind=?, description=?,
                    repository_url=?, site_url=?, editor_command=? WHERE id=?""", (*values, project.id))
                if cursor.rowcount == 0:
                    raise ValueError("Проект больше не существует.")
                self.db.execute("DELETE FROM commands WHERE project_id=?", (project.id,))
                self.db.execute("DELETE FROM links WHERE project_id=?", (project.id,))
            self.db.executemany("INSERT INTO commands (project_id, name, command) VALUES (?, ?, ?)",
                                [(project.id, c.name.strip(), c.command.strip()) for c in project.commands])
            self.db.executemany("INSERT INTO links (project_id, title, url) VALUES (?, ?, ?)",
                                [(project.id, link.title.strip(), link.url.strip()) for link in project.links])
        return self.get(project.id)

    def get(self, project_id: int) -> Project | None:
        row = self.db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if row is None:
            return None
        commands = [Command(name=c["name"], command=c["command"], id=c["id"])
                    for c in self.db.execute("SELECT * FROM commands WHERE project_id=? ORDER BY id", (project_id,))]
        links = [Link(title=link["title"], url=link["url"], id=link["id"])
                 for link in self.db.execute("SELECT * FROM links WHERE project_id=? ORDER BY id", (project_id,))]
        return Project(name=row["name"], folder=row["folder"], kind=row["kind"], description=row["description"],
                       repository_url=row["repository_url"], site_url=row["site_url"],
                       editor_command=row["editor_command"], commands=commands, links=links, id=row["id"])

    def list_projects(self) -> list[Project]:
        ids = [row["id"] for row in self.db.execute("SELECT id FROM projects ORDER BY name COLLATE NOCASE")]
        return [self.get(project_id) for project_id in ids]

    def delete(self, project_id: int) -> None:
        with self.db:
            self.db.execute("DELETE FROM projects WHERE id=?", (project_id,))

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.db:
            self.db.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    def close(self) -> None:
        self.db.close()
