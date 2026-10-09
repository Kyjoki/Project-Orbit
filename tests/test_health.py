import unittest
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from orbit.health import local_targets
from orbit.models import Link, Project

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    QApplication = None


class HealthTargetTests(unittest.TestCase):
    def test_only_loopback_site_and_links_are_monitored(self):
        project = Project(
            name="WishList", folder="C:/site", site_url="http://127.0.0.1:5173",
            links=[Link("API", "http://localhost:8010/docs"),
                   Link("GitHub", "https://github.com/example/repo"),
                   Link("Duplicate", "http://127.0.0.1:5173")],
        )
        self.assertEqual(local_targets(project), [
            ("Сайт", "http://127.0.0.1:5173"),
            ("API", "http://localhost:8010/docs"),
        ])

    def test_external_or_malformed_urls_are_excluded(self):
        project = Project(name="Site", folder="C:/site", site_url="http://example.com",
                          links=[Link("Bad", "http://localhost.evil.test"),
                                 Link("IPv6", "http://[::1]:8010/health")])
        self.assertEqual(local_targets(project), [("IPv6", "http://[::1]:8010/health")])


@unittest.skipUnless(QApplication is not None and os.environ.get("ORBIT_HEALTH_INTEGRATION") == "1",
                     "local HTTP integration")
class LocalHealthMonitorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_reports_success_and_http_error_without_blocking(self):
        from orbit.health import LocalHealthMonitor

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200 if self.path == "/ok" else 503)
                self.end_headers()
                self.wfile.write(b"test")

            def log_message(self, *_):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        monitor = LocalHealthMonitor(interval_ms=60_000)
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            ok, bad = base + "/ok", base + "/bad"
            monitor.set_targets({ok, bad})
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                self.app.processEvents()
                if monitor.states.get(ok) == "online" and monitor.states.get(bad) == "offline":
                    break
                time.sleep(0.01)
            self.assertEqual(monitor.states.get(ok), "online")
            self.assertEqual(monitor.states.get(bad), "offline")
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            monitor.check_now()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and monitor.states.get(ok) != "offline":
                self.app.processEvents()
                time.sleep(0.01)
            self.assertEqual(monitor.states.get(ok), "offline")
        finally:
            monitor.stop()
            monitor.deleteLater()
            self.app.processEvents()
            from PySide6.QtCore import QCoreApplication, QEvent
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            server.server_close()
            if thread.is_alive():
                server.shutdown()
                thread.join(timeout=2)
