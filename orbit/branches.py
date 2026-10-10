"""List and switch Git branches in one local checkout on explicit request."""

import os
import subprocess
from pathlib import Path


class BranchError(Exception):
    pass


class _Git:
    def __init__(self, folder: Path, run=subprocess.run):
        self.root = Path(folder).expanduser().resolve()
        self.run = run
        if not self.root.is_dir():
            raise BranchError("Папка проекта не найдена.")
        try:
            actual = Path(self("rev-parse", "--show-toplevel")).resolve()
        except (BranchError, OSError, ValueError) as exc:
            raise BranchError("В этой папке нет Git-репозитория.") from exc
        if os.path.normcase(str(actual)) != os.path.normcase(str(self.root)):
            raise BranchError("Выберите корневую папку Git-репозитория.")

    def probe(self, *arguments: str, timeout: int = 30) -> subprocess.CompletedProcess:
        args = ["git", "-C", str(self.root), *arguments]
        environment = os.environ.copy()
        environment["GIT_TERMINAL_PROMPT"] = "0"
        try:
            return self.run(args, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=timeout, env=environment)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BranchError(f"Git не завершил операцию: {exc}") from exc

    def __call__(self, *arguments: str, timeout: int = 30) -> str:
        result = self.probe(*arguments, timeout=timeout)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()[:400]
            raise BranchError(detail or "Git не смог выполнить операцию.")
        return result.stdout.strip()


def current_branch(folder: Path, run=subprocess.run) -> str:
    return _Git(folder, run)("branch", "--show-current")


def list_remote_branches(folder: Path, run=subprocess.run) -> list[str]:
    git = _Git(folder, run)
    lines = git("ls-remote", "--heads", "origin", timeout=30).splitlines()
    prefix = "refs/heads/"
    return sorted({line.split("\t", 1)[1][len(prefix):] for line in lines
                   if "\t" in line and line.split("\t", 1)[1].startswith(prefix)}, key=str.casefold)


def switch_branch(folder: Path, branch: str, run=subprocess.run) -> str:
    git = _Git(folder, run)
    if not branch or branch.startswith("-") or "\x00" in branch:
        raise BranchError("Некорректное имя ветки.")
    try:
        git("check-ref-format", "--branch", branch)
    except BranchError as exc:
        raise BranchError("Некорректное имя ветки.") from exc
    if git("status", "--porcelain", "--untracked-files=no"):
        raise BranchError("В проекте есть локальные изменения. Сохраните их перед переключением ветки.")
    if git("branch", "--show-current") == branch:
        return branch

    remote_ref = f"refs/heads/{branch}"
    git("ls-remote", "--exit-code", "--heads", "origin", remote_ref, timeout=30)
    fetch_spec = f"+{remote_ref}:refs/remotes/origin/{branch}"
    configured_result = git.probe("config", "--get-all", "remote.origin.fetch")
    configured = configured_result.stdout.strip() if configured_result.returncode == 0 else ""
    if fetch_spec not in configured.splitlines() and "+refs/heads/*:refs/remotes/origin/*" not in configured.splitlines():
        git("remote", "set-branches", "--add", "origin", branch)
    fetch = ["fetch", "--no-tags"]
    if git("rev-parse", "--is-shallow-repository") == "true":
        fetch.append("--depth=1")
    git(*fetch, "origin", fetch_spec, timeout=600)
    if git.probe("show-ref", "--verify", "--quiet", f"refs/heads/{branch}").returncode == 0:
        git("switch", branch)
        if git.probe("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}").returncode != 0:
            git("branch", "--set-upstream-to", f"origin/{branch}", branch)
    else:
        git("switch", "--track", "-c", branch, f"origin/{branch}")
    return branch
