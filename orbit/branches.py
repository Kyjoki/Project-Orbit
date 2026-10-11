"""List, switch and remove local Git branches in one checkout."""

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
    return sorted(remote_branch_heads(folder, run), key=str.casefold)


def remote_branch_heads(folder: Path, run=subprocess.run) -> dict[str, str]:
    """List branch tip hashes from origin without downloading repository data."""
    git = _Git(folder, run)
    lines = git("ls-remote", "--heads", "origin", timeout=30).splitlines()
    prefix = "refs/heads/"
    heads = {}
    for line in lines:
        if "\t" in line:
            sha, ref = line.split("\t", 1)
            if ref.startswith(prefix):
                heads[ref[len(prefix):]] = sha
    return heads


def origin_url(folder: Path, run=subprocess.run) -> str:
    return _Git(folder, run)("remote", "get-url", "origin")


def list_local_branches(folder: Path, run=subprocess.run) -> list[str]:
    git = _Git(folder, run)
    return sorted(git("for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines(),
                  key=str.casefold)


def list_merged_local_branches(folder: Path, run=subprocess.run) -> list[str]:
    """Return branches Git can prove are contained in the local main branch."""
    git = _Git(folder, run)
    if git.probe("show-ref", "--verify", "--quiet", "refs/heads/main").returncode != 0:
        return []
    return sorted(git("for-each-ref", "--merged=refs/heads/main",
                      "--format=%(refname:short)", "refs/heads").splitlines(), key=str.casefold)


def delete_local_branch(folder: Path, branch: str, run=subprocess.run) -> str:
    """Remove only a downloaded branch whose commits are present on origin."""
    git = _Git(folder, run)
    if not branch or branch.startswith("-") or "\x00" in branch:
        raise BranchError("Некорректное имя ветки.")
    try:
        git("check-ref-format", "--branch", branch)
    except BranchError as exc:
        raise BranchError("Некорректное имя ветки.") from exc
    if git("branch", "--show-current") == branch:
        raise BranchError("Нельзя удалить текущую ветку. Сначала переключитесь на другую.")
    default_ref = git.probe("symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    default_branch = default_ref.stdout.strip().removeprefix("origin/") if default_ref.returncode == 0 else ""
    if branch == default_branch or (not default_branch and branch in {"main", "master"}):
        raise BranchError("Основную ветку проекта удалять нельзя.")
    if git.probe("show-ref", "--verify", "--quiet", f"refs/heads/{branch}").returncode != 0:
        raise BranchError("Эта ветка не загружена на компьютер.")
    remote_ref = f"refs/heads/{branch}"
    if git.probe("ls-remote", "--exit-code", "--heads", "origin", remote_ref,
                 timeout=30).returncode != 0:
        raise BranchError("Ветка не найдена на GitHub. Локальная копия сохранена.")
    fetch = ["fetch", "--no-tags"]
    if git("rev-parse", "--is-shallow-repository") == "true":
        fetch.append("--depth=1")
    git(*fetch, "origin", f"+{remote_ref}:refs/remotes/origin/{branch}", timeout=600)
    local_commit = git("rev-parse", f"refs/heads/{branch}")
    remote_commit = git("rev-parse", f"refs/remotes/origin/{branch}")
    if local_commit != remote_commit and git.probe(
        "merge-base", "--is-ancestor", local_commit, remote_commit
    ).returncode != 0:
        raise BranchError("В локальной ветке есть коммиты, которые не опубликованы на GitHub.")
    git("branch", "-D", "--", branch)
    return branch


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
