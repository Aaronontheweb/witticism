#!/usr/bin/env python3

import sys
import signal
import logging
import argparse
import os
import platform
from pathlib import Path

def _is_headless_environment():
    """Detect if we're running in a headless/display-less environment"""
    return (
        not os.environ.get('DISPLAY') and
        os.environ.get('CI') == 'true'
    ) or (
        os.environ.get('GITHUB_ACTIONS') == 'true'
    ) or (
        os.environ.get('HEADLESS') == 'true'
    ) or (
        '--version' in sys.argv
    )

# Skip display-dependent imports in headless environments
if not _is_headless_environment():
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

    # These imports may require display access (pynput, PyQt5, audio)
    from witticism.core.whisperx_engine import WhisperXEngine
    from witticism.core.audio_capture import PushToTalkCapture
    from witticism.core.hotkey_manager import HotkeyManager
    from witticism.core.transcription_pipeline import TranscriptionPipeline
    from witticism.ui.system_tray import SystemTrayApp
else:
    # Headless mode - set to None to avoid undefined variables
    QApplication = None
    QMessageBox = None
    Qt = None

from witticism.utils.output_manager import OutputManager
from witticism.utils.config_manager import ConfigManager
from witticism.utils.logging_config import setup_logging
import witticism

logger = logging.getLogger(__name__)


def ensure_single_instance():
    """Ensure only one instance of Witticism is running with cross-platform support.

    Returns:
        file object: Lock file handle to keep alive, or None if another instance is running
    """
    # Use platform-appropriate temp directory
    if platform.system().lower() == 'windows':
        import tempfile
        lock_file_path = os.path.join(tempfile.gettempdir(), 'witticism.lock')
    else:
        lock_file_path = '/tmp/witticism.lock'  # nosec B108

    try:
        # Try to create and lock the file
        lock_file = open(lock_file_path, 'w')
        # Use platform-specific locking
        if platform.system().lower() == 'windows':
            # Windows file locking using msvcrt
            try:
                import msvcrt
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            except ImportError:
                # msvcrt not available, use simple file existence check
                pass
            except OSError:
                # File already locked
                lock_file.close()
                raise IOError("Another instance is running")
        else:
            # Unix file locking using fcntl
            import fcntl
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)

        # Write PID to lock file for debugging
        lock_file.write(str(os.getpid()))
        lock_file.flush()

        logger.info(f"[WITTICISM] SINGLETON_LOCK: acquired singleton lock at {lock_file_path}")
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
                        logger.error(f"[WITTICISM] INSTANCE_RUNNING: another Witticism instance is running (PID {old_pid})")
                        if QMessageBox is not None:
                            QMessageBox.information(
                                None,
                                "Witticism Already Running",
                                f"Another instance of Witticism is already running (PID {old_pid}).\n\n"
                                "Check your system tray or use 'ps aux | grep witticism' to find it."
                            )
                        return None

                    except OSError:
                        # Process doesn't exist - zombie lock file
                        logger.warning(f"[WITTICISM] ZOMBIE_CLEANUP: cleaning up zombie lock file (dead PID {old_pid})")
                        os.unlink(lock_file_path)

                        # Retry lock acquisition
                        return ensure_single_instance()

            except (ValueError, FileNotFoundError):
                # Corrupted or missing lock file - clean it up
                logger.warning("[WITTICISM] LOCK_CLEANUP: cleaning up corrupted lock file")
                try:
                    os.unlink(lock_file_path)
                except OSError:
                    pass
                return ensure_single_instance()

        # Default fallback - couldn't determine state
        logger.error(f"[WITTICISM] LOCK_FAILED: could not acquire singleton lock - {e}")
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

        logger.info(f"[WITTICISM] STARTUP: version={witticism.__version__}, args={vars(args)}")

        # Initialize components
        self.engine = None
        self.audio_capture = None
        self.hotkey_manager = None
        self.pipeline = None
        self.output_manager = None
        self.tray_app = None

    def initialize_components(self):
        try:
            # CRITICAL: Validate dependencies FIRST to catch missing requirements early
            logger.info("[WITTICISM] DEPENDENCY_CHECK: validating system and Python dependencies")
            from witticism.core.dependency_validator import DependencyValidator
            self.dependency_validator = DependencyValidator()
            dependency_results = self.dependency_validator.validate_all()

            # Check for fatal dependency issues
            if self.dependency_validator.has_fatal_issues(dependency_results):
                missing_required = self.dependency_validator.get_missing_required(dependency_results)
                error_msg = f"Missing required dependencies: {', '.join(dep.name for dep in missing_required)}"
                logger.error(f"[WITTICISM] DEPENDENCY_FATAL: {error_msg}")
                # Print detailed report for user
                self.dependency_validator.print_report(dependency_results)
                raise RuntimeError(f"Cannot start due to missing dependencies: {error_msg}")

            # Log warnings for missing optional dependencies
            missing_optional = self.dependency_validator.get_missing_optional(dependency_results)
            if missing_optional:
                logger.warning(f"[WITTICISM] DEPENDENCY_OPTIONAL_MISSING: {len(missing_optional)} optional features will be disabled")
                for dep in missing_optional:
                    logger.info(f"[WITTICISM] FEATURE_DISABLED: {dep.name} - {dep.error_message}")

            # CRITICAL: Create system tray EARLY for startup notifications
            # This must happen before any risky operations so users can see error messages
            logger.info("[WITTICISM] TRAY_EARLY_INIT: creating system tray for startup notifications")
            from witticism.ui.system_tray import SystemTrayApp
            self.tray_app = SystemTrayApp()
            # Set basic configuration access for early notifications
            if self.config_manager:
                self.tray_app.config_manager = self.config_manager
            logger.info("[WITTICISM] TRAY_EARLY_READY: system tray available for startup error notifications")

            # Initialize WhisperX engine
            model_size = self.args.model or self.config_manager.get("model.size", "base")
            device = self.config_manager.get("model.device")
            compute_type = self.config_manager.get("model.compute_type")
            language = self.config_manager.get("model.language", "en")
            logger.info(f"[WITTICISM] ENGINE_INIT: model_size={model_size}, device={device}, compute_type={compute_type}, language={language}")

            self.engine = WhisperXEngine(
                model_size=model_size,
                device=self.config_manager.get("model.device"),
                compute_type=self.config_manager.get("model.compute_type"),
                language=self.config_manager.get("model.language", "en")
            )

            # CRITICAL: Enable sleep monitoring BEFORE any CUDA operations or model loading
            # This ensures CUDA protection is active during startup CUDA validation
            try:
                logger.info("[WITTICISM] SLEEP_MONITORING: enabling proactive suspend/resume detection")
                self.engine.enable_sleep_monitoring()
                logger.info("[WITTICISM] SLEEP_MONITORING_ACTIVE: CUDA protection enabled for initialization")
            except Exception as e:
                logger.warning(f"[WITTICISM] SLEEP_MONITORING_FAILED: initialization failed - {e}")
                # Not a fatal error - continue without sleep monitoring protection

            # Perform startup CUDA health check and cleanup (now with sleep monitoring protection)
            if self.engine.device == "cuda":
                logger.info("[WITTICISM] CUDA_VALIDATION: performing startup health check with sleep monitor protection")
                cuda_healthy = self.engine.validate_and_clean_cuda_at_startup()
                if not cuda_healthy:
                    logger.warning(f"[WITTICISM] STARTUP_CUDA_FALLBACK: CUDA unhealthy, switching from {self.engine.device} to CPU")
                    # Update engine configuration for CPU mode
                    self.engine.device = "cpu"
                    self.engine.compute_type = "int8"
                    self.engine.cuda_fallback = True  # Mark that we've fallen back due to startup CUDA issue (closes #56)
                    # Update config manager to persist the change
                    self.config_manager.config["model"]["device"] = "cpu"
                    self.config_manager.config["model"]["compute_type"] = "int8"
                    logger.info("[WITTICISM] CONFIG_UPDATED: device settings changed to CPU due to startup CUDA failure")
                else:
                    logger.info("[WITTICISM] CUDA_VALIDATION_PASSED: startup health check successful")
            else:
                logger.info(f"[WITTICISM] NON_CUDA_DEVICE: using {self.engine.device}, skipping CUDA validation")

            # Load models (now with sleep monitoring protection)
            logger.info("[WITTICISM] MODEL_LOADING: starting WhisperX model loading")
            self.engine.load_models()
            logger.info("[WITTICISM] MODEL_LOADING_COMPLETE: all models loaded successfully")

            # Initialize audio capture
            sample_rate = self.config_manager.get("audio.sample_rate", 16000)
            channels = self.config_manager.get("audio.channels", 1)
            vad_aggressiveness = self.config_manager.get("audio.vad_aggressiveness", 2)
            logger.info(f"[WITTICISM] AUDIO_INIT: sample_rate={sample_rate}, channels={channels}, vad_aggressiveness={vad_aggressiveness}")
            self.audio_capture = PushToTalkCapture(
                sample_rate=sample_rate,
                channels=channels,
                vad_aggressiveness=vad_aggressiveness
            )

            # Initialize transcription pipeline
            min_audio_length = self.config_manager.get("pipeline.min_audio_length", 0.5)
            max_audio_length = self.config_manager.get("pipeline.max_audio_length", 30.0)
            logger.info(f"[WITTICISM] PIPELINE_INIT: min_audio_length={min_audio_length}s, max_audio_length={max_audio_length}s")
            self.pipeline = TranscriptionPipeline(
                self.engine,
                min_audio_length=min_audio_length,
                max_audio_length=max_audio_length
            )
            self.pipeline.start()

            # Initialize output manager
            output_mode = self.config_manager.get("output.mode", "type")
            logger.info(f"[WITTICISM] OUTPUT_INIT: mode={output_mode}")
            self.output_manager = OutputManager(
                output_mode=output_mode
            )

            # Initialize hotkey manager
            self.hotkey_manager = HotkeyManager(self.config_manager)

            logger.info("[WITTICISM] INIT_COMPLETE: all components initialized successfully")

        except Exception as e:
            logger.error(f"[WITTICISM] INIT_FAILED: failed to initialize components - {e}")
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
            self.config_manager,
            self.dependency_validator
        )

        # Start hotkey manager
        self.hotkey_manager.start()

    def _force_cpu_mode_and_retry(self):
        """Force CPU mode and retry initialization after CUDA failure"""
        logger.warning("[WITTICISM] CUDA_FALLBACK_RETRY: forcing CPU mode due to initialization failure")

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
        if not _is_headless_environment():
            from PyQt5.QtWidgets import QSystemTrayIcon
            if not QSystemTrayIcon.isSystemTrayAvailable():
                if QMessageBox is not None:
                    QMessageBox.critical(None, "System Tray", "System tray is not available on this system.")
                sys.exit(1)

        # Initialize components with graceful CUDA fallback
        try:
            self.initialize_components()
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[WITTICISM] INITIALIZATION_FAILED: {error_msg}")

            # Use early system tray for error notifications if available
            error_title = "Witticism Startup Error"

            # Check if this is a CUDA-related error that we can recover from
            if ("CUDA" in error_msg or "cuda" in error_msg or
                "GPU" in error_msg or "torch" in error_msg):
                logger.warning(f"[WITTICISM] CUDA_INIT_FAILURE: CUDA-related error detected - {error_msg[:100]}...")
                logger.info("[WITTICISM] RECOVERY_ATTEMPT: attempting CPU fallback recovery")

                # Show recovery notification via tray if available
                if self.tray_app:
                    from PyQt5.QtWidgets import QSystemTrayIcon
                    self.tray_app.showMessage(
                        error_title,
                        "GPU initialization failed. Attempting CPU fallback...",
                        QSystemTrayIcon.Warning,
                        3000
                    )

                try:
                    # Force CPU mode and retry initialization
                    self._force_cpu_mode_and_retry()
                    logger.info("[WITTICISM] RECOVERY_SUCCESS: CPU fallback initialization successful")

                    # Show success notification
                    if self.tray_app:
                        self.tray_app.showMessage(
                            "Witticism Recovery",
                            "Successfully recovered using CPU mode. GPU functionality disabled.",
                            QSystemTrayIcon.Information,
                            5000
                        )

                except Exception as retry_error:
                    logger.error(f"[WITTICISM] RECOVERY_FAILED: CPU fallback also failed - {retry_error}")

                    # Show failure notification via tray if available
                    if self.tray_app:
                        self.tray_app.showMessage(
                            error_title,
                            "Startup failed even with CPU fallback. Check logs for details.",
                            QSystemTrayIcon.Critical,
                            8000
                        )

                    if QMessageBox is not None:
                        QMessageBox.critical(None, "Initialization Error",
                                           f"Failed to initialize even with CPU fallback:\n{str(retry_error)}")
                    sys.exit(1)
            else:
                # Non-CUDA errors are still fatal
                # Show error notification via tray if available
                if self.tray_app:
                    self.tray_app.showMessage(
                        error_title,
                        f"Critical startup error: {error_msg[:100]}{'...' if len(error_msg) > 100 else ''}",
                        QSystemTrayIcon.Critical,
                        8000
                    )

                if QMessageBox is not None:
                    QMessageBox.critical(None, "Initialization Error", f"Failed to initialize: {error_msg}")
                sys.exit(1)

        # System tray already created early during initialization
        # Setup connections with all components
        self.setup_connections()

        # Handle signals
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        # Show initial notification
        if self.config_manager.get("ui.show_notifications", True):
            from PyQt5.QtWidgets import QSystemTrayIcon
            ptt_key = self.config_manager.get("hotkeys.push_to_talk", "F9").upper()
            self.tray_app.showMessage(
                "Witticism",
                f"Voice transcription ready. Hold {ptt_key} to record (or switch to Toggle mode).",
                QSystemTrayIcon.Information,
                3000
            )

        logger.info("[WITTICISM] STARTUP_COMPLETE: application ready and running")

        # Run application
        sys.exit(app.exec_())

    def signal_handler(self, signum, frame):
        logger.info(f"[WITTICISM] SIGNAL_RECEIVED: received signal {signum}, shutting down")
        self.cleanup()
        QApplication.quit()

    def cleanup(self):
        logger.info("[WITTICISM] CLEANUP_START: cleaning up components")

        if self.hotkey_manager:
            self.hotkey_manager.stop()

        if self.pipeline:
            self.pipeline.stop()

        if self.audio_capture:
            self.audio_capture.cleanup()

        if self.engine:
            self.engine.cleanup()

        logger.info("[WITTICISM] CLEANUP_COMPLETE: all components cleaned up successfully")


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
