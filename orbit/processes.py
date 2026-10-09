"""Run only user-started commands and expose their output without blocking Qt."""

import os
import queue
import signal
import subprocess
import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessEvent:
    command_id: int
    kind: str
    text: str = ""


class ProcessManager:
    def __init__(self):
        self._processes: dict[int, subprocess.Popen] = {}
        self._events: queue.Queue[ProcessEvent] = queue.Queue()
        self._lock = threading.Lock()
        self._threads: list[threading.Thread] = []

    def start(self, command_id: int, command: str, folder: str) -> None:
        if not command.strip():
            raise ValueError("Пустая команда запуска.")
        if not os.path.isdir(folder):
            raise ValueError("Папка проекта не существует.")
        with self._lock:
            previous = self._processes.get(command_id)
            if previous is not None and previous.poll() is None:
                raise ValueError("Команда уже запущена.")
            options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
            process = subprocess.Popen(
                command, cwd=folder, shell=True, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, errors="replace", bufsize=1, **options,
            )
            self._processes[command_id] = process
        self._events.put(ProcessEvent(command_id, "started", f"PID {process.pid}"))
        readers = [
            threading.Thread(target=self._read_output, args=(command_id, process), daemon=True),
            threading.Thread(target=self._watch, args=(command_id, process), daemon=True),
        ]
        with self._lock:
            self._threads = [thread for thread in self._threads if thread.is_alive()]
            self._threads.extend(readers)
        for thread in readers:
            thread.start()

    def _read_output(self, command_id: int, process: subprocess.Popen) -> None:
        try:
            for line in process.stdout:
                self._events.put(ProcessEvent(command_id, "output", line))
        finally:
            process.stdout.close()

    def _watch(self, command_id: int, process: subprocess.Popen) -> None:
        code = process.wait()
        self._events.put(ProcessEvent(command_id, "finished", str(code)))
        with self._lock:
            if self._processes.get(command_id) is process:
                del self._processes[command_id]

    def is_running(self, command_id: int) -> bool:
        with self._lock:
            process = self._processes.get(command_id)
            return process is not None and process.poll() is None

    def stop(self, command_id: int) -> None:
        with self._lock:
            process = self._processes.get(command_id)
        if process is None or process.poll() is not None:
            return
        if os.name == "nt":
            from .windows_process_tree import terminate_tree
            terminate_tree(process.pid)
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        self._events.put(ProcessEvent(command_id, "stopping"))

    def stop_all(self) -> None:
        with self._lock:
            ids = list(self._processes)
            threads = list(self._threads)
        for command_id in ids:
            try:
                self.stop(command_id)
            except (OSError, subprocess.TimeoutExpired):
                pass
        for thread in threads:
            thread.join(timeout=5)

    def drain_events(self, limit: int = 200) -> list[ProcessEvent]:
        events = []
        while len(events) < limit:
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                return events
        return events
