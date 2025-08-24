from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                            QPushButton, QTextEdit, QFrame)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QIcon
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class HealthCheckWorker(QThread):
    """Worker thread to perform CUDA health check without blocking UI"""

    health_check_complete = pyqtSignal(dict)  # Emits health check results

    def __init__(self, engine, dependency_validator):
        super().__init__()
        self.engine = engine
        self.dependency_validator = dependency_validator

    def run(self):
        """Perform comprehensive health check"""
        try:
            results = {}

            # Engine device info
            if self.engine:
                results['engine_info'] = self.engine.get_device_info()

            # Dependency validator results
            if self.dependency_validator:
                dep_results = self.dependency_validator.validate_all()
                cuda_deps = [r for r in dep_results if r.name == 'cuda']
                results['cuda_dependency'] = cuda_deps[0] if cuda_deps else None

            # CUDA health test if engine supports it
            if self.engine and hasattr(self.engine, '_test_cuda_health'):
                try:
                    results['cuda_health_test'] = self.engine._test_cuda_health()
                except Exception as e:
                    results['cuda_health_test'] = False
                    results['cuda_health_error'] = str(e)

            self.health_check_complete.emit(results)

        except Exception as e:
            logger.error(f"Health check worker error: {e}")
            self.health_check_complete.emit({
                'error': str(e)
            })


class CudaHealthDialog(QDialog):
    """Dialog showing CUDA health check results"""

    def __init__(self, engine=None, dependency_validator=None, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.dependency_validator = dependency_validator

        self.setWindowTitle("CUDA Health Check")
        self.setFixedSize(500, 400)
        self.setModal(True)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Title
        title_label = QLabel("GPU/CUDA System Health Check")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # Status area
        self.status_label = QLabel("Running health check...")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)

        # Results area
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setFont(QFont("Consolas", 9))  # Monospace for better formatting
        layout.addWidget(self.results_text)

        # Button area
        button_layout = QHBoxLayout()

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.run_health_check)
        self.refresh_button.setEnabled(False)  # Disabled during initial check
        button_layout.addWidget(self.refresh_button)

        button_layout.addStretch()

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)

        layout.addLayout(button_layout)

        # Start initial health check
        self.run_health_check()

    def run_health_check(self):
        """Start health check in background thread"""
        self.status_label.setText("Running health check...")
        self.refresh_button.setEnabled(False)
        self.results_text.clear()

        # Start worker thread
        self.worker = HealthCheckWorker(self.engine, self.dependency_validator)
        self.worker.health_check_complete.connect(self.display_results)
        self.worker.start()

    def display_results(self, results: Dict[str, Any]):
        """Display health check results"""
        self.refresh_button.setEnabled(True)

        if 'error' in results:
            self.status_label.setText("❌ Health check failed")
            self.results_text.setPlainText(f"Error during health check:\n{results['error']}")
            return

        # Format results
        output_lines = []

        # Overall status
        engine_info = results.get('engine_info', {})
        cuda_available = engine_info.get('cuda_available', False)
        cuda_fallback = engine_info.get('cuda_fallback', False)

        if cuda_available and not cuda_fallback:
            self.status_label.setText("✅ CUDA Available")
            output_lines.append("🟢 CUDA STATUS: Healthy and Active")
        elif cuda_available and cuda_fallback:
            self.status_label.setText("⚠️ CUDA Fallback Mode")
            output_lines.append("🟡 CUDA STATUS: Fallback Mode (Performance Reduced)")
        else:
            self.status_label.setText("❌ CUDA Not Available")
            output_lines.append("🔴 CUDA STATUS: Not Available (CPU Mode)")

        output_lines.append("")

        # Device Information
        output_lines.append("=== DEVICE INFORMATION ===")
        if engine_info:
            current_device = engine_info.get('device', 'unknown')
            original_device = engine_info.get('original_device', 'unknown')
            compute_type = engine_info.get('compute_type', 'unknown')

            output_lines.append(f"Current Device: {current_device}")
            if original_device != current_device:
                output_lines.append(f"Original Device: {original_device}")
            output_lines.append(f"Compute Type: {compute_type}")

            if 'gpu_name' in engine_info:
                output_lines.append(f"GPU: {engine_info['gpu_name']}")
            if 'gpu_memory_allocated' in engine_info:
                output_lines.append(f"GPU Memory Allocated: {engine_info['gpu_memory_allocated']}")
                output_lines.append(f"GPU Memory Reserved: {engine_info.get('gpu_memory_reserved', 'N/A')}")

        output_lines.append("")

        # CUDA Dependency Check
        output_lines.append("=== CUDA DEPENDENCY CHECK ===")
        cuda_dep = results.get('cuda_dependency')
        if cuda_dep:
            if cuda_dep.available:
                output_lines.append(f"✅ CUDA Available: Yes (v{cuda_dep.version})")
            else:
                output_lines.append("❌ CUDA Available: No")
                if cuda_dep.error_message:
                    output_lines.append(f"   Error: {cuda_dep.error_message}")
        else:
            output_lines.append("⚠️ CUDA dependency check not available")

        output_lines.append("")

        # CUDA Health Test
        output_lines.append("=== CUDA HEALTH TEST ===")
        if 'cuda_health_test' in results:
            if results['cuda_health_test']:
                output_lines.append("✅ CUDA Context Test: PASSED")
                output_lines.append("   GPU operations working correctly")
            else:
                output_lines.append("❌ CUDA Context Test: FAILED")
                if 'cuda_health_error' in results:
                    output_lines.append(f"   Error: {results['cuda_health_error']}")
        else:
            output_lines.append("⚠️ CUDA health test not available")

        output_lines.append("")

        # Recommendations
        output_lines.append("=== RECOMMENDATIONS ===")
        if cuda_available and not cuda_fallback:
            output_lines.append("🎉 System is working optimally!")
            output_lines.append("   GPU acceleration is active and healthy.")
        elif cuda_available and cuda_fallback:
            output_lines.append("⚠️ System is in fallback mode:")
            output_lines.append("   • Performance may be 2-3x slower")
            output_lines.append("   • This often occurs after suspend/resume")
            output_lines.append("   • Try restarting the application")
            output_lines.append("   • If issues persist, restart your computer")
        else:
            output_lines.append("ℹ️ Running in CPU mode:")
            output_lines.append("   • Transcription will be slower but functional")
            output_lines.append("   • Consider installing CUDA-capable GPU drivers")
            output_lines.append("   • Ensure PyTorch with CUDA support is installed")

        # Display results
        self.results_text.setPlainText("\n".join(output_lines))
