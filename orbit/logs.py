"""Timestamped, size-bounded command logs written away from the UI thread."""

import queue
import threading
from datetime import datetime
from pathlib import Path


def timestamp_lines(value: str, now: datetime | None = None) -> str:
    if not value:
        return ""
    stamp = (now or datetime.now()).strftime("[%Y-%m-%d %H:%M:%S] ")
    return "".join(stamp + line.rstrip("\r\n") + "\n" for line in value.splitlines(keepends=True))


class LogStore:
    def __init__(self, directory: Path, per_command_bytes: int = 1_048_576,
                 total_bytes: int = 20_971_520):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.per_command_bytes = per_command_bytes
        self.total_bytes = total_bytes
        self.error: OSError | None = None
        self._closed = False
        self._queue: queue.Queue[tuple[str, int, str]] = queue.Queue()
        self._thread = threading.Thread(target=self._work, name="OrbitLogWriter")
        self._thread.start()

    def _path(self, command_id: int) -> Path:
        if not isinstance(command_id, int) or command_id < 1:
            raise ValueError("Invalid command ID")
        return self.directory / f"{command_id}.log"

    def append(self, command_id: int, value: str) -> None:
        self._path(command_id)
        if value:
            self._queue.put(("append", command_id, value))

    def delete(self, command_id: int) -> None:
        self._path(command_id)
        self._queue.put(("delete", command_id, ""))

    def prune(self, valid_ids: set[int]) -> None:
        for path in self.directory.glob("*.log"):
            if path.stem.isdigit() and int(path.stem) not in valid_ids:
                self.delete(int(path.stem))

    def read(self, command_id: int) -> str:
        path = self._path(command_id)
        try:
            with path.open("rb") as stream:
                stream.seek(0, 2)
                stream.seek(max(0, stream.tell() - self.per_command_bytes))
                return stream.read().decode("utf-8", errors="replace")
        except FileNotFoundError:
            return ""

    def flush(self) -> None:
        self._queue.join()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._queue.put(("close", 0, ""))
        self._queue.join()
        self._thread.join()

    def _work(self) -> None:
        while True:
            action, command_id, value = self._queue.get()
            try:
                if action == "close":
                    return
                if action == "delete":
                    self._path(command_id).unlink(missing_ok=True)
                elif action == "append":
                    self._append_now(command_id, value)
            except OSError as exc:
                self.error = exc
            finally:
                self._queue.task_done()

    def _append_now(self, command_id: int, value: str) -> None:
        path = self._path(command_id)
        payload = value.encode("utf-8", errors="replace")[-self.per_command_bytes:]
        with path.open("ab") as stream:
            stream.write(payload)
        if path.stat().st_size > self.per_command_bytes:
            data = path.read_bytes()[-self.per_command_bytes:]
            newline = data.find(b"\n")
            if 0 <= newline < len(data) - 1:
                data = data[newline + 1:]
            path.write_bytes(data)
        self._enforce_total_limit()

    def _enforce_total_limit(self) -> None:
        files = sorted(self.directory.glob("*.log"), key=lambda path: path.stat().st_mtime_ns)
        total = sum(path.stat().st_size for path in files)
        for path in files:
            if total <= self.total_bytes:
                break
            size = path.stat().st_size
            path.unlink()
            total -= size
