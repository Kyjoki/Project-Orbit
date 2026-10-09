from dataclasses import dataclass, field


PROJECT_KINDS = ("Веб-сайт", "API", "Бот", "Расширение", "Приложение", "Другое")


@dataclass
class Command:
    name: str
    command: str
    id: int | None = None


@dataclass
class Link:
    title: str
    url: str
    id: int | None = None


@dataclass
class Project:
    name: str
    folder: str
    kind: str = "Другое"
    description: str = ""
    repository_url: str = ""
    site_url: str = ""
    editor_command: str = "code"
    commands: list[Command] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    id: int | None = None
