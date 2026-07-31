import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.views.main_window import MainWindow


def load_stylesheet() -> str:
    style_path = Path(__file__).parent / "app" / "styles" / "style.qss"

    if not style_path.exists():
        return ""

    return style_path.read_text(encoding="utf-8")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("PandaIA BOT")
    app.setStyleSheet(load_stylesheet())

    window = MainWindow()
    window.showMaximized()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()