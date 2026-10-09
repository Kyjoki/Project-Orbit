import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from orbit.github import (
    GithubError, GithubRepository, clone_repository,
    list_authenticated_repositories, list_public_repositories, suggest_commands,
)


class GithubTests(unittest.TestCase):
    def test_public_listing_uses_validated_github_urls_and_paginates(self):
        calls = []

        def fetch(username, page):
            calls.append((username, page))
            if page == 1:
                return [{"name": "site", "full_name": "Kyjoki/site", "description": "My site",
                         "html_url": "https://github.com/Kyjoki/site", "private": False,
                         "homepage": "https://example.com"}]
            return []

        repos = list_public_repositories("Kyjoki", fetch_page=fetch)
        self.assertEqual(calls, [("Kyjoki", 1), ("Kyjoki", 2)])
        self.assertEqual(repos[0].clone_url, "https://github.com/Kyjoki/site.git")
        self.assertEqual(repos[0].homepage, "https://example.com")

    def test_public_listing_rejects_malformed_names(self):
        with self.assertRaises(GithubError):
            list_public_repositories("bad/name")
        with self.assertRaises(GithubError):
            list_public_repositories("Kyjoki", fetch_page=lambda *_: [
                {"name": "..", "full_name": "Kyjoki/.."}])

    def test_authenticated_listing_uses_gh_without_token_in_command(self):
        seen = []

        def run(args, **kwargs):
            seen.append(args)
            data = [{"name": "private", "nameWithOwner": "Kyjoki/private",
                     "description": "Secret", "url": "https://github.com/Kyjoki/private",
                     "isPrivate": True, "homepageUrl": ""}]
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps(data), stderr="")

        repos = list_authenticated_repositories("Kyjoki", run=run, find_gh=lambda _: "gh")
        self.assertEqual(repos[0].private, True)
        self.assertEqual(seen[0][:3], ["gh", "repo", "list"])
        self.assertNotIn("token", " ".join(seen[0]).lower())

    def test_clone_refuses_to_replace_existing_directory(self):
        repo = GithubRepository("site", "Kyjoki/site", "", "https://github.com/Kyjoki/site",
                                "https://github.com/Kyjoki/site.git", False)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            (Path(folder) / "site").mkdir()
            with self.assertRaises(FileExistsError):
                clone_repository(repo, Path(folder), run=lambda *_args, **_kwargs: self.fail("git ran"))

    def test_clone_public_repository_to_selected_folder(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder)
            repo = GithubRepository("site", "Kyjoki/site", "", "https://github.com/Kyjoki/site",
                                    "https://github.com/Kyjoki/site.git", False)
            seen = []

            def run(args, **_kwargs):
                seen.append(args)
                Path(args[-1]).mkdir()
                return subprocess.CompletedProcess(args, 0, "", "")

            destination = clone_repository(repo, root / "projects", run=run)
            self.assertEqual(destination, root / "projects" / "site")
            self.assertEqual(seen[0][:4], ["git", "clone", "--", repo.clone_url])

    def test_suggestions_read_manifests_without_running_commands(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder)
            (root / "frontend").mkdir()
            (root / "frontend" / "package.json").write_text('{"scripts":{"dev":"vite"}}', encoding="utf-8")
            (root / "backend").mkdir()
            (root / "backend" / "main.py").write_text("print('hello')", encoding="utf-8")
            commands = suggest_commands(root)
            self.assertEqual([(c.name, c.command) for c in commands],
                             [("Frontend", "cd frontend && npm run dev"),
                              ("Backend", "cd backend && python main.py")])


if __name__ == "__main__":
    unittest.main()
