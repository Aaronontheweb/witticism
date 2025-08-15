import logging
from pynput import keyboard
from threading import Thread
from typing import Optional, Callable, Dict

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
        
        # PTT state
        self.ptt_key = keyboard.Key.f9
        self.ptt_active = False
        
        logger.info("HotkeyManager initialized")
        
    def set_callbacks(
        self,
        on_push_to_talk_start: Optional[Callable] = None,
        on_push_to_talk_stop: Optional[Callable] = None,
        on_toggle: Optional[Callable] = None
    ):
        self.on_push_to_talk_start = on_push_to_talk_start
        self.on_push_to_talk_stop = on_push_to_talk_stop
        self.on_toggle = on_toggle
        
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
            # Handle push-to-talk
            if key == self.ptt_key and not self.ptt_active:
                self.ptt_active = True
                logger.debug("PTT key pressed")
                if self.on_push_to_talk_start:
                    self.on_push_to_talk_start()
                    
            # Track current keys for combinations
            self.current_keys.add(key)
            
            # Check for toggle combination (Ctrl+Alt+M)
            if self._is_combo_pressed(
                keyboard.Key.ctrl_l,
                keyboard.Key.alt_l,
                keyboard.KeyCode.from_char('m')
            ):
                logger.debug("Toggle hotkey pressed")
                if self.on_toggle:
                    self.on_toggle()
                    
        except Exception as e:
            logger.error(f"Error in key press handler: {e}")
            
    def _on_key_release(self, key):
        try:
            # Handle push-to-talk release
            if key == self.ptt_key and self.ptt_active:
                self.ptt_active = False
                logger.debug("PTT key released")
                if self.on_push_to_talk_stop:
                    self.on_push_to_talk_stop()
                    
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