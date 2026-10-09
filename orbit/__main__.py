import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .storage import ProjectStore
from .theme import apply_theme


def data_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
    return base / "ProjectOrbit" / "orbit.sqlite3"


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Project Orbit")
    apply_theme(app)
    window = MainWindow(ProjectStore(data_path()))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
