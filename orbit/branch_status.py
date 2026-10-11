"""Check whether remote branch commits are contained in GitHub's main branch."""

import json
import re
import shutil
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from urllib.parse import urlsplit


_NAME = re.compile(r"[A-Za-z0-9_.-]+\Z")
_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")


def github_repository(remote_url: str) -> str | None:
    """Return owner/repo for a github.com origin, without credentials."""
    if remote_url.startswith("git@github.com:"):
        path = remote_url[len("git@github.com:"):]
    else:
        parsed = urlsplit(remote_url)
        if parsed.scheme not in {"https", "ssh"} or parsed.hostname != "github.com":
            return None
        path = parsed.path.lstrip("/")
    parts = path.removesuffix(".git").split("/")
    if len(parts) != 2 or not all(_NAME.fullmatch(part) for part in parts):
        return None
    return "/".join(parts)


def _gh_path() -> str | None:
    gh = shutil.which("gh")
    if not gh:
        return None
    try:
        result = subprocess.run([gh, "auth", "status", "-h", "github.com"],
                                capture_output=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return gh if result.returncode == 0 else None


@lru_cache(maxsize=1024)
def _fetch_compare(repository: str, base: str, head: str, gh: str | None) -> dict:
    endpoint = f"repos/{repository}/compare/{base}...{head}?per_page=1"
    if gh:
        result = subprocess.run([gh, "api", endpoint], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=15)
        if result.returncode != 0:
            raise OSError("GitHub CLI не смог сравнить ветки.")
        return json.loads(result.stdout)
    request = urllib.request.Request(f"https://api.github.com/{endpoint}", headers={
        "Accept": "application/vnd.github+json", "User-Agent": "Project-Orbit",
    })
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def compare_branch_heads(remote_url: str, heads: dict[str, str], fetch_compare=None) -> dict[str, str]:
    """Return merged/unmerged/unknown against the remote main tip for every branch."""
    repository = github_repository(remote_url)
    result = {name: "unknown" for name in heads}
    base = heads.get("main")
    if not repository or not base or not _SHA.fullmatch(base):
        return result
    result["main"] = "merged"
    if fetch_compare is None:
        gh = _gh_path()
        fetch_compare = lambda repo, main, branch: _fetch_compare(repo, main, branch, gh)

    def check(name: str, sha: str) -> tuple[str, str]:
        if not _SHA.fullmatch(sha):
            return name, "unknown"
        try:
            payload = fetch_compare(repository, base, sha)
            ahead = payload.get("ahead_by") if isinstance(payload, dict) else None
            if type(ahead) is int and ahead >= 0:
                return name, "merged" if ahead == 0 else "unmerged"
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
            pass
        return name, "unknown"

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(check, name, sha) for name, sha in heads.items() if name != "main"]
        for future in as_completed(futures):
            name, status = future.result()
            result[name] = status
    return result
