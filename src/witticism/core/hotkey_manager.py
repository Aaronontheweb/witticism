import logging
from pynput import keyboard
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class HotkeyManager:
    def __init__(self):
        self.listener = None
        self.hotkeys = {}
        self.current_keys = set()

        # Callbacks
        self.on_push_to_talk_start = None
        self.on_push_to_talk_stop = None
        self.on_toggle = None
        self.on_toggle_dictation = None

        # PTT state
        self.ptt_key = keyboard.Key.f9
        self.ptt_active = False

        # Mode state
        self.mode = "push_to_talk"  # "push_to_talk" or "toggle"
        self.dictation_active = False

        logger.info("HotkeyManager initialized")

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
            logger.warning("HotkeyManager already started")
            return

        # Create listener for push-to-talk
        self.listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release
        )
        self.listener.start()

        logger.info("HotkeyManager started")

    def stop(self):
        if self.listener:
            self.listener.stop()
            self.listener = None
            logger.info("HotkeyManager stopped")

    def _on_key_press(self, key):
        try:
            # Handle F9 based on mode
            if key == self.ptt_key:
                if self.mode == "push_to_talk":
                    # Push-to-talk mode
                    if not self.ptt_active:
                        self.ptt_active = True
                        logger.debug("PTT key pressed")
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
                logger.debug("Mode toggle hotkey pressed")
                if self.on_toggle:
                    self.on_toggle()

        except Exception as e:
            logger.error(f"Error in key press handler: {e}")

    def _on_key_release(self, key):
        try:
            # Handle F9 based on mode
            if key == self.ptt_key:
                if self.mode == "push_to_talk":
                    # Push-to-talk mode - stop recording on release
                    if self.ptt_active:
                        self.ptt_active = False
                        logger.debug("PTT key released")
                        if self.on_push_to_talk_stop:
                            self.on_push_to_talk_stop()
                elif self.mode == "toggle":
                    # Toggle mode - toggle dictation state
                    self.dictation_active = not self.dictation_active
                    logger.debug(f"Toggle dictation: {self.dictation_active}")
                    if self.on_toggle_dictation:
                        self.on_toggle_dictation(self.dictation_active)

            # Remove from current keys
            self.current_keys.discard(key)

        except Exception as e:
            logger.error(f"Error in key release handler: {e}")

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
        self.ptt_key = key
        logger.info(f"PTT key changed to: {key}")

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
            self.dictation_active = False
            if self.on_toggle_dictation:
                self.on_toggle_dictation(False)

        self.mode = mode
        logger.info(f"Hotkey mode changed to: {mode}")


class GlobalHotkeyManager(HotkeyManager):
    def __init__(self):
        super().__init__()
        self.global_hotkeys = {}

    def register_global_hotkey(self, hotkey_str: str, callback: Callable):
        # Parse hotkey string like "<ctrl>+<alt>+m"
        self.global_hotkeys[hotkey_str] = callback
        logger.info(f"Registered global hotkey: {hotkey_str}")

    def start(self):
        if self.global_hotkeys:
            # Use GlobalHotKeys for registered combinations
            self.global_listener = keyboard.GlobalHotKeys(self.global_hotkeys)
            self.global_listener.start()

        # Also start regular listener for PTT
        super().start()
