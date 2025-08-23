#!/usr/bin/env python3

import sys
import signal
import logging
import argparse
import fcntl
import os
from pathlib import Path
try:
    from PyQt5.QtWidgets import QApplication, QMessageBox
    from PyQt5.QtCore import Qt
except ImportError:
    # Try alternative import
    from PyQt5 import QtWidgets as QtW
    from PyQt5 import QtCore
    QApplication = QtW.QApplication
    QMessageBox = QtW.QMessageBox
    Qt = QtCore.Qt

from witticism.core.whisperx_engine import WhisperXEngine
from witticism.core.audio_capture import PushToTalkCapture
from witticism.core.hotkey_manager import HotkeyManager
from witticism.core.transcription_pipeline import TranscriptionPipeline
from witticism.ui.system_tray import SystemTrayApp
from witticism.utils.output_manager import OutputManager
from witticism.utils.config_manager import ConfigManager
from witticism.utils.logging_config import setup_logging
import witticism

logger = logging.getLogger(__name__)


def ensure_single_instance():
    """Ensure only one instance of Witticism is running with zombie cleanup.

    Returns:
        file object: Lock file handle to keep alive, or None if another instance is running
    """
    lock_file_path = '/tmp/witticism.lock'  # nosec B108

    try:
        # Try to create and lock the file
        lock_file = open(lock_file_path, 'w')
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)

        # Write PID to lock file for debugging
        lock_file.write(str(os.getpid()))
        lock_file.flush()

        logger.info(f"Acquired singleton lock: {lock_file_path}")
        return lock_file  # Keep this alive to maintain lock

    except (IOError, OSError) as e:
        # Lock file exists - check if the process is still running
        if os.path.exists(lock_file_path):
            try:
                with open(lock_file_path, 'r') as f:
                    old_pid = f.read().strip()

                if old_pid.isdigit():
                    old_pid = int(old_pid)

                    # Check if process is still running
                    try:
                        os.kill(old_pid, 0)  # Signal 0 just tests if process exists
                        # Process exists - show user message
                        logger.error(f"Another Witticism instance is running (PID {old_pid})")
                        QMessageBox.information(
                            None,
                            "Witticism Already Running",
                            f"Another instance of Witticism is already running (PID {old_pid}).\n\n"
                            "Check your system tray or use 'ps aux | grep witticism' to find it."
                        )
                        return None

                    except OSError:
                        # Process doesn't exist - zombie lock file
                        logger.warning(f"Cleaning up zombie lock file (dead PID {old_pid})")
                        os.unlink(lock_file_path)

                        # Retry lock acquisition
                        return ensure_single_instance()

            except (ValueError, FileNotFoundError):
                # Corrupted or missing lock file - clean it up
                logger.warning("Cleaning up corrupted lock file")
                try:
                    os.unlink(lock_file_path)
                except OSError:
                    pass
                return ensure_single_instance()

        # Default fallback - couldn't determine state
        logger.error(f"Could not acquire singleton lock: {e}")
        return None


class WitticismApp:
    def __init__(self, args):
        self.args = args

        # Initialize configuration
        self.config_manager = ConfigManager()

        # Setup logging
        log_level = args.log_level or self.config_manager.get("logging.level", "INFO")
        log_file = None
        if self.config_manager.get("logging.file"):
            log_file = Path(self.config_manager.get("logging.file"))
        setup_logging(level=log_level, log_file=log_file)

        logger.info("Witticism starting...")

        # Initialize components
        self.engine = None
        self.audio_capture = None
        self.hotkey_manager = None
        self.pipeline = None
        self.output_manager = None
        self.tray_app = None

    def initialize_components(self):
        try:
            # Initialize WhisperX engine
            model_size = self.args.model or self.config_manager.get("model.size", "base")
            logger.info(f"Initializing WhisperX engine with model: {model_size}")

            self.engine = WhisperXEngine(
                model_size=model_size,
                device=self.config_manager.get("model.device"),
                compute_type=self.config_manager.get("model.compute_type"),
                language=self.config_manager.get("model.language", "en")
            )

            # Perform startup CUDA health check and cleanup if needed
            cuda_healthy = self.engine.validate_and_clean_cuda_at_startup()
            if not cuda_healthy and self.engine.device == "cuda":
                logger.warning("CUDA context corrupted - forcing CPU mode")
                # Update engine configuration for CPU mode
                self.engine.device = "cpu"
                self.engine.compute_type = "int8"
                # Update config manager to persist the change
                self.config_manager.config["model"]["device"] = "cpu"
                self.config_manager.config["model"]["compute_type"] = "int8"

            # Load models
            logger.info("Loading WhisperX models...")
            self.engine.load_models()

            # Enable sleep monitoring for proactive CUDA recovery
            try:
                self.engine.enable_sleep_monitoring()
            except Exception as e:
                logger.warning(f"Sleep monitoring initialization failed: {e}")
                # Not a fatal error - continue without sleep monitoring

            # Initialize audio capture
            self.audio_capture = PushToTalkCapture(
                sample_rate=self.config_manager.get("audio.sample_rate", 16000),
                channels=self.config_manager.get("audio.channels", 1),
                vad_aggressiveness=self.config_manager.get("audio.vad_aggressiveness", 2)
            )

            # Initialize transcription pipeline
            self.pipeline = TranscriptionPipeline(
                self.engine,
                min_audio_length=self.config_manager.get("pipeline.min_audio_length", 0.5),
                max_audio_length=self.config_manager.get("pipeline.max_audio_length", 30.0)
            )
            self.pipeline.start()

            # Initialize output manager
            self.output_manager = OutputManager(
                output_mode=self.config_manager.get("output.mode", "type")
            )

            # Initialize hotkey manager
            self.hotkey_manager = HotkeyManager()

            logger.info("All components initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            raise

    def setup_connections(self):
        # Connect hotkey manager to system tray
        self.hotkey_manager.set_callbacks(
            on_push_to_talk_start=self.tray_app.start_recording,
            on_push_to_talk_stop=self.tray_app.stop_recording,
            on_toggle=self.tray_app.toggle_enabled,
            on_toggle_dictation=self.tray_app.toggle_dictation
        )

        # Pass components to tray app
        self.tray_app.set_components(
            self.engine,
            self.audio_capture,
            self.hotkey_manager,
            self.output_manager,
            self.config_manager
        )

        # Start hotkey manager
        self.hotkey_manager.start()

    def _force_cpu_mode_and_retry(self):
        """Force CPU mode and retry initialization after CUDA failure"""
        logger.warning("Forcing CPU mode due to CUDA initialization failure")

        # Update configuration to force CPU mode
        self.config_manager.config["model"]["device"] = "cpu"
        self.config_manager.config["model"]["compute_type"] = "int8"  # CPU optimization

        # Clear any existing components
        if hasattr(self, 'engine') and self.engine:
            try:
                self.engine.cleanup()
            except Exception:
                pass
            self.engine = None

        # Retry initialization with CPU mode
        self.initialize_components()

    def run(self):
        # Create Qt application
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)

        # Check system tray availability
        from PyQt5.QtWidgets import QSystemTrayIcon
        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.critical(None, "System Tray", "System tray is not available on this system.")
            sys.exit(1)

        # Initialize components with graceful CUDA fallback
        try:
            self.initialize_components()
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Initialization failed: {error_msg}")

            # Check if this is a CUDA-related error that we can recover from
            if ("CUDA" in error_msg or "cuda" in error_msg or
                "GPU" in error_msg or "torch" in error_msg):
                logger.warning("CUDA-related initialization failure - attempting CPU fallback recovery")

                try:
                    # Force CPU mode and retry initialization
                    self._force_cpu_mode_and_retry()
                    logger.info("Successfully recovered using CPU fallback mode")
                except Exception as retry_error:
                    logger.error(f"CPU fallback also failed: {retry_error}")
                    QMessageBox.critical(None, "Initialization Error",
                                       f"Failed to initialize even with CPU fallback:\n{str(retry_error)}")
                    sys.exit(1)
            else:
                # Non-CUDA errors are still fatal
                QMessageBox.critical(None, "Initialization Error", f"Failed to initialize: {error_msg}")
                sys.exit(1)

        # Create system tray app
        self.tray_app = SystemTrayApp()

        # Setup connections
        self.setup_connections()

        # Handle signals
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        # Show initial notification
        if self.config_manager.get("ui.show_notifications", True):
            from PyQt5.QtWidgets import QSystemTrayIcon
            self.tray_app.showMessage(
                "Witticism",
                "Voice transcription ready. Hold F9 to record (or switch to Toggle mode).",
                QSystemTrayIcon.Information,
                3000
            )

        logger.info("Witticism started successfully")

        # Run application
        sys.exit(app.exec_())

    def signal_handler(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        self.cleanup()
        QApplication.quit()

    def cleanup(self):
        logger.info("Cleaning up...")

        if self.hotkey_manager:
            self.hotkey_manager.stop()

        if self.pipeline:
            self.pipeline.stop()

        if self.audio_capture:
            self.audio_capture.cleanup()

        if self.engine:
            self.engine.cleanup()

        logger.info("Cleanup complete")


def main():
    parser = argparse.ArgumentParser(description="Witticism - WhisperX Voice Transcription")
    parser.add_argument(
        "--model",
        choices=["tiny", "tiny.en", "base", "base.en", "small", "small.en",
                 "medium", "medium.en", "large-v3"],
        help="WhisperX model to use"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level"
    )
    parser.add_argument(
        "--reset-config",
        action="store_true",
        help="Reset configuration to defaults"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {witticism.__version__}"
    )

    args = parser.parse_args()

    # Handle config reset
    if args.reset_config:
        config = ConfigManager()
        config.reset_to_defaults()
        print(f"Configuration reset to defaults: {config.get_config_path()}")
        sys.exit(0)

    # Check for single instance before initializing Qt
    lock_file = ensure_single_instance()
    if not lock_file:
        sys.exit(0)  # Another instance is running

    # Run application
    try:
        app = WitticismApp(args)
        app.run()
    finally:
        # Clean up lock file
        if lock_file:
            try:
                lock_file.close()
                os.unlink('/tmp/witticism.lock')  # nosec B108
            except OSError:
                pass


if __name__ == "__main__":
    main()
