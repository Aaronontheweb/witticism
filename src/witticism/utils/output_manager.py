import logging
import time
from pynput.keyboard import Controller
import pyperclip

logger = logging.getLogger(__name__)


class OutputManager:
    def __init__(self, output_mode: str = "type"):
        self.output_mode = output_mode
        self.keyboard = Controller()

        logger.info(f"OutputManager initialized with mode: {output_mode}")

    def output_text(self, text: str) -> None:
        if not text:
            return

        # Type directly at cursor position
        self.type_text(text)

    def type_text(self, text: str) -> None:
        try:
            # Small delay to ensure the application is ready
            time.sleep(0.1)

            # Type the text character by character
            self.keyboard.type(text)

            logger.info(f"Typed {len(text)} characters")

        except Exception as e:
            logger.error(f"Failed to type text: {e}")
            # Fallback to clipboard
            self.copy_to_clipboard(text)

    def copy_to_clipboard(self, text: str) -> None:
        try:
            pyperclip.copy(text)
            logger.info(f"Copied {len(text)} characters to clipboard")
        except Exception as e:
            logger.error(f"Failed to copy to clipboard: {e}")

    def set_output_mode(self, mode: str) -> None:
        self.output_mode = mode
        logger.info(f"Output mode changed to: {mode}")
