"""Dark space palette shared by all Project Orbit screens."""

from PySide6.QtGui import QColor, QFont, QPalette


STYLESHEET = """
* { outline: none; }
QWidget { color: #E7E9EF; font-family: 'Segoe UI'; font-size: 13px; }
QMainWindow, QDialog, #root { background: #14151A; }
QLabel { background: transparent; }
#sidebar { background: #101116; border-right: 1px solid #2A2D38; }
#title { font-size: 24px; font-weight: 700; color: #F2F4FA; }
#cardTitle { font-size: 15px; font-weight: 700; color: #F2F4FA; }
#sectionTitle { font-size: 16px; font-weight: 700; }
#muted { color: #98A0B0; }
#error { color: #FF6B6B; }
#smallCaption { color: #768093; font-size: 12px; }
#projectCard, #statCard, #detailSection {
    background: #1B1D24; border: 1px solid #2A2D38; border-radius: 12px;
}
#iconTile { background: #292744; border-radius: 10px; }
#statusBadge { border-radius: 11px; padding: 3px 10px; font-size: 12px; font-weight: 700; }
#statusBadge[state="running"] { color: #3DD598; background: #1C3B34; border: 1px solid #28614F; }
#statusBadge[state="stopped"] { color: #98A0B0; background: #252932; border: 1px solid #3A3F4D; }
#statusBadge[state="error"] { color: #FF6B6B; background: #3A242A; border: 1px solid #70424B; }
QPushButton { background: #23262F; border: 1px solid #3A3F4D; border-radius: 8px;
    padding: 7px 12px; min-height: 18px; }
QPushButton:hover { background: #303440; border-color: #5A6172; }
QPushButton:pressed { background: #20232C; }
QPushButton:disabled { color: #5C6270; background: #1B1D24; border-color: #2A2D38; }
QPushButton#primary { background: #7464EC; border-color: #8B7CFF; color: #FFFFFF; font-weight: 700; }
QPushButton#primary:hover { background: #8879FA; }
QPushButton#danger { background: #37252A; border-color: #70424B; color: #FF6B6B; font-weight: 700; }
QPushButton#danger:hover { background: #4A2C34; }
QToolButton#nav { border: none; border-radius: 10px; color: #98A0B0; background: transparent;
    font-size: 11px; padding: 6px 2px; }
QToolButton#nav:hover { background: #23262F; color: #FFFFFF; }
QToolButton#nav:checked { background: #292744; color: #FFFFFF; }
QToolButton#moreButton { background: #23262F; border: 1px solid #3A3F4D; border-radius: 8px; padding: 5px; }
QToolButton#moreButton::menu-indicator { image: none; }
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QTableWidget, QListWidget {
    background: #16181E; border: 1px solid #3A3F4D; border-radius: 8px;
    padding: 7px 10px; selection-background-color: #5A4EC1;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border-color: #8B7CFF; }
QComboBox QAbstractItemView { background: #23262F; border: 1px solid #3A3F4D; selection-background-color: #4C417F; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QPlainTextEdit { font-family: 'Cascadia Mono', Consolas, monospace; font-size: 12px; background: #0F1014; }
QHeaderView::section { background: #23262F; color: #B7BFCE; padding: 7px; border: 0; }
QMenu { background: #23262F; border: 1px solid #3A3F4D; padding: 6px; }
QMenu::item { padding: 7px 18px; }
QMenu::item:selected { background: #3D356C; }
QScrollBar:vertical { background: transparent; width: 9px; }
QScrollBar::handle:vertical { background: #383D4A; border-radius: 4px; min-height: 24px; }
"""


def apply_theme(app):
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#14151A"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#E7E9EF"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#16181E"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#E7E9EF"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#23262F"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#E7E9EF"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#7464EC"))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)
