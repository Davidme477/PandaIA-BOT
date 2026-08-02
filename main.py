import os
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from app.views.main_window import MainWindow
from core.app_paths import configure_model_caches, initialize_user_data, is_frozen, resource_path


def load_stylesheet() -> str:
    style_path = resource_path("app", "styles", "style.qss")

    if not style_path.exists():
        return ""

    return style_path.read_text(encoding="utf-8")


def main() -> int:
    initialize_user_data()
    configure_model_caches()
    if "--overlay-server" in sys.argv:
        from overlay.server import run_server
        run_server()
        return 0
    if "--smoke-test" in sys.argv:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication(sys.argv)
    app.setApplicationName("PandaIA BOT")
    app.setOrganizationName("PandaIA")
    app.setWindowIcon(QIcon(str(resource_path("resources", "icons", "pandaia.ico"))))
    app.setStyleSheet(load_stylesheet())

    from core.single_instance import SingleInstance
    instance = SingleInstance()
    if not instance.acquire():
        return 0

    window = MainWindow()
    instance.activation_requested.connect(lambda: (window.showNormal(), window.raise_(), window.activateWindow()))
    window._single_instance = instance
    window.showMaximized()

    if "--smoke-test" in sys.argv:
        from PySide6.QtCore import QTimer
        for index in range(window.pages.count()):
            window.pages.setCurrentIndex(index)
            app.processEvents()
        QTimer.singleShot(1200, window.close)
    elif is_frozen():
        from core.first_run import first_run_pending
        if first_run_pending():
            from app.dialogs.first_run_dialog import FirstRunDialog
            FirstRunDialog(window).exec()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
