from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QPushButton,
                             QKeySequenceEdit, QLabel)
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QKeySequence

class HotkeyInputWidget(QWidget):
    keySequenceChanged = pyqtSignal(str)

    def __init__(self, default_key="", parent=None):
        super().__init__(parent)
        self.default_key = default_key
        self.original_key = default_key
        self.is_editing = False
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.key_display = QLabel(self.default_key if self.default_key else "Not set")
        self.key_display.setFrameStyle(QLabel.Box)
        self.key_display.setStyleSheet("""
            QLabel {
                padding: 4px 8px;
                background-color: palette(base);
                border: 1px solid palette(mid);
                border-radius: 3px;
                min-width: 150px;
            }
        """)

        self.key_edit = QKeySequenceEdit()
        self.key_edit.setKeySequence(QKeySequence(self.default_key))
        self.key_edit.hide()
        self.key_edit.keySequenceChanged.connect(self.on_key_sequence_changed)

        self.edit_btn = QPushButton("Edit")
        self.edit_btn.setMaximumWidth(60)
        self.edit_btn.clicked.connect(self.start_editing)

        self.save_btn = QPushButton("✓")
        self.save_btn.setMaximumWidth(30)
        self.save_btn.setToolTip("Save changes")
        self.save_btn.hide()
        self.save_btn.clicked.connect(self.save_changes)

        self.cancel_btn = QPushButton("✗")
        self.cancel_btn.setMaximumWidth(30)
        self.cancel_btn.setToolTip("Cancel changes")
        self.cancel_btn.hide()
        self.cancel_btn.clicked.connect(self.cancel_changes)

        self.reset_btn = QPushButton("↺")
        self.reset_btn.setMaximumWidth(30)
        self.reset_btn.setToolTip(f"Reset to default ({self.default_key})")
        self.reset_btn.clicked.connect(self.reset_to_default)

        layout.addWidget(self.key_display)
        layout.addWidget(self.key_edit)
        layout.addWidget(self.edit_btn)
        layout.addWidget(self.save_btn)
        layout.addWidget(self.cancel_btn)
        layout.addWidget(self.reset_btn)
        layout.addStretch()

        self.setLayout(layout)

    def start_editing(self):
        self.is_editing = True
        self.original_key = self.key_edit.keySequence().toString()

        self.key_display.hide()
        self.edit_btn.hide()
        self.reset_btn.hide()

        self.key_edit.show()
        self.save_btn.show()
        self.cancel_btn.show()

        self.key_edit.setFocus()
        self.key_edit.clear()

    def save_changes(self):
        new_key = self.key_edit.keySequence().toString()
        self.key_display.setText(new_key if new_key else "Not set")
        self.keySequenceChanged.emit(new_key)
        self.stop_editing()

    def cancel_changes(self):
        self.key_edit.setKeySequence(QKeySequence(self.original_key))
        self.stop_editing()

    def stop_editing(self):
        self.is_editing = False

        self.key_edit.hide()
        self.save_btn.hide()
        self.cancel_btn.hide()

        self.key_display.show()
        self.edit_btn.show()
        self.reset_btn.show()

    def reset_to_default(self):
        self.key_edit.setKeySequence(QKeySequence(self.default_key))
        self.key_display.setText(self.default_key if self.default_key else "Not set")
        self.keySequenceChanged.emit(self.default_key)

    def on_key_sequence_changed(self, key_sequence):
        pass

    def keySequence(self):
        return self.key_edit.keySequence()

    def setKeySequence(self, key_sequence):
        self.key_edit.setKeySequence(key_sequence)
        self.key_display.setText(key_sequence.toString() if key_sequence.toString() else "Not set")
