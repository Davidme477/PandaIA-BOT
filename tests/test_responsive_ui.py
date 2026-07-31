from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

PROJECT_DIR = Path(__file__).resolve().parents[1]
SITE_PACKAGES = PROJECT_DIR / ".venv" / "Lib" / "site-packages"
for path in (PROJECT_DIR, SITE_PACKAGES):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QSignalSpy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from app.dialogs.voice_dialog import VoiceDialog
from app.dialogs.personality_dialog import PersonalityDialog
from app.views.main_window import MainWindow
from app.views.dashboard_view import DashboardView
from app.widgets.responsive_grid import ResponsiveGrid, columns_for_width
from main import load_stylesheet


class ResponsiveUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(load_stylesheet())

    @staticmethod
    def rendered_color(widget, x: int = 2, y: int = 2):
        image = widget.grab().toImage()
        return image.pixelColor(
            min(max(0, x), image.width() - 1),
            min(max(0, y), image.height() - 1),
        )

    @staticmethod
    def luminance(color) -> float:
        return 0.2126 * color.red() + 0.7152 * color.green() + 0.0722 * color.blue()

    def test_breakpoints_cover_wide_medium_and_narrow(self) -> None:
        self.assertEqual(columns_for_width(1400, wide_columns=4), 4)
        self.assertEqual(columns_for_width(900, wide_columns=4), 2)
        self.assertEqual(columns_for_width(600, wide_columns=4), 1)

    def test_header_and_footer_fill_window_and_keep_dark_viewports(self) -> None:
        with patch.object(DashboardView, "load_ollama_models", lambda self: None):
            window = MainWindow()
        window.resize(1366, 768)
        window.show()
        self.app.processEvents()
        central_width = window.centralWidget().contentsRect().width()
        self.assertEqual(window.header.width(), central_width)
        self.assertEqual(window.footer.width(), central_width)
        self.assertEqual(window.header.horizontalScrollBar().maximum(), 0)
        self.assertEqual(window.footer.horizontalScrollBar().maximum(), 0)
        for container in (window.header, window.header.viewport(), window.footer, window.footer.viewport()):
            color = self.rendered_color(container)
            self.assertLess(self.luminance(color), 80, color.name())
        window.close()

    def test_grid_reflows_without_duplicating_widgets(self) -> None:
        grid = ResponsiveGrid(wide_columns=4, medium_columns=2)
        widgets = [QLabel(str(index)) for index in range(4)]
        for widget in widgets:
            grid.add_responsive_widget(widget)
        for width, columns in ((1400, 4), (900, 2), (600, 1)):
            grid.resize(width, 600)
            grid.reflow(force=True)
            self.assertEqual(grid.current_columns, columns)
            self.assertEqual(grid.grid.count(), 4)
            self.assertEqual(len({id(widget) for widget in grid.widgets}), 4)

    def test_personality_dialog_scrolls_without_overlap_and_keeps_actions_visible(self) -> None:
        dialog = PersonalityDialog(
            model="modelo", language="Español",
            custom_name="Personalidad", custom_prompt="Instrucciones extensas " * 20,
        )
        dialog.resize(dialog.minimumSize())
        dialog.show()
        self.app.processEvents()
        self.assertGreater(dialog.scroll_area.verticalScrollBar().maximum(), 0)
        self.assertTrue(dialog.cancel_button.isVisible())
        self.assertTrue(dialog.save_button.isVisible())
        self.assertGreaterEqual(
            dialog.actions_widget.geometry().top(),
            dialog.scroll_area.geometry().bottom(),
        )
        content_layout = dialog.scroll_area.widget().layout()
        geometries = [
            content_layout.itemAt(index).widget().geometry()
            for index in range(content_layout.count())
            if content_layout.itemAt(index).widget() is not None
        ]
        for previous, current in zip(geometries, geometries[1:]):
            self.assertLessEqual(previous.bottom(), current.top())
        dialog.close()

    def test_voice_dialog_is_dark_compact_and_screen_safe(self) -> None:
        dialog = VoiceDialog()
        dialog.show()
        self.app.processEvents()
        available = dialog.screen().availableGeometry()
        self.assertLessEqual(dialog.height(), available.height())
        self.assertLessEqual(dialog.width(), available.width())
        self.assertLess(dialog.scroll_area.widget().layout().itemAt(0).widget().geometry().top(), 30)
        self.assertTrue(dialog.cancel_button.isVisible())
        self.assertTrue(dialog.save_button.isVisible())
        self.assertGreaterEqual(dialog.actions_widget.geometry().top(), dialog.scroll_area.geometry().bottom())
        for container in (dialog, dialog.scroll_area.viewport(), dialog.scroll_area.widget()):
            color = self.rendered_color(container)
            self.assertLess(self.luminance(color), 80, color.name())
        title = dialog.findChild(QLabel, "voiceDialogTitle")
        foreground = title.palette().color(title.foregroundRole())
        background = self.rendered_color(dialog.scroll_area.widget())
        self.assertGreater(self.luminance(foreground) - self.luminance(background), 100)
        dialog.close()

    def test_personality_editors_grow_with_dialog(self) -> None:
        dialog = PersonalityDialog(
            model="modelo", language="Español",
            custom_name="Personalidad", custom_prompt="Instrucciones",
        )
        dialog.resize(dialog.minimumSize())
        dialog.show()
        self.app.processEvents()
        small_height = dialog.instructions_edit.height()
        dialog.resize(900, 1000)
        self.app.processEvents()
        self.assertGreaterEqual(dialog.instructions_edit.height(), small_height)
        dialog.close()

    def test_dashboard_cards_statistics_and_memory_reflow(self) -> None:
        with patch.object(DashboardView, "load_ollama_models", lambda self: None):
            dashboard = DashboardView()
        for grid, expected in (
            (dashboard.cards_grid, ((1300, 4), (900, 2), (600, 1))),
            (dashboard.stats_grid, ((1300, 5), (900, 3), (600, 1))),
            (dashboard.memory_grid, ((1300, 4), (900, 2), (600, 1))),
        ):
            original_ids = {id(widget) for widget in grid.widgets}
            for width, columns in expected:
                grid.resize(width, 800)
                grid.reflow(force=True)
                self.assertEqual(grid.current_columns, columns)
                self.assertEqual({id(widget) for widget in grid.widgets}, original_ids)
                self.assertEqual(grid.grid.count(), len(grid.widgets))
        dashboard.deleteLater()

    def test_dashboard_uses_viewport_width_without_horizontal_clipping(self) -> None:
        with patch.object(DashboardView, "load_ollama_models", lambda self: None):
            dashboard = DashboardView()
        for width, columns in ((1300, 4), (900, 2), (580, 1)):
            dashboard.resize(width, 700)
            dashboard.show()
            self.app.processEvents()
            dashboard.cards_grid.reflow(force=True)
            self.assertEqual(dashboard.cards_grid.current_columns, columns)
            self.assertEqual(
                dashboard.horizontalScrollBarPolicy(),
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
            )
            for card in dashboard.cards_grid.widgets:
                self.assertLessEqual(card.geometry().right(), dashboard.cards_grid.contentsRect().right())
        dashboard.close()

    def test_control_signal_is_emitted_once_per_click(self) -> None:
        with patch.object(DashboardView, "load_ollama_models", lambda self: None):
            dashboard = DashboardView()
        dashboard.save_dashboard_settings = lambda: None
        spy = QSignalSpy(dashboard.setting_changed)
        dashboard.control_toggles["respond_comments"].click()
        self.app.processEvents()
        self.assertEqual(spy.count(), 1)
        dashboard.deleteLater()


if __name__ == "__main__":
    unittest.main()
