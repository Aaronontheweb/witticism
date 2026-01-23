import logging
from pynput import keyboard
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class HotkeyManager:
    def __init__(self, config_manager=None):
        self.listener = None
        self.hotkeys = {}
        self.current_keys = set()

        # Callbacks
        self.on_push_to_talk_start = None
        self.on_push_to_talk_stop = None
        self.on_toggle = None
        self.on_toggle_dictation = None

        # PTT state - read from config or default to F9
        self.ptt_key = keyboard.Key.f9  # default fallback
        if config_manager:
            ptt_key_str = config_manager.get("hotkeys.push_to_talk", "f9")
            if self.update_hotkey_from_string(ptt_key_str):
                logger.info(f"[HOTKEY_MANAGER] CONFIG_PTT_KEY: using configured PTT key '{ptt_key_str}'")
            else:
                logger.warning(f"[HOTKEY_MANAGER] INVALID_PTT_KEY: invalid PTT key '{ptt_key_str}' in config, using default F9")

        self.ptt_active = False

        # Mode state
        self.mode = "push_to_talk"  # "push_to_talk" or "toggle"
        self.dictation_active = False

        ptt_key_name = getattr(self.ptt_key, 'name', str(self.ptt_key))
        logger.info(f"[HOTKEY_MANAGER] INIT: mode={self.mode}, ptt_key={ptt_key_name}")

    def set_callbacks(
        self,
        on_push_to_talk_start: Optional[Callable] = None,
        on_push_to_talk_stop: Optional[Callable] = None,
        on_toggle: Optional[Callable] = None,
        on_toggle_dictation: Optional[Callable] = None
    ):
        self.on_push_to_talk_start = on_push_to_talk_start
        self.on_push_to_talk_stop = on_push_to_talk_stop
        self.on_toggle = on_toggle
        self.on_toggle_dictation = on_toggle_dictation

    def start(self):
        if self.listener:
            logger.warning("[HOTKEY_MANAGER] ALREADY_STARTED: HotkeyManager already started")
            return

        # Create listener for push-to-talk
        self.listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release
        )
        self.listener.start()

        logger.info("[HOTKEY_MANAGER] STARTED: keyboard listener active")

    def stop(self):
        if self.listener:
            self.listener.stop()
            self.listener = None
            logger.info("[HOTKEY_MANAGER] STOPPED: keyboard listener deactivated")

    def _on_key_press(self, key):
        try:
            # Handle F9 based on mode
            if key == self.ptt_key:
                if self.mode == "push_to_talk":
                    # Push-to-talk mode
                    if not self.ptt_active:
                        self.ptt_active = True
                        ptt_key_name = getattr(self.ptt_key, 'name', str(self.ptt_key))
                        logger.debug(f"[HOTKEY_MANAGER] PTT_START: {ptt_key_name} pressed - recording started")
                        if self.on_push_to_talk_start:
                            self.on_push_to_talk_start()
                elif self.mode == "toggle":
                    # Toggle mode - F9 toggles dictation on/off
                    # We'll handle this on key release to avoid repeated toggles
                    pass

            # Track current keys for combinations
            self.current_keys.add(key)

            # Check for mode switch combination (Ctrl+Alt+M)
            if self._is_combo_pressed(
                keyboard.Key.ctrl_l,
                keyboard.Key.alt_l,
                keyboard.KeyCode.from_char('m')
            ):
                logger.debug("[HOTKEY_MANAGER] MODE_TOGGLE_COMBO: Ctrl+Alt+M pressed")
                if self.on_toggle:
                    self.on_toggle()

        except Exception as e:
            logger.error(f"[HOTKEY_MANAGER] KEY_PRESS_ERROR: error in key press handler - {e}")

    def _on_key_release(self, key):
        try:
            # Handle F9 based on mode
            if key == self.ptt_key:
                if self.mode == "push_to_talk":
                    # Push-to-talk mode - stop recording on release
                    if self.ptt_active:
                        self.ptt_active = False
                        ptt_key_name = getattr(self.ptt_key, 'name', str(self.ptt_key))
                        logger.debug(f"[HOTKEY_MANAGER] PTT_STOP: {ptt_key_name} released - recording stopped")
                        if self.on_push_to_talk_stop:
                            self.on_push_to_talk_stop()
                elif self.mode == "toggle":
                    # Toggle mode - toggle dictation state
                    self.dictation_active = not self.dictation_active
                    ptt_key_name = getattr(self.ptt_key, 'name', str(self.ptt_key))
                    logger.debug(f"[HOTKEY_MANAGER] TOGGLE_DICTATION: {ptt_key_name} pressed - dictation {'enabled' if self.dictation_active else 'disabled'}")
                    if self.on_toggle_dictation:
                        self.on_toggle_dictation(self.dictation_active)

            # Remove from current keys
            self.current_keys.discard(key)

        except Exception as e:
            logger.error(f"[HOTKEY_MANAGER] KEY_RELEASE_ERROR: error in key release handler - {e}")

    def _is_combo_pressed(self, *keys):
        for key in keys:
            # Check both left and right variants for modifiers
            if isinstance(key, keyboard.Key):
                if key in [keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r]:
                    if not any(k in self.current_keys for k in
                              [keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r]):
                        return False
                elif key in [keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r]:
                    if not any(k in self.current_keys for k in
                              [keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r]):
                        return False
                elif key not in self.current_keys:
                    return False
            elif key not in self.current_keys:
                return False
        return True

    def change_ptt_key(self, key):
        old_key_name = getattr(self.ptt_key, 'name', str(self.ptt_key))
        new_key_name = getattr(key, 'name', str(key))
        self.ptt_key = key
        logger.info(f"[HOTKEY_MANAGER] PTT_KEY_CHANGED: from {old_key_name} to {new_key_name}")

    def update_hotkey_from_string(self, key_string: str, hotkey_type: str = "ptt"):
        """Update hotkey from a Qt-style key string (e.g., 'F9', 'Ctrl+Alt+M')"""
        if hotkey_type == "ptt":
            # Map common keys
            key_map = {
                "F1": keyboard.Key.f1, "F2": keyboard.Key.f2, "F3": keyboard.Key.f3,
                "F4": keyboard.Key.f4, "F5": keyboard.Key.f5, "F6": keyboard.Key.f6,
                "F7": keyboard.Key.f7, "F8": keyboard.Key.f8, "F9": keyboard.Key.f9,
                "F10": keyboard.Key.f10, "F11": keyboard.Key.f11, "F12": keyboard.Key.f12,
                "Space": keyboard.Key.space, "Tab": keyboard.Key.tab,
                "Enter": keyboard.Key.enter, "Esc": keyboard.Key.esc,
            }

            key_upper = key_string.upper()
            if key_upper in key_map:
                self.change_ptt_key(key_map[key_upper])
                return True

            # Handle single character keys
            if len(key_string) == 1:
                self.change_ptt_key(keyboard.KeyCode.from_char(key_string.lower()))
                return True

        return False

    def set_mode(self, mode: str):
        """Set the hotkey mode: 'push_to_talk' or 'toggle'"""
        if mode not in ["push_to_talk", "toggle"]:
            raise ValueError(f"Invalid mode: {mode}")

        # If switching from toggle mode while dictation is active, stop it
        if self.mode == "toggle" and mode == "push_to_talk" and self.dictation_active:
            logger.info("[HOTKEY_MANAGER] DICTATION_STOP: switching from toggle to push-to-talk mode")
            self.dictation_active = False
            if self.on_toggle_dictation:
                self.on_toggle_dictation(False)

        old_mode = self.mode
        self.mode = mode
        logger.info(f"[HOTKEY_MANAGER] MODE_CHANGED: from {old_mode} to {mode}")


class GlobalHotkeyManager(HotkeyManager):
    def __init__(self, config_manager=None):
        super().__init__(config_manager)
        self.global_hotkeys = {}

    def register_global_hotkey(self, hotkey_str: str, callback: Callable):
        # Parse hotkey string like "<ctrl>+<alt>+m"
        self.global_hotkeys[hotkey_str] = callback
        logger.info(f"[HOTKEY_MANAGER] GLOBAL_HOTKEY_REGISTERED: {hotkey_str}")

    def start(self):
        if self.global_hotkeys:
            # Use GlobalHotKeys for registered combinations
            self.global_listener = keyboard.GlobalHotKeys(self.global_hotkeys)
            self.global_listener.start()

        # Also start regular listener for PTT
        super().start()
