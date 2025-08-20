from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QComboBox, QSlider,
                             QGroupBox, QFormLayout, QDialogButtonBox, QDoubleSpinBox)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QKeySequence
from witticism.ui.icon_utils import create_witticism_icon
from witticism.ui.hotkey_input_widget import HotkeyInputWidget

class SettingsDialog(QDialog):
    settings_changed = pyqtSignal(dict)

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setWindowTitle("Settings")
        self.setWindowIcon(create_witticism_icon())
        self.resize(800, 850)
        self.setMinimumSize(600, 650)
        self.init_ui()
        self.load_current_settings()

    def init_ui(self):
        layout = QVBoxLayout()

        # Hotkey Settings
        hotkey_group = QGroupBox("Keyboard Shortcuts")
        hotkey_layout = QFormLayout()

        self.ptt_key_edit = HotkeyInputWidget(default_key="F9")
        hotkey_layout.addRow("Push-to-Talk/Toggle Key:", self.ptt_key_edit)

        self.mode_switch_edit = HotkeyInputWidget(default_key="Ctrl+Alt+M")
        hotkey_layout.addRow("Switch Mode:", self.mode_switch_edit)

        hotkey_group.setLayout(hotkey_layout)
        layout.addWidget(hotkey_group)

        # Audio Settings
        audio_group = QGroupBox("Audio Settings")
        audio_layout = QFormLayout()

        # VAD Aggressiveness
        self.vad_slider = QSlider(Qt.Horizontal)
        self.vad_slider.setRange(0, 3)
        self.vad_slider.setTickPosition(QSlider.TicksBelow)
        self.vad_slider.setTickInterval(1)
        self.vad_label = QLabel("2")
        self.vad_slider.valueChanged.connect(lambda v: self.vad_label.setText(str(v)))

        vad_layout = QHBoxLayout()
        vad_layout.addWidget(self.vad_slider)
        vad_layout.addWidget(self.vad_label)

        audio_layout.addRow("Voice Detection Sensitivity:", vad_layout)
        audio_layout.addRow("", QLabel("0=Least aggressive, 3=Most aggressive"))

        # Sample rate
        self.sample_rate_combo = QComboBox()
        self.sample_rate_combo.addItems(["16000", "22050", "44100", "48000"])
        self.sample_rate_combo.setCurrentText("16000")
        audio_layout.addRow("Sample Rate (Hz):", self.sample_rate_combo)

        audio_group.setLayout(audio_layout)
        layout.addWidget(audio_group)

        # Transcription Settings
        trans_group = QGroupBox("Transcription Settings")
        trans_layout = QFormLayout()

        # Language
        self.language_combo = QComboBox()
        self.language_combo.addItems([
            "en - English",
            "es - Spanish",
            "fr - French",
            "de - German",
            "it - Italian",
            "pt - Portuguese",
            "ru - Russian",
            "ja - Japanese",
            "ko - Korean",
            "zh - Chinese"
        ])
        trans_layout.addRow("Language:", self.language_combo)

        # Chunk duration for dictation mode
        self.chunk_duration_spin = QDoubleSpinBox()
        self.chunk_duration_spin.setRange(0.5, 5.0)
        self.chunk_duration_spin.setSingleStep(0.5)
        self.chunk_duration_spin.setSuffix(" seconds")
        self.chunk_duration_spin.setValue(2.0)
        trans_layout.addRow("Dictation Chunk Duration:", self.chunk_duration_spin)

        # Min/Max audio length
        self.min_audio_spin = QDoubleSpinBox()
        self.min_audio_spin.setRange(0.1, 2.0)
        self.min_audio_spin.setSingleStep(0.1)
        self.min_audio_spin.setSuffix(" seconds")
        self.min_audio_spin.setValue(0.5)
        trans_layout.addRow("Min Audio Length:", self.min_audio_spin)

        self.max_audio_spin = QDoubleSpinBox()
        self.max_audio_spin.setRange(5.0, 60.0)
        self.max_audio_spin.setSingleStep(5.0)
        self.max_audio_spin.setSuffix(" seconds")
        self.max_audio_spin.setValue(30.0)
        trans_layout.addRow("Max Audio Length:", self.max_audio_spin)

        trans_group.setLayout(trans_layout)
        layout.addWidget(trans_group)

        # Compute Settings
        compute_group = QGroupBox("Compute Settings")
        compute_layout = QFormLayout()

        self.compute_type_combo = QComboBox()
        self.compute_type_combo.addItems(["auto", "int8", "float16", "float32"])
        compute_layout.addRow("Compute Type:", self.compute_type_combo)

        compute_group.setLayout(compute_layout)
        layout.addWidget(compute_group)

        layout.addStretch()

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults,
            Qt.Horizontal, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self.restore_defaults)

        layout.addWidget(buttons)
        self.setLayout(layout)

    def load_current_settings(self):
        """Load current settings from config manager"""
        # Hotkeys
        ptt_key = self.config_manager.get("hotkeys.push_to_talk", "F9")
        self.ptt_key_edit.setKeySequence(QKeySequence(ptt_key))

        mode_switch = self.config_manager.get("hotkeys.mode_switch", "Ctrl+Alt+M")
        self.mode_switch_edit.setKeySequence(QKeySequence(mode_switch))

        # Audio
        vad = self.config_manager.get("audio.vad_aggressiveness", 2)
        self.vad_slider.setValue(vad)

        sample_rate = str(self.config_manager.get("audio.sample_rate", 16000))
        self.sample_rate_combo.setCurrentText(sample_rate)

        # Transcription
        language = self.config_manager.get("model.language", "en")
        for i in range(self.language_combo.count()):
            if self.language_combo.itemText(i).startswith(language):
                self.language_combo.setCurrentIndex(i)
                break

        chunk_duration = self.config_manager.get("dictation.chunk_duration", 2.0)
        self.chunk_duration_spin.setValue(chunk_duration)

        min_audio = self.config_manager.get("pipeline.min_audio_length", 0.5)
        self.min_audio_spin.setValue(min_audio)

        max_audio = self.config_manager.get("pipeline.max_audio_length", 30.0)
        self.max_audio_spin.setValue(max_audio)

        # Compute
        compute_type = self.config_manager.get("model.compute_type", "auto")
        self.compute_type_combo.setCurrentText(compute_type)

    def restore_defaults(self):
        """Reset all settings to defaults"""
        self.ptt_key_edit.reset_to_default()
        self.mode_switch_edit.reset_to_default()
        self.vad_slider.setValue(2)
        self.sample_rate_combo.setCurrentText("16000")
        self.language_combo.setCurrentIndex(0)  # English
        self.chunk_duration_spin.setValue(2.0)
        self.min_audio_spin.setValue(0.5)
        self.max_audio_spin.setValue(30.0)
        self.compute_type_combo.setCurrentText("auto")

    def get_settings(self):
        """Get the current settings as a dictionary"""
        language_code = self.language_combo.currentText().split(" - ")[0]

        return {
            "hotkeys.push_to_talk": self.ptt_key_edit.keySequence().toString(),
            "hotkeys.mode_switch": self.mode_switch_edit.keySequence().toString(),
            "audio.vad_aggressiveness": self.vad_slider.value(),
            "audio.sample_rate": int(self.sample_rate_combo.currentText()),
            "model.language": language_code,
            "dictation.chunk_duration": self.chunk_duration_spin.value(),
            "pipeline.min_audio_length": self.min_audio_spin.value(),
            "pipeline.max_audio_length": self.max_audio_spin.value(),
            "model.compute_type": self.compute_type_combo.currentText()
        }

    def accept(self):
        """Save settings and close"""
        settings = self.get_settings()
        changed_settings = {}

        # Check which settings actually changed
        for key, value in settings.items():
            current_value = self.config_manager.get(key, None)

            # Compare and only save if changed
            if current_value != value:
                changed_settings[key] = value
                self.config_manager.set(key, value)

        # Only save and emit if there were actual changes
        if changed_settings:
            # Save to file
            self.config_manager.save_config()
            # Emit signal with only changed settings
            self.settings_changed.emit(changed_settings)

        super().accept()
