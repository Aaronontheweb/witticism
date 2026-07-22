"""Platform input/output adapter contracts and implementations."""

import asyncio
import json
import logging
import os
import platform
import re
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
GNOME_SHELL_BUS = "org.gnome.Shell"
GNOME_SHELL_PATH = "/org/gnome/Shell"
GNOME_SHELL_INTERFACE = "org.gnome.Shell"
DBUS_BUS = "org.freedesktop.DBus"
DBUS_PATH = "/org/freedesktop/DBus"
GNOME_EXTENSION_RECOVERY = (
    "Run: witticism-platform install-gnome-extension, then log out and back in"
)
GNOME_SHELL_XML = """<node>
  <interface name="org.gnome.Shell">
    <method name="GrabAccelerator"><arg type="s" direction="in"/><arg type="u" direction="in"/><arg type="u" direction="in"/><arg type="u" direction="out"/></method>
    <method name="GrabAccelerators"><arg type="a(suu)" direction="in"/><arg type="au" direction="out"/></method>
    <method name="UngrabAccelerator"><arg type="u" direction="in"/><arg type="b" direction="out"/></method>
    <signal name="AcceleratorActivated"><arg type="u"/><arg type="a{sv}"/></signal>
  </interface>
</node>"""
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
    #: Whether this backend can distinguish key-press from key-release, i.e.
    #: support genuine hold-to-talk. Backends that only deliver press events
    #: (e.g. GNOME Shell GrabAccelerator) set this to False so the hotkey
    #: manager can fall back to press-to-toggle.
    supports_hold: bool = True

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
        self._parsed = []
        self._parsed_source = None

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
        self._parse_bindings()
        self.on_event = on_event
        self.listener = self.keyboard.Listener(on_press=self._press, on_release=self._release)
        self.listener.start()
        return AdapterStatus(AdapterState.READY, "pynput")

    def update_bindings(self, bindings):
        self.bindings = list(bindings)
        self._parse_bindings()
        self.active.clear()
        return AdapterStatus(AdapterState.READY, "pynput")

    @staticmethod
    def _parse_accelerator(accelerator):
        modifiers, target = _split_accelerator(accelerator)
        special = {"escape": "esc", "return": "enter", " ": "space"}
        target = special.get(target.lower(), target.lower())
        return modifiers, target

    def _parse_bindings(self):
        """Parse accelerators once so key-event handlers stay off the parse path."""
        self._parsed = [
            (binding.id, *self._parse_accelerator(binding.accelerator), binding.trigger)
            for binding in self.bindings
        ]
        self._parsed_source = self.bindings

    def _parsed_bindings(self):
        # Re-parse only when the binding list object itself changes (start /
        # update_bindings assign a fresh list); never on a per-key-event basis.
        if self._parsed_source is not self.bindings:
            self._parse_bindings()
        return self._parsed

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

    def _press(self, key):
        key_name = self._key_name(key)
        self.pressed.add(key_name)
        now = time.monotonic()
        for binding_id, modifiers, target, _trigger in self._parsed_bindings():
            if binding_id in self.active or target != key_name:
                continue
            if not all(self._modifier_down(mod) for mod in modifiers):
                continue
            if now - self.last_release.get(binding_id, 0) < 0.005:
                self.suppressed.add(binding_id)
                continue
            self.active.add(binding_id)
            self.on_event(ShortcutEvent(binding_id, ShortcutEventType.ACTIVATED, int(time.time() * 1000)))

    def _release(self, key):
        key_name = self._key_name(key)
        for binding_id, _modifiers, target, trigger in self._parsed_bindings():
            if target != key_name:
                continue
            if binding_id in self.suppressed:
                self.suppressed.remove(binding_id)
                continue
            if binding_id in self.active:
                self.active.remove(binding_id)
                self.last_release[binding_id] = time.monotonic()
                # Only hold-to-talk bindings have a meaningful "release"; a
                # tap-to-activate binding is satisfied entirely by the press.
                if trigger == ShortcutTrigger.HOLD:
                    self.on_event(ShortcutEvent(binding_id, ShortcutEventType.DEACTIVATED, int(time.time() * 1000)))
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
        if not self.thread:
            self.thread = threading.Thread(target=self._run, daemon=True, name="witticism-dbus")
            self.thread.start()
        # Fail fast if the loop never comes up: proceeding would let submit()
        # dereference a None loop and raise an opaque AttributeError.
        if not self.ready.wait(timeout=2) or self.loop is None:
            raise RuntimeError("D-Bus async runtime failed to start")

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
        # Return promptly reporting STARTING (which AdapterStatus.usable already
        # treats as usable); _initialize() transitions to READY/REQUIRES_ACTION
        # asynchronously so we never block the caller on D-Bus round-trips.
        self.status = AdapterStatus(AdapterState.STARTING, "gnome-shell-extension")
        try:
            self.runtime.submit(self._initialize())
        except Exception as exc:
            self.status = AdapterStatus(
                AdapterState.FAILED,
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


_GNOME_MODIFIER_MAP = {
    "ctrl": "<Control>",
    "control": "<Control>",
    "alt": "<Alt>",
    "shift": "<Shift>",
    "super": "<Super>",
    "meta": "<Super>",
    "cmd": "<Super>",
    "win": "<Super>",
}


def _to_gnome_accelerator(accelerator):
    """Translate our accelerator format into a GNOME Shell accelerator string.

    "F9" -> "F9"; "Ctrl+Alt+M" -> "<Control><Alt>m".
    """
    parts = [part.strip() for part in accelerator.split("+") if part.strip()]
    if not parts:
        return ""
    *modifiers, key = parts
    prefix = "".join(_GNOME_MODIFIER_MAP.get(mod.lower(), f"<{mod}>") for mod in modifiers)
    if len(key) == 1:
        key = key.lower()
    return prefix + key


class GrabAcceleratorShortcutAdapter(ShortcutAdapter):
    """GNOME Wayland fallback using org.gnome.Shell.GrabAccelerator.

    This backend delivers key-press events only (via AcceleratorActivated); it
    can never observe a release, so it advertises ``supports_hold = False`` and
    the hotkey manager degrades hold-to-talk to press-to-toggle. It is the last
    resort when neither the GlobalShortcuts portal nor the Witticism GNOME Shell
    extension is available.
    """

    supports_hold = False

    def __init__(self, runtime=None):
        self.runtime = runtime or _AsyncDbusRuntime()
        self.bindings = []
        self.on_event = None
        self.bus = None
        self.interface = None
        self.grabs = {}  # action id -> binding id
        self.status = self._degraded_status()

    def _degraded_status(self):
        return AdapterStatus(
            AdapterState.DEGRADED,
            "gnome-shell-grab",
            "Hold-to-talk is unavailable in this session; press-to-toggle is active",
            GNOME_EXTENSION_RECOVERY,
        )

    def probe(self):
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
        if "gnome" not in desktop:
            return AdapterStatus(AdapterState.UNAVAILABLE, "gnome-shell-grab", "Not a GNOME session")
        return self._degraded_status()

    def start(self, bindings, on_event):
        status = self.probe()
        if not status.usable:
            return status
        self.bindings = list(bindings)
        self.on_event = on_event
        # The capability degradation (no hold-to-talk) is known synchronously, so
        # report DEGRADED immediately; the actual grabs happen asynchronously.
        self.status = self._degraded_status()
        try:
            self.runtime.submit(self._initialize())
        except Exception as exc:
            self.status = AdapterStatus(AdapterState.FAILED, "gnome-shell-grab", str(exc), GNOME_EXTENSION_RECOVERY)
        return self.status

    async def _initialize(self):
        try:
            from dbus_next import Message
            from dbus_next.aio import MessageBus
            from dbus_next.introspection import Node

            self.bus = await MessageBus().connect()
            obj = self.bus.get_proxy_object(GNOME_SHELL_BUS, GNOME_SHELL_PATH, Node.parse(GNOME_SHELL_XML))
            self.interface = obj.get_interface(GNOME_SHELL_INTERFACE)
            self.interface.on_accelerator_activated(self._on_accelerator_activated)
            await self._grab_all()
            await self._watch_shell_owner(Message)
            logger.info("[PLATFORM_ADAPTER] GNOME Shell GrabAccelerator ready (press-to-toggle)")
        except Exception as exc:
            self.status = AdapterStatus(AdapterState.FAILED, "gnome-shell-grab", str(exc), GNOME_EXTENSION_RECOVERY)
            logger.error("[PLATFORM_ADAPTER] GNOME Shell GrabAccelerator failed: %s", exc)

    async def _grab_all(self):
        self.grabs = {}
        for binding in self.bindings:
            accelerator = _to_gnome_accelerator(binding.accelerator)
            action = await self.interface.call_grab_accelerator(accelerator, 0, 0)
            if action:
                self.grabs[action] = binding.id

    async def _ungrab_all(self):
        for action in list(self.grabs):
            try:
                await self.interface.call_ungrab_accelerator(action)
            except Exception as exc:
                logger.debug("[PLATFORM_ADAPTER] UngrabAccelerator(%s) failed: %s", action, exc)
        self.grabs = {}

    async def _regrab(self):
        await self._ungrab_all()
        await self._grab_all()

    async def _watch_shell_owner(self, message_cls):
        """Re-grab accelerators if org.gnome.Shell restarts (best effort)."""
        try:
            await self.bus.call(
                message_cls(
                    destination=DBUS_BUS,
                    path=DBUS_PATH,
                    interface=DBUS_BUS,
                    member="AddMatch",
                    signature="s",
                    body=[
                        "type='signal',sender='org.freedesktop.DBus',"
                        "interface='org.freedesktop.DBus',member='NameOwnerChanged',"
                        f"arg0='{GNOME_SHELL_BUS}'"
                    ],
                )
            )
            from dbus_next import MessageType

            def handler(msg):
                if (
                    msg.message_type == MessageType.SIGNAL
                    and msg.interface == DBUS_BUS
                    and msg.member == "NameOwnerChanged"
                    and msg.body
                    and msg.body[0] == GNOME_SHELL_BUS
                    and msg.body[-1]
                ):
                    logger.info("[PLATFORM_ADAPTER] org.gnome.Shell restarted; re-grabbing accelerators")
                    asyncio.ensure_future(self._regrab())

            self.bus.add_message_handler(handler)
        except Exception as exc:
            logger.debug("[PLATFORM_ADAPTER] Could not watch org.gnome.Shell owner: %s", exc)

    def _on_accelerator_activated(self, action, _parameters):
        binding_id = self.grabs.get(action)
        if binding_id is not None and self.on_event:
            self.on_event(ShortcutEvent(binding_id, ShortcutEventType.ACTIVATED, int(time.time() * 1000)))

    def update_bindings(self, bindings):
        self.bindings = list(bindings)
        if self.interface:
            self.runtime.submit(self._regrab())
        return self.status

    def stop(self):
        if self.runtime.loop and self.interface and self.grabs:
            try:
                self.runtime.submit(self._ungrab_all()).result(timeout=2)
            except Exception:
                pass
        self.runtime.stop()
        self.status = AdapterStatus(AdapterState.STOPPED, "gnome-shell-grab")


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
        # Create the file 0600 from its first byte (no world-readable window
        # between write and chmod). O_CREAT's mode only applies on creation, so
        # remove any stale temp file first to guarantee fresh 0600 permissions.
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        payload = json.dumps({"restore_token": token}).encode("utf-8")
        fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)
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
        """Copy ``text`` and dispatch a paste keystroke without blocking.

        Contract: MUST be called on the Qt GUI/main thread. The clipboard copy
        is performed synchronously here (Qt clipboard access is main-thread
        only); the paste keystroke injection is submitted fire-and-forget to
        the async D-Bus runtime so the GUI thread never waits on a portal
        round-trip. A failed paste downgrades this adapter to DEGRADED
        (clipboard-only) via the done-callback so later status queries stay
        honest. The returned OutputResult reflects only what is known
        synchronously: the clipboard succeeded and a paste was dispatched
        (its eventual success is carried by ``status``, not the result).
        """
        copied = _clipboard(text)
        if not copied.success:
            return copied
        if not self.ready:
            return OutputResult(True, False, "Copied to clipboard; automatic paste is unavailable")
        try:
            future = self.runtime.submit(self._paste())
        except Exception as exc:
            self._downgrade(exc)
            return OutputResult(True, False, f"Copied to clipboard; automatic paste failed: {exc}")
        future.add_done_callback(self._on_paste_done)
        return OutputResult(True, True)

    def _on_paste_done(self, future):
        try:
            future.result()
        except Exception as exc:
            self._downgrade(exc)

    def _downgrade(self, exc):
        self.ready = False
        self.status = AdapterStatus(
            AdapterState.DEGRADED, "clipboard", str(exc), "Restart or reauthorize Wayland integration"
        )
        logger.warning("[PLATFORM_ADAPTER] Auto-paste failed; clipboard fallback active: %s", exc)

    def copy_to_clipboard(self, text): return _clipboard(text)

    def stop(self):
        self.ready = False
        if self.runtime.loop and self.session:
            try:
                self.runtime.submit(self._close_session()).result(timeout=2)
            except Exception:
                pass
        self.runtime.stop()


# Shared runtime for lightweight, one-off D-Bus queries (portal introspection,
# name-owner probes) so we do not spawn a subprocess or an event loop per call.
_query_runtime = _AsyncDbusRuntime()
_PORTAL_INTERFACES_CACHE = None


async def _introspect_portal_interfaces():
    from dbus_next.aio import MessageBus

    bus = await MessageBus().connect()
    try:
        node = await bus.introspect(PORTAL_BUS, PORTAL_PATH)
        return {interface.name for interface in node.interfaces}
    finally:
        bus.disconnect()


def portal_interfaces():
    """Return the set of portal interfaces the desktop exposes.

    Uses a native D-Bus introspection call through dbus-next (no dependency on
    the ``gdbus`` binary) and caches the result for the process lifetime, since
    the portal surface does not change while the app runs. A failed lookup is
    not cached so a transient failure can recover on the next call.
    """
    global _PORTAL_INTERFACES_CACHE
    if _PORTAL_INTERFACES_CACHE is not None:
        return _PORTAL_INTERFACES_CACHE
    try:
        interfaces = _query_runtime.submit(_introspect_portal_interfaces()).result(timeout=5)
    except Exception as exc:
        logger.warning("[PLATFORM_ADAPTER] Portal introspection failed: %s", exc)
        return set()
    _PORTAL_INTERFACES_CACHE = interfaces
    return interfaces


def portal_has_interface(interface):
    return interface in portal_interfaces()


async def _name_has_owner(name):
    from dbus_next import Message
    from dbus_next.aio import MessageBus

    bus = await MessageBus().connect()
    try:
        reply = await bus.call(
            Message(
                destination=DBUS_BUS,
                path=DBUS_PATH,
                interface=DBUS_BUS,
                member="NameHasOwner",
                signature="s",
                body=[name],
            )
        )
        return bool(reply.body[0])
    finally:
        bus.disconnect()


def _dbus_name_has_owner(name):
    """Cheap check for whether a well-known D-Bus name currently has an owner."""
    try:
        return _query_runtime.submit(_name_has_owner(name)).result(timeout=3)
    except Exception as exc:
        logger.debug("[PLATFORM_ADAPTER] NameHasOwner(%s) failed: %s", name, exc)
        return False


def create_shortcut_adapter():
    system = platform.system().lower()
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if system == "windows" or (system == "linux" and session != "wayland"):
        return PynputShortcutAdapter()
    if system == "linux" and session == "wayland":
        if portal_has_interface(GLOBAL_SHORTCUTS):
            return PortalShortcutAdapter()
        if "gnome" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower():
            # Prefer the dedicated GNOME Shell extension when it is loaded (its
            # D-Bus name has an owner); otherwise fall back to GrabAccelerator
            # press-to-toggle, which works without any extension install.
            if _dbus_name_has_owner(GNOME_BUS):
                return GnomeShellShortcutAdapter()
            return GrabAcceleratorShortcutAdapter()
        return UnavailableShortcutAdapter(
            "This Wayland compositor does not expose the Global Shortcuts portal",
            "Enable a compatible portal backend or use an X11 session",
        )
    return UnavailableShortcutAdapter("This platform is not supported", "Use Windows or Linux")


def create_text_output_adapter(config_manager=None):
    # An explicit "clipboard" output mode is honored on every platform.
    mode = None
    if config_manager is not None:
        try:
            mode = config_manager.get("output.mode", None)
        except Exception:
            mode = None
    if mode == "clipboard":
        return ClipboardTextOutputAdapter("Output mode is set to clipboard")
    system = platform.system().lower()
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if system == "windows" or (system == "linux" and session != "wayland"):
        return PynputTextOutputAdapter()
    if system == "linux" and session == "wayland":
        return RemoteDesktopPasteAdapter()
    return ClipboardTextOutputAdapter()
