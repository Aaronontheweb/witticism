import ast
import asyncio
import concurrent.futures
import os
import stat
import time

import pytest

from witticism.core import hotkey_manager
from witticism.core.hotkey_manager import HotkeyManager
from witticism.platform import input_output
from witticism.platform.input_output import (
    AdapterState,
    AdapterStatus,
    ClipboardTextOutputAdapter,
    GnomeKeybindingShortcutAdapter,
    GnomeShellShortcutAdapter,
    OutputResult,
    PynputShortcutAdapter,
    RemoteDesktopPasteAdapter,
    ShortcutBinding,
    ShortcutEvent,
    ShortcutEventType,
    ShortcutTrigger,
)


class FakeShortcutAdapter:
    def __init__(self):
        self.callback = None
        self.bindings = []

    def probe(self):
        return AdapterStatus(AdapterState.READY, "fake")

    def start(self, bindings, callback):
        self.bindings = list(bindings)
        self.callback = callback
        return self.probe()

    def update_bindings(self, bindings):
        self.bindings = list(bindings)
        return self.probe()

    def stop(self):
        self.callback = None

    def emit(self, shortcut_id, event_type):
        self.callback(ShortcutEvent(shortcut_id, event_type, 1))


class FakeConfig:
    def get(self, key, default=None):
        return {"hotkeys.ptt_debounce_ms": 1}.get(key, default)


class DebounceConfig:
    def __init__(self, debounce_ms):
        self.debounce_ms = debounce_ms

    def get(self, key, default=None):
        if key == "hotkeys.ptt_debounce_ms":
            return self.debounce_ms
        return default


class FakeNoHoldAdapter(FakeShortcutAdapter):
    """A backend that only delivers press events (no hold-to-talk)."""

    supports_hold = False


def test_push_to_talk_contract():
    adapter = FakeShortcutAdapter()
    manager = HotkeyManager(FakeConfig(), adapter=adapter)
    calls = []
    manager.set_callbacks(lambda: calls.append("start"), lambda: calls.append("stop"))
    manager.start()
    adapter.emit("push_to_talk", ShortcutEventType.ACTIVATED)
    adapter.emit("push_to_talk", ShortcutEventType.ACTIVATED)
    adapter.emit("push_to_talk", ShortcutEventType.DEACTIVATED)
    time.sleep(0.02)
    assert calls == ["start", "stop"]


def test_dynamic_binding_update():
    adapter = FakeShortcutAdapter()
    manager = HotkeyManager(FakeConfig(), adapter=adapter)
    manager.start()
    assert manager.update_hotkey_from_string("F10")
    assert adapter.bindings[0].accelerator == "F10"
    assert not manager.update_hotkey_from_string("Ctrl+Shift+P")


def test_mode_switch_contract():
    adapter = FakeShortcutAdapter()
    manager = HotkeyManager(FakeConfig(), adapter=adapter)
    calls = []
    manager.set_callbacks(on_toggle=lambda: calls.append("toggle"))
    manager.start()
    adapter.emit("mode_switch", ShortcutEventType.ACTIVATED)
    adapter.emit("mode_switch", ShortcutEventType.DEACTIVATED)
    assert calls == ["toggle"]


def test_doctor_contract_excludes_sensitive_field_names():
    from witticism.platform import cli
    source = cli.doctor.__code__.co_consts
    rendered = " ".join(value for value in source if isinstance(value, str)).lower()
    for forbidden in ("hostname", "username", "restore_token", "transcript", "device_name"):
        assert forbidden not in rendered


def test_wayland_factory_prefers_global_shortcuts_portal(monkeypatch):
    monkeypatch.setattr(input_output.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    monkeypatch.setattr(input_output, "portal_has_interface", lambda name: name == input_output.GLOBAL_SHORTCUTS)
    assert input_output.create_shortcut_adapter().__class__.__name__ == "PortalShortcutAdapter"


def test_wayland_factory_uses_gnome_bridge_without_portal(monkeypatch):
    monkeypatch.setattr(input_output.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "ubuntu:GNOME")
    monkeypatch.setattr(input_output, "portal_has_interface", lambda _name: False)
    monkeypatch.setattr(input_output, "_dbus_name_has_owner", lambda name: name == input_output.GNOME_BUS)
    assert isinstance(input_output.create_shortcut_adapter(), GnomeShellShortcutAdapter)


def test_wayland_factory_uses_keybinding_adapter_without_extension(monkeypatch):
    monkeypatch.setattr(input_output.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "ubuntu:GNOME")
    monkeypatch.setattr(input_output, "portal_has_interface", lambda _name: False)
    monkeypatch.setattr(input_output, "_dbus_name_has_owner", lambda _name: False)
    adapter = input_output.create_shortcut_adapter()
    assert isinstance(adapter, GnomeKeybindingShortcutAdapter)
    assert adapter.supports_hold is False
    status = adapter.probe()
    assert status.usable
    assert "install-gnome-extension" in (status.recovery_action or "")


def test_x11_factory_preserves_pynput(monkeypatch):
    monkeypatch.setattr(input_output.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert isinstance(input_output.create_shortcut_adapter(), PynputShortcutAdapter)


def test_macos_is_explicitly_unsupported(monkeypatch):
    monkeypatch.setattr(input_output.platform, "system", lambda: "Darwin")
    assert input_output.create_shortcut_adapter().probe().state == AdapterState.UNAVAILABLE
    assert isinstance(input_output.create_text_output_adapter(), ClipboardTextOutputAdapter)


def test_pynput_adapter_suppresses_duplicate_complete_cycle():
    class Key:
        name = "f9"
        char = None

    adapter = PynputShortcutAdapter()
    adapter.bindings = [input_output.ShortcutBinding("ptt", "F9", input_output.ShortcutTrigger.HOLD)]
    events = []
    adapter.on_event = events.append
    adapter._press(Key())
    adapter._release(Key())
    adapter._press(Key())
    adapter._release(Key())
    assert [event.type.value for event in events] == ["activated", "deactivated"]


class FakePortalMessage:
    def __init__(self, path, response, results):
        from dbus_next import MessageType
        self.message_type = MessageType.SIGNAL
        self.interface = "org.freedesktop.portal.Request"
        self.member = "Response"
        self.path = path
        self.body = [response, results]


class FakePortalBus:
    unique_name = ":1.42"

    def __init__(self):
        self.handler = None

    def add_message_handler(self, handler):
        self.handler = handler

    def remove_message_handler(self, handler):
        assert handler is self.handler


def test_portal_request_handles_success_and_denial():
    pytest.importorskip("dbus_next")
    from dbus_next import Variant

    async def run(response):
        bus = FakePortalBus()
        token = "test_token"
        path = input_output._request_path(bus.unique_name, token)

        async def method(_options):
            asyncio.get_running_loop().call_soon(
                bus.handler,
                FakePortalMessage(path, response, {"session_handle": Variant("s", "/session/1")}),
            )
            return path

        return await input_output._portal_request(bus, method, [{}], token)

    assert asyncio.run(run(0))["session_handle"] == "/session/1"
    with pytest.raises(PermissionError):
        asyncio.run(run(1))


def test_static_portal_interfaces_are_valid():
    pytest.importorskip("dbus_next")
    from dbus_next.introspection import Node
    global_node = Node.parse(input_output.GLOBAL_SHORTCUTS_XML)
    remote_node = Node.parse(input_output.REMOTE_DESKTOP_XML)
    assert global_node.interfaces[0].name == input_output.GLOBAL_SHORTCUTS
    assert remote_node.interfaces[0].name == input_output.REMOTE_DESKTOP


def test_remote_desktop_releases_control_after_paste_failure():
    class Interface:
        def __init__(self):
            self.calls = []

        async def call_notify_keyboard_keysym(self, session, options, keysym, state):
            self.calls.append((keysym, state))
            if keysym == ord("v") and state == 1:
                raise RuntimeError("injected failure")

    adapter = RemoteDesktopPasteAdapter()
    adapter.interface = Interface()
    adapter.session = "/session/1"
    with pytest.raises(RuntimeError):
        asyncio.run(adapter._paste())
    assert adapter.interface.calls[-1] == (0xFFE3, 0)


def test_portal_restore_token_is_private_and_rotated(tmp_path):
    adapter = RemoteDesktopPasteAdapter()
    adapter.token_file = tmp_path / "state" / "wayland-portal.json"
    adapter._store_token("first")
    assert adapter._load_token() == "first"
    assert stat.S_IMODE(adapter.token_file.stat().st_mode) == 0o600
    adapter._store_token("second")
    assert adapter._load_token() == "second"
    assert not adapter.token_file.with_suffix(".tmp").exists()


def test_token_file_created_0600_without_chmod_window(tmp_path, monkeypatch):
    adapter = RemoteDesktopPasteAdapter()
    adapter.token_file = tmp_path / "state" / "wayland-portal.json"

    real_open = os.open
    open_modes = []

    def recording_open(path, flags, mode=0o777, *args, **kwargs):
        if str(path).endswith(".tmp"):
            open_modes.append(mode)
        return real_open(path, flags, mode, *args, **kwargs)

    chmod_calls = []
    monkeypatch.setattr(input_output.os, "open", recording_open)
    monkeypatch.setattr(input_output.os, "chmod", lambda *a, **k: chmod_calls.append(a))

    adapter._store_token("secret")

    # The temp file was created 0600 from its first byte (mode passed to os.open),
    # and no chmod was used (so there is no world-readable window).
    assert open_modes == [0o600]
    assert chmod_calls == []
    assert stat.S_IMODE(adapter.token_file.stat().st_mode) == 0o600


def test_remote_desktop_output_text_is_non_blocking(monkeypatch):
    adapter = RemoteDesktopPasteAdapter()
    adapter.ready = True

    class NeverRuntime:
        def __init__(self):
            self.loop = object()
            self.future = concurrent.futures.Future()
            self.submitted = 0

        def submit(self, coroutine):
            # Do not run the paste coroutine; return a future that never resolves.
            coroutine.close()
            self.submitted += 1
            return self.future

        def stop(self):
            self.loop = None

    runtime = NeverRuntime()
    adapter.runtime = runtime
    monkeypatch.setattr(input_output, "_clipboard", lambda text: OutputResult(True, False))

    started = time.monotonic()
    result = adapter.output_text("hello world")
    elapsed = time.monotonic() - started

    # Returns immediately with an optimistic result even though the paste future
    # is still pending (never resolved) -- i.e. the GUI thread did not block.
    assert result.success is True
    assert result.pasted is True
    assert elapsed < 0.5
    assert runtime.submitted == 1
    assert not runtime.future.done()

    # When the paste eventually fails, the done-callback downgrades the adapter.
    runtime.future.set_exception(RuntimeError("paste boom"))
    assert adapter.ready is False
    assert adapter.status.state == AdapterState.DEGRADED
    assert adapter.status.backend == "clipboard"


# ---------------------------------------------------------------------------
# Auto-paste is consent-gated: the adapter must never touch the Remote Desktop
# portal (no probe, no session, no dialog) until the user has granted it.
# ---------------------------------------------------------------------------

class _AutopasteConfig:
    def __init__(self, autopaste="unset"):
        self.values = {"output.autopaste": autopaste}

    def get(self, key, default=None):
        return self.values.get(key, default)


class _RecordingRuntime:
    def __init__(self):
        self.loop = None
        self.submitted = []

    def submit(self, coroutine):
        self.submitted.append(coroutine.__name__)
        coroutine.close()  # never actually run the portal coroutine
        return concurrent.futures.Future()

    def stop(self):
        self.loop = None


def _paste_adapter(monkeypatch, autopaste, tmp_path, token=None):
    def _no_portal(_name):
        raise AssertionError("the Remote Desktop portal must not be touched at startup")

    monkeypatch.setattr(input_output, "portal_has_interface", _no_portal)
    adapter = RemoteDesktopPasteAdapter(_AutopasteConfig(autopaste))
    adapter.runtime = _RecordingRuntime()
    adapter.token_file = tmp_path / "wayland-portal.json"
    if token is not None:
        adapter.token_file.write_text('{"restore_token": "%s"}' % token)
    return adapter


def test_autopaste_unset_makes_no_portal_calls_at_startup(monkeypatch, tmp_path):
    adapter = _paste_adapter(monkeypatch, "unset", tmp_path)
    status = adapter.start()
    assert adapter.runtime.submitted == []       # no session coroutine submitted
    assert status.state == AdapterState.READY     # clipboard is the designed default
    assert status.backend == "clipboard"
    assert adapter.ready is False


def test_autopaste_declined_makes_no_portal_calls_at_startup(monkeypatch, tmp_path):
    adapter = _paste_adapter(monkeypatch, "declined", tmp_path)
    status = adapter.start()
    assert adapter.runtime.submitted == []
    assert status.state == AdapterState.READY
    assert status.backend == "clipboard"


def test_autopaste_granted_with_token_restores_session_silently(monkeypatch, tmp_path):
    adapter = _paste_adapter(monkeypatch, "granted", tmp_path, token="tok")
    status = adapter.start()
    assert adapter.runtime.submitted == ["_restore_session"]  # silent restore, no prompt
    assert status.state == AdapterState.STARTING
    assert status.backend == "xdg-remote-desktop"


def test_autopaste_granted_without_token_does_not_reprompt(monkeypatch, tmp_path):
    adapter = _paste_adapter(monkeypatch, "granted", tmp_path)  # no token file present
    status = adapter.start()
    assert adapter.runtime.submitted == []       # never opens a session -> no dialog
    assert status.state == AdapterState.DEGRADED
    assert status.backend == "clipboard"
    assert "re-enable" in (status.message or "").lower()


def test_request_autopaste_success_reports_granted():
    adapter = RemoteDesktopPasteAdapter()
    results = []

    async def fake_open():
        adapter.ready = True

    adapter._open_session = fake_open
    asyncio.run(adapter._consent_session(lambda granted, message: results.append((granted, message))))
    assert results == [(True, None)]
    assert adapter.ready is True
    assert adapter.status.backend == "xdg-remote-desktop"
    assert adapter.status.state == AdapterState.READY


def test_request_autopaste_denial_reports_not_granted():
    adapter = RemoteDesktopPasteAdapter()
    results = []

    async def fake_open():
        raise PermissionError("Keyboard permission was not granted")

    adapter._open_session = fake_open
    asyncio.run(adapter._consent_session(lambda granted, message: results.append((granted, message))))
    assert results[0][0] is False
    assert adapter.ready is False
    # Denial leaves the adapter on the clipboard default (state stays usable).
    assert adapter.status.backend == "clipboard"
    assert adapter.status.state == AdapterState.READY


def test_wayland_output_adapter_receives_config(monkeypatch):
    monkeypatch.setattr(input_output.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    cfg = _AutopasteConfig("granted")
    adapter = input_output.create_text_output_adapter(cfg)
    assert isinstance(adapter, RemoteDesktopPasteAdapter)
    assert adapter._consent_state() == "granted"


def test_trigger_is_honored_in_pynput_adapter():
    class Key:
        name = "f9"
        char = None

    # An ACTIVATE (tap) binding must emit ACTIVATED only, never DEACTIVATED.
    activate = PynputShortcutAdapter()
    activate.update_bindings([ShortcutBinding("switch", "F9", ShortcutTrigger.ACTIVATE)])
    activate_events = []
    activate.on_event = activate_events.append
    activate._press(Key())
    activate._release(Key())
    assert [event.type.value for event in activate_events] == ["activated"]

    # A HOLD binding still emits both press and release.
    hold = PynputShortcutAdapter()
    hold.update_bindings([ShortcutBinding("ptt", "F9", ShortcutTrigger.HOLD)])
    hold_events = []
    hold.on_event = hold_events.append
    hold._press(Key())
    hold._release(Key())
    assert [event.type.value for event in hold_events] == ["activated", "deactivated"]


def test_gnome_accelerator_translation():
    assert input_output._to_gnome_accelerator("F9") == "F9"
    assert input_output._to_gnome_accelerator("Ctrl+Alt+M") == "<Control><Alt>m"
    assert input_output._to_gnome_accelerator("Super+Shift+K") == "<Super><Shift>k"


def test_split_accelerator_tolerates_legacy_bracket_format():
    assert input_output._split_accelerator("<ctrl>+<alt>+m") == input_output._split_accelerator("ctrl+alt+m")
    assert input_output._split_accelerator("<ctrl>+<alt>+m") == ({"ctrl", "alt"}, "m")


def test_gnome_accelerator_translation_tolerates_legacy_format():
    assert input_output._to_gnome_accelerator("<ctrl>+<alt>+m") == "<Control><Alt>m"
    assert input_output._to_gnome_accelerator("Ctrl+Alt+M") == "<Control><Alt>m"


def test_pynput_matches_legacy_bracket_accelerator():
    class MKey:
        name = "m"
        char = "m"

    for accelerator in ("ctrl+alt+m", "<ctrl>+<alt>+m"):
        adapter = PynputShortcutAdapter()
        adapter.update_bindings([ShortcutBinding("switch", accelerator, ShortcutTrigger.ACTIVATE)])
        events = []
        adapter.on_event = events.append
        adapter.pressed = {"ctrl", "alt"}
        adapter._press(MKey())
        assert [event.type.value for event in events] == ["activated"], accelerator


# ---------------------------------------------------------------------------
# GNOME custom-keybinding press-to-toggle adapter (media-keys).
# All gsettings/D-Bus interaction is mocked; nothing touches the real desktop.
# ---------------------------------------------------------------------------

_KB_BASE = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"


class _FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _gsettings_fake(list_value="@as []", record=None):
    """Fake ``subprocess.run`` for gsettings that serves a custom-keybindings
    list and (optionally) records every invocation."""
    def run(cmd, **kwargs):
        if record is not None:
            record.append(list(cmd))
        if cmd[:2] == ["gsettings", "get"] and cmd[-1] == "custom-keybindings":
            return _FakeProc(stdout=list_value)
        return _FakeProc()
    return run


def test_keybinding_registration_writes_entries_and_preserves_list(monkeypatch):
    adapter = GnomeKeybindingShortcutAdapter()
    adapter.bindings = [
        ShortcutBinding("push_to_talk", "F9", ShortcutTrigger.HOLD),
        ShortcutBinding("mode_switch", "Ctrl+Alt+M", ShortcutTrigger.ACTIVATE),
    ]
    adapter._binding_ids = {"push_to_talk", "mode_switch"}
    calls = []
    existing = repr([_KB_BASE + "custom0/"])
    monkeypatch.setattr(input_output.subprocess, "run", _gsettings_fake(existing, record=calls))

    status = adapter._register()
    assert status.state == AdapterState.READY

    ptt = _KB_BASE + "witticism-push-to-talk/"
    sets = [c for c in calls if c[:2] == ["gsettings", "set"]]
    name = next(c for c in sets if ptt in c[2] and c[3] == "name")
    assert name[4] == "Witticism push-to-talk"
    command = next(c for c in sets if ptt in c[2] and c[3] == "command")
    assert "--dest com.stannardlabs.Witticism" in command[4]
    assert "--object-path /com/stannardlabs/Witticism" in command[4]
    assert command[4].endswith("TriggerShortcut push_to_talk")
    binding = next(c for c in sets if ptt in c[2] and c[3] == "binding")
    assert binding[4] == "F9"
    switch = next(c for c in sets if "witticism-mode-switch/" in c[2] and c[3] == "binding")
    assert switch[4] == "<Control><Alt>m"

    # The list write preserved the user entry and appended both of ours.
    list_write = next(c for c in sets if c[3] == "custom-keybindings")
    written = ast.literal_eval(list_write[4])
    assert _KB_BASE + "custom0/" in written
    assert ptt in written
    assert _KB_BASE + "witticism-mode-switch/" in written


def test_keybinding_registration_refuses_to_clobber_unparseable_list(monkeypatch):
    adapter = GnomeKeybindingShortcutAdapter()
    adapter.bindings = [ShortcutBinding("push_to_talk", "F9", ShortcutTrigger.HOLD)]
    adapter._binding_ids = {"push_to_talk"}
    sets = []

    def run(cmd, **kwargs):
        if cmd[:2] == ["gsettings", "get"]:
            return _FakeProc(stdout="not-a-parseable-list")
        if cmd[:2] == ["gsettings", "set"]:
            sets.append(list(cmd))
        return _FakeProc()

    monkeypatch.setattr(input_output.subprocess, "run", run)
    status = adapter._register()
    assert status.state == AdapterState.FAILED
    # Nothing was written: a non-empty unparseable list must never be clobbered.
    assert sets == []


def test_keybinding_registration_treats_empty_as_list(monkeypatch):
    adapter = GnomeKeybindingShortcutAdapter()
    adapter.bindings = [ShortcutBinding("push_to_talk", "F9", ShortcutTrigger.HOLD)]
    adapter._binding_ids = {"push_to_talk"}
    list_writes = []

    def run(cmd, **kwargs):
        if cmd[:2] == ["gsettings", "get"]:
            return _FakeProc(stdout="@as []")  # the empty-array form
        if cmd[:2] == ["gsettings", "set"] and cmd[3] == "custom-keybindings":
            list_writes.append(ast.literal_eval(cmd[4]))
        return _FakeProc()

    monkeypatch.setattr(input_output.subprocess, "run", run)
    status = adapter._register()
    assert status.state == AdapterState.READY
    assert list_writes[-1] == [_KB_BASE + "witticism-push-to-talk/"]


def test_keybinding_registration_cleans_stale_entries(monkeypatch):
    adapter = GnomeKeybindingShortcutAdapter()
    adapter.bindings = [ShortcutBinding("push_to_talk", "F9", ShortcutTrigger.HOLD)]
    adapter._binding_ids = {"push_to_talk"}
    user = _KB_BASE + "custom0/"
    stale = _KB_BASE + "witticism-old/"
    existing = repr([user, stale])
    resets = []
    list_writes = []

    def run(cmd, **kwargs):
        if cmd[:2] == ["gsettings", "get"]:
            return _FakeProc(stdout=existing)
        if cmd[:2] == ["gsettings", "reset-recursively"]:
            resets.append(cmd[2])
        if cmd[:2] == ["gsettings", "set"] and cmd[3] == "custom-keybindings":
            list_writes.append(ast.literal_eval(cmd[4]))
        return _FakeProc()

    monkeypatch.setattr(input_output.subprocess, "run", run)
    status = adapter._register()
    assert status.state == AdapterState.READY
    final = list_writes[-1]
    assert user in final                                  # user entry preserved
    assert stale not in final                             # stale witticism entry dropped from list
    assert _KB_BASE + "witticism-push-to-talk/" in final  # fresh entry added
    assert any("witticism-old" in r for r in resets)      # stale relocatable entry reset


def test_keybinding_stop_removes_only_our_entries(monkeypatch):
    adapter = GnomeKeybindingShortcutAdapter()
    adapter.bindings = [
        ShortcutBinding("push_to_talk", "F9", ShortcutTrigger.HOLD),
        ShortcutBinding("mode_switch", "Ctrl+Alt+M", ShortcutTrigger.ACTIVATE),
    ]
    adapter.bus = None  # no D-Bus teardown path
    user = _KB_BASE + "custom0/"
    ours1 = _KB_BASE + "witticism-push-to-talk/"
    ours2 = _KB_BASE + "witticism-mode-switch/"
    existing = repr([user, ours1, ours2])
    list_writes = []

    def run(cmd, **kwargs):
        if cmd[:2] == ["gsettings", "get"]:
            return _FakeProc(stdout=existing)
        if cmd[:2] == ["gsettings", "set"] and cmd[3] == "custom-keybindings":
            list_writes.append(ast.literal_eval(cmd[4]))
        return _FakeProc()

    monkeypatch.setattr(input_output.subprocess, "run", run)
    adapter.stop()
    final = list_writes[-1]
    assert user in final
    assert ours1 not in final and ours2 not in final
    assert adapter.status.state == AdapterState.STOPPED


def test_keybinding_trigger_dispatch_known_and_unknown():
    adapter = GnomeKeybindingShortcutAdapter()
    adapter.bindings = [ShortcutBinding("push_to_talk", "F9", ShortcutTrigger.HOLD)]
    adapter._binding_ids = {"push_to_talk"}
    events = []
    adapter.on_event = events.append
    adapter._dispatch_trigger("push_to_talk")   # known -> ACTIVATED
    adapter._dispatch_trigger("not_a_binding")  # unknown -> ignored
    assert [e.id for e in events] == ["push_to_talk"]
    assert events[0].type == ShortcutEventType.ACTIVATED
    assert adapter.supports_hold is False


def test_keybinding_control_interface_routes_to_dispatch():
    pytest.importorskip("dbus_next")
    received = []
    control = input_output._build_control_interface(received.append)
    control.TriggerShortcut("push_to_talk")
    assert received == ["push_to_talk"]


def test_hold_to_toggle_degradation_alternates_and_debounces(monkeypatch):
    # Shrink the press-to-toggle floor so the timing assertions stay fast.
    monkeypatch.setattr(hotkey_manager, "PRESS_TO_TOGGLE_DEBOUNCE_MS", 30)
    adapter = FakeNoHoldAdapter()
    manager = HotkeyManager(DebounceConfig(1), adapter=adapter)
    assert manager.supports_hold is False
    calls = []
    manager.set_callbacks(lambda: calls.append("start"), lambda: calls.append("stop"))
    manager.start()

    adapter.emit("push_to_talk", ShortcutEventType.ACTIVATED)  # first press -> start
    adapter.emit("push_to_talk", ShortcutEventType.ACTIVATED)  # within debounce -> ignored
    assert calls == ["start"]

    time.sleep(0.05)
    adapter.emit("push_to_talk", ShortcutEventType.ACTIVATED)  # next press -> stop
    assert calls == ["start", "stop"]

    time.sleep(0.05)
    adapter.emit("push_to_talk", ShortcutEventType.ACTIVATED)  # press-to-toggle again -> start
    assert calls == ["start", "stop", "start"]

    # A stray release must be ignored (press-to-toggle backends never emit it).
    adapter.emit("push_to_talk", ShortcutEventType.DEACTIVATED)
    assert calls == ["start", "stop", "start"]


def test_toggle_mode_works_on_press_only_backend(monkeypatch):
    monkeypatch.setattr(hotkey_manager, "PRESS_TO_TOGGLE_DEBOUNCE_MS", 30)
    adapter = FakeNoHoldAdapter()
    manager = HotkeyManager(DebounceConfig(1), adapter=adapter)
    manager.set_mode("toggle")
    states = []
    manager.set_callbacks(on_toggle_dictation=lambda active: states.append(active))
    manager.start()

    adapter.emit("push_to_talk", ShortcutEventType.ACTIVATED)  # dictation on
    adapter.emit("push_to_talk", ShortcutEventType.ACTIVATED)  # within debounce -> ignored
    assert states == [True]

    time.sleep(0.05)
    adapter.emit("push_to_talk", ShortcutEventType.ACTIVATED)  # dictation off
    assert states == [True, False]

    time.sleep(0.05)
    adapter.emit("push_to_talk", ShortcutEventType.ACTIVATED)  # dictation on again
    assert states == [True, False, True]


def test_press_to_toggle_debounce_floor_blocks_fast_repeats():
    # Even with a tiny configured ptt debounce, the 250ms floor guards repeats.
    adapter = FakeNoHoldAdapter()
    manager = HotkeyManager(DebounceConfig(1), adapter=adapter)
    assert manager._press_to_toggle_debounce_ms() == hotkey_manager.PRESS_TO_TOGGLE_DEBOUNCE_MS
    calls = []
    manager.set_callbacks(lambda: calls.append("start"), lambda: calls.append("stop"))
    manager.start()

    adapter.emit("push_to_talk", ShortcutEventType.ACTIVATED)  # start
    time.sleep(0.05)  # 50ms, well under the 250ms floor
    adapter.emit("push_to_talk", ShortcutEventType.ACTIVATED)  # blocked by floor
    assert calls == ["start"]


def test_no_hold_adapter_mode_switch_unaffected():
    adapter = FakeNoHoldAdapter()
    manager = HotkeyManager(DebounceConfig(50), adapter=adapter)
    calls = []
    manager.set_callbacks(on_toggle=lambda: calls.append("toggle"))
    manager.start()
    adapter.emit("mode_switch", ShortcutEventType.ACTIVATED)
    adapter.emit("mode_switch", ShortcutEventType.ACTIVATED)
    assert calls == ["toggle", "toggle"]


def test_output_factory_honors_clipboard_mode(monkeypatch):
    monkeypatch.setattr(input_output.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")

    class ClipboardCfg:
        def get(self, key, default=None):
            return "clipboard" if key == "output.mode" else default

    class TypeCfg:
        def get(self, key, default=None):
            return "type" if key == "output.mode" else default

    assert isinstance(input_output.create_text_output_adapter(ClipboardCfg()), ClipboardTextOutputAdapter)
    # Without clipboard mode, X11 Linux still selects the pynput typer.
    assert input_output.create_text_output_adapter(TypeCfg()).__class__.__name__ == "PynputTextOutputAdapter"


class FakeVersionReply:
    """Stand-in for a dbus-next reply message (only the fields we inspect)."""

    def __init__(self, message_type, error_name=None, body=None):
        self.message_type = message_type
        self.error_name = error_name
        self.body = body or []


def test_portal_probe_detects_per_interface_without_introspection():
    pytest.importorskip("dbus_next")
    from dbus_next import MessageType
    from dbus_next.errors import DBusError

    class FakeBus:
        def __init__(self):
            self.introspect_called = False
            self.calls = []

        async def call(self, msg):
            # We must probe a single property, never introspect the whole tree.
            assert msg.interface == "org.freedesktop.DBus.Properties"
            assert msg.member == "Get"
            interface, prop = msg.body
            assert prop == "version"
            self.calls.append(interface)
            if interface == input_output.REMOTE_DESKTOP:
                return FakeVersionReply(MessageType.METHOD_RETURN)
            if interface == input_output.GLOBAL_SHORTCUTS:
                # Real xdg-desktop-portal answers a missing interface this way.
                return FakeVersionReply(
                    MessageType.ERROR, error_name="org.freedesktop.DBus.Error.InvalidArgs"
                )
            raise DBusError("org.freedesktop.DBus.Error.ServiceUnknown", "no portal", None)

        def introspect(self, *args, **kwargs):
            self.introspect_called = True
            raise AssertionError("must not introspect the full portal tree")

        def disconnect(self):
            pass

    bus = FakeBus()
    # Present interface -> True even though full introspection would explode.
    assert asyncio.run(input_output._probe_portal_interface(input_output.REMOTE_DESKTOP, bus=bus)) is True
    # Definitively-absent interface (InvalidArgs) -> False, not an error.
    assert asyncio.run(input_output._probe_portal_interface(input_output.GLOBAL_SHORTCUTS, bus=bus)) is False
    assert bus.introspect_called is False
    assert bus.calls == [input_output.REMOTE_DESKTOP, input_output.GLOBAL_SHORTCUTS]


def test_portal_probe_raises_on_transport_error():
    pytest.importorskip("dbus_next")
    from dbus_next.errors import DBusError

    class BrokenBus:
        async def call(self, msg):
            raise DBusError("org.freedesktop.DBus.Error.NoReply", "timed out", None)

        def disconnect(self):
            pass

    # Transport-level failures must propagate so the caller does not cache them.
    with pytest.raises(DBusError):
        asyncio.run(input_output._probe_portal_interface(input_output.REMOTE_DESKTOP, bus=BrokenBus()))


def test_portal_has_interface_caches_positive_and_negative(monkeypatch):
    input_output._PORTAL_INTERFACE_CACHE.clear()
    probed = []

    async def fake_probe(interface, bus=None):
        probed.append(interface)
        return interface == input_output.REMOTE_DESKTOP

    monkeypatch.setattr(input_output, "_probe_portal_interface", fake_probe)

    assert input_output.portal_has_interface(input_output.REMOTE_DESKTOP) is True
    assert input_output.portal_has_interface(input_output.REMOTE_DESKTOP) is True
    assert input_output.portal_has_interface(input_output.GLOBAL_SHORTCUTS) is False
    assert input_output.portal_has_interface(input_output.GLOBAL_SHORTCUTS) is False
    # Both positive and definitive-negative results are cached: one probe each.
    assert probed == [input_output.REMOTE_DESKTOP, input_output.GLOBAL_SHORTCUTS]

    # portal_interfaces() reflects the cached subset that is present.
    assert input_output.portal_interfaces() == {input_output.REMOTE_DESKTOP}
    input_output._PORTAL_INTERFACE_CACHE.clear()
