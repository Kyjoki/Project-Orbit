"""GitHub discovery and cloning without storing credentials in Orbit."""

import json
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .models import Command


class GithubError(Exception):
    pass


_SEGMENT = re.compile(r"[A-Za-z0-9_.-]{1,100}\Z")
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                     *(f"LPT{i}" for i in range(1, 10))}


def _safe_segment(value: str) -> bool:
    return (bool(_SEGMENT.fullmatch(value)) and value not in (".", "..")
            and value.rstrip(". ") == value and value.upper().split(".")[0] not in _WINDOWS_RESERVED)


@dataclass(frozen=True)
class GithubRepository:
    name: str
    full_name: str
    description: str
    html_url: str
    clone_url: str
    private: bool
    homepage: str = ""

    @classmethod
    def from_payload(cls, full_name: str, description: str = "", private: bool = False,
                     homepage: str = "") -> "GithubRepository":
        parts = full_name.split("/")
        if len(parts) != 2 or not all(_safe_segment(part) for part in parts):
            raise GithubError("GitHub вернул некорректное имя репозитория.")
        url = f"https://github.com/{full_name}"
        return cls(parts[1], full_name, description or "", url, url + ".git", private,
                   homepage if homepage.startswith(("http://", "https://")) else "")


def _fetch_public_page(username: str, page: int) -> list[dict]:
    url = f"https://api.github.com/users/{username}/repos?type=owner&sort=updated&per_page=100&page={page}"
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "Project-Orbit",
    })
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise GithubError("Пользователь GitHub не найден.") from exc
        if exc.code in (403, 429):
            raise GithubError("GitHub ограничил запросы. Попробуйте позже или войдите через GitHub CLI.") from exc
        raise GithubError(f"GitHub вернул ошибку HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise GithubError(f"Не удалось связаться с GitHub: {exc}") from exc
    if not isinstance(payload, list):
        raise GithubError("Неожиданный ответ GitHub.")
    return payload


def list_public_repositories(username: str, fetch_page: Callable[[str, int], list[dict]] = _fetch_public_page,
                             cancelled: Callable[[], bool] = lambda: False) -> list[GithubRepository]:
    if not _safe_segment(username):
        raise GithubError("Укажите корректное имя пользователя GitHub.")
    repos: list[GithubRepository] = []
    for page in range(1, 11):
        if cancelled():
            return []
        payload = fetch_page(username, page)
        if not isinstance(payload, list):
            raise GithubError("Неожиданный ответ GitHub.")
        if not payload:
            break
        for item in payload:
            if not isinstance(item, dict):
                raise GithubError("Неожиданный ответ GitHub.")
            repos.append(GithubRepository.from_payload(
                str(item.get("full_name", "")), str(item.get("description") or ""),
                bool(item.get("private", False)), str(item.get("homepage") or "")))
    return repos


def list_authenticated_repositories(username: str, run=subprocess.run,
                                    find_gh=shutil.which) -> list[GithubRepository]:
    if not _safe_segment(username):
        raise GithubError("Укажите корректное имя пользователя GitHub.")
    gh = find_gh("gh")
    if not gh:
        raise GithubError("Установите GitHub CLI (`winget install GitHub.cli`) и выполните `gh auth login`.")
    args = [gh, "repo", "list", username, "--limit", "1000", "--json",
            "name,nameWithOwner,description,url,isPrivate,homepageUrl"]
    try:
        result = run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GithubError(f"Не удалось получить репозитории через GitHub CLI: {exc}") from exc
    if result.returncode != 0:
        raise GithubError("GitHub CLI не авторизован или запрос не удался. Выполните `gh auth login`. " +
                          (result.stderr or "").strip()[:300])
    try:
        payload = json.loads(result.stdout)
        if not isinstance(payload, list):
            raise ValueError()
        return [GithubRepository.from_payload(
            str(item.get("nameWithOwner", "")), str(item.get("description") or ""),
            bool(item.get("isPrivate", False)), str(item.get("homepageUrl") or ""))
            for item in payload]
    except (ValueError, AttributeError) as exc:
        raise GithubError("GitHub CLI вернул неожиданный ответ.") from exc


def clone_repository(repo: GithubRepository, parent: Path, run=subprocess.run) -> Path:
    if not _safe_segment(repo.name) or repo.full_name.split("/")[-1] != repo.name:
        raise GithubError("Некорректное имя репозитория.")
    parent = parent.expanduser().resolve()
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / repo.name
    if destination.exists():
        raise FileExistsError(f"Папка уже существует: {destination}. Выберите другую папку или добавьте локальный проект.")
    if repo.private:
        gh = shutil.which("gh")
        if not gh:
            raise GithubError("Для приватного репозитория установите GitHub CLI и выполните `gh auth login`.")
        args = [gh, "repo", "clone", repo.full_name, str(destination)]
    else:
        args = ["git", "clone", "--", repo.clone_url, str(destination)]
    try:
        result = run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GithubError(f"Не удалось скачать репозиторий: {exc}") from exc
    if result.returncode != 0:
        raise GithubError("Не удалось скачать репозиторий. " + (result.stderr or result.stdout or "").strip()[:400])
    if not destination.is_dir():
        raise GithubError("Git сообщил об успехе, но папка проекта не найдена.")
    return destination


def suggest_commands(folder: Path) -> list[Command]:
    """Suggest launch commands from filenames only; never execute project code."""
    commands: list[Command] = []
    for subdir, label in (("", "Frontend"), ("frontend", "Frontend"),
                          ("client", "Client"), ("web", "Web")):
        manifest = folder / subdir / "package.json"
        if not manifest.is_file() or manifest.stat().st_size > 1_000_000:
            continue
        try:
            scripts = json.loads(manifest.read_text(encoding="utf-8")).get("scripts", {})
        except (OSError, ValueError, AttributeError):
            continue
        script = "dev" if "dev" in scripts else "start" if "start" in scripts else None
        if script:
            prefix = f"cd {subdir} && " if subdir else ""
            commands.append(Command(label, prefix + ("npm run dev" if script == "dev" else "npm start")))
    for subdir, label in (("", "Python"), ("backend", "Backend"),
                          ("server", "Server"), ("api", "API")):
        for entry in ("main.py", "app.py", "bot.py"):
            if (folder / subdir / entry).is_file():
                prefix = f"cd {subdir} && " if subdir else ""
                commands.append(Command(label, prefix + f"python {entry}"))
                break
    return commands
