"""
Dependency validation system for Witticism.

This module provides comprehensive validation of system and Python dependencies
to prevent silent failures during initialization.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from enum import Enum
import logging
import os
import platform
import subprocess
import sys

logger = logging.getLogger(__name__)


class DependencyType(Enum):
    """Type of dependency and how critical it is"""
    REQUIRED = "required"  # Must be present - fatal if missing
    OPTIONAL = "optional"  # Enhances functionality but not required
    PLATFORM_SPECIFIC = "platform_specific"  # Required only on certain platforms


@dataclass
class DependencyResult:
    """Result of a dependency check"""
    name: str
    available: bool
    version: Optional[str] = None
    error_message: Optional[str] = None
    dependency_type: DependencyType = DependencyType.REQUIRED
    platform_required: Optional[str] = None  # e.g., "linux", "windows", "darwin"

    def __str__(self):
        status = "[OK]" if self.available else "[FAIL]"
        version_info = f" (v{self.version})" if self.version else ""
        platform_info = f" [{self.platform_required}]" if self.platform_required else ""
        return f"{status} {self.name}{version_info}{platform_info}"


class DependencyValidator:
    """Validates system and Python dependencies before initialization"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.current_platform = platform.system().lower()

    def _is_headless_environment(self) -> bool:
        """Detect if we're running in a headless/display-less environment"""
        # Most reliable for CI environments
        return (
            not os.environ.get('DISPLAY') and
            os.environ.get('CI') == 'true'
        ) or (
            # GitHub Actions specific
            os.environ.get('GITHUB_ACTIONS') == 'true'
        ) or (
            # General headless indicators
            os.environ.get('HEADLESS') == 'true'
        )

    def validate_all(self) -> List[DependencyResult]:
        """Validate all dependencies and return results"""
        self.logger.info("[DEPENDENCY_VALIDATOR] VALIDATION_START: checking all dependencies")

        results = []
        results.extend(self._validate_python_deps())
        results.extend(self._validate_system_deps())
        results.extend(self._validate_platform_deps())

        self.logger.info(f"[DEPENDENCY_VALIDATOR] VALIDATION_COMPLETE: checked {len(results)} dependencies")
        return results

    def _validate_python_deps(self) -> List[DependencyResult]:
        """Check Python package dependencies"""
        deps = [
            ("torch", DependencyType.REQUIRED, None),
            ("whisperx", DependencyType.REQUIRED, None),
            ("PyQt5", DependencyType.REQUIRED, None),
            ("pydbus", DependencyType.PLATFORM_SPECIFIC, "linux"),  # Linux only
            ("pyaudio", DependencyType.REQUIRED, None),
            ("numpy", DependencyType.REQUIRED, None),
            ("scipy", DependencyType.OPTIONAL, None),
            ("transformers", DependencyType.REQUIRED, None),
        ]

        results = []
        for dep_name, dep_type, platform_req in deps:
            # Skip platform-specific dependencies if not on that platform
            if platform_req and self.current_platform != platform_req:
                continue

            try:
                import importlib
                module = importlib.import_module(dep_name)
                version = getattr(module, '__version__', 'unknown')
                results.append(DependencyResult(
                    dep_name, True, version, None, dep_type, platform_req
                ))
                self.logger.debug(f"[DEPENDENCY_VALIDATOR] PYTHON_OK: {dep_name} v{version}")

            except ImportError as e:
                error_msg = str(e)
                results.append(DependencyResult(
                    dep_name, False, None, error_msg, dep_type, platform_req
                ))

                if dep_type == DependencyType.REQUIRED:
                    self.logger.error(f"[DEPENDENCY_VALIDATOR] PYTHON_MISSING_REQUIRED: {dep_name} - {error_msg}")
                elif dep_type == DependencyType.PLATFORM_SPECIFIC:
                    self.logger.warning(f"[DEPENDENCY_VALIDATOR] PYTHON_MISSING_PLATFORM: {dep_name} - feature will be disabled")
                else:
                    self.logger.info(f"[DEPENDENCY_VALIDATOR] PYTHON_MISSING_OPTIONAL: {dep_name} - enhanced features unavailable")

        return results

    def _validate_system_deps(self) -> List[DependencyResult]:
        """Check system dependencies"""
        results = []

        # Check for systemd-inhibit on Linux (used for sleep monitoring protection)
        if self.current_platform == "linux":
            systemd_result = self._check_command_available(
                "systemd-inhibit",
                DependencyType.OPTIONAL,
                "linux"
            )
            results.append(systemd_result)

            if systemd_result.available:
                self.logger.debug("[DEPENDENCY_VALIDATOR] SYSTEM_OK: systemd-inhibit available for sleep protection")
            else:
                self.logger.warning("[DEPENDENCY_VALIDATOR] SYSTEM_MISSING: systemd-inhibit not available - CUDA sleep protection will be limited")

        # Check for Python version compatibility
        python_version = sys.version_info
        if python_version >= (3, 8):
            results.append(DependencyResult(
                "python_version", True, f"{python_version.major}.{python_version.minor}.{python_version.micro}",
                None, DependencyType.REQUIRED
            ))
            self.logger.debug(f"[DEPENDENCY_VALIDATOR] SYSTEM_OK: Python {python_version.major}.{python_version.minor}")
        else:
            error_msg = f"Python {python_version.major}.{python_version.minor} too old, need >= 3.8"
            results.append(DependencyResult(
                "python_version", False, f"{python_version.major}.{python_version.minor}",
                error_msg, DependencyType.REQUIRED
            ))
            self.logger.error(f"[DEPENDENCY_VALIDATOR] SYSTEM_VERSION_ERROR: {error_msg}")

        return results

    def _validate_platform_deps(self) -> List[DependencyResult]:
        """Check platform-specific dependencies"""
        results = []

        if self.current_platform == "linux":
            # Check for DBus availability (used for sleep monitoring)
            try:
                import pydbus
                bus = pydbus.SystemBus()
                # Try to connect to login manager to verify it's accessible
                bus.get("org.freedesktop.login1")
                results.append(DependencyResult(
                    "dbus_login_manager", True, None, None,
                    DependencyType.PLATFORM_SPECIFIC, "linux"
                ))
                self.logger.debug("[DEPENDENCY_VALIDATOR] PLATFORM_OK: DBus login manager accessible")

            except ImportError:
                results.append(DependencyResult(
                    "dbus_login_manager", False, None, "pydbus not available",
                    DependencyType.PLATFORM_SPECIFIC, "linux"
                ))
                self.logger.warning("[DEPENDENCY_VALIDATOR] PLATFORM_MISSING: pydbus not available - sleep monitoring disabled")

            except Exception as e:
                results.append(DependencyResult(
                    "dbus_login_manager", False, None, str(e),
                    DependencyType.PLATFORM_SPECIFIC, "linux"
                ))
                self.logger.warning(f"[DEPENDENCY_VALIDATOR] PLATFORM_ERROR: DBus connection failed - {e}")

        elif self.current_platform == "windows":
            # Check for Windows-specific sleep monitoring capabilities
            try:
                # Test if we can access Win32 API for power management
                import subprocess
                result = subprocess.run(['powershell', '-Command', 'Get-WmiObject', '-Class', 'Win32_PowerPlan'],
                                      capture_output=True, timeout=5, text=True)
                if result.returncode == 0:
                    results.append(DependencyResult(
                        "windows_power_management", True, None, None,
                        DependencyType.PLATFORM_SPECIFIC, "windows"
                    ))
                    self.logger.debug("[DEPENDENCY_VALIDATOR] PLATFORM_OK: Windows power management accessible")
                else:
                    results.append(DependencyResult(
                        "windows_power_management", False, None, "PowerShell/WMI not accessible",
                        DependencyType.PLATFORM_SPECIFIC, "windows"
                    ))
                    self.logger.warning("[DEPENDENCY_VALIDATOR] PLATFORM_WARNING: Windows power management not accessible")
            except Exception as e:
                results.append(DependencyResult(
                    "windows_power_management", False, None, str(e),
                    DependencyType.PLATFORM_SPECIFIC, "windows"
                ))
                self.logger.warning(f"[DEPENDENCY_VALIDATOR] PLATFORM_ERROR: Windows power management check failed - {e}")

        # Check for CUDA availability (optional but important for performance)
        try:
            import torch
            if torch.cuda.is_available():
                cuda_version = torch.version.cuda
                device_count = torch.cuda.device_count()
                device_name = torch.cuda.get_device_name(0) if device_count > 0 else "Unknown"

                results.append(DependencyResult(
                    "cuda", True, cuda_version, None, DependencyType.OPTIONAL
                ))
                self.logger.info(f"[DEPENDENCY_VALIDATOR] CUDA_OK: {device_name} with CUDA {cuda_version}")
            else:
                results.append(DependencyResult(
                    "cuda", False, None, "CUDA not available - will use CPU",
                    DependencyType.OPTIONAL
                ))
                self.logger.info("[DEPENDENCY_VALIDATOR] CUDA_UNAVAILABLE: will use CPU mode")

        except Exception as e:
            results.append(DependencyResult(
                "cuda", False, None, str(e), DependencyType.OPTIONAL
            ))
            self.logger.warning(f"[DEPENDENCY_VALIDATOR] CUDA_ERROR: {e}")

        return results

    def _check_command_available(self, command: str, dep_type: DependencyType,
                                platform_req: Optional[str] = None) -> DependencyResult:
        """Check if a system command is available"""
        try:
            result = subprocess.run([command, '--help'],
                                  capture_output=True, timeout=5, text=True)
            available = result.returncode == 0

            # Try to extract version info from help output
            version = None
            if available and result.stdout:
                # Simple heuristic to find version info
                lines = result.stdout.split('\n')[:5]  # Check first few lines
                for line in lines:
                    if 'version' in line.lower():
                        version = line.strip()
                        break

            return DependencyResult(
                command, available, version, None, dep_type, platform_req
            )

        except subprocess.TimeoutExpired:
            return DependencyResult(
                command, False, None, "Command timeout", dep_type, platform_req
            )
        except FileNotFoundError:
            return DependencyResult(
                command, False, None, "Command not found", dep_type, platform_req
            )
        except Exception as e:
            return DependencyResult(
                command, False, None, str(e), dep_type, platform_req
            )

    def has_fatal_issues(self, results: List[DependencyResult]) -> bool:
        """Check if any required dependencies are missing"""
        for result in results:
            if not result.available and result.dependency_type == DependencyType.REQUIRED:
                return True
        return False

    def get_missing_required(self, results: List[DependencyResult]) -> List[DependencyResult]:
        """Get list of missing required dependencies"""
        return [r for r in results if not r.available and r.dependency_type == DependencyType.REQUIRED]

    def get_missing_optional(self, results: List[DependencyResult]) -> List[DependencyResult]:
        """Get list of missing optional dependencies"""
        return [r for r in results if not r.available and r.dependency_type in
                [DependencyType.OPTIONAL, DependencyType.PLATFORM_SPECIFIC]]

    def report_summary(self, results: List[DependencyResult]) -> Dict[str, Any]:
        """Generate a summary report of dependency validation"""
        total = len(results)
        available = sum(1 for r in results if r.available)
        missing_required = len(self.get_missing_required(results))
        missing_optional = len(self.get_missing_optional(results))

        summary = {
            "total_dependencies": total,
            "available": available,
            "missing_required": missing_required,
            "missing_optional": missing_optional,
            "success": missing_required == 0,
            "platform": self.current_platform,
            "details": results
        }

        self.logger.info(f"[DEPENDENCY_VALIDATOR] SUMMARY: {available}/{total} dependencies available, "
                        f"{missing_required} required missing, {missing_optional} optional missing")

        return summary

    def print_report(self, results: List[DependencyResult]) -> None:
        """Print a human-readable dependency report"""
        summary = self.report_summary(results)

        print("\n=== Witticism Dependency Report ===")
        print(f"Platform: {summary['platform']}")
        print(f"Dependencies: {summary['available']}/{summary['total_dependencies']} available")

        missing_req = self.get_missing_required(results)
        if missing_req:
            print(f"\n[ERROR] MISSING REQUIRED DEPENDENCIES ({len(missing_req)}):")
            for dep in missing_req:
                print(f"   {dep}")
                print(f"      Error: {dep.error_message}")

        missing_opt = self.get_missing_optional(results)
        if missing_opt:
            print(f"\n[WARNING] MISSING OPTIONAL DEPENDENCIES ({len(missing_opt)}):")
            for dep in missing_opt:
                print(f"   {dep}")
                if dep.error_message:
                    print(f"      Note: {dep.error_message}")

        available = [r for r in results if r.available]
        if available:
            print(f"\n[SUCCESS] AVAILABLE DEPENDENCIES ({len(available)}):")
            for dep in available[:10]:  # Show first 10 to avoid spam
                print(f"   {dep}")
            if len(available) > 10:
                print(f"   ... and {len(available) - 10} more")

        if summary['success']:
            print("\n[SUCCESS] All required dependencies are available!")
        else:
            print(f"\n[ERROR] {len(missing_req)} required dependencies missing - application may not start")

