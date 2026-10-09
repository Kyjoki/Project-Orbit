"""Timestamp command output before showing it in the UI."""

from datetime import datetime


def timestamp_lines(value: str, now: datetime | None = None) -> str:
    if not value:
        return ""
    stamp = (now or datetime.now()).strftime("[%Y-%m-%d %H:%M:%S] ")
    return "".join(stamp + line.rstrip("\r\n") + "\n" for line in value.splitlines(keepends=True))
