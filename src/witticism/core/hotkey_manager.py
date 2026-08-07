import logging
import threading
import time
from typing import Callable, Optional

from witticism.platform.input_output import (
    ShortcutBinding,
    ShortcutEvent,
    ShortcutEventType,
    ShortcutTrigger,
    create_shortcut_adapter,
)
from witticism.utils.config_manager import is_usable_accelerator

logger = logging.getLogger(__name__)
DEFAULT_PTT_DEBOUNCE_MS = 30
# Minimum debounce for press-to-toggle backends (no key-release signal). Must be
# well above keyboard auto-repeat (~33ms) so a held key cannot flutter state.
PRESS_TO_TOGGLE_DEBOUNCE_MS = 250


class HotkeyManager:
    """Platform-neutral hotkey state machine."""

    def __init__(self, config_manager=None, adapter=None):
        self.config_manager = config_manager
        self.adapter = adapter or create_shortcut_adapter()
        self.listener = None
        self.on_push_to_talk_start: Optional[Callable] = None
        self.on_push_to_talk_stop: Optional[Callable] = None
        self.on_toggle: Optional[Callable] = None
        self.on_toggle_dictation: Optional[Callable] = None
        self.ptt_key = self._accel_or_default(self._configured("hotkeys.push_to_talk", "f9"), "f9")
        self.mode_switch_key = self._accel_or_default(
            self._configured("hotkeys.mode_switch", "Ctrl+Alt+M"), "Ctrl+Alt+M"
        )
        self.ptt_active = False
        self.mode = "push_to_talk"
        self.dictation_active = False
        self.ptt_debounce_ms = int(self._configured("hotkeys.ptt_debounce_ms", DEFAULT_PTT_DEBOUNCE_MS))
        self._ptt_stop_timer: Optional[threading.Timer] = None
        self._ptt_timer_lock = threading.Lock()
        # Guards ptt_active across the shortcut-event thread (D-Bus/pynput
        # listener) and the debounce Timer thread, so a fresh press racing a
        # firing stop-timer cannot corrupt the recording state.
        self._state_lock = threading.Lock()
        # Set when a mode switch stops an active hold whose key may still be
        # physically down; the next push_to_talk release is then swallowed.
        self._pending_ptt_release = False
        self._last_toggle_press = 0.0
        # Backends that cannot observe key-release (e.g. a GNOME custom
        # keyboard shortcut) advertise supports_hold=False; the manager then
        # turns push-to-talk into press-to-toggle. Unknown adapters default True.
        self.supports_hold = bool(getattr(self.adapter, "supports_hold", True))
        self.status = self.adapter.probe()
        logger.info(
            "[HOTKEY_MANAGER] INIT: mode=%s, ptt_key=%s, debounce=%sms, backend=%s, supports_hold=%s",
            self.mode, self.ptt_key, self.ptt_debounce_ms, self.status.backend, self.supports_hold,
        )

    def _configured(self, key, default):
        return self.config_manager.get(key, default) if self.config_manager else default

    def _bindings(self):
        return [
            ShortcutBinding("push_to_talk", self.ptt_key, ShortcutTrigger.HOLD),
            ShortcutBinding("mode_switch", self.mode_switch_key, ShortcutTrigger.ACTIVATE),
        ]

    def set_callbacks(
        self,
        on_push_to_talk_start=None,
        on_push_to_talk_stop=None,
        on_toggle=None,
        on_toggle_dictation=None,
    ):
        self.on_push_to_talk_start = on_push_to_talk_start
        self.on_push_to_talk_stop = on_push_to_talk_stop
        self.on_toggle = on_toggle
        self.on_toggle_dictation = on_toggle_dictation

    def start(self):
        if self.listener:
            logger.warning("[HOTKEY_MANAGER] ALREADY_STARTED")
            return
        self.status = self.adapter.start(self._bindings(), self._on_shortcut_event)
        self.listener = self.adapter
        log = logger.info if self.status.usable else logger.error
        log(
            "[HOTKEY_MANAGER] %s: backend=%s, state=%s, guidance=%s",
            "STARTED" if self.status.usable else "UNAVAILABLE",
            self.status.backend,
            self.status.state.value,
            self.status.recovery_action or "none",
        )

    def stop(self):
        self._cancel_ptt_stop_timer()
        if self.ptt_active:
            self._do_ptt_stop()
        self.adapter.stop()
        self.listener = None
        logger.info("[HOTKEY_MANAGER] STOPPED")

    def _on_shortcut_event(self, event: ShortcutEvent):
        try:
            if event.id == "mode_switch" and event.type == ShortcutEventType.ACTIVATED:
                if self.on_toggle:
                    self.on_toggle()
                return
            if event.id != "push_to_talk":
                return
            if event.type == ShortcutEventType.ACTIVATED:
                if not self.supports_hold:
                    # Press-only backend: the ACTIVATED press is the only signal
                    # we ever get, so drive both modes from it. push_to_talk
                    # alternates start/stop; toggle flips continuous dictation.
                    if self.mode == "push_to_talk":
                        self._toggle_ptt_press()
                    elif self.mode == "toggle":
                        self._toggle_dictation_press()
                    return
                if self.mode != "push_to_talk":
                    return
                self._cancel_ptt_stop_timer()
                self._begin_ptt()
                return
            if event.type != ShortcutEventType.DEACTIVATED:
                return
            if self._pending_ptt_release:
                # A leftover physical key-release from a capture we already
                # stopped on a mode switch (the key was still held). Consume it
                # so it does not fall through and flip dictation on.
                self._pending_ptt_release = False
                return
            if not self.supports_hold:
                # Press-to-toggle backends never emit release events; ignore any.
                return
            if self.mode == "push_to_talk" and self.ptt_active:
                self._schedule_ptt_stop() if self.ptt_debounce_ms > 0 else self._do_ptt_stop()
            elif self.mode == "toggle":
                self.dictation_active = not self.dictation_active
                if self.on_toggle_dictation:
                    self.on_toggle_dictation(self.dictation_active)
        except Exception:
            logger.exception("[HOTKEY_MANAGER] SHORTCUT_EVENT_ERROR")

    def _press_to_toggle_debounce_ms(self):
        # Press-to-toggle needs a much larger guard than hold-to-talk's release
        # debounce: keyboard auto-repeat fires roughly every ~33ms, so the 30ms
        # default would let repeats flutter the recording state. No human
        # intentionally toggles twice within a quarter second.
        return max(self.ptt_debounce_ms, PRESS_TO_TOGGLE_DEBOUNCE_MS)

    def _toggle_debounced(self):
        """Return True if this press should act, updating the debounce clock."""
        now = time.monotonic()
        if (now - self._last_toggle_press) * 1000 < self._press_to_toggle_debounce_ms():
            return False
        self._last_toggle_press = now
        return True

    def _toggle_ptt_press(self):
        if not self._toggle_debounced():
            return
        # Alternate start/stop; each transition fires its own callback under the
        # lock (see _begin_ptt / _end_ptt).
        if not self._begin_ptt():
            self._end_ptt()

    def _begin_ptt(self):
        """Atomically transition into recording and fire on_push_to_talk_start.

        Returns True only for the call that made the transition. The callback is
        fired while the lock is held so that, when a fresh press races a firing
        stop-timer on another thread, the start/stop notifications reach
        listeners in the same order as the underlying state transitions. The
        callbacks only enqueue a Qt signal (or, in tests, do trivial work), so
        holding the lock across them is cheap and cannot re-enter these methods.
        """
        with self._state_lock:
            if self.ptt_active:
                return False
            self.ptt_active = True
            if self.on_push_to_talk_start:
                self.on_push_to_talk_start()
            return True

    def _end_ptt(self):
        """Atomically transition out of recording and fire on_push_to_talk_stop.

        Returns True only for the call that made the transition. See _begin_ptt
        for why the callback fires under the lock.
        """
        with self._state_lock:
            if not self.ptt_active:
                return False
            self.ptt_active = False
            if self.on_push_to_talk_stop:
                self.on_push_to_talk_stop()
            return True

    def _toggle_dictation_press(self):
        # Toggle (continuous dictation) mode on a press-only backend: each press
        # flips dictation on/off, mirroring the DEACTIVATED path used by
        # hold-capable backends.
        if not self._toggle_debounced():
            return
        self.dictation_active = not self.dictation_active
        if self.on_toggle_dictation:
            self.on_toggle_dictation(self.dictation_active)

    def _schedule_ptt_stop(self):
        with self._ptt_timer_lock:
            if self._ptt_stop_timer is not None:
                self._ptt_stop_timer.cancel()
            self._ptt_stop_timer = threading.Timer(self.ptt_debounce_ms / 1000.0, self._do_ptt_stop)
            self._ptt_stop_timer.daemon = True
            self._ptt_stop_timer.start()

    def _cancel_ptt_stop_timer(self):
        with self._ptt_timer_lock:
            if self._ptt_stop_timer is not None:
                self._ptt_stop_timer.cancel()
                self._ptt_stop_timer = None

    def _do_ptt_stop(self):
        with self._ptt_timer_lock:
            self._ptt_stop_timer = None
        self._end_ptt()

    def update_hotkey_from_string(self, key_string: str, hotkey_type: str = "ptt"):
        if hotkey_type != "ptt" or not self._valid_ptt_key(key_string):
            return False
        old = self.ptt_key
        self.ptt_key = key_string
        if self.listener:
            self.status = self.adapter.update_bindings(self._bindings())
        logger.info("[HOTKEY_MANAGER] PTT_KEY_CHANGED: from %s to %s", old, key_string)
        return True

    @staticmethod
    def _valid_ptt_key(key_string):
        if not isinstance(key_string, str) or not key_string:
            return False
        upper = key_string.upper()
        return upper in {f"F{i}" for i in range(1, 13)} | {"SPACE", "TAB", "ENTER", "ESC"} or len(key_string) == 1

    @staticmethod
    def _accel_or_default(value, default):
        """Coerce a configured accelerator to a usable string.

        A null/number/empty/modifier-only value (from a hand-edited or
        partially-migrated config) would otherwise reach the accelerator parser,
        which raises on a non-string. Uses the same usability rule as the config
        migration (is_usable_accelerator) so the two cannot diverge; falls back
        to the default so a bad config disables nothing.
        """
        return value if is_usable_accelerator(value) else default

    def set_mode(self, mode: str):
        if mode not in ("push_to_talk", "toggle"):
            raise ValueError(f"Invalid mode: {mode}")
        if self.mode == "toggle" and mode == "push_to_talk" and self.dictation_active:
            self.dictation_active = False
            if self.on_toggle_dictation:
                self.on_toggle_dictation(False)
        # Symmetric to the above: leaving push-to-talk with a capture in flight
        # must stop it. Otherwise the in-flight press never gets its matching
        # release (subsequent ACTIVATED events route to dictation), so ptt_active
        # stays set, the mic keeps recording until shutdown, and tray health is
        # pinned at RECORDING.
        if self.mode == "push_to_talk" and mode == "toggle":
            self._cancel_ptt_stop_timer()
            # Stop the in-flight capture. On a hold-capable backend the physical
            # key may still be down, so remember that its release is coming and
            # must not be misread as a dictation toggle once we are in toggle mode.
            if self._end_ptt() and self.supports_hold:
                self._pending_ptt_release = True
        old = self.mode
        self.mode = mode
        logger.info("[HOTKEY_MANAGER] MODE_CHANGED: from %s to %s", old, mode)
