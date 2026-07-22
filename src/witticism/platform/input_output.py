"""Platform input/output adapter contracts and implementations."""

import ast
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
APP_OBJECT_PATH = "/com/stannardlabs/Witticism"
APP_CONTROL_INTERFACE = "com.stannardlabs.Witticism.Control"
# Standard GNOME media-keys custom keyboard shortcuts. Registering an entry here
# is exactly what a user does by hand in Settings > Keyboard > Custom Shortcuts;
# the entry is visible and editable there and is removed when Witticism exits.
GNOME_MEDIA_KEYS_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
GNOME_CUSTOM_KEYBINDING_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
GNOME_CUSTOM_KEYBINDINGS_KEY = "custom-keybindings"
GNOME_CUSTOM_KEYBINDING_BASE = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
DBUS_BUS = "org.freedesktop.DBus"
DBUS_PATH = "/org/freedesktop/DBus"
GNOME_EXTENSION_RECOVERY = (
    "Run: witticism-platform install-gnome-extension, then log out and back in"
)
# Auto-paste consent (config key output.autopaste). Clipboard-first is the
# designed Wayland default; the Remote Desktop portal - and GNOME's permission
# dialog - is only touched after the user explicitly consents.
AUTOPASTE_UNSET = "unset"
AUTOPASTE_GRANTED = "granted"
AUTOPASTE_DECLINED = "declined"
CLIPBOARD_WAYLAND_MESSAGE = "Transcripts are copied to the clipboard - paste with Ctrl+V"
AUTOPASTE_REENABLE_RECOVERY = "Re-enable automatic paste from the tray menu"
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
PORTAL_SESSION_INTERFACE = "org.freedesktop.portal.Session"
PORTAL_SESSION_XML = """<node>
  <interface name="org.freedesktop.portal.Session">
    <method name="Close"/>
    <signal name="Closed"><arg type="a{sv}"/></signal>
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
    #: (e.g. a GNOME custom keyboard shortcut) set this to False so the hotkey
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


def _accelerator_tokens(accelerator):
    """Split an accelerator into (ordered modifier tokens, final key token).

    Tolerates both our plain format ("Ctrl+Alt+M") and the legacy pynput-style
    format that wraps tokens in angle brackets ("<ctrl>+<alt>+m"); the brackets
    are stripped so both formats parse identically. This ordered parse is the
    single source of truth consumed by both pynput matching and the GNOME
    accelerator translation (``_to_gnome_accelerator``).
    """
    tokens = []
    for raw in re.split(r"\+", accelerator):
        token = raw.strip().strip("<>").strip()
        if token:
            tokens.append(token)
    if not tokens:
        return [], ""
    return tokens[:-1], tokens[-1]


def _split_accelerator(accelerator):
    modifiers, key = _accelerator_tokens(accelerator)
    return {modifier.lower() for modifier in modifiers}, key


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

    "F9" -> "F9"; "Ctrl+Alt+M" -> "<Control><Alt>m". Legacy pynput-style input
    ("<ctrl>+<alt>+m") translates identically since it shares the same parse.
    """
    modifiers, key = _accelerator_tokens(accelerator)
    if not key:
        return ""
    prefix = "".join(_GNOME_MODIFIER_MAP.get(mod.lower(), f"<{mod}>") for mod in modifiers)
    if len(key) == 1:
        key = key.lower()
    return prefix + key


class _KeybindingError(Exception):
    """A gsettings operation failed, or the existing custom-keybindings list
    could not be parsed safely (in which case we refuse to overwrite it)."""


def _build_control_interface(dispatch):
    """Build the exported ``com.stannardlabs.Witticism.Control`` service object.

    dbus-next's service machinery is imported lazily so this module stays
    importable without dbus-next. ``dispatch`` is called with the shortcut id
    each time a registered keybinding fires ``gdbus ... TriggerShortcut``.
    """
    from dbus_next.service import ServiceInterface, method

    class _WitticismControl(ServiceInterface):
        def __init__(self):
            super().__init__(APP_CONTROL_INTERFACE)

        @method()
        def TriggerShortcut(self, shortcut_id: "s"):  # noqa: F821 - dbus-next type
            dispatch(shortcut_id)

    return _WitticismControl()


def _parse_uint(text, default):
    """Extract the first unsigned integer from a gsettings value (e.g. the
    ``500`` in ``"uint32 500"``); return ``default`` when there is none."""
    match = re.search(r"\d+", text or "")
    return int(match.group()) if match else default


class _RepeatStreamTracker:
    """Infer hold-to-talk from a GNOME custom-keybinding auto-repeat stream.

    gnome-settings-daemon fires the bound command once per key auto-repeat while
    the key is held. A tap is a single event; a hold is one event, a ~delay gap,
    then events every ~interval until release. We treat that stream as a release
    detector: emit ACTIVATED on the first event of a stream, swallow the repeats,
    and emit DEACTIVATED once the stream goes quiet (key released, or - for a
    tap - after the tap window elapses).

    Pure logic with an injectable ``schedule(seconds, callback) -> handle`` (the
    handle only needs ``.cancel()``) so it is unit-testable without an event
    loop. All calls must happen on a single thread (the async runtime loop);
    it holds no locks.
    """

    def __init__(self, triggers, emit, delay_ms, interval_ms, schedule):
        self._triggers = dict(triggers)          # binding_id -> ShortcutTrigger
        self._emit = emit                        # emit(binding_id, ShortcutEventType)
        self._delay = delay_ms / 1000.0
        self._interval = interval_ms / 1000.0
        self._schedule = schedule
        self._timers = {}                        # binding_id -> timer handle
        self._active = set()                     # binding_ids with a live stream

    def _tap_window(self):
        # Must bridge the first-repeat gap (== delay) plus slack, so a genuine
        # hold's first repeat lands before this fires and cancels the tap guess.
        return self._delay + 4 * self._interval + 0.1

    def _quiet_window(self):
        # Once repeats flow every ~interval, this bounds "the key went quiet".
        return 4 * self._interval + 0.1

    def on_event(self, binding_id):
        if binding_id not in self._triggers:
            return
        if binding_id in self._active:
            # Mid-stream repeat: swallow it, push the quiet deadline out.
            self._arm(binding_id, self._quiet_window())
            return
        # First event of a new stream.
        self._active.add(binding_id)
        self._emit(binding_id, ShortcutEventType.ACTIVATED)
        self._arm(binding_id, self._tap_window())

    def _arm(self, binding_id, seconds):
        handle = self._timers.pop(binding_id, None)
        if handle is not None:
            handle.cancel()
        self._timers[binding_id] = self._schedule(seconds, lambda: self._expire(binding_id))

    def _expire(self, binding_id):
        self._timers.pop(binding_id, None)
        if binding_id not in self._active:
            return
        self._active.discard(binding_id)
        # HOLD bindings have a meaningful release; ACTIVATE (tap) bindings are
        # satisfied by the press alone and emit no deactivation.
        if self._triggers.get(binding_id) == ShortcutTrigger.HOLD:
            self._emit(binding_id, ShortcutEventType.DEACTIVATED)

    def cancel_all(self):
        for handle in self._timers.values():
            try:
                handle.cancel()
            except Exception:
                pass
        self._timers.clear()
        self._active.clear()


class GnomeKeybindingShortcutAdapter(ShortcutAdapter):
    """GNOME Wayland backend built on a standard custom keyboard shortcut.

    This registers an ordinary GNOME custom keyboard shortcut - exactly the kind
    a user creates by hand in Settings > Keyboard > Custom Shortcuts - whose
    command asks Witticism (over its own session-bus name) to trigger the bound
    action. The shortcut is visible and editable in GNOME Settings, injects no
    code into the compositor, requires no logout, and is removed when Witticism
    exits.

    gnome-settings-daemon fires the command once per key auto-repeat while the
    key is held, so when key repeat is enabled (the normal case) this backend
    synthesizes true hold-to-talk by inferring the release from the repeat
    stream (``supports_hold = True``; see :class:`_RepeatStreamTracker`). When
    key repeat is disabled it falls back to press-to-toggle
    (``supports_hold = False``). The optional GNOME Shell extension remains the
    upgrade path to exact, repeat-independent release timing.
    """

    supports_hold = False

    def __init__(self, runtime=None, keyboard_repeat=None):
        self.runtime = runtime or _AsyncDbusRuntime()
        self.bindings = []
        self._binding_ids = set()
        self.on_event = None
        self.bus = None
        self._control = None
        self._tracker = None
        # Read the keyboard repeat settings up front (before HotkeyManager reads
        # supports_hold at construction). Injectable for tests.
        if keyboard_repeat is None:
            keyboard_repeat = self._read_keyboard_repeat()
        self._repeat_enabled, self._repeat_delay_ms, self._repeat_interval_ms = keyboard_repeat
        self.supports_hold = bool(self._repeat_enabled)
        self.status = AdapterStatus(AdapterState.STARTING, "gnome-media-keys")

    @staticmethod
    def _read_keyboard_repeat():
        """Read GNOME keyboard auto-repeat settings (repeat, delay, interval).

        Defaults on any failure: repeat=True, delay=500ms, interval=30ms.
        """
        schema = "org.gnome.desktop.peripherals.keyboard"

        def _get(key):
            try:
                result = subprocess.run(
                    ["gsettings", "get", schema, key],
                    capture_output=True, text=True, check=False,
                )
                return result.stdout.strip() if result.returncode == 0 else ""
            except Exception:
                return ""

        repeat_raw = _get("repeat").lower()
        # Default to enabled unless gsettings explicitly reports false.
        repeat = "false" not in repeat_raw
        delay = _parse_uint(_get("delay"), 500)
        interval = _parse_uint(_get("repeat-interval"), 30)
        return repeat, delay, interval

    # -- capability probe ---------------------------------------------------

    def probe(self):
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
        if "gnome" not in desktop:
            return AdapterStatus(AdapterState.UNAVAILABLE, "gnome-media-keys", "Not a GNOME session")
        return AdapterStatus(
            AdapterState.READY,
            "gnome-media-keys",
            "A standard GNOME custom keyboard shortcut provides press-to-toggle",
            GNOME_EXTENSION_RECOVERY,
        )

    # -- lifecycle ----------------------------------------------------------

    def start(self, bindings, on_event):
        status = self.probe()
        if not status.usable:
            return status
        self.bindings = list(bindings)
        self._binding_ids = {b.id for b in self.bindings}
        self.on_event = on_event
        # Export the D-Bus control object first so the registered gdbus command
        # has something to call. Bounded wait: the export is a couple of local
        # round-trips on the async runtime, not a user-facing operation.
        try:
            self.runtime.submit(self._export_control()).result(timeout=5)
        except Exception as exc:
            self.status = AdapterStatus(
                AdapterState.FAILED,
                "gnome-media-keys",
                f"Could not export the D-Bus control interface: {exc}",
                GNOME_EXTENSION_RECOVERY,
            )
            logger.error("[PLATFORM_ADAPTER] GNOME keybinding D-Bus export failed: %s", exc)
            return self.status
        # When key repeat is on, infer hold-to-talk from the repeat stream. The
        # tracker runs entirely on the runtime loop (same thread as dispatch).
        if self._repeat_enabled:
            self._tracker = self._new_tracker()
        # gsettings writes are fast local operations, safe to run synchronously.
        return self._register()

    def update_bindings(self, bindings):
        self.bindings = list(bindings)
        self._binding_ids = {b.id for b in self.bindings}
        if self._tracker is not None:
            self._tracker.cancel_all()
            self._tracker = self._new_tracker()
        return self._register()

    def stop(self):
        if self._tracker is not None:
            self._tracker.cancel_all()
        try:
            self._deregister()
        except Exception as exc:
            logger.debug("[PLATFORM_ADAPTER] Keybinding deregister failed on stop: %s", exc)
        if self.runtime.loop and self.bus is not None:
            try:
                self.runtime.submit(self._teardown_control()).result(timeout=2)
            except Exception:
                pass
        self.runtime.stop()
        self.status = AdapterStatus(AdapterState.STOPPED, "gnome-media-keys")

    # -- D-Bus control object ----------------------------------------------

    async def _export_control(self):
        from dbus_next.aio import MessageBus

        self.bus = await MessageBus().connect()
        self._control = _build_control_interface(self._dispatch_trigger)
        self.bus.export(APP_OBJECT_PATH, self._control)
        await self.bus.request_name(APP_BUS)
        logger.info("[PLATFORM_ADAPTER] GNOME keybinding control interface exported")

    async def _teardown_control(self):
        try:
            if self._control is not None:
                self.bus.unexport(APP_OBJECT_PATH, self._control)
        except Exception:
            pass
        try:
            await self.bus.release_name(APP_BUS)
        except Exception:
            pass
        try:
            self.bus.disconnect()
        except Exception:
            pass

    def _dispatch_trigger(self, shortcut_id):
        if shortcut_id not in self._binding_ids:
            logger.debug("[PLATFORM_ADAPTER] Ignoring unknown TriggerShortcut id: %s", shortcut_id)
            return
        if self._tracker is not None:
            # Hold-to-talk inference owns emission (ACTIVATED now, DEACTIVATED
            # when the repeat stream goes quiet).
            self._tracker.on_event(shortcut_id)
        else:
            # Press-to-toggle fallback (key repeat disabled): press-only signal.
            self._emit_event(shortcut_id, ShortcutEventType.ACTIVATED)

    def _emit_event(self, shortcut_id, event_type):
        if self.on_event:
            self.on_event(ShortcutEvent(shortcut_id, event_type, int(time.time() * 1000)))

    def _new_tracker(self):
        triggers = {b.id: b.trigger for b in self.bindings}
        return _RepeatStreamTracker(
            triggers, self._emit_event,
            self._repeat_delay_ms, self._repeat_interval_ms, self._schedule_on_loop,
        )

    def _schedule_on_loop(self, seconds, callback):
        # Called on the runtime loop thread (from _dispatch_trigger), so using
        # the loop's non-thread-safe call_later directly is correct here.
        return self.runtime.loop.call_later(seconds, callback)

    # -- gsettings registration --------------------------------------------

    @staticmethod
    def _entry_path(binding_id):
        return f"{GNOME_CUSTOM_KEYBINDING_BASE}witticism-{binding_id.replace('_', '-')}/"

    @staticmethod
    def _is_witticism_path(path):
        return path.startswith(f"{GNOME_CUSTOM_KEYBINDING_BASE}witticism-")

    @staticmethod
    def _trigger_command(binding_id):
        return (
            "gdbus call --session "
            f"--dest {APP_BUS} "
            f"--object-path {APP_OBJECT_PATH} "
            f"--method {APP_CONTROL_INTERFACE}.TriggerShortcut {binding_id}"
        )

    def _read_custom_keybindings(self):
        """Return the current custom-keybindings list, preserving user entries.

        Only ``@as []`` / empty output is treated as an empty list. A non-empty
        value that will not parse is treated as an error so we never risk
        clobbering the user's real keybindings.
        """
        result = subprocess.run(
            ["gsettings", "get", GNOME_MEDIA_KEYS_SCHEMA, GNOME_CUSTOM_KEYBINDINGS_KEY],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            raise _KeybindingError(f"gsettings get {GNOME_CUSTOM_KEYBINDINGS_KEY} failed: {result.stderr.strip()}")
        raw = (result.stdout or "").strip()
        if raw in ("", "@as []", "[]"):
            return []
        try:
            parsed = ast.literal_eval(raw)
        except (SyntaxError, ValueError):
            raise _KeybindingError(
                "Refusing to modify GNOME custom keybindings: the existing list could not be "
                "parsed and overwriting it could clobber your shortcuts"
            )
        if not isinstance(parsed, list):
            raise _KeybindingError("Unexpected GNOME custom-keybindings value; refusing to modify it")
        return [str(item) for item in parsed]

    def _set_entry(self, path, key, value):
        schema = f"{GNOME_CUSTOM_KEYBINDING_SCHEMA}:{path}"
        result = subprocess.run(
            ["gsettings", "set", schema, key, value],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            raise _KeybindingError(f"gsettings set {schema} {key} failed: {result.stderr.strip()}")

    def _write_list(self, paths):
        result = subprocess.run(
            ["gsettings", "set", GNOME_MEDIA_KEYS_SCHEMA, GNOME_CUSTOM_KEYBINDINGS_KEY, repr(paths)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            raise _KeybindingError(f"gsettings set {GNOME_CUSTOM_KEYBINDINGS_KEY} failed: {result.stderr.strip()}")

    def _reset_entry(self, path):
        schema = f"{GNOME_CUSTOM_KEYBINDING_SCHEMA}:{path}"
        try:
            subprocess.run(
                ["gsettings", "reset-recursively", schema],
                capture_output=True, text=True, check=False,
            )
        except Exception as exc:
            logger.debug("[PLATFORM_ADAPTER] reset-recursively %s failed: %s", schema, exc)

    def _register(self):
        try:
            existing = self._read_custom_keybindings()
        except _KeybindingError as exc:
            self.status = AdapterStatus(AdapterState.FAILED, "gnome-media-keys", str(exc), GNOME_EXTENSION_RECOVERY)
            logger.error("[PLATFORM_ADAPTER] GNOME keybinding registration aborted: %s", exc)
            return self.status
        our_paths = [self._entry_path(b.id) for b in self.bindings]
        our_set = set(our_paths)
        # Crash-recovery: drop any leftover witticism-* entries from a prior run,
        # while preserving every user entry, then register a fresh set.
        stale = [p for p in existing if self._is_witticism_path(p) and p not in our_set]
        preserved = [p for p in existing if not self._is_witticism_path(p)]
        new_list = preserved + our_paths
        written = []
        try:
            for binding in self.bindings:
                path = self._entry_path(binding.id)
                self._set_entry(path, "name", f"Witticism {binding.id.replace('_', '-')}")
                self._set_entry(path, "command", self._trigger_command(binding.id))
                self._set_entry(path, "binding", _to_gnome_accelerator(binding.accelerator))
                written.append(path)
            self._write_list(new_list)
        except _KeybindingError as exc:
            self._rollback(written, existing)
            self.status = AdapterStatus(AdapterState.FAILED, "gnome-media-keys", str(exc), GNOME_EXTENSION_RECOVERY)
            logger.error("[PLATFORM_ADAPTER] GNOME keybinding registration failed: %s", exc)
            return self.status
        for path in stale:
            self._reset_entry(path)
        self.status = self._ready_status()
        mode = "hold-to-talk via key repeat" if self._repeat_enabled else "press-to-toggle"
        logger.info("[PLATFORM_ADAPTER] GNOME custom keyboard shortcut registered (%s)", mode)
        return self.status

    def _rollback(self, written, original_list):
        for path in written:
            self._reset_entry(path)
        try:
            self._write_list(original_list)
        except _KeybindingError as exc:
            logger.debug("[PLATFORM_ADAPTER] Could not restore keybinding list during rollback: %s", exc)

    def _deregister(self):
        if not self.bindings:
            return
        our_paths = [self._entry_path(b.id) for b in self.bindings]
        our_set = set(our_paths)
        try:
            existing = self._read_custom_keybindings()
        except _KeybindingError:
            existing = None
        if existing is not None:
            preserved = [p for p in existing if p not in our_set]
            try:
                self._write_list(preserved)
            except _KeybindingError as exc:
                logger.debug("[PLATFORM_ADAPTER] Could not prune keybinding list on stop: %s", exc)
        for path in our_paths:
            self._reset_entry(path)

    def _ready_status(self):
        ptt = next((b for b in self.bindings if b.id == "push_to_talk"), None)
        source = ptt or (self.bindings[0] if self.bindings else None)
        key = source.accelerator.upper() if source else "the hotkey"
        if self._repeat_enabled:
            message = (
                f"Hold {key} to talk (release detected via GNOME key repeat), registered as a "
                "standard GNOME custom keyboard shortcut"
            )
        else:
            message = (
                f"{key} is registered as a standard GNOME custom keyboard shortcut (press-to-toggle); "
                "view or change it in Settings > Keyboard"
            )
        return AdapterStatus(AdapterState.READY, "gnome-media-keys", message, GNOME_EXTENSION_RECOVERY)


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
    def __init__(self, message="Direct text output is unsupported on this platform", state=AdapterState.DEGRADED):
        self.status = AdapterStatus(state, "clipboard", message)

    def start(self): return self.status
    def output_text(self, text): return _clipboard(text)
    def copy_to_clipboard(self, text): return _clipboard(text)
    def stop(self): pass


class RemoteDesktopPasteAdapter(TextOutputAdapter):
    """Wayland auto-paste via the Remote Desktop portal - strictly consent-gated.

    Auto-paste is OFF by default. The adapter never touches the Remote Desktop
    portal (no probe, no session, no dialog) until the user has explicitly
    consented through ``request_autopaste()``. Until then it behaves exactly as
    the designed clipboard-only output. A previously granted session is restored
    silently at startup using the persisted token; if that token is gone or
    revoked the adapter falls back to clipboard and asks the user to re-enable,
    rather than silently popping GNOME's permission dialog at startup.
    """

    def __init__(self, config_manager=None):
        self.config = config_manager
        self.runtime = _AsyncDbusRuntime()
        self.bus = None
        self.interface = None
        self.session = None
        self.ready = False
        # Optional UI callback fired when auto-paste is lost (revoked from the
        # system indicator, or a paste failed because the session went away) so
        # the tray can re-surface its "Enable automatic paste..." entry.
        self.on_revoked = None
        self.status = AdapterStatus(AdapterState.STARTING, "xdg-remote-desktop")
        state_dir = Path(platformdirs.user_state_dir("witticism"))
        self.token_file = state_dir / "wayland-portal.json"

    def _consent_state(self):
        if self.config is None:
            return AUTOPASTE_UNSET
        try:
            return self.config.get("output.autopaste", AUTOPASTE_UNSET)
        except Exception:
            return AUTOPASTE_UNSET

    def start(self):
        # Designed default: clipboard-only unless the user has enabled auto-paste.
        # No portal probe or session is issued in this path, so no dialog appears.
        if self._consent_state() != AUTOPASTE_GRANTED:
            self.ready = False
            self.status = AdapterStatus(AdapterState.READY, "clipboard", CLIPBOARD_WAYLAND_MESSAGE)
            return self.status
        if not self._load_token():
            # Granted before, but the restore token is gone: never silently
            # re-prompt at startup - fall back and let the user re-enable.
            self.ready = False
            self.status = AdapterStatus(
                AdapterState.DEGRADED, "clipboard",
                "Automatic paste needs to be re-enabled", AUTOPASTE_REENABLE_RECOVERY,
            )
            return self.status
        # Granted with a saved token: restore the session silently (no dialog).
        self.status = AdapterStatus(AdapterState.STARTING, "xdg-remote-desktop")
        self.runtime.submit(self._restore_session())
        return self.status

    def request_autopaste(self, on_result=None):
        """Start a Remote Desktop portal session.

        This is the ONLY place GNOME's permission dialog may appear. It is
        invoked from the in-app priming flow after the user opts in.
        ``on_result(granted: bool, message)`` fires when the portal flow
        resolves (on the D-Bus runtime thread).
        """
        try:
            self.runtime.submit(self._consent_session(on_result))
        except Exception as exc:
            logger.warning("[PLATFORM_ADAPTER] Auto-paste consent flow failed to start: %s", exc)
            if on_result:
                on_result(False, str(exc))

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

    async def _open_session(self):
        """Open a keyboard-only Remote Desktop portal session.

        With a stored restore token the portal restores silently; without one it
        prompts. Callers gate which path is reachable so a fresh prompt only ever
        happens from the consent flow, never at startup. Raises on failure.
        """
        from dbus_next import Variant
        from dbus_next.aio import MessageBus

        if not portal_has_interface(REMOTE_DESKTOP):
            raise RuntimeError("Remote Desktop portal is unavailable")
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
        await self._subscribe_session_closed()

    async def _subscribe_session_closed(self):
        """Watch the portal session's Closed signal so a mid-session revocation
        (e.g. the user turning auto-paste off from GNOME's system indicator) is
        noticed instead of dying silently."""
        try:
            from dbus_next.introspection import Node

            obj = self.bus.get_proxy_object(PORTAL_BUS, self.session, Node.parse(PORTAL_SESSION_XML))
            session_iface = obj.get_interface(PORTAL_SESSION_INTERFACE)
            session_iface.on_closed(self._on_session_closed)
        except Exception as exc:
            logger.debug("[PLATFORM_ADAPTER] Could not watch session Closed signal: %s", exc)

    def _on_session_closed(self, *_args):
        logger.info("[PLATFORM_ADAPTER] Remote Desktop session was closed by the system; auto-paste revoked")
        self._handle_revocation()

    def _handle_revocation(self):
        """The grant is gone. Drop to clipboard, clear the (now-dead) session,
        and reset consent + token so re-enabling runs the full priming + portal
        flow again and the tray offer reappears."""
        self.ready = False
        self.session = None
        self._reset_consent()
        self.status = AdapterStatus(
            AdapterState.DEGRADED, "clipboard",
            "Automatic paste was turned off from the system indicator - transcripts stay on the clipboard",
            AUTOPASTE_REENABLE_RECOVERY,
        )
        self._notify_revoked()

    def _reset_consent(self):
        self._delete_token()
        if self.config is not None:
            try:
                self.config.set("output.autopaste", AUTOPASTE_UNSET)
            except Exception:
                logger.debug("[PLATFORM_ADAPTER] Could not reset autopaste consent", exc_info=True)

    def _delete_token(self):
        try:
            self.token_file.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            logger.debug("[PLATFORM_ADAPTER] Could not delete restore token", exc_info=True)

    def _notify_revoked(self):
        callback = self.on_revoked
        if callback is None:
            return
        try:
            callback()
        except Exception:
            logger.debug("[PLATFORM_ADAPTER] on_revoked callback failed", exc_info=True)

    async def _restore_session(self):
        """Startup path for an already-granted session: silent token restore."""
        try:
            await self._open_session()
            self.status = AdapterStatus(AdapterState.READY, "xdg-remote-desktop")
            logger.info("[PLATFORM_ADAPTER] Remote Desktop paste restored")
        except Exception as exc:
            self.ready = False
            self.status = AdapterStatus(
                AdapterState.DEGRADED, "clipboard",
                "Automatic paste needs to be re-enabled", AUTOPASTE_REENABLE_RECOVERY,
            )
            logger.warning("[PLATFORM_ADAPTER] Auto-paste session could not be restored: %s", exc)

    async def _consent_session(self, on_result):
        """Consent path: the only place a fresh portal prompt may appear."""
        granted = False
        message = None
        try:
            await self._open_session()
            granted = True
            self.status = AdapterStatus(AdapterState.READY, "xdg-remote-desktop")
            logger.info("[PLATFORM_ADAPTER] Remote Desktop paste enabled")
        except Exception as exc:
            self.ready = False
            message = str(exc)
            self.status = AdapterStatus(AdapterState.READY, "clipboard", CLIPBOARD_WAYLAND_MESSAGE)
            logger.info("[PLATFORM_ADAPTER] Auto-paste was not enabled: %s", exc)
        finally:
            if on_result:
                on_result(granted, message)

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
            # Clipboard-only is the designed default until the user enables
            # auto-paste; report a clean success with no per-transcript warning.
            return OutputResult(True, False)
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
        # A paste failed (often because the session went away just before its
        # Closed signal arrived). The transcript is already on the clipboard -
        # copied before paste - so this only affects future pastes. Closed, if
        # it follows, does the authoritative consent reset.
        self.ready = False
        self.status = AdapterStatus(
            AdapterState.DEGRADED, "clipboard",
            "Automatic paste stopped working - transcripts stay on the clipboard",
            AUTOPASTE_REENABLE_RECOVERY,
        )
        logger.warning("[PLATFORM_ADAPTER] Auto-paste failed; clipboard fallback active: %s", exc)
        self._notify_revoked()

    def copy_to_clipboard(self, text): return _clipboard(text)

    def stop(self):
        self.ready = False
        if self.runtime.loop and self.session:
            try:
                self.runtime.submit(self._close_session()).result(timeout=2)
            except Exception:
                pass
        self.runtime.stop()


# Shared runtime for lightweight, one-off D-Bus queries (portal probes,
# name-owner probes) so we do not spawn a subprocess or an event loop per call.
_query_runtime = _AsyncDbusRuntime()

# Cache of definitive present/absent results per portal interface, kept for the
# process lifetime (the portal surface does not change while the app runs).
_PORTAL_INTERFACE_CACHE = {}

# Known portal interfaces we probe (used by the portal_interfaces() helper that
# the doctor command relies on).
_KNOWN_PORTAL_INTERFACES = (GLOBAL_SHORTCUTS, REMOTE_DESKTOP)

# D-Bus errors that definitively mean "this interface is not present" (as
# opposed to a transport-level failure, which we must not cache).
_PORTAL_ABSENT_ERRORS = frozenset(
    {
        "org.freedesktop.DBus.Error.InvalidArgs",
        "org.freedesktop.DBus.Error.UnknownInterface",
        "org.freedesktop.DBus.Error.UnknownProperty",
        "org.freedesktop.DBus.Error.UnknownMethod",
        "org.freedesktop.DBus.Error.UnknownObject",
    }
)


async def _probe_portal_interface(interface, bus=None):
    """Return whether the desktop portal exposes ``interface``.

    Probes the single interface directly via
    ``org.freedesktop.DBus.Properties.Get(interface, "version")`` on the portal
    object, rather than parsing the full introspection document. Real
    xdg-desktop-portal introspection XML can contain member names that violate
    strict D-Bus rules (e.g. PowerProfileMonitor's ``power-saver-enabled``),
    which makes dbus-next reject the ENTIRE document and hides every portal.

    Returns True on a successful reply, False on a definitive "no such
    interface" error, and RAISES on transport-level failures so the caller can
    avoid caching a transient error.
    """
    from dbus_next import Message, MessageType
    from dbus_next.errors import DBusError

    owns_bus = bus is None
    if owns_bus:
        from dbus_next.aio import MessageBus

        bus = await MessageBus().connect()
    try:
        try:
            reply = await bus.call(
                Message(
                    destination=PORTAL_BUS,
                    path=PORTAL_PATH,
                    interface="org.freedesktop.DBus.Properties",
                    member="Get",
                    signature="ss",
                    body=[interface, "version"],
                )
            )
        except DBusError as exc:
            if exc.type in _PORTAL_ABSENT_ERRORS:
                return False
            raise
        # dbus-next's low-level call() returns the reply message rather than
        # raising on an error reply, so inspect it explicitly.
        if reply is not None and reply.message_type == MessageType.ERROR:
            if reply.error_name in _PORTAL_ABSENT_ERRORS:
                return False
            raise DBusError(reply.error_name, reply.body[0] if reply.body else "", reply)
        return True
    finally:
        if owns_bus:
            bus.disconnect()


def portal_has_interface(interface):
    """Whether the desktop portal exposes ``interface`` (cached per process).

    Positive and definitive-negative results are cached for the process
    lifetime; transport-level failures are not cached so a transient D-Bus
    outage can recover on a later call.
    """
    if interface in _PORTAL_INTERFACE_CACHE:
        return _PORTAL_INTERFACE_CACHE[interface]
    try:
        present = _query_runtime.submit(_probe_portal_interface(interface)).result(timeout=5)
    except Exception as exc:
        logger.warning("[PLATFORM_ADAPTER] Portal probe for %s failed: %s", interface, exc)
        return False
    _PORTAL_INTERFACE_CACHE[interface] = present
    return present


def portal_interfaces():
    """Return the subset of known portal interfaces that are present.

    Compatibility helper for callers (e.g. the ``doctor`` command) that expect a
    set of interface names. Each interface is probed directly rather than by
    parsing the full portal introspection tree.
    """
    return {name for name in _KNOWN_PORTAL_INTERFACES if portal_has_interface(name)}


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
            # D-Bus name has an owner); otherwise register a standard GNOME
            # custom keyboard shortcut (press-to-toggle), which needs no install.
            if _dbus_name_has_owner(GNOME_BUS):
                return GnomeShellShortcutAdapter()
            return GnomeKeybindingShortcutAdapter()
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
        return ClipboardTextOutputAdapter("Output mode is set to clipboard", state=AdapterState.READY)
    system = platform.system().lower()
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if system == "windows" or (system == "linux" and session != "wayland"):
        return PynputTextOutputAdapter()
    if system == "linux" and session == "wayland":
        return RemoteDesktopPasteAdapter(config_manager)
    return ClipboardTextOutputAdapter()
