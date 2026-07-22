#!/usr/bin/env python3
"""Tests for the witticism-platform CLI (consent flow + doctor).

Runs in CI without GPU dependencies. Uses pytest + monkeypatch, matching the
style of the pytest-based platform adapter tests. The D-Bus / subprocess
boundaries are mocked so nothing touches the real desktop session.
"""

import json
import sys
from pathlib import Path

# Add src to path for import (same mechanism as tests/test_config_manager.py)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from witticism.platform import cli

# Reuse the sensitive-field-name convention from test_platform_adapters.py
# without importing that module (kept local to avoid fixture coupling).
FORBIDDEN_FIELD_NAMES = ("hostname", "username", "restore_token", "transcript", "device_name")


class FakeStdin:
    def __init__(self, tty):
        self._tty = tty

    def isatty(self):
        return self._tty


class FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _boom(*args, **kwargs):
    raise AssertionError("subprocess.run must not be reached before consent")


# --------------------------------------------------------------------------
# Consent flow
# --------------------------------------------------------------------------

def test_install_refuses_without_confirmation_on_non_tty(monkeypatch):
    monkeypatch.setattr(cli.sys, "stdin", FakeStdin(tty=False))
    monkeypatch.setattr(cli.subprocess, "run", _boom)
    rc = cli.install_extension(assume_yes=False)
    assert rc != 0


def test_install_aborts_on_negative_answer(monkeypatch):
    monkeypatch.setattr(cli.sys, "stdin", FakeStdin(tty=True))
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    monkeypatch.setattr(cli.subprocess, "run", _boom)
    rc = cli.install_extension(assume_yes=False)
    assert rc != 0


def test_install_proceeds_with_yes(monkeypatch):
    recorded = []

    def fake_run(cmd, **kwargs):
        recorded.append(list(cmd))
        return FakeProc(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    rc = cli.install_extension(assume_yes=True)
    assert rc == 0
    # The install mechanics ran: gnome-extensions install was invoked.
    assert any(cmd[:2] == ["gnome-extensions", "install"] for cmd in recorded)


def test_install_pre_enables_via_gsettings_when_live_enable_fails(monkeypatch):
    recorded = []

    def fake_run(cmd, **kwargs):
        recorded.append(list(cmd))
        # gnome-extensions install succeeds, live enable fails, gsettings works.
        if cmd[:2] == ["gnome-extensions", "enable"]:
            return FakeProc(returncode=1, stderr="cannot enable")
        if cmd[:2] == ["gsettings", "get"]:
            return FakeProc(returncode=0, stdout="['other@x']")
        return FakeProc(returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    rc = cli.install_extension(assume_yes=True)
    assert rc == 0
    assert any(cmd[:2] == ["gsettings", "set"] for cmd in recorded)


# --------------------------------------------------------------------------
# Doctor
# --------------------------------------------------------------------------

def test_doctor_json_has_expected_keys_and_no_forbidden_names(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_safe_portal_interfaces", lambda: set())
    monkeypatch.setattr(cli, "_probe_shortcut", lambda: ("pynput", "ready", None))
    monkeypatch.setattr(cli, "_probe_output", lambda: "pynput")
    monkeypatch.setattr(cli, "_probe_extension", lambda: (False, False))
    monkeypatch.setattr(cli, "_restore_grant_present", lambda: False)
    monkeypatch.setattr(cli, "_keybinding_registered", lambda: False)
    monkeypatch.setattr(cli, "_keyboard_repeat_enabled", lambda: True)

    rc = cli.doctor(as_json=True)
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    expected_keys = {
        "schema_version",
        "display_protocol",
        "desktop",
        "global_shortcuts_portal",
        "remote_desktop_portal",
        "shortcut_adapter",
        "shortcut_capability",
        "output_adapter",
        "output_capability",
        "gnome_extension_installed",
        "gnome_extension_loaded",
        "portal_restore_permission_present",
    }
    assert expected_keys.issubset(payload.keys())
    assert payload["shortcut_capability"] in ("hold-to-talk", "press-to-toggle (fallback)", "unavailable")
    assert payload["output_capability"] in ("portal typing", "typing", "clipboard")
    # Pynput backend maps to full hold-to-talk / typing.
    assert payload["shortcut_capability"] == "hold-to-talk"
    assert payload["output_capability"] == "typing"

    blob = json.dumps(payload).lower()
    for forbidden in FORBIDDEN_FIELD_NAMES:
        assert forbidden not in blob


def test_doctor_reports_press_to_toggle_when_key_repeat_disabled(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_safe_portal_interfaces", lambda: set())
    # GNOME custom-keybinding backend, but key auto-repeat is off -> no hold
    # inference, so it degrades to press-to-toggle.
    monkeypatch.setattr(cli, "_probe_shortcut", lambda: ("gnome-media-keys", "ready", None))
    monkeypatch.setattr(cli, "_probe_output", lambda: "clipboard")
    monkeypatch.setattr(cli, "_probe_extension", lambda: (False, False))
    monkeypatch.setattr(cli, "_restore_grant_present", lambda: False)
    monkeypatch.setattr(cli, "_keybinding_registered", lambda: True)
    monkeypatch.setattr(cli, "_keyboard_repeat_enabled", lambda: False)
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")

    rc = cli.doctor(as_json=True)
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["shortcut_capability"] == "press-to-toggle (fallback)"
    assert payload["keybinding_registered"] is True
    assert payload["keyboard_repeat_enabled"] is False
    # Press-to-toggle GNOME session should guide toward the optional extension.
    assert "install-gnome-extension" in payload["how_to_improve"]


def test_doctor_reports_hold_to_talk_when_key_repeat_enabled(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_safe_portal_interfaces", lambda: set())
    monkeypatch.setattr(cli, "_probe_shortcut", lambda: ("gnome-media-keys", "ready", None))
    monkeypatch.setattr(cli, "_probe_output", lambda: "clipboard")
    monkeypatch.setattr(cli, "_probe_extension", lambda: (False, False))
    monkeypatch.setattr(cli, "_restore_grant_present", lambda: False)
    monkeypatch.setattr(cli, "_keybinding_registered", lambda: True)
    monkeypatch.setattr(cli, "_keyboard_repeat_enabled", lambda: True)
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")

    rc = cli.doctor(as_json=True)
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    # Key repeat present -> the custom-keybinding backend infers hold-to-talk.
    assert payload["shortcut_capability"] == "hold-to-talk"
    assert payload["keyboard_repeat_enabled"] is True


def test_doctor_reports_portal_typing_when_autopaste_granted(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_safe_portal_interfaces", lambda: {cli.REMOTE_DESKTOP})
    monkeypatch.setattr(cli, "_probe_shortcut", lambda: ("xdg-global-shortcuts", "ready", None))
    monkeypatch.setattr(cli, "_probe_output", lambda: "xdg-remote-desktop")
    monkeypatch.setattr(cli, "_probe_extension", lambda: (False, False))
    monkeypatch.setattr(cli, "_restore_grant_present", lambda: True)
    monkeypatch.setattr(cli, "_autopaste_consent", lambda: "granted")
    monkeypatch.setattr(cli, "_keybinding_registered", lambda: False)
    monkeypatch.setattr(cli, "_keyboard_repeat_enabled", lambda: True)

    rc = cli.doctor(as_json=True)
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["autopaste_consent"] == "granted"
    # Portal typing only reported when granted AND a restore token exists.
    assert payload["output_capability"] == "portal typing"


def test_doctor_output_clipboard_and_hint_when_autopaste_unset(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_safe_portal_interfaces", lambda: {cli.REMOTE_DESKTOP})
    monkeypatch.setattr(cli, "_probe_shortcut", lambda: ("xdg-global-shortcuts", "ready", None))
    monkeypatch.setattr(cli, "_probe_output", lambda: "xdg-remote-desktop")
    monkeypatch.setattr(cli, "_probe_extension", lambda: (False, False))
    monkeypatch.setattr(cli, "_restore_grant_present", lambda: False)
    monkeypatch.setattr(cli, "_autopaste_consent", lambda: "unset")
    monkeypatch.setattr(cli, "_keybinding_registered", lambda: False)
    monkeypatch.setattr(cli, "_keyboard_repeat_enabled", lambda: True)
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")

    rc = cli.doctor(as_json=True)
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    # Clipboard-first is the designed default, not a degradation.
    assert payload["output_capability"] == "clipboard"
    assert payload["autopaste_consent"] == "unset"
    assert "automatic typing" in payload["how_to_improve"].lower()


def test_doctor_text_survives_dbus_unreachable(monkeypatch, capsys):
    def boom(*args, **kwargs):
        raise OSError("D-Bus is unreachable")

    monkeypatch.setattr(cli, "portal_interfaces", boom)
    monkeypatch.setattr(cli, "create_shortcut_adapter", boom)
    monkeypatch.setattr(cli, "create_text_output_adapter", boom)
    monkeypatch.setattr(cli.subprocess, "run", boom)
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/gnome-extensions")

    rc = cli.doctor(as_json=False)  # must not raise
    assert rc == 0
    out = capsys.readouterr().out
    assert "Witticism platform diagnostics" in out


# ---------------------------------------------------------------------------
# Uninstall must remove the pre-enabled gsettings entry that
# `gnome-extensions disable` cannot touch for a never-loaded extension.
# ---------------------------------------------------------------------------

def test_uninstall_removes_uuid_from_enabled_extensions(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:2] == ["gsettings", "get"]:
            return FakeProc(stdout="['other@example.com', 'witticism@stannardlabs.com']")
        return FakeProc()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    assert cli._remove_from_enabled_extensions() is True
    set_call = calls[-1]
    assert set_call[:2] == ["gsettings", "set"]
    assert "witticism@stannardlabs.com" not in set_call[-1]
    assert "other@example.com" in set_call[-1]


def test_uninstall_enabled_extensions_noop_when_absent(monkeypatch):
    monkeypatch.setattr(
        cli.subprocess, "run",
        lambda cmd, **kwargs: FakeProc(stdout="['other@example.com']"),
    )
    assert cli._remove_from_enabled_extensions() is False


def test_uninstall_enabled_extensions_tolerates_gsettings_failure(monkeypatch):
    monkeypatch.setattr(
        cli.subprocess, "run",
        lambda cmd, **kwargs: FakeProc(returncode=1),
    )
    assert cli._remove_from_enabled_extensions() is False
