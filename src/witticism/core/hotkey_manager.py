import logging
import threading
from typing import Callable, Optional

from witticism.platform.input_output import (
    ShortcutBinding,
    ShortcutEvent,
    ShortcutEventType,
    ShortcutTrigger,
    create_shortcut_adapter,
)

logger = logging.getLogger(__name__)
DEFAULT_PTT_DEBOUNCE_MS = 30


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
        self.ptt_key = self._configured("hotkeys.push_to_talk", "f9")
        self.mode_switch_key = self._configured("hotkeys.mode_switch", "Ctrl+Alt+M")
        self.ptt_active = False
        self.mode = "push_to_talk"
        self.dictation_active = False
        self.ptt_debounce_ms = int(self._configured("hotkeys.ptt_debounce_ms", DEFAULT_PTT_DEBOUNCE_MS))
        self._ptt_stop_timer: Optional[threading.Timer] = None
        self._ptt_timer_lock = threading.Lock()
        self.status = self.adapter.probe()
        logger.info(
            "[HOTKEY_MANAGER] INIT: mode=%s, ptt_key=%s, debounce=%sms, backend=%s",
            self.mode, self.ptt_key, self.ptt_debounce_ms, self.status.backend,
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
                if self.mode == "push_to_talk":
                    self._cancel_ptt_stop_timer()
                    if not self.ptt_active:
                        self.ptt_active = True
                        if self.on_push_to_talk_start:
                            self.on_push_to_talk_start()
                return
            if event.type != ShortcutEventType.DEACTIVATED:
                return
            if self.mode == "push_to_talk" and self.ptt_active:
                self._schedule_ptt_stop() if self.ptt_debounce_ms > 0 else self._do_ptt_stop()
            elif self.mode == "toggle":
                self.dictation_active = not self.dictation_active
                if self.on_toggle_dictation:
                    self.on_toggle_dictation(self.dictation_active)
        except Exception:
            logger.exception("[HOTKEY_MANAGER] SHORTCUT_EVENT_ERROR")

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
        if self.ptt_active:
            self.ptt_active = False
            if self.on_push_to_talk_stop:
                self.on_push_to_talk_stop()

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

    def change_ptt_key(self, key):
        return self.update_hotkey_from_string(str(getattr(key, "name", key)))

    def set_mode(self, mode: str):
        if mode not in ("push_to_talk", "toggle"):
            raise ValueError(f"Invalid mode: {mode}")
        if self.mode == "toggle" and mode == "push_to_talk" and self.dictation_active:
            self.dictation_active = False
            if self.on_toggle_dictation:
                self.on_toggle_dictation(False)
        old = self.mode
        self.mode = mode
        logger.info("[HOTKEY_MANAGER] MODE_CHANGED: from %s to %s", old, mode)


class GlobalHotkeyManager(HotkeyManager):
    """Compatibility alias; all adapters now support registered bindings."""

    def register_global_hotkey(self, hotkey_str: str, callback: Callable):
        logger.warning("register_global_hotkey is deprecated; use HotkeyManager callbacks")
