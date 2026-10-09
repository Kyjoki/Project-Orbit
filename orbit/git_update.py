"""Fetch only missing Git objects and fast-forward an existing local project."""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitUpdateError(Exception):
    pass


@dataclass(frozen=True)
class GitUpdateResult:
    before: str
    after: str

    @property
    def changed(self) -> bool:
        return self.before != self.after


def update_repository(folder: Path, run=subprocess.run) -> GitUpdateResult:
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        raise GitUpdateError("Папка проекта не найдена.")

    def git(*arguments: str, timeout: int = 30) -> str:
        args = ["git", "-C", str(root), *arguments]
        try:
            result = run(args, capture_output=True, text=True, encoding="utf-8",
                         errors="replace", timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GitUpdateError(f"Не удалось выполнить Git: {exc}") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()[:400]
            raise GitUpdateError(detail or "Git не смог выполнить обновление.")
        return result.stdout.strip()

    try:
        git_root = Path(git("rev-parse", "--show-toplevel")).resolve()
    except (GitUpdateError, OSError, ValueError) as exc:
        raise GitUpdateError("В этой папке нет Git-репозитория.") from exc
    if os.path.normcase(str(git_root)) != os.path.normcase(str(root)):
        raise GitUpdateError("Выберите корневую папку Git-репозитория для обновления.")
    try:
        git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    except GitUpdateError as exc:
        raise GitUpdateError("У ветки нет настроенного источника обновлений (upstream).") from exc
    if git("status", "--porcelain", "--untracked-files=no"):
        raise GitUpdateError("В проекте есть локальные изменения. Сохраните их коммитом или уберите перед обновлением.")

    before = git("rev-parse", "HEAD")
    git("pull", "--ff-only", "--no-rebase", "--no-tags", timeout=600)
    after = git("rev-parse", "HEAD")
    return GitUpdateResult(before, after)
