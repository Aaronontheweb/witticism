import sys
from pathlib import Path
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTextBrowser, QTabWidget, QWidget)
from PyQt5.QtGui import QFont
import importlib.metadata
from witticism.ui.icon_utils import create_witticism_icon

class AboutDialog(QDialog):
    def __init__(self, config_manager=None, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setWindowTitle("About Witticism")
        self.setWindowIcon(create_witticism_icon())
        self.resize(750, 600)
        self.setMinimumSize(600, 450)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Header with icon and title
        header_layout = QHBoxLayout()

        # App icon
        icon_label = QLabel()
        icon = create_witticism_icon(64)
        icon_label.setPixmap(icon.pixmap(64, 64))

        # Title and version
        title_layout = QVBoxLayout()
        title_label = QLabel("Witticism")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title_label.setFont(title_font)

        # Get version from package metadata
        try:
            version = importlib.metadata.version("witticism")
        except Exception:
            # Fallback if package not installed
            version = "0.1.0"

        version_label = QLabel(f"Version {version}")
        subtitle_label = QLabel("WhisperX-powered voice transcription")

        title_layout.addWidget(title_label)
        title_layout.addWidget(version_label)
        title_layout.addWidget(subtitle_label)
        title_layout.addStretch()

        header_layout.addWidget(icon_label)
        header_layout.addSpacing(20)
        header_layout.addLayout(title_layout)
        header_layout.addStretch()

        layout.addLayout(header_layout)
        layout.addSpacing(20)

        # Tab widget for different sections
        tabs = QTabWidget()

        # About tab
        about_tab = QWidget()
        about_layout = QVBoxLayout()
        about_text = QTextBrowser()
        about_text.setOpenExternalLinks(True)

        # Get current hotkey settings
        ptt_key = "F9"  # Default
        mode_switch_key = "Ctrl+Alt+M"  # Default
        if self.config_manager:
            ptt_key = self.config_manager.get("hotkeys.push_to_talk", "F9").upper()
            mode_switch_key = self.config_manager.get("hotkeys.mode_switch", "Ctrl+Alt+M")

        about_text.setHtml(f"""
        <p>Witticism is a powerful voice transcription tool that types with your voice anywhere on your system.</p>

        <h3>Features:</h3>
        <ul>
            <li><b>Push-to-Talk Mode:</b> Hold {ptt_key} to record, release to transcribe</li>
            <li><b>Toggle Dictation Mode:</b> Press {ptt_key} to start/stop continuous transcription</li>
            <li><b>GPU Acceleration:</b> Uses CUDA for fast transcription when available</li>
            <li><b>Multiple Models:</b> Choose from tiny to large models based on your needs</li>
            <li><b>System Tray Integration:</b> Runs quietly in the background</li>
        </ul>

        <h3>Keyboard Shortcuts:</h3>
        <ul>
            <li><b>{ptt_key}:</b> Push-to-talk or toggle dictation (depending on mode)</li>
            <li><b>{mode_switch_key}:</b> Switch between push-to-talk and toggle modes</li>
        </ul>

        <p>Visit <a href="https://github.com/Aaronontheweb/witticism">GitHub</a> for more information.</p>
        """)
        about_layout.addWidget(about_text)
        about_tab.setLayout(about_layout)
        tabs.addTab(about_tab, "About")

        # Credits tab
        credits_tab = QWidget()
        credits_layout = QVBoxLayout()
        credits_text = QTextBrowser()
        credits_text.setOpenExternalLinks(True)
        credits_text.setHtml("""
        <h3>Built with:</h3>
        <ul>
            <li><a href="https://github.com/m-bain/whisperX">WhisperX</a> - Fast automatic speech recognition</li>
            <li><a href="https://github.com/openai/whisper">OpenAI Whisper</a> - Speech recognition models</li>
            <li><a href="https://www.riverbankcomputing.com/software/pyqt/">PyQt5</a> - GUI framework</li>
            <li><a href="https://github.com/moses-palmer/pynput">pynput</a> - Keyboard control</li>
            <li><a href="https://people.csail.mit.edu/hubert/pyaudio/">PyAudio</a> - Audio capture</li>
        </ul>

        <h3>Author:</h3>
        <p>Created by <a href="https://aaronstannard.com/">Aaron Stannard</a></p>

        <h3>License:</h3>
        <p>Apache License 2.0</p>
        """)
        credits_layout.addWidget(credits_text)
        credits_tab.setLayout(credits_layout)
        tabs.addTab(credits_tab, "Credits")

        # System Info tab
        system_tab = QWidget()
        system_layout = QVBoxLayout()
        system_text = QTextBrowser()

        # Get system information
        import torch
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            try:
                gpu_name = torch.cuda.get_device_name(0)
                gpu_memory = f"{torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB"
            except RuntimeError:
                # CUDA initialization failed
                cuda_available = False
                gpu_name = "Not available"
                gpu_memory = "N/A"
        else:
            gpu_name = "Not available"
            gpu_memory = "N/A"

        system_text.setHtml(f"""
        <h3>System Information:</h3>
        <ul>
            <li><b>Python Version:</b> {sys.version.split()[0]}</li>
            <li><b>PyTorch Version:</b> {torch.__version__}</li>
            <li><b>CUDA Available:</b> {'Yes' if cuda_available else 'No'}</li>
            <li><b>GPU:</b> {gpu_name}</li>
            <li><b>GPU Memory:</b> {gpu_memory}</li>
        </ul>

        <h3>Cache Location:</h3>
        <p>{Path.home() / '.cache' / 'huggingface' / 'hub'}</p>
        """)
        system_layout.addWidget(system_text)
        system_tab.setLayout(system_layout)
        tabs.addTab(system_tab, "System")

        layout.addWidget(tabs)

        # Close button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)

        layout.addLayout(button_layout)

        self.setLayout(layout)
