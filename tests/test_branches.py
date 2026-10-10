import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from orbit.branches import BranchError, current_branch, list_remote_branches, switch_branch


class BranchSafetyTests(unittest.TestCase):
    def test_rejects_dirty_checkout_before_fetch_or_switch(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            calls = []

            def run(args, **_kwargs):
                calls.append(args)
                if "--show-toplevel" in args:
                    output = str(root)
                elif "status" in args:
                    output = " M main.py\n"
                else:
                    output = "main"
                return subprocess.CompletedProcess(args, 0, output, "")

            with self.assertRaisesRegex(BranchError, "локальные изменения"):
                switch_branch(root, "feat/pretest-check", run=run)
            self.assertFalse(any("fetch" in args or "switch" in args for args in calls))


@unittest.skipUnless(os.environ.get("ORBIT_GIT_INTEGRATION") == "1", "local Git integration")
class BranchIntegrationTests(unittest.TestCase):
    def test_lists_and_switches_shallow_clone_without_second_copy(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            remote, seed, local = (root / name for name in ("remote.git", "seed", "local"))

            def git(*args):
                result = subprocess.run(["git", *map(str, args)], check=True,
                                        capture_output=True, text=True, encoding="utf-8")
                return result.stdout.strip()

            git("init", "--bare", remote)
            git("-C", remote, "symbolic-ref", "HEAD", "refs/heads/main")
            git("clone", remote, seed)
            (seed / "main.py").write_text("print('main')\n", encoding="utf-8")
            git("-C", seed, "add", "main.py")
            git("-C", seed, "-c", "user.name=OrbitTest", "-c", "user.email=orbit@example.invalid",
                "commit", "-m", "main")
            git("-C", seed, "push", "-u", "origin", "HEAD:main")
            git("-C", seed, "switch", "-c", "feat/pretest-check")
            (seed / "main.py").write_text("print('feature')\n", encoding="utf-8")
            git("-C", seed, "add", "main.py")
            git("-C", seed, "-c", "user.name=OrbitTest", "-c", "user.email=orbit@example.invalid",
                "commit", "-m", "feature")
            git("-C", seed, "push", "-u", "origin", "HEAD:feat/pretest-check")
            git("clone", "--depth=1", "--single-branch", "--branch", "main", remote.as_uri(), local)

            self.assertEqual(list_remote_branches(local), ["feat/pretest-check", "main"])
            self.assertEqual(current_branch(local), "main")
            switch_branch(local, "feat/pretest-check")
            self.assertEqual(current_branch(local), "feat/pretest-check")
            self.assertEqual((local / "main.py").read_text(encoding="utf-8"), "print('feature')\n")
            self.assertEqual(git("-C", local, "rev-parse", "--abbrev-ref", "--symbolic-full-name",
                                 "@{upstream}"), "origin/feat/pretest-check")
            self.assertEqual(len(list(root.glob("local*"))), 1)
            switch_branch(local, "main")
            self.assertEqual((local / "main.py").read_text(encoding="utf-8"), "print('main')\n")
