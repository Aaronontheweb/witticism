import logging
import sys
from pathlib import Path
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QAction, QMessageBox
from PyQt5.QtCore import QObject, pyqtSignal, QThread, Qt, QTimer
from PyQt5.QtGui import QIcon, QPixmap
from typing import Optional
import numpy as np
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
        
        self.menu.addSeparator()
        
        # Toggle enable/disable
        self.toggle_action = QAction("Disable", self)
        self.toggle_action.triggered.connect(self.toggle_enabled)
        self.menu.addAction(self.toggle_action)
        
        # Push-to-talk action
        self.ptt_action = QAction("Push-to-Talk (Hold F9)", self)
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
            "gray": QColor(158, 158, 158)
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
        from pathlib import Path
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
            if model == "base":  # Default
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
                
    def set_status(self, status: str):
        self.status_action.setText(f"Status: {status}")
        self.setToolTip(f"Witticism - {status}")
        
        # Update icon color based on status
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
        
    def change_model(self, model_name: str):
        # Uncheck all other models
        for action in self.model_actions:
            action.setChecked(action.data() == model_name)
            
        if self.engine:
            # Stop dictation if active (model change invalidates transcriber)
            if self.is_dictating:
                self.stop_dictation()
                
            self.set_status(f"Loading {model_name}...")
            self.engine.change_model(model_name)
            
            # Recreate continuous transcriber with new engine
            if hasattr(self, 'continuous_transcriber'):
                self.continuous_transcriber.stop()
                del self.continuous_transcriber
                
            self.set_status("Ready")
            
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
        if mode == "push_to_talk":
            self.ptt_action.setText("Push-to-Talk (Hold F9)")
        else:
            self.ptt_action.setText("Toggle Dictation (Press F9)")
            
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
        
        # Update language if changed (can reload)
        if "model.language" in settings and self.engine:
            self.engine.language = settings["model.language"]
            
        # Update chunk duration for dictation (can reload)
        if "dictation.chunk_duration" in settings and self.continuous_capture:
            self.continuous_capture.chunk_duration = settings["dictation.chunk_duration"]
            
        # Update VAD aggressiveness (can reload for new sessions)
        if "audio.vad_aggressiveness" in settings and self.audio_capture:
            self.audio_capture.vad_aggressiveness = settings["audio.vad_aggressiveness"]
            if self.audio_capture.vad:
                self.audio_capture.vad.set_mode(settings["audio.vad_aggressiveness"])
                
        # Update pipeline settings (can reload)
        if "pipeline.min_audio_length" in settings:
            # Update transcription pipeline if it exists
            pass  # Would need reference to pipeline
            
        # Check which settings need restart
        if "hotkeys.push_to_talk" in settings or "hotkeys.mode_switch" in settings:
            needs_restart.append("Keyboard shortcuts")
        if "audio.sample_rate" in settings:
            needs_restart.append("Sample rate")
        if "model.compute_type" in settings:
            needs_restart.append("Compute type")
            
        # Show message if any settings need restart
        if needs_restart:
            QMessageBox.information(
                None,
                "Settings Applied",
                f"Most settings have been applied.\n\n"
                f"These settings require restart:\n• " + "\n• ".join(needs_restart) + 
                f"\n\nPlease restart the application for these to take effect."
            )
        else:
            # Show brief notification that settings were applied
            self.showMessage(
                "Settings Applied",
                "All settings have been applied successfully.",
                QSystemTrayIcon.Information,
                2000
            )
        
    def show_about(self):
        """Show the about dialog"""
        dialog = AboutDialog()
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
        self.audio_capture = audio_capture
        self.hotkey_manager = hotkey_manager
        self.output_manager = output_manager
        self.config_manager = config_manager
        
        # Update device menu now that we have audio_capture
        self.update_device_menu()