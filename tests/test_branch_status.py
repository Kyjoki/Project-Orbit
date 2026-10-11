import unittest
import subprocess

from orbit.branch_status import compare_branch_heads, github_repository


class BranchStatusTests(unittest.TestCase):
    def test_remote_only_branches_report_both_merged_and_unmerged(self):
        heads = {"main": "a" * 40, "feat/merged": "b" * 40,
                 "feat/new": "c" * 40}
        answers = {"b" * 40: {"ahead_by": 0}, "c" * 40: {"ahead_by": 3}}

        result = compare_branch_heads(
            "https://github.com/example/project.git", heads,
            lambda _repo, _base, head: answers[head])

        self.assertEqual(result, {"main": "merged", "feat/merged": "merged",
                                  "feat/new": "unmerged"})

    def test_failed_or_invalid_compare_is_unknown(self):
        heads = {"main": "a" * 40, "feat/error": "b" * 40,
                 "feat/invalid": "c" * 40}

        def fetch(_repo, _base, head):
            if head == "b" * 40:
                raise OSError("unavailable")
            return {"status": "ahead"}

        result = compare_branch_heads("git@github.com:example/project.git", heads, fetch)
        self.assertEqual(result["feat/error"], "unknown")
        self.assertEqual(result["feat/invalid"], "unknown")

    def test_non_github_remote_stays_unknown(self):
        self.assertIsNone(github_repository("https://gitlab.com/example/project.git"))
        result = compare_branch_heads("https://gitlab.com/example/project.git",
                                      {"main": "a" * 40, "feat/x": "b" * 40},
                                      lambda *_: self.fail("Unexpected request"))
        self.assertEqual(result["feat/x"], "unknown")

    def test_timeout_leaves_branch_unverified(self):
        result = compare_branch_heads(
            "https://github.com/example/project", {"main": "a" * 40, "feat/slow": "b" * 40},
            lambda *_: (_ for _ in ()).throw(subprocess.TimeoutExpired("gh", 15)))
        self.assertEqual(result["feat/slow"], "unknown")


if __name__ == "__main__":
    unittest.main()
