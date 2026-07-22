import asyncio
import os
import stat
import time

import pytest

from witticism.core.hotkey_manager import HotkeyManager
from witticism.platform import input_output
from witticism.platform.input_output import (
    AdapterState,
    AdapterStatus,
    GnomeShellShortcutAdapter,
    ClipboardTextOutputAdapter,
    PynputShortcutAdapter,
    RemoteDesktopPasteAdapter,
    ShortcutEvent,
    ShortcutEventType,
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
    assert isinstance(input_output.create_shortcut_adapter(), GnomeShellShortcutAdapter)


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
