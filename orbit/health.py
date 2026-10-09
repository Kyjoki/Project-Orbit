"""Asynchronous checks for local site and API links."""

from urllib.parse import urlsplit

from PySide6.QtCore import QObject, QTimer, Signal, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .models import Project


def _is_loopback_url(value: str) -> bool:
    try:
        parts = urlsplit(value)
        return (parts.scheme in ("http", "https")
                and parts.hostname in ("localhost", "127.0.0.1", "::1")
                and parts.username is None and parts.password is None)
    except ValueError:
        return False


def local_targets(project: Project) -> list[tuple[str, str]]:
    candidates = [("Сайт", project.site_url)] + [(link.title, link.url) for link in project.links]
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for label, url in candidates:
        if _is_loopback_url(url) and url not in seen:
            seen.add(url)
            result.append((label, url))
    return result


class LocalHealthMonitor(QObject):
    changed = Signal(str, str)

    def __init__(self, parent=None, interval_ms: int = 10_000):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self.targets: set[str] = set()
        self.states: dict[str, str] = {}
        self.pending: dict[str, QNetworkReply] = {}
        self.timer = QTimer(self)
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self.check_now)
        self.timer.start()

    def set_targets(self, urls: set[str]) -> None:
        removed = self.targets - urls
        for url in removed:
            reply = self.pending.pop(url, None)
            if reply:
                reply.abort()
            self.states.pop(url, None)
        added = urls - self.targets
        self.targets = set(urls)
        for url in added:
            self.states[url] = "checking"
            self._check(url)

    def check_now(self) -> None:
        for url in self.targets:
            self._check(url)

    def _check(self, url: str) -> None:
        if url in self.pending or url not in self.targets:
            return
        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(2_000)
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        reply = self.manager.get(request)
        reply.readyRead.connect(reply.readAll)
        self.pending[url] = reply
        reply.finished.connect(lambda r=reply, target=url: self._finished(target, r))

    def _finished(self, url: str, reply: QNetworkReply) -> None:
        if self.pending.get(url) is not reply:
            reply.deleteLater()
            return
        del self.pending[url]
        code = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        online = reply.error() == QNetworkReply.NetworkError.NoError and code is not None and 200 <= int(code) < 400
        state = "online" if online else "offline"
        if self.states.get(url) != state:
            self.states[url] = state
            self.changed.emit(url, state)
        reply.deleteLater()

    def stop(self) -> None:
        self.timer.stop()
        replies = list(self.pending.values())
        self.pending.clear()
        for reply in replies:
            reply.abort()
