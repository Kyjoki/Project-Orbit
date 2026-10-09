import unittest
from datetime import datetime

from orbit.logs import timestamp_lines


class LogTests(unittest.TestCase):
    def test_timestamp_is_added_to_each_output_line(self):
        now = datetime(2026, 10, 10, 12, 34, 56)
        self.assertEqual(timestamp_lines("one\ntwo\n", now),
                         "[2026-10-10 12:34:56] one\n[2026-10-10 12:34:56] two\n")
