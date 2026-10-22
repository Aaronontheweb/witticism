#!/usr/bin/env python3
"""Tests for the custom-vocabulary (Whisper hotwords) feature.

Covers the two contracts that actually matter:
  1. WhisperXEngine._asr_options() decides whether/how hotwords reach
     whisperx.load_model().
  2. SettingsDialog vocabulary parsing normalizes free-form input (commas
     and/or newlines) into a clean, idempotent model.hotwords value.

Runs headless in CI (QT_QPA_PLATFORM=offscreen, PyQt5 installed). Skips
cleanly where PyQt5 or numpy is absent.
"""

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

pytest.importorskip("numpy")
pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from witticism.core.whisperx_engine import WhisperXEngine  # noqa: E402
from witticism.ui.settings_dialog import SettingsDialog  # noqa: E402
from witticism.utils.config_manager import ConfigManager  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def config_manager(tmp_path, monkeypatch):
    """A ConfigManager isolated to a temp dir (never touches the real config)."""
    monkeypatch.setattr("platformdirs.user_config_dir",
                        lambda *a, **k: str(tmp_path / "config"))
    monkeypatch.setattr("platformdirs.user_data_dir",
                        lambda *a, **k: str(tmp_path / "data"))
    return ConfigManager(app_name="witticism_test")


# --- Engine: _asr_options() contract -----------------------------------------

def test_asr_options_none_when_unset():
    engine = WhisperXEngine(model_size="base", device="cpu")
    assert engine.hotwords == ""
    assert engine._asr_options() is None


def test_asr_options_none_when_whitespace_only():
    engine = WhisperXEngine(model_size="base", device="cpu", hotwords="   \n  ")
    assert engine._asr_options() is None


def test_asr_options_carries_trimmed_hotwords():
    engine = WhisperXEngine(model_size="base", device="cpu",
                            hotwords="  Akka.NET, Petabridge  ")
    assert engine._asr_options() == {"hotwords": "Akka.NET, Petabridge"}


def test_hotwords_none_is_coerced_to_empty_string():
    engine = WhisperXEngine(model_size="base", device="cpu", hotwords=None)
    assert engine.hotwords == ""
    assert engine._asr_options() is None


# --- Settings dialog: vocabulary parsing/normalization -----------------------

def test_parse_vocabulary_handles_commas_and_newlines():
    parsed = SettingsDialog._parse_vocabulary(
        "Akka.NET\nPetabridge, Phobos\n\n  Akka.Cluster  "
    )
    assert parsed == ["Akka.NET", "Petabridge", "Phobos", "Akka.Cluster"]


def test_parse_vocabulary_empty_and_blank_input():
    assert SettingsDialog._parse_vocabulary("") == []
    assert SettingsDialog._parse_vocabulary("  ,  \n , ") == []


def test_get_settings_normalizes_vocabulary(app, config_manager):
    dialog = SettingsDialog(config_manager)
    dialog.vocabulary_edit.setPlainText("Akka.NET\nPetabridge\n\n  Phobos  ")
    assert dialog.get_settings()["model.hotwords"] == "Akka.NET, Petabridge, Phobos"


def test_get_settings_vocabulary_is_idempotent(app, config_manager):
    # A stored comma-list, re-read and re-serialized, must be unchanged so that
    # re-opening the dialog and pressing OK reports no spurious change.
    config_manager.set("model.hotwords", "Akka.NET, Petabridge, Phobos")
    dialog = SettingsDialog(config_manager)
    assert dialog.get_settings()["model.hotwords"] == "Akka.NET, Petabridge, Phobos"


def test_vocabulary_loads_from_config_with_term_count(app, config_manager):
    config_manager.set("model.hotwords", "Akka.NET, Petabridge")
    dialog = SettingsDialog(config_manager)
    assert dialog.vocabulary_edit.toPlainText() == "Akka.NET, Petabridge"
    assert dialog.vocabulary_count_label.text() == "2 terms"


def test_restore_defaults_clears_vocabulary(app, config_manager):
    config_manager.set("model.hotwords", "Akka.NET, Petabridge")
    dialog = SettingsDialog(config_manager)
    dialog.restore_defaults()
    assert dialog.vocabulary_edit.toPlainText() == ""
    assert dialog.vocabulary_count_label.text() == "0 terms"


# --- Config default -----------------------------------------------------------

def test_config_default_hotwords_is_empty(config_manager):
    assert config_manager.get("model.hotwords", "MISSING") == ""
