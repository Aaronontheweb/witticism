import logging
from pathlib import Path
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QAction, QMessageBox
from PyQt5.QtCore import pyqtSignal, QThread, Qt, QTimer
from PyQt5.QtGui import QIcon, QPixmap
from typing import Optional
from witticism.core.continuous_transcriber import ContinuousTranscriber
from witticism.ui.about_dialog import AboutDialog
from witticism.ui.settings_dialog import SettingsDialog

logger = logging.getLogger(__name__)


class TranscriptionWorker(QThread):
    transcription_complete = pyqtSignal(str)
    transcription_error = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(self, engine, audio_data):
        super().__init__()
        self.engine = engine
        self.audio_data = audio_data

    def run(self):
        try:
            self.status_update.emit("Transcribing...")
            result = self.engine.transcribe(self.audio_data)
            text = self.engine.format_result(result)
            self.transcription_complete.emit(text)
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            self.transcription_error.emit(str(e))


class SystemTrayApp(QSystemTrayIcon):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.engine = None
        self.audio_capture = None
        self.continuous_capture = None  # For toggle mode
        self.hotkey_manager = None
        self.output_manager = None
        self.config_manager = None

        self.is_recording = False
        self.is_enabled = True
        self.is_dictating = False  # For toggle mode
        self.mode = "push_to_talk"  # "push_to_talk" or "toggle"
        self.cuda_error_shown = False  # Track if we've shown CUDA error notification

        self.init_ui()
        self.set_status("Ready")

    def init_ui(self):
        # Create tray icon
        self.create_icon()

        # Create context menu
        self.menu = QMenu()

        # Status action (disabled, just shows status)
        self.status_action = QAction("Status: Ready")
        self.status_action.setEnabled(False)
        self.menu.addAction(self.status_action)

        # GPU status action (only shown when there's a CUDA error)
        self.gpu_status_action = QAction("⚠ GPU Error - Restart Required")
        self.gpu_status_action.setEnabled(False)
        self.gpu_status_action.setVisible(False)  # Hidden by default
        self.menu.addAction(self.gpu_status_action)

        # Loading progress action (only shown during model loading)
        self.loading_progress_action = QAction("Loading: 0%")
        self.loading_progress_action.setEnabled(False)
        self.loading_progress_action.setVisible(False)  # Hidden by default
        self.menu.addAction(self.loading_progress_action)

        # Cancel loading action (only shown during model loading)
        self.cancel_loading_action = QAction("Cancel Loading")
        self.cancel_loading_action.triggered.connect(self.cancel_model_loading)
        self.cancel_loading_action.setVisible(False)  # Hidden by default
        self.menu.addAction(self.cancel_loading_action)

        self.menu.addSeparator()

        # Toggle enable/disable
        self.toggle_action = QAction("Disable", self)
        self.toggle_action.triggered.connect(self.toggle_enabled)
        self.menu.addAction(self.toggle_action)

        # Push-to-talk action (text will be updated later when config is loaded)
        self.ptt_action = QAction("Push-to-Talk", self)
        self.ptt_action.setEnabled(False)
        self.menu.addAction(self.ptt_action)

        # Mode selection submenu
        self.mode_menu = self.menu.addMenu("Mode")
        self.create_mode_menu()

        self.menu.addSeparator()

        # Model selection submenu
        self.model_menu = self.menu.addMenu("Model")
        self.create_model_menu()

        # Device selection submenu
        self.device_menu = self.menu.addMenu("Audio Device")
        self.update_device_menu()

        self.menu.addSeparator()

        # Settings action
        self.settings_action = QAction("Settings...", self)
        self.settings_action.triggered.connect(self.show_settings)
        self.menu.addAction(self.settings_action)

        # About action
        self.about_action = QAction("About", self)
        self.about_action.triggered.connect(self.show_about)
        self.menu.addAction(self.about_action)

        self.menu.addSeparator()

        # Quit action
        self.quit_action = QAction("Quit", self)
        self.quit_action.triggered.connect(self.quit_app)
        self.menu.addAction(self.quit_action)

        # Set context menu
        self.setContextMenu(self.menu)

        # Show tray icon
        self.show()

        # Connect to activated signal for left click
        self.activated.connect(self.on_tray_activated)

    def create_icon(self):
        # Create a simple colored icon
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)

        # Draw a simple microphone shape or use text
        from PyQt5.QtGui import QPainter, QFont, QColor
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Background circle
        painter.setBrush(QColor(76, 175, 80))  # Green when ready
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(8, 8, 48, 48)

        # Text
        painter.setPen(Qt.white)
        font = QFont("Arial", 20, QFont.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "W")

        painter.end()

        icon = QIcon(pixmap)
        self.setIcon(icon)

    def update_icon_color(self, color: str):
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)

        from PyQt5.QtGui import QPainter, QFont, QColor
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Map color names to QColor
        color_map = {
            "green": QColor(76, 175, 80),
            "red": QColor(244, 67, 54),
            "yellow": QColor(255, 193, 7),
            "gray": QColor(158, 158, 158),
            "orange": QColor(255, 152, 0)  # Orange for CUDA fallback
        }

        # Background circle
        painter.setBrush(color_map.get(color, QColor(76, 175, 80)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(8, 8, 48, 48)

        # Text
        painter.setPen(Qt.white)
        font = QFont("Arial", 20, QFont.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "W")

        painter.end()

        icon = QIcon(pixmap)
        self.setIcon(icon)

    def create_mode_menu(self):
        # Push-to-talk mode
        ptt_mode_action = QAction("Push-to-Talk", self)
        ptt_mode_action.setCheckable(True)
        ptt_mode_action.setChecked(True)
        ptt_mode_action.triggered.connect(lambda: self.change_mode("push_to_talk"))
        self.mode_menu.addAction(ptt_mode_action)

        # Toggle mode
        toggle_mode_action = QAction("Toggle Dictation", self)
        toggle_mode_action.setCheckable(True)
        toggle_mode_action.triggered.connect(lambda: self.change_mode("toggle"))
        self.mode_menu.addAction(toggle_mode_action)

        self.mode_actions = [ptt_mode_action, toggle_mode_action]

    def create_model_menu(self):
        models = ["tiny", "tiny.en", "base", "base.en", "small", "small.en", "medium", "medium.en", "large-v3"]

        # Check which models are cached
        cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
        cached_models = set()

        if cache_dir.exists():
            for model_dir in cache_dir.glob("models--Systran--faster-whisper-*"):
                model_name = model_dir.name.replace("models--Systran--faster-whisper-", "")
                # Map folder names to model names
                if model_name == "large-v3":
                    cached_models.add("large-v3")
                elif model_name in ["tiny", "base", "small", "medium"]:
                    cached_models.add(model_name)
                    # Also mark the English-only variants
                    if model_name in ["tiny", "base", "small", "medium"]:
                        cached_models.add(f"{model_name}.en")

        model_group = []
        for model in models:
            # Add visual indicator and tooltip based on cache status
            if model in cached_models or model.replace(".en", "") in cached_models:
                display_name = f"● {model}"  # Filled circle for downloaded models
                action = QAction(display_name, self)
                action.setToolTip(f"{model} - Ready (cached locally)")
            else:
                display_name = f"○ {model}"  # Empty circle for models that need downloading
                action = QAction(display_name, self)
                action.setToolTip(f"{model} - Needs download (will download on first use)")

            action.setData(model)  # Store actual model name
            action.setCheckable(True)
            # Check the currently selected model from config
            current_model = self.config_manager.get("model.size", "base") if self.config_manager else "base"
            if model == current_model:
                action.setChecked(True)
            action.triggered.connect(lambda checked, m=model: self.change_model(m))
            self.model_menu.addAction(action)
            model_group.append(action)

        # Store for exclusive selection
        self.model_actions = model_group

    def update_device_menu(self):
        self.device_menu.clear()

        # Default device
        default_action = QAction("Default", self)
        default_action.setCheckable(True)
        default_action.setChecked(True)
        default_action.triggered.connect(lambda: self.change_audio_device(None))
        self.device_menu.addAction(default_action)

        self.device_menu.addSeparator()

        # Get available devices from audio_capture when it's initialized
        if self.audio_capture:
            devices = self.audio_capture.get_audio_devices()
            for device in devices:
                action = QAction(device['name'], self)
                action.setCheckable(True)
                action.triggered.connect(
                    lambda checked, idx=device['index']: self.change_audio_device(idx)
                )
                self.device_menu.addAction(action)

    def update_model_menu_selection(self):
        """Update model menu checkmarks based on current config"""
        if not self.config_manager:
            return

        current_model = self.config_manager.get("model.size", "base")

        # Update checkmarks for all model actions
        for action in self.model_actions:
            action.setChecked(action.data() == current_model)

    def set_status(self, status: str):
        # Check if we're in CUDA fallback mode
        if self.engine and hasattr(self.engine, 'cuda_fallback') and self.engine.cuda_fallback:
            if "Ready" in status:
                status = "Ready (CPU Mode - CUDA Error)"
                self.setToolTip("Witticism (CPU Mode - Restart for GPU)")
            else:
                self.setToolTip(f"Witticism - {status} (CPU Mode)")
        else:
            self.setToolTip(f"Witticism - {status}")

        self.status_action.setText(f"Status: {status}")

        # Update icon color based on status and CUDA fallback
        if self.engine and hasattr(self.engine, 'cuda_fallback') and self.engine.cuda_fallback:
            # Orange for CPU fallback mode
            if "Ready" in status:
                self.update_icon_color("orange")
            elif "Recording" in status or "Dictating" in status:
                self.update_icon_color("red")
            elif "Transcribing" in status:
                self.update_icon_color("yellow")
            else:
                self.update_icon_color("orange")
        else:
            # Normal colors
            if "Ready" in status:
                self.update_icon_color("green")
            elif "Recording" in status:
                self.update_icon_color("red")
            elif "Dictating" in status:
                self.update_icon_color("red")  # Red for active dictation
            elif "Transcribing" in status:
                self.update_icon_color("yellow")
            elif "Disabled" in status:
                self.update_icon_color("gray")
            else:
                self.update_icon_color("green")

    def toggle_enabled(self):
        self.is_enabled = not self.is_enabled
        if self.is_enabled:
            self.toggle_action.setText("Disable")
            self.set_status("Ready")
            self.ptt_action.setEnabled(False)
        else:
            self.toggle_action.setText("Enable")
            self.set_status("Disabled")
            self.ptt_action.setEnabled(False)

    def start_recording(self):
        if not self.is_enabled or self.is_recording:
            return

        self.is_recording = True
        self.set_status("Recording...")

        if self.audio_capture:
            self.audio_capture.start_push_to_talk()

    def stop_recording(self):
        if not self.is_recording:
            return

        self.is_recording = False
        self.set_status("Processing...")

        if self.audio_capture:
            audio_data = self.audio_capture.stop_push_to_talk()
            if len(audio_data) > 0:
                self.process_transcription(audio_data)
            else:
                self.set_status("Ready")

    def process_transcription(self, audio_data):
        if not self.engine:
            self.set_status("Engine not initialized")
            return

        # Convert to float32 for WhisperX
        audio_float = audio_data.astype('float32') / 32768.0

        # Run transcription in worker thread
        self.worker = TranscriptionWorker(self.engine, audio_float)
        self.worker.transcription_complete.connect(self.on_transcription_complete)
        self.worker.transcription_error.connect(self.on_transcription_error)
        self.worker.status_update.connect(self.set_status)
        self.worker.start()

    def on_transcription_complete(self, text):
        self.set_status("Ready")

        if text and self.output_manager:
            self.output_manager.output_text(text)

    def on_transcription_error(self, error):
        self.set_status("Error")
        logger.error(f"Transcription error: {error}")

        # Check if this is a CUDA error and we've fallen back
        if "CUDA" in str(error) and self.engine and hasattr(self.engine, 'cuda_fallback'):
            if self.engine.cuda_fallback and not self.cuda_error_shown:
                # Show GPU error notification once per session
                self.show_cuda_error_notification()
                self.cuda_error_shown = True

                # Show GPU status in menu
                self.gpu_status_action.setVisible(True)

                # Update status to reflect CPU mode
                self.set_status("Ready")

    def show_cuda_error_notification(self):
        """Show a system tray notification about CUDA error and CPU fallback."""
        if self.supportsMessages():
            self.showMessage(
                "GPU Error Detected",
                "Transcription falling back to CPU mode.\n"
                "Performance may be reduced.\n"
                "Restart computer to restore GPU acceleration.",
                QSystemTrayIcon.Warning,
                10000  # Show for 10 seconds
            )
        else:
            # Fallback to message box if system doesn't support tray messages
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle("GPU Error Detected")
            msg.setText("Transcription is running in CPU mode due to a GPU error.")
            msg.setInformativeText(
                "Performance may be reduced (2-3x slower).\n\n"
                "This typically occurs after suspend/resume.\n"
                "Restart your computer to restore GPU acceleration."
            )
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec_()

    def show_notification(self, title: str, message: str, icon=None, duration=5000):
        """Show a general system tray notification."""
        if icon is None:
            icon = QSystemTrayIcon.Information

        if self.supportsMessages():
            self.showMessage(title, message, icon, duration)

    def change_model(self, model_name: str):
        # Uncheck all other models
        for action in self.model_actions:
            action.setChecked(action.data() == model_name)

        if self.engine:
            # Stop dictation if active (model change invalidates transcriber)
            if self.is_dictating:
                self.stop_dictation()

            self.set_status(f"Loading {model_name}...")

            # Show loading progress UI
            self.loading_progress_action.setVisible(True)
            self.cancel_loading_action.setVisible(True)

            try:
                # Use progress callback and timeout (2 minutes for smaller models, 5 for larger)
                timeout = 120 if model_name in ["tiny", "tiny.en", "base", "base.en"] else 300
                self.engine.change_model(model_name, self.on_loading_progress, timeout)

                # Save the model selection to config
                if self.config_manager:
                    self.config_manager.set("model.size", model_name)

                # Recreate continuous transcriber with new engine
                if hasattr(self, 'continuous_transcriber'):
                    self.continuous_transcriber.stop()
                    del self.continuous_transcriber

                self.set_status("Ready")

            except TimeoutError as e:
                logger.error(f"Model loading timed out: {e}")
                self.set_status("Model loading timed out")
                # Don't change model selection on timeout - keep original
            except Exception as e:
                logger.error(f"Model loading failed: {e}")
                self.set_status(f"Loading failed: {str(e)[:50]}")
                # Don't change model selection on error - keep original
            finally:
                # Hide loading progress UI
                self.loading_progress_action.setVisible(False)
                self.cancel_loading_action.setVisible(False)

    def on_loading_progress(self, status: str, progress: int):
        """Handle model loading progress updates."""
        self.loading_progress_action.setText(f"Loading: {progress}% - {status}")
        self.set_status(f"{status} ({progress}%)")

    def cancel_model_loading(self):
        """Cancel ongoing model loading."""
        if self.engine and hasattr(self.engine, 'cancel_loading'):
            self.engine.cancel_loading()
            self.set_status("Loading cancelled")
            # Hide loading progress UI
            self.loading_progress_action.setVisible(False)
            self.cancel_loading_action.setVisible(False)

    def change_mode(self, mode: str):
        """Switch between push-to-talk and toggle modes"""
        self.mode = mode

        # Update UI checkmarks
        for action in self.mode_actions:
            if mode == "push_to_talk":
                action.setChecked(action.text() == "Push-to-Talk")
            else:
                action.setChecked(action.text() == "Toggle Dictation")

        # Update hotkey manager mode
        if self.hotkey_manager:
            self.hotkey_manager.set_mode(mode)

        # Update PTT action text
        ptt_key = "F9"  # Default
        if self.config_manager:
            ptt_key = self.config_manager.get("hotkeys.push_to_talk", "F9").upper()

        if mode == "push_to_talk":
            self.ptt_action.setText(f"Push-to-Talk (Hold {ptt_key})")
        else:
            self.ptt_action.setText(f"Toggle Dictation (Press {ptt_key})")

        # Stop any ongoing dictation if switching away from toggle mode
        if mode == "push_to_talk" and self.is_dictating:
            self.stop_dictation()

        logger.info(f"Mode changed to: {mode}")

    def toggle_dictation(self, active: bool):
        """Handle toggle dictation on/off"""
        if active:
            self.start_dictation()
        else:
            self.stop_dictation()

    def start_dictation(self):
        """Start continuous dictation mode"""
        if self.is_dictating or not self.is_enabled:
            return

        self.is_dictating = True
        self.set_status("Dictating...")

        # Initialize continuous transcriber if not already done
        if not hasattr(self, 'continuous_transcriber'):
            self.continuous_transcriber = ContinuousTranscriber(
                self.engine,
                self.on_continuous_text
            )

        # Initialize continuous capture if not already done
        if not self.continuous_capture and self.audio_capture:
            from witticism.core.audio_capture import ContinuousCapture
            self.continuous_capture = ContinuousCapture(
                chunk_callback=self.continuous_transcriber.process_audio,
                sample_rate=16000,
                channels=1,
                vad_aggressiveness=2
            )

        # Start transcriber first, then capture
        self.continuous_transcriber.start()

        if self.continuous_capture:
            self.continuous_capture.start_continuous()
            logger.info("Started continuous dictation")

    def stop_dictation(self):
        """Stop continuous dictation mode"""
        if not self.is_dictating:
            return

        self.is_dictating = False
        self.set_status("Ready")

        if self.continuous_capture:
            self.continuous_capture.stop_continuous()
            # Clean up continuous capture so it's recreated fresh next time
            self.continuous_capture.cleanup()
            self.continuous_capture = None

        if hasattr(self, 'continuous_transcriber'):
            self.continuous_transcriber.stop()

        logger.info("Stopped continuous dictation")

    def on_continuous_text(self, text):
        """Handle continuous transcription text output"""
        if text and self.output_manager and self.is_dictating:
            self.output_manager.output_text(text)

    def change_audio_device(self, device_index: Optional[int]):
        # Update checkmarks
        for action in self.device_menu.actions():
            if action.text() == "Default":
                action.setChecked(device_index is None)
            else:
                action.setChecked(False)

        # Store selected device
        self.selected_device = device_index

    def show_settings(self):
        """Show the settings dialog"""
        if not self.config_manager:
            QMessageBox.warning(None, "Settings", "Configuration not available")
            return

        dialog = SettingsDialog(self.config_manager)
        dialog.settings_changed.connect(self.on_settings_changed)
        dialog.exec_()

    def on_settings_changed(self, settings):
        """Handle settings changes - reload what we can without restart"""
        needs_restart = []
        actually_changed = False

        # Update language if changed (can reload)
        if "model.language" in settings and self.engine:
            if self.engine.language != settings["model.language"]:
                self.engine.language = settings["model.language"]
                actually_changed = True

        # Update chunk duration for dictation (can reload)
        if "dictation.chunk_duration" in settings and self.continuous_capture:
            if self.continuous_capture.chunk_duration != settings["dictation.chunk_duration"]:
                self.continuous_capture.chunk_duration = settings["dictation.chunk_duration"]
                actually_changed = True

        # Update VAD aggressiveness (can reload for new sessions)
        if "audio.vad_aggressiveness" in settings and self.audio_capture:
            if self.audio_capture.vad_aggressiveness != settings["audio.vad_aggressiveness"]:
                self.audio_capture.vad_aggressiveness = settings["audio.vad_aggressiveness"]
                if self.audio_capture.vad:
                    self.audio_capture.vad.set_mode(settings["audio.vad_aggressiveness"])
                actually_changed = True

        # Update pipeline settings (can reload)
        if "pipeline.min_audio_length" in settings:
            # Update transcription pipeline if it exists
            pass  # Would need reference to pipeline

        # Update hotkeys dynamically (no restart needed)
        if "hotkeys.push_to_talk" in settings and self.hotkey_manager:
            key_str = settings["hotkeys.push_to_talk"]
            if key_str and self.hotkey_manager.update_hotkey_from_string(key_str, "ptt"):
                actually_changed = True
                # Update menu text with new hotkey
                ptt_key = key_str.upper()
                if self.mode == "push_to_talk":
                    self.ptt_action.setText(f"Push-to-Talk (Hold {ptt_key})")
                else:
                    self.ptt_action.setText(f"Toggle Dictation (Press {ptt_key})")

        # Check which settings actually need restart
        if "audio.sample_rate" in settings:
            current_rate = self.config_manager.get("audio.sample_rate", 16000)
            if current_rate != settings["audio.sample_rate"]:
                needs_restart.append("Sample rate")
        if "model.compute_type" in settings:
            current_type = self.config_manager.get("model.compute_type", "auto")
            if current_type != settings["model.compute_type"]:
                needs_restart.append("Compute type")

        # Show message if any settings need restart
        if needs_restart:
            QMessageBox.information(
                None,
                "Settings Applied",
                "Most settings have been applied.\n\n"
                "These settings require restart:\n• " + "\n• ".join(needs_restart) +
                "\n\nPlease restart the application for these to take effect."
            )
        elif actually_changed:
            # Show brief notification that settings were applied
            self.showMessage(
                "Settings Applied",
                "All settings have been applied successfully.",
                QSystemTrayIcon.Information,
                2000
            )

    def show_about(self):
        """Show the about dialog"""
        dialog = AboutDialog(config_manager=self.config_manager)
        dialog.exec_()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            # Left click - show menu at cursor position
            self.menu.popup(self.geometry().center())

    def quit_app(self):
        # Cleanup
        if self.is_dictating:
            self.stop_dictation()

        # Clean up continuous transcriber
        if hasattr(self, 'continuous_transcriber'):
            self.continuous_transcriber.stop()

        if self.audio_capture:
            self.audio_capture.cleanup()
        if self.continuous_capture:
            self.continuous_capture.cleanup()
        if self.hotkey_manager:
            self.hotkey_manager.stop()

        QApplication.quit()

    def set_components(self, engine, audio_capture, hotkey_manager, output_manager, config_manager):
        self.engine = engine

        # Check if engine is in CUDA fallback mode on startup
        if engine and hasattr(engine, 'cuda_fallback') and engine.cuda_fallback:
            # Show GPU status in menu
            self.gpu_status_action.setVisible(True)
            # Update status to show CPU mode
            self.set_status("Ready")
            # Show notification if not already shown
            if not self.cuda_error_shown:
                QTimer.singleShot(1000, self.show_cuda_error_notification)
                self.cuda_error_shown = True

        self.audio_capture = audio_capture
        self.hotkey_manager = hotkey_manager
        self.output_manager = output_manager
        self.config_manager = config_manager

        # Update PTT action text with actual configured hotkey
        if self.config_manager:
            ptt_key = self.config_manager.get("hotkeys.push_to_talk", "F9").upper()
            if self.mode == "push_to_talk":
                self.ptt_action.setText(f"Push-to-Talk (Hold {ptt_key})")
            else:
                self.ptt_action.setText(f"Toggle Dictation (Press {ptt_key})")

        # Update device menu now that we have audio_capture
        self.update_device_menu()

        # Update model menu now that we have config_manager - this ensures
        # the correct model is checked after restarts/upgrades
        self.update_model_menu_selection()
