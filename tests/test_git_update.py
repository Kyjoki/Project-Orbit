import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from orbit.git_update import GitUpdateError, update_repository


class GitUpdateTests(unittest.TestCase):
    def test_refuses_local_changes_before_network(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            calls = []

            def run(args, **_kwargs):
                calls.append(args)
                if "--show-toplevel" in args:
                    output = str(root)
                elif "@{upstream}" in args:
                    output = "origin/main"
                elif "status" in args:
                    output = " M app.py\n"
                else:
                    output = "main"
                return subprocess.CompletedProcess(args, 0, output, "")

            with self.assertRaisesRegex(GitUpdateError, "локальные изменения"):
                update_repository(root, run=run)
            self.assertFalse(any("pull" in args for args in calls))

    def test_fast_forward_uses_existing_folder_and_upstream(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            calls = []
            commits = iter(["old", "new"])

            def run(args, **_kwargs):
                calls.append(args)
                if "--show-toplevel" in args:
                    output = str(root)
                elif "@{upstream}" in args:
                    output = "origin/main"
                elif "status" in args:
                    output = ""
                elif "rev-parse" in args and "HEAD" in args:
                    output = next(commits)
                else:
                    output = "main"
                return subprocess.CompletedProcess(args, 0, output, "")

            result = update_repository(root, run=run)
            self.assertEqual((result.before, result.after), ("old", "new"))
            pull = next(args for args in calls if "pull" in args)
            self.assertIn("--ff-only", pull)
            self.assertEqual(pull[0:3], ["git", "-C", str(root)])
            self.assertFalse(any("clone" in args for args in calls))

    def test_refuses_nested_folder(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            child = root / "child"
            child.mkdir()

            def run(args, **_kwargs):
                return subprocess.CompletedProcess(args, 0, str(root), "")

            with self.assertRaisesRegex(GitUpdateError, "корневую папку"):
                update_repository(child, run=run)

    @unittest.skipUnless(os.environ.get("ORBIT_GIT_INTEGRATION") == "1", "local Git integration")
    def test_fetches_new_commit_without_recloning(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            remote, seed, local = (root / name for name in ("remote.git", "seed", "local"))

            def git(*args):
                subprocess.run(["git", *map(str, args)], check=True, capture_output=True)

            git("init", "--bare", remote)
            git("-C", remote, "symbolic-ref", "HEAD", "refs/heads/main")
            git("clone", remote, seed)
            git("-C", seed, "-c", "user.name=OrbitTest", "-c", "user.email=orbit@example.invalid",
                "commit", "--allow-empty", "-m", "initial")
            git("-C", seed, "push", "-u", "origin", "HEAD:main")
            git("clone", remote, local)
            (seed / "new.txt").write_text("incremental update", encoding="utf-8")
            git("-C", seed, "add", "new.txt")
            git("-C", seed, "-c", "user.name=OrbitTest", "-c", "user.email=orbit@example.invalid",
                "commit", "-m", "add data")
            git("-C", seed, "push")

            result = update_repository(local)
            self.assertTrue(result.changed)
            self.assertEqual((local / "new.txt").read_text(encoding="utf-8"), "incremental update")
            self.assertTrue((local / ".git").exists())
