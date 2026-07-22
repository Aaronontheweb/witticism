import asyncio
import concurrent.futures
import os
import stat
import time

import pytest

from witticism.core.hotkey_manager import HotkeyManager
from witticism.platform import input_output
from witticism.platform.input_output import (
    AdapterState,
    AdapterStatus,
    ClipboardTextOutputAdapter,
    GnomeShellShortcutAdapter,
    GrabAcceleratorShortcutAdapter,
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


def test_wayland_factory_uses_grab_accelerator_without_extension(monkeypatch):
    monkeypatch.setattr(input_output.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "ubuntu:GNOME")
    monkeypatch.setattr(input_output, "portal_has_interface", lambda _name: False)
    monkeypatch.setattr(input_output, "_dbus_name_has_owner", lambda _name: False)
    adapter = input_output.create_shortcut_adapter()
    assert isinstance(adapter, GrabAcceleratorShortcutAdapter)
    status = adapter.probe()
    assert status.state == AdapterState.DEGRADED
    assert status.usable
    assert "install-gnome-extension" in status.recovery_action


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


class FakeGrabInterface:
    def __init__(self):
        self.grabbed = []
        self.ungrabbed = []
        self._next_action = 100
        self.signal_handler = None

    def on_accelerator_activated(self, handler):
        self.signal_handler = handler

    async def call_grab_accelerator(self, accelerator, mode_flags, grab_flags):
        self.grabbed.append((accelerator, mode_flags, grab_flags))
        self._next_action += 1
        return self._next_action

    async def call_ungrab_accelerator(self, action):
        self.ungrabbed.append(action)
        return True


def test_grab_accelerator_translation():
    assert input_output._to_gnome_accelerator("F9") == "F9"
    assert input_output._to_gnome_accelerator("Ctrl+Alt+M") == "<Control><Alt>m"
    assert input_output._to_gnome_accelerator("Super+Shift+K") == "<Super><Shift>k"


def test_grab_accelerator_grabs_with_translated_accelerators():
    adapter = GrabAcceleratorShortcutAdapter()
    adapter.interface = FakeGrabInterface()
    adapter.bindings = [
        ShortcutBinding("push_to_talk", "F9", ShortcutTrigger.HOLD),
        ShortcutBinding("mode_switch", "Ctrl+Alt+M", ShortcutTrigger.ACTIVATE),
    ]
    asyncio.run(adapter._grab_all())
    assert adapter.interface.grabbed == [("F9", 0, 0), ("<Control><Alt>m", 0, 0)]
    assert set(adapter.grabs.values()) == {"push_to_talk", "mode_switch"}


def test_grab_accelerator_emits_activated_on_signal():
    adapter = GrabAcceleratorShortcutAdapter()
    adapter.interface = FakeGrabInterface()
    adapter.bindings = [ShortcutBinding("push_to_talk", "F9", ShortcutTrigger.HOLD)]
    asyncio.run(adapter._grab_all())
    events = []
    adapter.on_event = events.append
    action = next(iter(adapter.grabs))
    adapter._on_accelerator_activated(action, {})
    assert len(events) == 1
    assert events[0].id == "push_to_talk"
    assert events[0].type == ShortcutEventType.ACTIVATED
    # This backend can never deliver a release event.
    assert adapter.supports_hold is False


def test_grab_accelerator_ungrabs_on_stop():
    class SyncRuntime:
        def __init__(self):
            self.loop = object()

        def submit(self, coroutine):
            future = concurrent.futures.Future()
            try:
                future.set_result(asyncio.run(coroutine))
            except Exception as exc:  # pragma: no cover - defensive
                future.set_exception(exc)
            return future

        def stop(self):
            self.loop = None

    adapter = GrabAcceleratorShortcutAdapter(runtime=SyncRuntime())
    interface = FakeGrabInterface()
    adapter.interface = interface
    adapter.bindings = [ShortcutBinding("push_to_talk", "F9", ShortcutTrigger.HOLD)]
    asyncio.run(adapter._grab_all())
    grabbed_actions = list(adapter.grabs)
    adapter.stop()
    assert interface.ungrabbed == grabbed_actions
    assert adapter.grabs == {}
    assert adapter.status.state == AdapterState.STOPPED


def test_grab_accelerator_status_degraded_outside_and_unavailable(monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "ubuntu:GNOME")
    adapter = GrabAcceleratorShortcutAdapter()
    status = adapter.probe()
    assert status.state == AdapterState.DEGRADED
    assert status.usable
    assert "install-gnome-extension" in status.recovery_action
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    assert adapter.probe().state == AdapterState.UNAVAILABLE


def test_hold_to_toggle_degradation_alternates_and_debounces():
    adapter = FakeNoHoldAdapter()
    manager = HotkeyManager(DebounceConfig(50), adapter=adapter)
    assert manager.supports_hold is False
    calls = []
    manager.set_callbacks(lambda: calls.append("start"), lambda: calls.append("stop"))
    manager.start()

    adapter.emit("push_to_talk", ShortcutEventType.ACTIVATED)  # first press -> start
    adapter.emit("push_to_talk", ShortcutEventType.ACTIVATED)  # within debounce -> ignored
    assert calls == ["start"]

    time.sleep(0.06)
    adapter.emit("push_to_talk", ShortcutEventType.ACTIVATED)  # next press -> stop
    assert calls == ["start", "stop"]

    time.sleep(0.06)
    adapter.emit("push_to_talk", ShortcutEventType.ACTIVATED)  # press-to-toggle again -> start
    assert calls == ["start", "stop", "start"]

    # A stray release must be ignored (press-to-toggle backends never emit it).
    adapter.emit("push_to_talk", ShortcutEventType.DEACTIVATED)
    assert calls == ["start", "stop", "start"]


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
