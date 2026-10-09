import unittest

from orbit.models import Project
from orbit.project_filters import filter_projects


class FilterProjectsTests(unittest.TestCase):
    def setUp(self):
        self.projects = [
            Project(name="Сайт", folder="C:/web", description="Портфолио", kind="Веб-сайт", id=1),
            Project(name="API", folder="C:/service", description="Сервер", kind="API", id=2),
        ]

    def test_searches_name_description_and_folder_case_insensitively(self):
        self.assertEqual([p.id for p in filter_projects(self.projects, "ПОРТФОЛИО")], [1])
        self.assertEqual([p.id for p in filter_projects(self.projects, "service")], [2])

    def test_combines_type_and_runtime_state(self):
        statuses = {1: "running", 2: "stopped"}
        result = filter_projects(self.projects, kind="API", state="stopped", statuses=statuses)
        self.assertEqual([p.id for p in result], [2])
        self.assertEqual(filter_projects(self.projects, kind="API", state="running", statuses=statuses), [])
