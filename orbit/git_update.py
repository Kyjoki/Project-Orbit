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

    def probe(*arguments: str, timeout: int = 30) -> subprocess.CompletedProcess:
        args = ["git", "-C", str(root), *arguments]
        environment = os.environ.copy()
        environment["GIT_TERMINAL_PROMPT"] = "0"
        try:
            return run(args, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, env=environment)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GitUpdateError(f"Не удалось выполнить Git: {exc}") from exc

    def git(*arguments: str, timeout: int = 30) -> str:
        result = probe(*arguments, timeout=timeout)
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
        upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    except GitUpdateError as exc:
        raise GitUpdateError("У ветки нет настроенного источника обновлений (upstream).") from exc
    if "/" not in upstream:
        raise GitUpdateError("Источник обновлений должен быть веткой удалённого репозитория.")
    remote, branch = upstream.split("/", 1)
    if git("status", "--porcelain", "--untracked-files=no"):
        raise GitUpdateError("В проекте есть локальные изменения. Сохраните их коммитом или уберите перед обновлением.")

    before = git("rev-parse", "HEAD")
    refspec = f"+refs/heads/{branch}:refs/remotes/{upstream}"
    git("fetch", "--no-tags", remote, refspec, timeout=600)
    target = git("rev-parse", upstream)
    if target != before:
        for deepen in (32, 64, 128, 256):
            if probe("merge-base", "--is-ancestor", before, target).returncode == 0:
                break
            if git("rev-parse", "--is-shallow-repository") != "true":
                raise GitUpdateError("Локальная ветка расходится с GitHub. Автоматическое слияние не выполняется.")
            git("fetch", "--no-tags", f"--deepen={deepen}", remote, refspec, timeout=600)
            target = git("rev-parse", upstream)
        if probe("merge-base", "--is-ancestor", before, target).returncode != 0:
            raise GitUpdateError("Не удалось подтвердить безопасное обновление: история Git слишком короткая или ветки расходятся.")
        git("merge", "--ff-only", upstream, timeout=600)
    after = git("rev-parse", "HEAD")
    return GitUpdateResult(before, after)
