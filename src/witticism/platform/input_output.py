"""Platform input/output adapter contracts and implementations."""

import asyncio
import json
import logging
import os
import platform
import re
import subprocess
import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable, Optional

import platformdirs

logger = logging.getLogger(__name__)
PORTAL_BUS = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
GLOBAL_SHORTCUTS = "org.freedesktop.portal.GlobalShortcuts"
REMOTE_DESKTOP = "org.freedesktop.portal.RemoteDesktop"
GNOME_BUS = "com.stannardlabs.Witticism.Shell"
GNOME_PATH = "/com/stannardlabs/Witticism/Shell"
GNOME_INTERFACE = GNOME_BUS
APP_BUS = "com.stannardlabs.Witticism"
GLOBAL_SHORTCUTS_XML = """<node>
  <interface name="org.freedesktop.portal.GlobalShortcuts">
    <method name="CreateSession"><arg type="a{sv}" direction="in"/><arg type="o" direction="out"/></method>
    <method name="BindShortcuts"><arg type="o" direction="in"/><arg type="a(sa{sv})" direction="in"/><arg type="s" direction="in"/><arg type="a{sv}" direction="in"/><arg type="o" direction="out"/></method>
    <signal name="Activated"><arg type="o"/><arg type="s"/><arg type="t"/><arg type="a{sv}"/></signal>
    <signal name="Deactivated"><arg type="o"/><arg type="s"/><arg type="t"/><arg type="a{sv}"/></signal>
  </interface>
</node>"""
REMOTE_DESKTOP_XML = """<node>
  <interface name="org.freedesktop.portal.RemoteDesktop">
    <method name="CreateSession"><arg type="a{sv}" direction="in"/><arg type="o" direction="out"/></method>
    <method name="SelectDevices"><arg type="o" direction="in"/><arg type="a{sv}" direction="in"/><arg type="o" direction="out"/></method>
    <method name="Start"><arg type="o" direction="in"/><arg type="s" direction="in"/><arg type="a{sv}" direction="in"/><arg type="o" direction="out"/></method>
    <method name="NotifyKeyboardKeysym"><arg type="o" direction="in"/><arg type="a{sv}" direction="in"/><arg type="i" direction="in"/><arg type="u" direction="in"/></method>
  </interface>
</node>"""


class AdapterState(Enum):
    UNAVAILABLE = "unavailable"
    REQUIRES_ACTION = "requires_action"
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass(frozen=True)
class AdapterStatus:
    state: AdapterState
    backend: str
    message: Optional[str] = None
    recovery_action: Optional[str] = None

    @property
    def usable(self):
        return self.state in (AdapterState.STARTING, AdapterState.READY, AdapterState.DEGRADED)


class ShortcutTrigger(Enum):
    HOLD = "hold"
    ACTIVATE = "activate"


class ShortcutEventType(Enum):
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"


@dataclass(frozen=True)
class ShortcutBinding:
    id: str
    accelerator: str
    trigger: ShortcutTrigger


@dataclass(frozen=True)
class ShortcutEvent:
    id: str
    type: ShortcutEventType
    timestamp: int = 0


@dataclass(frozen=True)
class OutputResult:
    success: bool
    pasted: bool = False
    message: Optional[str] = None


class ShortcutAdapter(ABC):
    @abstractmethod
    def probe(self) -> AdapterStatus: ...

    @abstractmethod
    def start(self, bindings: Iterable[ShortcutBinding], on_event: Callable[[ShortcutEvent], None]) -> AdapterStatus: ...

    @abstractmethod
    def update_bindings(self, bindings: Iterable[ShortcutBinding]) -> AdapterStatus: ...

    @abstractmethod
    def stop(self) -> None: ...


class TextOutputAdapter(ABC):
    @abstractmethod
    def start(self) -> AdapterStatus: ...

    @abstractmethod
    def output_text(self, text: str) -> OutputResult: ...

    @abstractmethod
    def copy_to_clipboard(self, text: str) -> OutputResult: ...

    @abstractmethod
    def stop(self) -> None: ...


class UnavailableShortcutAdapter(ShortcutAdapter):
    def __init__(self, message, action):
        self.status = AdapterStatus(AdapterState.UNAVAILABLE, "none", message, action)

    def probe(self): return self.status
    def start(self, bindings, on_event): return self.status
    def update_bindings(self, bindings): return self.status
    def stop(self): pass


def _split_accelerator(accelerator):
    parts = [part.strip() for part in re.split(r"\+", accelerator) if part.strip()]
    return {part.lower() for part in parts[:-1]}, parts[-1] if parts else ""


class PynputShortcutAdapter(ShortcutAdapter):
    def __init__(self):
        self.listener = None
        self.bindings = []
        self.on_event = None
        self.pressed = set()
        self.active = set()
        self.suppressed = set()
        self.last_release = {}
        self.keyboard = None

    def probe(self):
        try:
            from pynput import keyboard
            self.keyboard = keyboard
            return AdapterStatus(AdapterState.READY, "pynput")
        except Exception as exc:
            return AdapterStatus(AdapterState.UNAVAILABLE, "pynput", str(exc), "Install or repair pynput")

    def start(self, bindings, on_event):
        status = self.probe()
        if not status.usable:
            return status
        self.bindings = list(bindings)
        self.on_event = on_event
        self.listener = self.keyboard.Listener(on_press=self._press, on_release=self._release)
        self.listener.start()
        return AdapterStatus(AdapterState.READY, "pynput")

    def update_bindings(self, bindings):
        self.bindings = list(bindings)
        self.active.clear()
        return AdapterStatus(AdapterState.READY, "pynput")

    def _key_name(self, key):
        char = getattr(key, "char", None)
        if char:
            return char.lower()
        return str(getattr(key, "name", key)).lower().replace("key.", "")

    def _modifier_down(self, modifier):
        aliases = {
            "ctrl": {"ctrl", "ctrl_l", "ctrl_r"},
            "control": {"ctrl", "ctrl_l", "ctrl_r"},
            "alt": {"alt", "alt_l", "alt_r", "alt_gr"},
            "shift": {"shift", "shift_l", "shift_r"},
            "super": {"cmd", "cmd_l", "cmd_r"},
            "meta": {"cmd", "cmd_l", "cmd_r"},
        }
        return bool(aliases.get(modifier, {modifier}) & self.pressed)

    def _matches(self, binding, key_name):
        modifiers, target = _split_accelerator(binding.accelerator)
        special = {"escape": "esc", "return": "enter", " ": "space"}
        target = special.get(target.lower(), target.lower())
        return target == key_name and all(self._modifier_down(mod) for mod in modifiers)

    def _press(self, key):
        key_name = self._key_name(key)
        self.pressed.add(key_name)
        now = time.monotonic()
        for binding in self.bindings:
            if binding.id not in self.active and self._matches(binding, key_name):
                if now - self.last_release.get(binding.id, 0) < 0.005:
                    self.suppressed.add(binding.id)
                    continue
                self.active.add(binding.id)
                self.on_event(ShortcutEvent(binding.id, ShortcutEventType.ACTIVATED, int(time.time() * 1000)))

    def _release(self, key):
        key_name = self._key_name(key)
        for binding in self.bindings:
            _, target = _split_accelerator(binding.accelerator)
            target = {"escape": "esc", "return": "enter", " ": "space"}.get(target.lower(), target.lower())
            if binding.id in self.suppressed and target == key_name:
                self.suppressed.remove(binding.id)
                continue
            if binding.id in self.active and target == key_name:
                self.active.remove(binding.id)
                self.last_release[binding.id] = time.monotonic()
                self.on_event(ShortcutEvent(binding.id, ShortcutEventType.DEACTIVATED, int(time.time() * 1000)))
        self.pressed.discard(key_name)

    def stop(self):
        if self.listener:
            self.listener.stop()
        self.listener = None
        self.active.clear()
        self.suppressed.clear()
        self.last_release.clear()
        self.pressed.clear()


class _AsyncDbusRuntime:
    def __init__(self):
        self.loop = None
        self.thread = None
        self.ready = threading.Event()

    def start(self):
        if self.thread:
            return
        self.thread = threading.Thread(target=self._run, daemon=True, name="witticism-dbus")
        self.thread.start()
        self.ready.wait(timeout=2)

    def _run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.ready.set()
        self.loop.run_forever()

    def submit(self, coroutine):
        self.start()
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop)

    def stop(self):
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)
        if self.thread:
            self.thread.join(timeout=2)
        self.loop = None
        self.thread = None


def _token(prefix):
    return f"{prefix}_{uuid.uuid4().hex}"


def _request_path(unique_name, token):
    sender = unique_name.lstrip(":").replace(".", "_")
    return f"/org/freedesktop/portal/desktop/request/{sender}/{token}"


async def _portal_request(bus, method, args, token):
    from dbus_next import MessageType

    expected = _request_path(bus.unique_name, token)
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    accepted_paths = {expected}

    def handler(message):
        if (
            message.message_type == MessageType.SIGNAL
            and message.interface == "org.freedesktop.portal.Request"
            and message.member == "Response"
            and message.path in accepted_paths
            and not future.done()
        ):
            loop.call_soon_threadsafe(future.set_result, message.body)

    bus.add_message_handler(handler)
    try:
        handle = await method(*args)
        accepted_paths.add(handle)
        response, results = await asyncio.wait_for(future, 120)
        if response != 0:
            raise PermissionError("Portal request was cancelled or denied")
        return {key: value.value for key, value in results.items()}
    finally:
        bus.remove_message_handler(handler)


class PortalShortcutAdapter(ShortcutAdapter):
    def __init__(self):
        self.runtime = _AsyncDbusRuntime()
        self.bindings = []
        self.on_event = None
        self.bus = None
        self.session = None
        self.interface = None
        self.status = AdapterStatus(AdapterState.STARTING, "xdg-global-shortcuts")

    def probe(self):
        if portal_has_interface(GLOBAL_SHORTCUTS):
            return AdapterStatus(AdapterState.STARTING, "xdg-global-shortcuts")
        return AdapterStatus(AdapterState.UNAVAILABLE, "xdg-global-shortcuts", "Global Shortcuts portal is unavailable")

    def start(self, bindings, on_event):
        status = self.probe()
        if not status.usable:
            return status
        self.bindings = list(bindings)
        self.on_event = on_event
        self.runtime.submit(self._initialize())
        return self.status

    async def _initialize(self):
        try:
            from dbus_next import Variant
            from dbus_next.aio import MessageBus

            self.bus = await MessageBus().connect()
            from dbus_next.introspection import Node
            obj = self.bus.get_proxy_object(PORTAL_BUS, PORTAL_PATH, Node.parse(GLOBAL_SHORTCUTS_XML))
            self.interface = obj.get_interface(GLOBAL_SHORTCUTS)
            create_token = _token("create")
            result = await _portal_request(
                self.bus,
                self.interface.call_create_session,
                [{"handle_token": Variant("s", create_token), "session_handle_token": Variant("s", _token("session"))}],
                create_token,
            )
            self.session = result["session_handle"]
            bind_token = _token("bind")
            shortcuts = [
                [
                    binding.id,
                    {
                        "description": Variant("s", binding.id.replace("_", " ").title()),
                        "preferred_trigger": Variant("s", binding.accelerator),
                    },
                ]
                for binding in self.bindings
            ]
            await _portal_request(
                self.bus,
                self.interface.call_bind_shortcuts,
                [self.session, shortcuts, "", {"handle_token": Variant("s", bind_token)}],
                bind_token,
            )
            self.interface.on_activated(lambda session, sid, timestamp, options: self._emit(sid, True, timestamp))
            self.interface.on_deactivated(lambda session, sid, timestamp, options: self._emit(sid, False, timestamp))
            self.status = AdapterStatus(AdapterState.READY, "xdg-global-shortcuts")
            logger.info("[PLATFORM_ADAPTER] Global Shortcuts portal ready")
        except Exception as exc:
            self.status = AdapterStatus(AdapterState.FAILED, "xdg-global-shortcuts", str(exc), "Review portal permission and retry")
            logger.error("[PLATFORM_ADAPTER] Global Shortcuts portal failed: %s", exc)

    def _emit(self, shortcut_id, active, timestamp):
        self.on_event(ShortcutEvent(shortcut_id, ShortcutEventType.ACTIVATED if active else ShortcutEventType.DEACTIVATED, timestamp))

    def update_bindings(self, bindings):
        self.bindings = list(bindings)
        self.status = AdapterStatus(AdapterState.STARTING, "xdg-global-shortcuts", "Rebinding shortcuts")
        self.runtime.submit(self._restart_session())
        return self.status

    async def _restart_session(self):
        await self._close_session()
        await self._initialize()

    async def _close_session(self):
        if not self.bus or not self.session:
            return
        from dbus_next import Message
        await self.bus.call(Message(destination=PORTAL_BUS, path=self.session, interface="org.freedesktop.portal.Session", member="Close"))
        self.session = None

    def stop(self):
        if self.runtime.loop and self.session:
            try:
                self.runtime.submit(self._close_session()).result(timeout=2)
            except Exception:
                pass
        self.runtime.stop()
        self.status = AdapterStatus(AdapterState.STOPPED, "xdg-global-shortcuts")


class GnomeShellShortcutAdapter(ShortcutAdapter):
    def __init__(self):
        self.runtime = _AsyncDbusRuntime()
        self.bindings = []
        self.on_event = None
        self.interface = None
        self.status = AdapterStatus(AdapterState.STARTING, "gnome-shell-extension")

    def probe(self):
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
        if "gnome" not in desktop:
            return AdapterStatus(AdapterState.UNAVAILABLE, "gnome-shell-extension", "Not a GNOME session")
        return AdapterStatus(AdapterState.STARTING, "gnome-shell-extension")

    def start(self, bindings, on_event):
        self.bindings = list(bindings)
        self.on_event = on_event
        future = self.runtime.submit(self._initialize())
        try:
            future.result(timeout=5)
        except Exception as exc:
            self.status = AdapterStatus(
                AdapterState.REQUIRES_ACTION,
                "gnome-shell-extension",
                str(exc),
                "Run: witticism-platform install-gnome-extension",
            )
        return self.status

    async def _initialize(self):
        try:
            from dbus_next.aio import MessageBus

            bus = await MessageBus().connect()
            await bus.request_name(APP_BUS)
            introspection = await bus.introspect(GNOME_BUS, GNOME_PATH)
            obj = bus.get_proxy_object(GNOME_BUS, GNOME_PATH, introspection)
            self.interface = obj.get_interface(GNOME_INTERFACE)
            self.interface.on_activated(lambda sid, timestamp: self._emit(sid, True, timestamp))
            self.interface.on_deactivated(lambda sid, timestamp: self._emit(sid, False, timestamp))
            await self._configure()
            self.status = AdapterStatus(AdapterState.READY, "gnome-shell-extension")
            logger.info("[PLATFORM_ADAPTER] GNOME Shell extension ready")
        except Exception as exc:
            self.status = AdapterStatus(
                AdapterState.REQUIRES_ACTION,
                "gnome-shell-extension",
                str(exc),
                "Run: witticism-platform install-gnome-extension",
            )
            logger.error("[PLATFORM_ADAPTER] GNOME Shell extension unavailable: %s", exc)

    async def _configure(self):
        encoded = [[b.id, b.accelerator, 1 if b.trigger == ShortcutTrigger.HOLD else 0] for b in self.bindings]
        await self.interface.call_configure(encoded)

    def _emit(self, shortcut_id, active, timestamp):
        self.on_event(ShortcutEvent(shortcut_id, ShortcutEventType.ACTIVATED if active else ShortcutEventType.DEACTIVATED, timestamp))

    def update_bindings(self, bindings):
        self.bindings = list(bindings)
        if self.interface:
            self.runtime.submit(self._configure())
        return self.status

    def stop(self):
        self.runtime.stop()
        self.status = AdapterStatus(AdapterState.STOPPED, "gnome-shell-extension")


def _clipboard(text):
    try:
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            app.clipboard().setText(text)
            return OutputResult(True, False)
    except Exception:
        pass
    try:
        import pyperclip
        pyperclip.copy(text)
        return OutputResult(True, False)
    except Exception as exc:
        return OutputResult(False, False, str(exc))


class PynputTextOutputAdapter(TextOutputAdapter):
    def __init__(self):
        self.keyboard = None
        self.status = AdapterStatus(AdapterState.STARTING, "pynput")

    def start(self):
        try:
            from pynput.keyboard import Controller
            self.keyboard = Controller()
            self.status = AdapterStatus(AdapterState.READY, "pynput")
        except Exception as exc:
            self.status = AdapterStatus(AdapterState.FAILED, "pynput", str(exc))
        return self.status

    def output_text(self, text):
        try:
            time.sleep(0.1)
            self.keyboard.type(text)
            return OutputResult(True, True)
        except Exception as exc:
            result = _clipboard(text)
            return OutputResult(result.success, False, f"Typing failed; copied to clipboard: {exc}")

    def copy_to_clipboard(self, text): return _clipboard(text)
    def stop(self): self.keyboard = None


class ClipboardTextOutputAdapter(TextOutputAdapter):
    def __init__(self, message="Direct text output is unsupported on this platform"):
        self.status = AdapterStatus(AdapterState.DEGRADED, "clipboard", message)

    def start(self): return self.status
    def output_text(self, text): return _clipboard(text)
    def copy_to_clipboard(self, text): return _clipboard(text)
    def stop(self): pass


class RemoteDesktopPasteAdapter(TextOutputAdapter):
    def __init__(self):
        self.runtime = _AsyncDbusRuntime()
        self.bus = None
        self.interface = None
        self.session = None
        self.ready = False
        self.status = AdapterStatus(AdapterState.STARTING, "xdg-remote-desktop")
        state_dir = Path(platformdirs.user_state_dir("witticism"))
        self.token_file = state_dir / "wayland-portal.json"

    def start(self):
        if not portal_has_interface(REMOTE_DESKTOP):
            self.status = AdapterStatus(AdapterState.DEGRADED, "clipboard", "Remote Desktop portal unavailable", "Transcripts will remain on the clipboard")
            return self.status
        self.runtime.submit(self._initialize())
        return self.status

    def _load_token(self):
        try:
            return json.loads(self.token_file.read_text()).get("restore_token")
        except Exception:
            return None

    def _store_token(self, token):
        if not token:
            return
        self.token_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.token_file.with_suffix(".tmp")
        temporary.write_text(json.dumps({"restore_token": token}))
        temporary.chmod(0o600)
        temporary.replace(self.token_file)

    async def _initialize(self):
        try:
            from dbus_next import Variant
            from dbus_next.aio import MessageBus

            self.bus = await MessageBus().connect()
            from dbus_next.introspection import Node
            obj = self.bus.get_proxy_object(PORTAL_BUS, PORTAL_PATH, Node.parse(REMOTE_DESKTOP_XML))
            self.interface = obj.get_interface(REMOTE_DESKTOP)
            create_token = _token("create")
            result = await _portal_request(
                self.bus,
                self.interface.call_create_session,
                [{"handle_token": Variant("s", create_token), "session_handle_token": Variant("s", _token("session"))}],
                create_token,
            )
            self.session = result["session_handle"]
            select_token = _token("devices")
            options = {
                "handle_token": Variant("s", select_token),
                "types": Variant("u", 1),
                "persist_mode": Variant("u", 2),
            }
            restore_token = self._load_token()
            if restore_token:
                options["restore_token"] = Variant("s", restore_token)
            await _portal_request(self.bus, self.interface.call_select_devices, [self.session, options], select_token)
            start_token = _token("start")
            started = await _portal_request(
                self.bus,
                self.interface.call_start,
                [self.session, "", {"handle_token": Variant("s", start_token)}],
                start_token,
            )
            if not started.get("devices", 0) & 1:
                raise PermissionError("Keyboard permission was not granted")
            self._store_token(started.get("restore_token"))
            self.ready = True
            self.status = AdapterStatus(AdapterState.READY, "xdg-remote-desktop")
            logger.info("[PLATFORM_ADAPTER] Remote Desktop paste ready")
        except Exception as exc:
            self.ready = False
            self.status = AdapterStatus(AdapterState.DEGRADED, "clipboard", str(exc), "Grant keyboard control to enable automatic paste")
            logger.warning("[PLATFORM_ADAPTER] Auto-paste unavailable; clipboard fallback active: %s", exc)

    async def _paste(self):
        await self.interface.call_notify_keyboard_keysym(self.session, {}, 0xFFE3, 1)
        try:
            await self.interface.call_notify_keyboard_keysym(self.session, {}, ord("v"), 1)
            await self.interface.call_notify_keyboard_keysym(self.session, {}, ord("v"), 0)
        finally:
            await self.interface.call_notify_keyboard_keysym(self.session, {}, 0xFFE3, 0)

    async def _close_session(self):
        if not self.bus or not self.session:
            return
        from dbus_next import Message
        await self.bus.call(Message(destination=PORTAL_BUS, path=self.session, interface="org.freedesktop.portal.Session", member="Close"))
        self.session = None

    def output_text(self, text):
        copied = _clipboard(text)
        if not copied.success:
            return copied
        if not self.ready:
            return OutputResult(True, False, "Copied to clipboard; automatic paste is unavailable")
        try:
            self.runtime.submit(self._paste()).result(timeout=3)
            return OutputResult(True, True)
        except Exception as exc:
            self.ready = False
            self.status = AdapterStatus(AdapterState.DEGRADED, "clipboard", str(exc), "Restart or reauthorize Wayland integration")
            return OutputResult(True, False, f"Copied to clipboard; automatic paste failed: {exc}")

    def copy_to_clipboard(self, text): return _clipboard(text)

    def stop(self):
        self.ready = False
        if self.runtime.loop and self.session:
            try:
                self.runtime.submit(self._close_session()).result(timeout=2)
            except Exception:
                pass
        self.runtime.stop()


def portal_interfaces():
    try:
        result = subprocess.run(
            ["gdbus", "introspect", "--session", "--dest", PORTAL_BUS, "--object-path", PORTAL_PATH],
            capture_output=True, text=True, timeout=3, check=False,
        )
        return set(re.findall(r"interface (org\.freedesktop\.portal\.[A-Za-z]+)", result.stdout))
    except Exception:
        return set()


def portal_has_interface(interface):
    return interface in portal_interfaces()


def create_shortcut_adapter():
    system = platform.system().lower()
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if system == "windows" or (system == "linux" and session != "wayland"):
        return PynputShortcutAdapter()
    if system == "linux" and session == "wayland":
        if portal_has_interface(GLOBAL_SHORTCUTS):
            return PortalShortcutAdapter()
        if "gnome" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower():
            return GnomeShellShortcutAdapter()
        return UnavailableShortcutAdapter(
            "This Wayland compositor does not expose the Global Shortcuts portal",
            "Enable a compatible portal backend or use an X11 session",
        )
    return UnavailableShortcutAdapter("This platform is not supported", "Use Windows or Linux")


def create_text_output_adapter(config_manager=None):
    system = platform.system().lower()
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if system == "windows" or (system == "linux" and session != "wayland"):
        return PynputTextOutputAdapter()
    if system == "linux" and session == "wayland":
        return RemoteDesktopPasteAdapter()
    return ClipboardTextOutputAdapter()
