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
    RemoteDesktopTypeAdapter,
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
    # The adapter reads keyboard-repeat settings in __init__; mock gsettings so
    # the test never touches the real desktop. Repeat on -> hold-to-talk.
    monkeypatch.setattr(input_output.subprocess, "run", _keyboard_repeat_gsettings(True))
    adapter = input_output.create_shortcut_adapter()
    assert isinstance(adapter, GnomeKeybindingShortcutAdapter)
    assert adapter.supports_hold is True
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


def test_char_to_keysym_mapping():
    to = input_output._char_to_keysym
    # Printable ASCII maps to its own codepoint (case/symbols carried directly).
    assert to("a") == ord("a")
    assert to("A") == ord("A")
    assert to("Z") == ord("Z")
    assert to("1") == ord("1")
    assert to(" ") == 0x20
    assert to("~") == 0x7E
    assert to("!") == ord("!")
    # Non-ASCII -> Unicode keysym (0x01000000 + codepoint).
    assert to("é") == 0x01000000 + ord("é")
    assert to("emoji"[0]) == ord("e")  # sanity: ascii unaffected
    assert to("\U0001F600") == 0x01000000 + 0x1F600  # grinning face emoji
    # Whitespace controls.
    assert to("\n") == 0xFF0D  # XK_Return
    assert to("\r") == 0xFF0D
    assert to("\t") == 0xFF09  # XK_Tab


def test_type_text_emits_press_release_per_char_in_order():
    class Interface:
        def __init__(self):
            self.calls = []

        async def call_notify_keyboard_keysym(self, session, options, keysym, state):
            self.calls.append((keysym, state))

    adapter = RemoteDesktopTypeAdapter()
    adapter.interface = Interface()
    adapter.session = "/session/1"
    asyncio.run(adapter._type_text("Hi\n"))
    # Each character is a press (1) then release (0), in order, no modifiers.
    assert adapter.interface.calls == [
        (ord("H"), 1), (ord("H"), 0),
        (ord("i"), 1), (ord("i"), 0),
        (0xFF0D, 1), (0xFF0D, 0),
    ]


def test_type_text_failure_midway_propagates():
    class Interface:
        def __init__(self):
            self.calls = []

        async def call_notify_keyboard_keysym(self, session, options, keysym, state):
            self.calls.append((keysym, state))
            if keysym == ord("i") and state == 1:
                raise RuntimeError("session is gone")

    adapter = RemoteDesktopTypeAdapter()
    adapter.interface = Interface()
    adapter.session = "/session/1"
    # A mid-type failure surfaces to the done-callback path (which degrades).
    with pytest.raises(RuntimeError):
        asyncio.run(adapter._type_text("Hi"))
    # It failed on the 'i' press, after fully emitting 'H'.
    assert adapter.interface.calls[:2] == [(ord("H"), 1), (ord("H"), 0)]


def test_portal_restore_token_is_private_and_rotated(tmp_path):
    adapter = RemoteDesktopTypeAdapter()
    adapter.token_file = tmp_path / "state" / "wayland-portal.json"
    adapter._store_token("first")
    assert adapter._load_token() == "first"
    assert stat.S_IMODE(adapter.token_file.stat().st_mode) == 0o600
    adapter._store_token("second")
    assert adapter._load_token() == "second"
    assert not adapter.token_file.with_suffix(".tmp").exists()


def test_token_file_created_0600_without_chmod_window(tmp_path, monkeypatch):
    adapter = RemoteDesktopTypeAdapter()
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
    # so the token file itself has no world-readable window: chmod is never called
    # on the token file (only, at most, to tighten the parent state directory).
    assert open_modes == [0o600]
    assert all(call[0] == adapter.token_file.parent for call in chmod_calls)
    assert adapter.token_file not in [call[0] for call in chmod_calls]
    assert stat.S_IMODE(adapter.token_file.stat().st_mode) == 0o600


def test_remote_desktop_output_text_is_non_blocking(monkeypatch):
    adapter = RemoteDesktopTypeAdapter()
    adapter.ready = True

    class NeverRuntime:
        def __init__(self):
            self.loop = object()
            self.future = concurrent.futures.Future()
            self.submitted = 0

        def submit(self, coroutine):
            # Do not run the typing coroutine; return a future that never resolves.
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

    # Returns immediately with an optimistic result even though the typing future
    # is still pending (never resolved) -- i.e. the GUI thread did not block.
    assert result.success is True
    assert result.pasted is True
    assert elapsed < 0.5
    assert runtime.submitted == 1
    assert not runtime.future.done()

    # When the typing eventually fails, the done-callback downgrades the adapter.
    runtime.future.set_exception(RuntimeError("type boom"))
    assert adapter.ready is False
    assert adapter.status.state == AdapterState.DEGRADED
    assert adapter.status.backend == "clipboard"


# ---------------------------------------------------------------------------
# Automatic typing is consent-gated: the adapter must never touch the Remote Desktop
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
    adapter = RemoteDesktopTypeAdapter(_AutopasteConfig(autopaste))
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
    adapter = RemoteDesktopTypeAdapter()
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
    adapter = RemoteDesktopTypeAdapter()
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
    assert isinstance(adapter, RemoteDesktopTypeAdapter)
    assert adapter._consent_state() == "granted"


# ---------------------------------------------------------------------------
# Mid-session revocation: the portal Session Closed signal (e.g. the user turns
# automatic typing off from GNOME's system indicator) must degrade cleanly and reset
# consent so the tray offer reappears.
# ---------------------------------------------------------------------------

class _WritableConfig:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


def test_session_closed_revokes_resets_consent_and_deletes_token(tmp_path):
    cfg = _WritableConfig({"output.autopaste": "granted"})
    adapter = RemoteDesktopTypeAdapter(cfg)
    adapter.token_file = tmp_path / "wayland-portal.json"
    adapter.token_file.write_text('{"restore_token": "tok"}')
    adapter.ready = True
    adapter.session = "/session/1"
    notified = []
    adapter.on_revoked = lambda: notified.append(True)

    adapter._on_session_closed({})  # the portal Closed signal fires

    assert adapter.ready is False
    assert adapter.session is None
    assert adapter.status.state == AdapterState.DEGRADED
    assert adapter.status.backend == "clipboard"
    assert "system indicator" in (adapter.status.message or "")
    # Consent reset + dead token removed so re-enabling runs the full flow again.
    assert cfg.values["output.autopaste"] == "unset"
    assert not adapter.token_file.exists()
    assert notified == [True]  # UI told to re-surface the "Enable..." offer


def test_type_failure_degrades_without_exception(monkeypatch):
    adapter = RemoteDesktopTypeAdapter()
    adapter.ready = True
    notified = []
    adapter.on_revoked = lambda: notified.append(True)
    # Clipboard copy happens before typing is dispatched, so the transcript
    # is already delivered even when the (gone) session makes typing fail.
    monkeypatch.setattr(input_output, "_clipboard", lambda text: OutputResult(True, False))

    class GoneRuntime:
        loop = object()

        def submit(self, coroutine):
            coroutine.close()  # do not run the typing coroutine
            future = concurrent.futures.Future()
            future.set_exception(RuntimeError("session is gone"))
            return future

        def stop(self):
            self.loop = None

    adapter.runtime = GoneRuntime()
    result = adapter.output_text("hello world")

    # No exception surfaced; the clipboard copy succeeded.
    assert result.success is True
    # The failed typing degraded to clipboard and notified the UI.
    assert adapter.ready is False
    assert adapter.status.state == AdapterState.DEGRADED
    assert adapter.status.backend == "clipboard"
    assert notified == [True]


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


def _keyboard_repeat_gsettings(repeat=True, delay=500, interval=30):
    """Fake ``subprocess.run`` answering the three keyboard-repeat gsettings
    reads the keybinding adapter performs in __init__."""
    values = {
        "repeat": "true" if repeat else "false",
        "delay": f"uint32 {delay}",
        "repeat-interval": f"uint32 {interval}",
    }

    def run(cmd, **kwargs):
        if cmd[:2] == ["gsettings", "get"] and cmd[-1] in values:
            return _FakeProc(stdout=values[cmd[-1]])
        return _FakeProc()
    return run


def test_keybinding_registration_writes_entries_and_preserves_list(monkeypatch):
    adapter = GnomeKeybindingShortcutAdapter(keyboard_repeat=(True, 500, 30))
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
    # The command carries the per-process auth secret as the second argument so
    # an unauthenticated caller of TriggerShortcut is rejected.
    assert command[4].endswith(f"TriggerShortcut push_to_talk {adapter._trigger_secret}")
    assert len(adapter._trigger_secret) >= 16
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
    adapter = GnomeKeybindingShortcutAdapter(keyboard_repeat=(True, 500, 30))
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
    adapter = GnomeKeybindingShortcutAdapter(keyboard_repeat=(True, 500, 30))
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
    adapter = GnomeKeybindingShortcutAdapter(keyboard_repeat=(True, 500, 30))
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
    adapter = GnomeKeybindingShortcutAdapter(keyboard_repeat=(True, 500, 30))
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


def test_keybinding_repeat_disabled_is_press_to_toggle():
    adapter = GnomeKeybindingShortcutAdapter(keyboard_repeat=(False, 500, 30))
    assert adapter.supports_hold is False
    assert adapter._tracker is None
    adapter.bindings = [ShortcutBinding("push_to_talk", "F9", ShortcutTrigger.HOLD)]
    adapter._binding_ids = {"push_to_talk"}
    events = []
    adapter.on_event = events.append
    secret = adapter._trigger_secret
    adapter._dispatch_trigger("push_to_talk", secret)   # press-only: single ACTIVATED
    adapter._dispatch_trigger("not_a_binding", secret)  # unknown -> ignored
    adapter._dispatch_trigger("push_to_talk", "wrong")  # bad token -> ignored
    assert [e.id for e in events] == ["push_to_talk"]
    assert events[0].type == ShortcutEventType.ACTIVATED


def test_keybinding_repeat_enabled_supports_hold_and_routes_to_tracker():
    adapter = GnomeKeybindingShortcutAdapter(keyboard_repeat=(True, 500, 30))
    assert adapter.supports_hold is True
    adapter._binding_ids = {"push_to_talk"}

    class _FakeTracker:
        def __init__(self):
            self.seen = []

        def on_event(self, binding_id):
            self.seen.append(binding_id)

    adapter._tracker = _FakeTracker()
    events = []
    adapter.on_event = events.append
    secret = adapter._trigger_secret
    adapter._dispatch_trigger("push_to_talk", secret)   # routed to tracker, not emitted directly
    adapter._dispatch_trigger("not_a_binding", secret)  # unknown -> ignored, not routed
    adapter._dispatch_trigger("push_to_talk", "wrong")  # bad token -> ignored, not routed
    assert adapter._tracker.seen == ["push_to_talk"]
    assert events == []  # the tracker owns emission


def test_keybinding_control_interface_routes_to_dispatch():
    pytest.importorskip("dbus_next")
    received = []
    control = input_output._build_control_interface(lambda sid, token: received.append((sid, token)))
    control.TriggerShortcut("push_to_talk", "secret123")
    assert received == [("push_to_talk", "secret123")]


# ---------------------------------------------------------------------------
# Repeat-stream hold inference: a GNOME custom shortcut fires once per key
# auto-repeat; the tracker turns that stream into ACTIVATED/DEACTIVATED.
# ---------------------------------------------------------------------------

class _FakeHandle:
    def __init__(self, seconds, callback):
        self.seconds = seconds
        self.callback = callback
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class _FakeScheduler:
    def __init__(self):
        self.handles = []

    def __call__(self, seconds, callback):
        handle = _FakeHandle(seconds, callback)
        self.handles.append(handle)
        return handle

    def live(self):
        return [h for h in self.handles if not h.cancelled]

    def fire_live(self):
        # Fire the still-live timers (each re-arm cancels the previous one, so
        # per binding only the latest survives).
        for handle in self.live():
            handle.cancelled = True
            handle.callback()


def _tracker(triggers, delay=500, interval=30):
    events = []
    sched = _FakeScheduler()
    tracker = input_output._RepeatStreamTracker(
        triggers, lambda bid, et: events.append((bid, et)), delay, interval, sched,
    )
    return tracker, events, sched


def test_repeat_tracker_tap_emits_activated_then_deactivated():
    tracker, events, sched = _tracker({"push_to_talk": ShortcutTrigger.HOLD})
    tracker.on_event("push_to_talk")  # single tap event, then silence
    assert events == [("push_to_talk", ShortcutEventType.ACTIVATED)]
    # Tap window bridges the first-repeat gap: 0.5 + 4*0.03 + 0.1 = 0.72s.
    assert sched.live()[-1].seconds == pytest.approx(0.72)
    sched.fire_live()
    assert events == [
        ("push_to_talk", ShortcutEventType.ACTIVATED),
        ("push_to_talk", ShortcutEventType.DEACTIVATED),
    ]


def test_repeat_tracker_hold_single_activated_single_deactivated():
    tracker, events, sched = _tracker({"push_to_talk": ShortcutTrigger.HOLD})
    # First press + three repeats (0, 500, 530, 560), then release => silence.
    for _ in range(4):
        tracker.on_event("push_to_talk")
    # Exactly one ACTIVATED so far, no DEACTIVATED, no intermediate events.
    assert events == [("push_to_talk", ShortcutEventType.ACTIVATED)]
    live = sched.live()
    assert len(live) == 1                          # only the latest timer is live
    assert live[0].seconds == pytest.approx(0.22)  # quiet window 4*0.03 + 0.1
    sched.fire_live()                              # the stream went quiet => release
    assert events == [
        ("push_to_talk", ShortcutEventType.ACTIVATED),
        ("push_to_talk", ShortcutEventType.DEACTIVATED),
    ]


def test_repeat_tracker_activate_swallows_repeats_no_deactivated():
    tracker, events, sched = _tracker({"mode_switch": ShortcutTrigger.ACTIVATE})
    for _ in range(4):
        tracker.on_event("mode_switch")
    assert events == [("mode_switch", ShortcutEventType.ACTIVATED)]
    sched.fire_live()
    # ACTIVATE triggers never emit DEACTIVATED.
    assert events == [("mode_switch", ShortcutEventType.ACTIVATED)]
    # A later tap starts a fresh stream -> ACTIVATED again.
    tracker.on_event("mode_switch")
    assert events == [
        ("mode_switch", ShortcutEventType.ACTIVATED),
        ("mode_switch", ShortcutEventType.ACTIVATED),
    ]


def test_repeat_tracker_ignores_unknown_binding():
    tracker, events, sched = _tracker({"push_to_talk": ShortcutTrigger.HOLD})
    tracker.on_event("mystery")
    assert events == []
    assert sched.handles == []


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


def test_parse_uint_ignores_gsettings_type_annotation():
    # Regression: "uint32 500" must parse as 500, not the 32 inside "uint32".
    # The wrong value made the repeat tracker's tap window ~0.26s instead of
    # ~0.72s, cutting every hold into a phantom short recording plus a restart.
    from witticism.platform.input_output import _parse_uint
    assert _parse_uint("uint32 500", 0) == 500
    assert _parse_uint("uint32 30", 0) == 30
    assert _parse_uint("500", 0) == 500
    assert _parse_uint("", 123) == 123
    assert _parse_uint(None, 123) == 123


# ---------------------------------------------------------------------------
# set_mode must stop an in-flight push-to-talk capture when leaving PTT, or
# ptt_active stays set, the mic records until shutdown, and tray health pins
# at RECORDING (regression for the mode-switch-mid-recording bug).
# ---------------------------------------------------------------------------

def test_set_mode_ptt_to_toggle_stops_active_recording():
    adapter = FakeNoHoldAdapter()
    manager = HotkeyManager(FakeConfig(), adapter=adapter)
    calls = []
    manager.set_callbacks(
        on_push_to_talk_start=lambda: calls.append("start"),
        on_push_to_talk_stop=lambda: calls.append("stop"),
    )
    manager.start()
    adapter.emit("push_to_talk", ShortcutEventType.ACTIVATED)  # press-to-toggle start
    assert manager.ptt_active is True
    manager.set_mode("toggle")
    assert manager.ptt_active is False
    assert calls == ["start", "stop"]


def test_set_mode_ptt_to_toggle_is_noop_when_idle():
    adapter = FakeNoHoldAdapter()
    manager = HotkeyManager(FakeConfig(), adapter=adapter)
    calls = []
    manager.set_callbacks(
        on_push_to_talk_start=lambda: calls.append("start"),
        on_push_to_talk_stop=lambda: calls.append("stop"),
    )
    manager.start()
    manager.set_mode("toggle")  # nothing recording -> no spurious stop
    assert calls == []
    assert manager.ptt_active is False


def test_set_mode_toggle_to_ptt_still_stops_dictation():
    adapter = FakeNoHoldAdapter()
    manager = HotkeyManager(FakeConfig(), adapter=adapter)
    dictation = []
    manager.set_callbacks(on_toggle_dictation=lambda active: dictation.append(active))
    manager.start()
    manager.set_mode("toggle")
    adapter.emit("push_to_talk", ShortcutEventType.ACTIVATED)  # dictation on
    assert manager.dictation_active is True
    manager.set_mode("push_to_talk")
    assert manager.dictation_active is False
    assert dictation == [True, False]


def test_hotkey_manager_coerces_bad_mode_switch_to_default():
    class _BadConfig:
        def get(self, key, default=None):
            if key == "hotkeys.mode_switch":
                return None  # e.g. a partially-migrated/corrupt config
            if key == "hotkeys.ptt_debounce_ms":
                return 1
            return default

    manager = HotkeyManager(_BadConfig(), adapter=FakeShortcutAdapter())
    assert manager.mode_switch_key == "Ctrl+Alt+M"  # coerced, not None


# ---------------------------------------------------------------------------
# D-Bus name-ownership guard.
# ---------------------------------------------------------------------------

def test_require_primary_owner_accepts_owner_and_rejects_squatter():
    pytest.importorskip("dbus_next")
    from dbus_next import RequestNameReply

    # Owning the name (freshly or already) is fine.
    input_output._require_primary_owner(RequestNameReply.PRIMARY_OWNER, input_output.APP_BUS)
    input_output._require_primary_owner(RequestNameReply.ALREADY_OWNER, input_output.APP_BUS)
    # Queued/blocked behind another owner is refused rather than run behind it.
    for reply in (RequestNameReply.IN_QUEUE, RequestNameReply.EXISTS):
        with pytest.raises(RuntimeError):
            input_output._require_primary_owner(reply, input_output.APP_BUS)


# ---------------------------------------------------------------------------
# gsettings rollback: a failure mid-registration must restore the user's
# original custom-keybindings list and reset the entries it wrote.
# ---------------------------------------------------------------------------

def test_keybinding_rollback_restores_list_on_failed_write(monkeypatch):
    adapter = GnomeKeybindingShortcutAdapter(keyboard_repeat=(True, 500, 30))
    adapter.bindings = [
        ShortcutBinding("push_to_talk", "F9", ShortcutTrigger.HOLD),
        ShortcutBinding("mode_switch", "Ctrl+Alt+M", ShortcutTrigger.ACTIVATE),
    ]
    adapter._binding_ids = {"push_to_talk", "mode_switch"}
    user = _KB_BASE + "custom0/"
    original = repr([user])
    list_writes = []
    reset_paths = []

    def run(cmd, **kwargs):
        if cmd[:2] == ["gsettings", "get"] and cmd[-1] == "custom-keybindings":
            return _FakeProc(stdout=original)
        if cmd[:2] == ["gsettings", "set"] and cmd[3] == "custom-keybindings":
            written_list = ast.literal_eval(cmd[4])
            list_writes.append(written_list)
            # Fail the write that adds our entries; allow the rollback restore.
            if any("witticism-" in p for p in written_list):
                return _FakeProc(returncode=1, stderr="boom")
            return _FakeProc()
        if cmd[:2] == ["gsettings", "reset-recursively"]:
            reset_paths.append(cmd[2])
        return _FakeProc()

    monkeypatch.setattr(input_output.subprocess, "run", run)
    status = adapter._register()

    assert status.state == AdapterState.FAILED
    # Our just-written entries were reset, and the original user-only list restored.
    assert any("witticism-push-to-talk" in p for p in reset_paths)
    assert any("witticism-mode-switch" in p for p in reset_paths)
    assert list_writes[-1] == [user]
    # The user's own entry was never among the reset paths.
    assert all("custom0" not in p for p in reset_paths)


# ---------------------------------------------------------------------------
# RemoteDesktop portal handshake (_open_session): the keyboard-granted bitmask,
# restore-token persistence, and restore-token replay were previously untested.
# ---------------------------------------------------------------------------

def _remote_desktop_env(monkeypatch, adapter, started_result, select_options_capture):
    import dbus_next.aio

    monkeypatch.setattr(input_output, "portal_has_interface", lambda name: True)

    class _Iface:
        def call_create_session(self):
            pass

        def call_select_devices(self):
            pass

        def call_start(self):
            pass

    iface = _Iface()

    class _Proxy:
        def get_interface(self, name):
            return iface

    class _Bus:
        def get_proxy_object(self, *args):
            return _Proxy()

        def disconnect(self):
            pass

    class _MB:
        async def connect(self):
            return _Bus()

    monkeypatch.setattr(dbus_next.aio, "MessageBus", lambda: _MB())

    async def fake_portal_request(bus, method, args, token):
        if method == iface.call_create_session:
            return {"session_handle": "/session/1"}
        if method == iface.call_select_devices:
            select_options_capture.append(args[1])
            return {}
        if method == iface.call_start:
            return started_result
        raise AssertionError("unexpected portal method")

    monkeypatch.setattr(input_output, "_portal_request", fake_portal_request)

    async def _noop_subscribe(self):
        return None

    monkeypatch.setattr(RemoteDesktopTypeAdapter, "_subscribe_session_closed", _noop_subscribe)
    return iface


def test_open_session_stores_token_when_keyboard_granted(monkeypatch, tmp_path):
    pytest.importorskip("dbus_next")
    adapter = RemoteDesktopTypeAdapter()
    adapter.token_file = tmp_path / "state" / "wayland-portal.json"
    captured = []
    _remote_desktop_env(monkeypatch, adapter, {"devices": 1, "restore_token": "tok-123"}, captured)

    asyncio.run(adapter._open_session())

    assert adapter.ready is True
    assert adapter.session == "/session/1"
    assert adapter._load_token() == "tok-123"
    assert "restore_token" not in captured[0]  # none existed to replay


def test_open_session_raises_when_keyboard_not_granted(monkeypatch, tmp_path):
    pytest.importorskip("dbus_next")
    adapter = RemoteDesktopTypeAdapter()
    adapter.token_file = tmp_path / "state" / "wayland-portal.json"
    _remote_desktop_env(monkeypatch, adapter, {"devices": 0, "restore_token": "nope"}, [])

    with pytest.raises(PermissionError):
        asyncio.run(adapter._open_session())

    assert adapter.ready is False
    assert adapter._load_token() is None  # nothing persisted on denial


def test_open_session_replays_existing_restore_token(monkeypatch, tmp_path):
    pytest.importorskip("dbus_next")
    adapter = RemoteDesktopTypeAdapter()
    adapter.token_file = tmp_path / "state" / "wayland-portal.json"
    adapter._store_token("prior-token")
    captured = []
    _remote_desktop_env(monkeypatch, adapter, {"devices": 1, "restore_token": "rotated"}, captured)

    asyncio.run(adapter._open_session())

    assert "restore_token" in captured[0]
    assert captured[0]["restore_token"].value == "prior-token"
    assert adapter._load_token() == "rotated"  # rotated token replaces the old one


# ---------------------------------------------------------------------------
# Concurrent transcripts must not interleave their keysyms.
# ---------------------------------------------------------------------------

def test_type_text_serializes_concurrent_calls():
    pytest.importorskip("dbus_next")
    adapter = RemoteDesktopTypeAdapter()
    adapter.session = "/session/1"
    order = []

    class _Iface:
        async def call_notify_keyboard_keysym(self, session, opts, keysym, state):
            if state == 1:  # record presses only
                order.append(chr(keysym))
                await asyncio.sleep(0)  # yield: would interleave without the lock

    adapter.interface = _Iface()

    async def run():
        await asyncio.gather(adapter._type_text("AB"), adapter._type_text("cd"))

    asyncio.run(run())
    assert "".join(order) in ("ABcd", "cdAB")  # never interleaved


def test_store_token_tightens_loose_state_dir(tmp_path):
    adapter = RemoteDesktopTypeAdapter()
    state = tmp_path / "state"
    state.mkdir()
    os.chmod(state, 0o777)  # simulate a pre-existing world-accessible dir
    adapter.token_file = state / "wayland-portal.json"

    adapter._store_token("secret")

    assert stat.S_IMODE(state.stat().st_mode) == 0o700


# ---------------------------------------------------------------------------
# set_mode on a hold-capable backend must not let a dangling key-release (the
# key still held when the user switched modes via the tray) flip dictation on.
# ---------------------------------------------------------------------------

def test_set_mode_hold_backend_swallows_dangling_release():
    adapter = FakeShortcutAdapter()  # supports_hold defaults True
    manager = HotkeyManager(FakeConfig(), adapter=adapter)
    events = []
    manager.set_callbacks(
        on_push_to_talk_start=lambda: events.append("start"),
        on_push_to_talk_stop=lambda: events.append("stop"),
        on_toggle_dictation=lambda active: events.append(("dict", active)),
    )
    manager.start()
    adapter.emit("push_to_talk", ShortcutEventType.ACTIVATED)   # hold begins
    assert manager.ptt_active is True
    manager.set_mode("toggle")                                  # stops the capture
    assert manager.ptt_active is False
    adapter.emit("push_to_talk", ShortcutEventType.DEACTIVATED)  # trailing release
    assert manager.dictation_active is False                    # NOT toggled on
    assert events == ["start", "stop"]                          # no dictation event


def test_hold_backend_toggle_mode_still_flips_dictation_on_release():
    """The swallow only consumes the one dangling release; a normal toggle-mode
    press/release still flips dictation."""
    adapter = FakeShortcutAdapter()  # supports_hold True
    manager = HotkeyManager(FakeConfig(), adapter=adapter)
    flips = []
    manager.set_callbacks(on_toggle_dictation=lambda active: flips.append(active))
    manager.start()
    manager.set_mode("toggle")  # nothing active -> no pending release
    adapter.emit("push_to_talk", ShortcutEventType.ACTIVATED)
    adapter.emit("push_to_talk", ShortcutEventType.DEACTIVATED)
    assert flips == [True]
    assert manager.dictation_active is True


def test_ptt_transition_callbacks_fire_once_under_lock():
    """_begin_ptt/_end_ptt fire their callback exactly once per real transition
    (and inside the state lock, so start/stop cannot be reordered under a race)."""
    adapter = FakeShortcutAdapter()
    manager = HotkeyManager(FakeConfig(), adapter=adapter)
    events = []
    manager.set_callbacks(
        on_push_to_talk_start=lambda: events.append("start"),
        on_push_to_talk_stop=lambda: events.append("stop"),
    )
    manager.start()
    assert manager._begin_ptt() is True
    assert manager._begin_ptt() is False   # already active: no duplicate start
    assert manager._end_ptt() is True
    assert manager._end_ptt() is False     # already stopped: no duplicate stop
    assert events == ["start", "stop"]


def test_set_mode_does_not_arm_swallow_after_release_debounce():
    """If the PTT key was already released (a debounce stop is pending) when the
    user switches to toggle, no trailing release is coming, so the swallow must
    NOT be armed - otherwise the first real toggle press would be eaten."""
    adapter = FakeShortcutAdapter()  # supports_hold True
    manager = HotkeyManager(DebounceConfig(1000), adapter=adapter)
    flips = []
    manager.set_callbacks(on_toggle_dictation=lambda active: flips.append(active))
    manager.start()
    adapter.emit("push_to_talk", ShortcutEventType.ACTIVATED)    # hold begins
    adapter.emit("push_to_talk", ShortcutEventType.DEACTIVATED)  # release -> debounce stop scheduled
    assert manager.ptt_active is True                            # still within debounce window
    manager.set_mode("toggle")                                  # release already seen
    assert manager._pending_ptt_release is False
    adapter.emit("push_to_talk", ShortcutEventType.ACTIVATED)
    adapter.emit("push_to_talk", ShortcutEventType.DEACTIVATED)
    assert flips == [True]                                       # first toggle NOT swallowed


def test_switch_out_and_back_does_not_strand_swallow():
    """Switching PTT->toggle mid-hold then back to PTT must clear the swallow, so
    a later genuine release is never eaten (which would leave the mic stuck)."""
    adapter = FakeShortcutAdapter()  # supports_hold True
    manager = HotkeyManager(FakeConfig(), adapter=adapter)  # debounce 1ms
    events = []
    manager.set_callbacks(
        on_push_to_talk_start=lambda: events.append("start"),
        on_push_to_talk_stop=lambda: events.append("stop"),
    )
    manager.start()
    adapter.emit("push_to_talk", ShortcutEventType.ACTIVATED)   # hold begins (key still down)
    manager.set_mode("toggle")
    assert manager._pending_ptt_release is True                 # armed (key was held)
    manager.set_mode("push_to_talk")
    assert manager._pending_ptt_release is False                # cleared on switch back
    events.clear()
    adapter.emit("push_to_talk", ShortcutEventType.ACTIVATED)
    adapter.emit("push_to_talk", ShortcutEventType.DEACTIVATED)
    time.sleep(0.02)                                            # let the 1ms debounce stop fire
    assert manager.ptt_active is False                          # not stuck recording
    assert events == ["start", "stop"]


def test_set_mode_cancels_not_stops_when_cancel_wired():
    """With a cancel handler wired, leaving PTT mid-capture fires cancel
    (discard), never stop (which would transcribe the partial)."""
    adapter = FakeNoHoldAdapter()
    manager = HotkeyManager(FakeConfig(), adapter=adapter)
    events = []
    manager.set_callbacks(
        on_push_to_talk_start=lambda: events.append("start"),
        on_push_to_talk_stop=lambda: events.append("stop"),
        on_push_to_talk_cancel=lambda: events.append("cancel"),
    )
    manager.start()
    adapter.emit("push_to_talk", ShortcutEventType.ACTIVATED)  # recording
    manager.set_mode("toggle")
    assert events == ["start", "cancel"]
    assert manager.ptt_active is False
