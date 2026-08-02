from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.app_paths import get_paths, initialize_user_data, resource_path


class WindowsPackagingTests(unittest.TestCase):
    def test_user_directories_and_defaults_are_created(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"PANDAIA_DATA_DIR": folder}):
            report = initialize_user_data()
            paths = get_paths()
            self.assertTrue(report["writable"])
            for path in (paths.config, paths.cache, paths.logs, paths.temp, paths.credentials,
                         paths.animations_custom, paths.sounds_custom):
                self.assertTrue(path.is_dir())
            self.assertEqual(json.loads(paths.settings_file.read_text(encoding="utf-8"))["dashboard"]["response_length"], "Corta")

    def test_migration_never_overwrites_existing_settings(self):
        with tempfile.TemporaryDirectory() as data, tempfile.TemporaryDirectory() as legacy:
            target = Path(data) / "config" / "settings.json"
            target.parent.mkdir(parents=True); target.write_text('{"personal": true}', encoding="utf-8")
            source = Path(legacy) / "config" / "settings.json"
            source.parent.mkdir(parents=True); source.write_text('{"personal": false}', encoding="utf-8")
            with patch.dict(os.environ, {"PANDAIA_DATA_DIR": data}):
                report = initialize_user_data(legacy_root=Path(legacy))
            self.assertEqual(target.read_text(encoding="utf-8"), '{"personal": true}')
            self.assertEqual(report["migrated"], [])

    def test_private_configs_are_not_declared_as_packaged_resources(self):
        spec = resource_path("packaging", "PandaIA.spec").read_text(encoding="utf-8")
        self.assertNotIn("spotify_local.json", spec)
        self.assertNotIn("telegram_local.json", spec)
        self.assertNotIn("config/settings.json", spec)
        self.assertNotIn("resources/defaults/settings.json", spec)

    def test_installer_preserves_local_app_data(self):
        script = resource_path("packaging", "installer", "PandaIA.iss").read_text(encoding="utf-8")
        self.assertNotIn("{localappdata}\\PandaIA", script)


if __name__ == "__main__":
    unittest.main()
