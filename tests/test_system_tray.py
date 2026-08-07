#!/usr/bin/env python3
"""System-tray tests: the mode-switch blocker fix and the hotkey-callback
marshaling wiring.

Runs headless in CI (QT_QPA_PLATFORM=offscreen, PyQt5 installed). Skips cleanly
where PyQt5 or numpy (pulled in by the tray's transcriber import) is absent.
"""

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

pytest.importorskip("PyQt5")
pytest.importorskip("numpy")

import numpy as np
from PyQt5.QtWidgets import QApplication

from witticism.ui.system_tray import SystemTrayApp


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _AudioStub:
    def __init__(self):
        self.started = False
        self.stopped = False

    def start_push_to_talk(self):
        self.started = True

    def stop_push_to_talk(self):
        self.stopped = True
        return np.array([], dtype="float32")  # empty -> no transcription kicked off


def test_change_mode_toggle_stops_active_recording(app):
    """Switching to Toggle while a push-to-talk capture is live must stop the
    mic (regression for the stuck-recording blocker)."""
    tray = SystemTrayApp()
    tray.is_enabled = True
    audio = _AudioStub()
    tray.audio_capture = audio
    tray.hotkey_manager = None

    tray.start_recording()
    assert tray.is_recording is True

    tray.change_mode("toggle")

    assert tray.is_recording is False
    assert audio.stopped is True


def test_change_mode_toggle_noop_when_not_recording(app):
    tray = SystemTrayApp()
    tray.is_enabled = True
    audio = _AudioStub()
    tray.audio_capture = audio
    tray.hotkey_manager = None

    tray.change_mode("toggle")  # nothing in flight

    assert tray.is_recording is False
    assert audio.stopped is False


def test_request_wrappers_emit_signals(app):
    """The thread-safe entry points the hotkey manager calls just emit signals."""
    tray = SystemTrayApp()
    fired = []
    tray.ptt_start_requested.connect(lambda: fired.append("start"))
    tray.ptt_stop_requested.connect(lambda: fired.append("stop"))
    tray.toggle_enabled_requested.connect(lambda: fired.append("enabled"))
    tray.toggle_dictation_requested.connect(lambda active: fired.append(("dictation", active)))

    tray.request_ptt_start()
    tray.request_ptt_stop()
    tray.request_toggle_enabled()
    tray.request_toggle_dictation(True)
    app.processEvents()

    assert fired == ["start", "stop", "enabled", ("dictation", True)]


def test_set_components_wires_hotkey_signals_to_handlers(app):
    """set_components connects the marshaling signals to the real handlers, so a
    hotkey event delivered off-thread drives start/stop on the GUI thread."""
    tray = SystemTrayApp()
    tray.is_enabled = True
    audio = _AudioStub()
    try:
        tray.set_components(None, audio, None, None, None)
    except Exception:
        # The connect block runs before any component-dependent menu refresh, so
        # the signal wiring is in place even if the tail needs real components.
        pass

    tray.request_ptt_start()
    app.processEvents()
    assert tray.is_recording is True
    assert audio.started is True

    tray.request_ptt_stop()
    app.processEvents()
    assert tray.is_recording is False
    assert audio.stopped is True


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
