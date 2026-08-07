#!/usr/bin/env python3
"""Tests for the one-time hotkeys.toggle_enable -> hotkeys.mode_switch migration.

Runs in CI without GPU dependencies. Follows the ConfigManager test conventions
in tests/test_config_manager.py (unittest, temp dir, path-overridden config).
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

# Add src to path for import (same mechanism as tests/test_config_manager.py)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from witticism.utils.config_manager import ConfigManager


class TestConfigMigration(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = Path(self.temp_dir) / "config.json"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write(self, data):
        with open(self.config_path, "w") as f:
            json.dump(data, f)

    def _load(self):
        """Build a ConfigManager pointed at the temp config and load it."""
        config = ConfigManager("test_app")
        config.config_dir = Path(self.temp_dir)
        config.config_file = self.config_path
        config.config = {}
        config.load_config()
        return config

    def _on_disk(self):
        with open(self.config_path, "r") as f:
            return json.load(f)

    def test_default_config_has_mode_switch_and_no_toggle_enable(self):
        """Fresh config exposes the new default and drops the dead key."""
        config = self._load()
        self.assertEqual(config.get("hotkeys.mode_switch"), "ctrl+alt+m")
        self.assertIsNone(config.get("hotkeys.toggle_enable"))

    def test_toggle_enable_value_is_copied_to_mode_switch(self):
        """An old toggle_enable value migrates into mode_switch (normalized)."""
        self._write({"hotkeys": {"toggle_enable": "<ctrl>+<alt>+x"}})
        config = self._load()
        self.assertEqual(config.get("hotkeys.mode_switch"), "ctrl+alt+x")

    def test_legacy_default_value_normalizes(self):
        """Master's pynput-style default normalizes to the canonical form."""
        self._write({"hotkeys": {"toggle_enable": "<ctrl>+<alt>+m"}})
        config = self._load()
        self.assertEqual(config.get("hotkeys.mode_switch"), "ctrl+alt+m")
        self.assertEqual(self._on_disk()["hotkeys"]["mode_switch"], "ctrl+alt+m")

    def test_custom_legacy_value_normalizes_preserving_keys(self):
        """A user-customized legacy value normalizes but keeps its keys."""
        self._write({"hotkeys": {"toggle_enable": "<ctrl>+<shift>+d"}})
        config = self._load()
        self.assertEqual(config.get("hotkeys.mode_switch"), "ctrl+shift+d")

    def test_already_canonical_value_passes_through(self):
        """A legacy key already holding the canonical form is unchanged."""
        self._write({"hotkeys": {"toggle_enable": "ctrl+alt+m"}})
        config = self._load()
        self.assertEqual(config.get("hotkeys.mode_switch"), "ctrl+alt+m")

    def test_toggle_enable_is_deleted_after_migration(self):
        """toggle_enable is removed from both memory and disk."""
        self._write({"hotkeys": {"toggle_enable": "<ctrl>+<alt>+x"}})
        config = self._load()
        self.assertIsNone(config.get("hotkeys.toggle_enable"))
        on_disk = self._on_disk()
        self.assertNotIn("toggle_enable", on_disk["hotkeys"])
        self.assertEqual(on_disk["hotkeys"]["mode_switch"], "ctrl+alt+x")

    def test_existing_mode_switch_is_not_clobbered(self):
        """When both keys exist, mode_switch wins and toggle_enable is dropped."""
        self._write({"hotkeys": {"toggle_enable": "old-value", "mode_switch": "kept-value"}})
        config = self._load()
        self.assertEqual(config.get("hotkeys.mode_switch"), "kept-value")
        self.assertIsNone(config.get("hotkeys.toggle_enable"))
        self.assertNotIn("toggle_enable", self._on_disk()["hotkeys"])

    def test_migration_is_idempotent(self):
        """Reloading an already-migrated config changes nothing."""
        self._write({"hotkeys": {"toggle_enable": "<ctrl>+<alt>+x"}})
        self._load()  # first load performs the migration and persists

        # Second, independent load of the now-migrated file.
        config2 = self._load()
        self.assertEqual(config2.get("hotkeys.mode_switch"), "ctrl+alt+x")
        self.assertIsNone(config2.get("hotkeys.toggle_enable"))
        self.assertNotIn("toggle_enable", self._on_disk()["hotkeys"])

    def test_no_migration_when_only_mode_switch_present(self):
        """A config with only mode_switch is left untouched."""
        self._write({"hotkeys": {"mode_switch": "keep-me"}})
        config = self._load()
        self.assertEqual(config.get("hotkeys.mode_switch"), "keep-me")
        self.assertIsNone(config.get("hotkeys.toggle_enable"))

    def test_null_toggle_enable_falls_back_to_default(self):
        """A null legacy value must not persist as mode_switch (it would crash
        accelerator parsing); the default applies instead."""
        self._write({"hotkeys": {"toggle_enable": None}})
        config = self._load()
        self.assertEqual(config.get("hotkeys.mode_switch"), "ctrl+alt+m")
        self.assertNotIn("toggle_enable", self._on_disk()["hotkeys"])

    def test_non_string_toggle_enable_falls_back_to_default(self):
        """A numeric legacy value is dropped rather than persisted."""
        self._write({"hotkeys": {"toggle_enable": 5}})
        config = self._load()
        self.assertEqual(config.get("hotkeys.mode_switch"), "ctrl+alt+m")
        self.assertNotIn("toggle_enable", self._on_disk()["hotkeys"])

    def test_empty_string_toggle_enable_falls_back_to_default(self):
        """An empty legacy value would be a non-functional binding; drop it."""
        self._write({"hotkeys": {"toggle_enable": ""}})
        config = self._load()
        self.assertEqual(config.get("hotkeys.mode_switch"), "ctrl+alt+m")
        self.assertNotIn("toggle_enable", self._on_disk()["hotkeys"])

    def test_save_is_atomic_and_leaves_no_temp_file(self):
        """save_config writes via a temp file + replace, leaving no .tmp behind
        and always-valid JSON on disk."""
        config = self._load()
        config.set("model.size", "large")
        tmp = self.config_path.with_name(self.config_path.name + ".tmp")
        self.assertFalse(tmp.exists())
        # File on disk is complete/valid and reflects the write.
        self.assertEqual(self._on_disk()["model"]["size"], "large")

    def test_failed_save_does_not_corrupt_existing_config(self):
        """If the atomic write fails mid-flight, the previous config.json is
        left intact (os.replace never ran) rather than truncated."""
        import json as _json
        config = self._load()
        config.set("model.size", "base")
        good = self._on_disk()

        # Force json.dump to blow up partway through the temp write.
        original_dump = _json.dump

        def exploding_dump(*args, **kwargs):
            raise OSError("disk full")

        from witticism.utils import config_manager as cm
        cm.json.dump = exploding_dump
        try:
            config.config["model"]["size"] = "large"
            config.save_config()  # swallowed; must not corrupt the real file
        finally:
            cm.json.dump = original_dump

        # The on-disk file is still the last good one, and no temp remains.
        self.assertEqual(self._on_disk(), good)
        tmp = self.config_path.with_name(self.config_path.name + ".tmp")
        self.assertFalse(tmp.exists())


if __name__ == "__main__":
    unittest.main()
