#!/usr/bin/env python3
"""Tests for the tray health decision (compute_tray_health).

The decision is pure (no Qt), so the precedence/trigger/clear matrix runs in the
venv without PyQt5. The Qt side only renders the returned tier.
"""

import sys
from pathlib import Path

# Add src to path for import (same mechanism as tests/test_platform_cli.py).
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from witticism.ui.tray_health import (
    AUTOTYPE_REASON,
    HOTKEY_REASON,
    TrayHealth,
    compute_tray_health,
)


def _health(hotkey_usable=True, autopaste_state="unset", autopaste_broken=False,
            error_active=False, recording=False):
    return compute_tray_health(hotkey_usable, autopaste_state, autopaste_broken, error_active, recording)


def test_normal_when_nothing_wrong():
    assert _health() == (TrayHealth.NORMAL, None)


def test_unset_never_granted_is_normal():
    # Clipboard-only because the user never enabled auto-typing is the designed
    # default, not degraded.
    assert _health(autopaste_state="unset", autopaste_broken=False) == (TrayHealth.NORMAL, None)


def test_declined_is_normal():
    assert _health(autopaste_state="declined", autopaste_broken=False) == (TrayHealth.NORMAL, None)


def test_hotkey_unusable_is_degraded():
    tier, reason = _health(hotkey_usable=False)
    assert tier == TrayHealth.DEGRADED
    assert reason == HOTKEY_REASON


def test_autopaste_broken_after_revocation_is_degraded():
    # Mid-session revocation resets consent to "unset" but sets the broken flag.
    tier, reason = _health(autopaste_state="unset", autopaste_broken=True)
    assert tier == TrayHealth.DEGRADED
    assert reason == AUTOTYPE_REASON


def test_autopaste_broken_while_granted_is_degraded():
    # Startup token-restore failure: consent still says granted, but it is broken.
    tier, reason = _health(autopaste_state="granted", autopaste_broken=True)
    assert tier == TrayHealth.DEGRADED
    assert reason == AUTOTYPE_REASON


def test_declined_after_revocation_clears_degraded():
    # The user declined after a revocation -> chose the clipboard default -> normal.
    assert _health(autopaste_state="declined", autopaste_broken=True) == (TrayHealth.NORMAL, None)


def test_regranted_clears_degraded():
    # Re-granted (broken flag cleared) -> normal.
    assert _health(autopaste_state="granted", autopaste_broken=False) == (TrayHealth.NORMAL, None)


def test_recording_masks_degraded():
    # A live recording indicator takes precedence over degraded.
    assert _health(hotkey_usable=False, recording=True) == (TrayHealth.RECORDING, None)
    assert _health(autopaste_broken=True, recording=True) == (TrayHealth.RECORDING, None)


def test_error_outranks_recording_and_degraded():
    # Real errors (CUDA/model) outrank everything, including recording.
    assert _health(error_active=True, recording=True, hotkey_usable=False,
                   autopaste_broken=True) == (TrayHealth.ERROR, None)


def test_error_outranks_degraded_when_idle():
    assert _health(error_active=True, hotkey_usable=False) == (TrayHealth.ERROR, None)
