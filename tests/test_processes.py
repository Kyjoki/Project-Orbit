import sys
import time
import unittest
import subprocess
import os
import ctypes

from orbit.processes import ProcessManager


class ProcessManagerTests(unittest.TestCase):
    def setUp(self):
        self.manager = ProcessManager()

    def tearDown(self):
        self.manager.stop_all()

    def test_start_streams_output_and_reports_exit(self):
        command = f'"{sys.executable}" -u -c "print(12345)"'
        self.manager.start(1, command, ".")
        deadline = time.monotonic() + 5
        events = []
        while time.monotonic() < deadline:
            events.extend(self.manager.drain_events())
            if any(event.kind == "finished" for event in events):
                break
            time.sleep(0.02)
        self.assertIn("12345", "".join(e.text for e in events if e.kind == "output"))
        self.assertTrue(any(e.kind == "finished" for e in events))

    def test_duplicate_start_is_rejected(self):
        command = f'"{sys.executable}" -u -c "import time; time.sleep(10)"'
        self.manager.start(2, command, ".")
        with self.assertRaises(ValueError):
            self.manager.start(2, command, ".")

    def test_stop_all_waits_for_its_output_threads(self):
        command = f'"{sys.executable}" -u -c "import time; time.sleep(10)"'
        self.manager.start(9, command, ".")
        self.manager.stop_all()
        self.assertFalse(self.manager.is_running(9))
        self.assertFalse(any(thread.is_alive() for thread in self.manager._threads))

    def test_stop_does_not_touch_unowned_process(self):
        command = f'"{sys.executable}" -u -c "import time; time.sleep(10)"'
        unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
        try:
            self.manager.start(3, command, ".")
            self.manager.stop(3)
            deadline = time.monotonic() + 5
            while self.manager.is_running(3) and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertFalse(self.manager.is_running(3))
            self.assertIsNone(unrelated.poll())
        finally:
            unrelated.kill()
            unrelated.wait()

    @unittest.skipUnless(os.name == "nt", "Windows process tree test")
    def test_stop_ends_spawned_child(self):
        command = f'"{sys.executable}" -u -c "import os,time; print(os.getpid(),flush=True); time.sleep(10)"'
        self.manager.start(4, command, ".")
        child_pid = None
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and child_pid is None:
            for event in self.manager.drain_events():
                if event.kind == "output" and event.text.strip().isdigit():
                    child_pid = int(event.text.strip())
            time.sleep(0.02)
        self.assertIsNotNone(child_pid)
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x00100000, False, child_pid)
        self.assertTrue(handle)
        try:
            self.manager.stop(4)
            self.assertEqual(kernel32.WaitForSingleObject(handle, 5000), 0)
        finally:
            kernel32.CloseHandle(handle)


if __name__ == "__main__":
    unittest.main()
