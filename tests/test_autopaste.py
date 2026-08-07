#!/usr/bin/env python3
"""Tests for the auto-paste consent state machine (AutopasteConsent).

The logic lives outside the Qt widget, so these run without PyQt5 installed.
Only the plain-Python controller is exercised here; the priming dialog itself
imports PyQt5 lazily and is not touched.
"""

import sys
from pathlib import Path

# Add src to path for import (same mechanism as tests/test_platform_cli.py).
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from witticism.ui.autopaste_prompt import AutopasteConsent


class FakeConfig:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.writes = []

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value
        self.writes.append((key, value))


def test_should_auto_prompt_requires_supported_unset_and_unprompted():
    assert AutopasteConsent(FakeConfig(), supported=True).should_auto_prompt() is True
    # Not a supported (Wayland) session -> never offer.
    assert AutopasteConsent(FakeConfig(), supported=False).should_auto_prompt() is False
    # Already granted or declined -> never auto-offer.
    granted = FakeConfig({"output.autopaste": "granted"})
    assert AutopasteConsent(granted, supported=True).should_auto_prompt() is False
    declined = FakeConfig({"output.autopaste": "declined"})
    assert AutopasteConsent(declined, supported=True).should_auto_prompt() is False


def test_auto_prompt_fires_at_most_once():
    cfg = FakeConfig()
    consent = AutopasteConsent(cfg, supported=True)
    assert consent.should_auto_prompt() is True
    consent.mark_prompted()  # shown once
    assert cfg.values["output.autopaste_prompted"] is True
    assert consent.should_auto_prompt() is False  # never again


def test_decline_persists_and_stops_prompting_but_allows_manual_reentry():
    cfg = FakeConfig()
    consent = AutopasteConsent(cfg, supported=True)
    consent.decline()
    assert cfg.values["output.autopaste"] == "declined"
    assert cfg.values["output.autopaste_prompted"] is True
    assert consent.should_auto_prompt() is False
    # The manual tray entry is still meaningful: the user can opt in later.
    assert consent.can_offer() is True


def test_grant_persists_and_removes_the_offer():
    cfg = FakeConfig()
    consent = AutopasteConsent(cfg, supported=True)
    consent.grant()
    assert cfg.values["output.autopaste"] == "granted"
    assert consent.is_granted() is True
    assert consent.can_offer() is False           # nothing left to offer
    assert consent.should_auto_prompt() is False


def test_manual_grant_after_decline():
    cfg = FakeConfig({"output.autopaste": "declined", "output.autopaste_prompted": True})
    consent = AutopasteConsent(cfg, supported=True)
    assert consent.can_offer() is True
    consent.grant()
    assert consent.is_granted() is True
    assert consent.can_offer() is False


def test_can_offer_returns_after_revocation_reset():
    # Granted, then revoked from the system indicator: the adapter resets
    # output.autopaste to "unset", and the tray re-evaluates can_offer() (which
    # reads config live) so the "Enable automatic paste..." item reappears.
    cfg = FakeConfig({"output.autopaste": "granted", "output.autopaste_prompted": True})
    consent = AutopasteConsent(cfg, supported=True)
    assert consent.can_offer() is False           # granted -> nothing to offer
    cfg.values["output.autopaste"] = "unset"      # revocation reset by the adapter
    assert consent.can_offer() is True            # offer re-surfaces
    assert consent.should_auto_prompt() is False  # but no second auto-prompt


def test_can_offer_false_when_unsupported():
    cfg = FakeConfig()
    consent = AutopasteConsent(cfg, supported=False)
    assert consent.can_offer() is False
    assert consent.should_auto_prompt() is False


def test_none_config_is_safe():
    consent = AutopasteConsent(None, supported=True)
    assert consent.state() == "unset"
    assert consent.already_prompted() is False
    # No config to write to; these must not raise.
    consent.mark_prompted()
    consent.decline()
    consent.grant()
