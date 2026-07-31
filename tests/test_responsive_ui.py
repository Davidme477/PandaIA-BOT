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
from PySide6.QtWidgets import QApplication, QLabel

from app.dialogs.personality_dialog import PersonalityDialog
from app.views.dashboard_view import DashboardView
from app.widgets.responsive_grid import ResponsiveGrid, columns_for_width


class ResponsiveUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_breakpoints_cover_wide_medium_and_narrow(self) -> None:
        self.assertEqual(columns_for_width(1400, wide_columns=4), 4)
        self.assertEqual(columns_for_width(900, wide_columns=4), 2)
        self.assertEqual(columns_for_width(600, wide_columns=4), 1)

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
