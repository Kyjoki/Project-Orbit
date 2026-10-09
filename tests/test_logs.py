import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from orbit.logs import LogStore, timestamp_lines


class LogTests(unittest.TestCase):
    def test_timestamp_is_added_to_each_output_line(self):
        now = datetime(2026, 10, 10, 12, 34, 56)
        self.assertEqual(timestamp_lines("one\ntwo\n", now),
                         "[2026-10-10 12:34:56] one\n[2026-10-10 12:34:56] two\n")

    def test_logs_survive_reopen_and_rotate_with_small_limits(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory)
            writer = LogStore(path, per_command_bytes=120, total_bytes=180)
            try:
                writer.append(1, "old\n" * 30)
                writer.append(1, "latest line\n")
                writer.flush()
                self.assertIn("latest line", writer.read(1))
                self.assertLessEqual((path / "1.log").stat().st_size, 120)
            finally:
                writer.close()
            reopened = LogStore(path, per_command_bytes=120, total_bytes=180)
            try:
                self.assertIn("latest line", reopened.read(1))
                reopened.append(2, "other\n" * 20)
                reopened.flush()
                self.assertLessEqual(sum(file.stat().st_size for file in path.glob("*.log")), 180)
            finally:
                reopened.close()

    def test_deleting_command_removes_its_log(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            store = LogStore(Path(directory))
            try:
                store.append(5, "secret\n")
                store.delete(5)
                store.flush()
                self.assertEqual(store.read(5), "")
            finally:
                store.close()
