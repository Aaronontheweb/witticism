import logging
import os
import platform
import subprocess
from abc import ABC, abstractmethod
from typing import Callable

logger = logging.getLogger(__name__)


class SleepMonitor(ABC):
    """Abstract interface for system sleep/resume monitoring"""

    def __init__(self, on_suspend: Callable[[], None], on_resume: Callable[[], None]):
        self.on_suspend = on_suspend
        self.on_resume = on_resume

    @abstractmethod
    def start_monitoring(self) -> None:
        """Start monitoring for sleep/resume events"""
        pass

    @abstractmethod
    def stop_monitoring(self) -> None:
        """Stop monitoring for sleep/resume events"""
        pass

    @abstractmethod
    def is_monitoring(self) -> bool:
        """Check if currently monitoring"""
        pass


class LinuxDBusSleepMonitor(SleepMonitor):
    """Linux sleep monitoring using DBus"""

    def __init__(self, on_suspend: Callable[[], None], on_resume: Callable[[], None]):
        super().__init__(on_suspend, on_resume)
        self._monitoring = False

        # Import here to avoid dependency issues
        try:
            from pydbus import SystemBus
            self.bus = SystemBus()
            self.login_manager = self.bus.get("org.freedesktop.login1")
            logger.info("[SLEEP_MONITOR] INIT: DBus sleep monitoring initialized")
        except ImportError:
            logger.error("[SLEEP_MONITOR] DEPENDENCY_MISSING: pydbus not available - cannot monitor sleep events")
            raise

    def start_monitoring(self) -> None:
        if not self._monitoring:
            self.login_manager.PrepareForSleep.connect(self._on_prepare_for_sleep)
            self._monitoring = True
            logger.info("[SLEEP_MONITOR] STARTED: DBus PrepareForSleep signal monitoring active")

    def stop_monitoring(self) -> None:
        if self._monitoring:
            # Note: pydbus doesn't have easy disconnect, but this is fine for our use case
            self._monitoring = False
            logger.info("[SLEEP_MONITOR] STOPPED: DBus sleep monitoring deactivated")

    def is_monitoring(self) -> bool:
        return self._monitoring

    def _on_prepare_for_sleep(self, suspending: bool):
        """Handle DBus PrepareForSleep signal"""
        import time
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        if suspending:
            logger.info(f"[SLEEP_MONITOR] SUSPEND_DETECTED: system entering sleep state at {timestamp}")
            self.on_suspend()
        else:
            logger.info(f"[SLEEP_MONITOR] RESUME_DETECTED: system waking from sleep state at {timestamp}")
            self.on_resume()


class SystemdInhibitorSleepMonitor(LinuxDBusSleepMonitor):
    """Enhanced DBus sleep monitor with systemd inhibitor locks for CUDA protection"""

    def __init__(self, on_suspend: Callable[[], None], on_resume: Callable[[], None]):
        super().__init__(on_suspend, on_resume)
        self.inhibitor_process = None
        self.cleanup_timeout = 20  # seconds max delay for cleanup

    def _check_inhibitor_support(self) -> bool:
        """Check if systemd inhibitors are available"""
        try:
            result = subprocess.run(['systemd-inhibit', '--help'],
                                  capture_output=True, timeout=2)
            return result.returncode == 0
        except Exception:
            return False

    def _on_prepare_for_sleep(self, suspending: bool):
        """Handle DBus PrepareForSleep signal with inhibitor protection"""
        import time
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        if suspending:
            logger.info(f"[SLEEP_MONITOR] SUSPEND_WITH_INHIBITOR: acquiring lock for CUDA cleanup at {timestamp}")

            # CRITICAL: Start inhibitor BEFORE cleanup to delay suspend
            inhibitor_acquired = self._acquire_inhibitor()

            try:
                # Now we have guaranteed time to clean up safely
                logger.info(f"[SLEEP_MONITOR] PROTECTED_CLEANUP: performing CUDA cleanup with {self.cleanup_timeout}s protection")
                self.on_suspend()
                logger.info("[SLEEP_MONITOR] CLEANUP_COMPLETE: releasing inhibitor to allow suspend")
            except Exception as e:
                logger.error(f"[SLEEP_MONITOR] CLEANUP_ERROR: suspend cleanup failed - {e}")
            finally:
                # ALWAYS release lock, even on failure - system must be able to suspend
                if inhibitor_acquired:
                    self._release_inhibitor()

        else:
            logger.info(f"[SLEEP_MONITOR] RESUME_WITH_INHIBITOR: system resumed from suspend at {timestamp}")
            self.on_resume()

    def _acquire_inhibitor(self) -> bool:
        """Delay suspend while cleanup happens"""
        try:
            self.inhibitor_process = subprocess.Popen([
                'systemd-inhibit',
                '--what=sleep',
                '--who=witticism',
                '--why=CUDA context cleanup required to prevent crash',
                '--mode=delay',
                'sleep', str(self.cleanup_timeout)
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            logger.debug(f"[SLEEP_MONITOR] INHIBITOR_ACQUIRED: systemd inhibitor active (max {self.cleanup_timeout}s delay)")
            return True
        except Exception as e:
            logger.error(f"[SLEEP_MONITOR] INHIBITOR_FAILED: could not acquire suspend inhibitor - {e}")
            return False

    def _release_inhibitor(self):
        """Allow suspend to proceed by terminating inhibitor process"""
        if self.inhibitor_process:
            try:
                self.inhibitor_process.terminate()
                # Give it a moment to terminate gracefully
                self.inhibitor_process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                # Force kill if it doesn't terminate quickly
                self.inhibitor_process.kill()
                self.inhibitor_process.wait()
            except Exception as e:
                logger.warning(f"[SLEEP_MONITOR] INHIBITOR_ERROR: error releasing inhibitor - {e}")
            finally:
                self.inhibitor_process = None
                logger.debug("[SLEEP_MONITOR] INHIBITOR_RELEASED: systemd inhibitor terminated, suspend allowed")

    def stop_monitoring(self) -> None:
        """Stop monitoring and clean up any active inhibitor"""
        # Release any active inhibitor first
        if self.inhibitor_process:
            self._release_inhibitor()
        # Then stop DBus monitoring
        super().stop_monitoring()


class MockSleepMonitor(SleepMonitor):
    """Mock sleep monitor for testing"""

    def __init__(self, on_suspend: Callable[[], None], on_resume: Callable[[], None]):
        super().__init__(on_suspend, on_resume)
        self._monitoring = False
        self.suspend_calls = []
        self.resume_calls = []

    def start_monitoring(self) -> None:
        self._monitoring = True
        logger.debug("[SLEEP_MONITOR] MOCK_STARTED: mock sleep monitoring for testing")

    def stop_monitoring(self) -> None:
        self._monitoring = False
        logger.debug("[SLEEP_MONITOR] MOCK_STOPPED: mock sleep monitoring deactivated")

    def is_monitoring(self) -> bool:
        return self._monitoring

    # Test control methods
    def simulate_suspend(self):
        """Test method to simulate suspend event"""
        if self._monitoring:
            logger.debug("[SLEEP_MONITOR] MOCK_SUSPEND: simulating suspend event for testing")
            self.suspend_calls.append(True)
            self.on_suspend()

    def simulate_resume(self):
        """Test method to simulate resume event"""
        if self._monitoring:
            logger.debug("[SLEEP_MONITOR] MOCK_RESUME: simulating resume event for testing")
            self.resume_calls.append(True)
            self.on_resume()


class WindowsPowerEventSleepMonitor(SleepMonitor):
    """Windows sleep monitoring using PowerShell event monitoring"""
    def __init__(self, on_suspend: Callable[[], None], on_resume: Callable[[], None]):
        super().__init__(on_suspend, on_resume)
        self._monitoring = False
        self._monitor_thread = None
        self._stop_event = None
    def start_monitoring(self) -> None:
        if not self._monitoring:
            import threading
            self._stop_event = threading.Event()
            self._monitor_thread = threading.Thread(target=self._monitor_power_events, daemon=True)
            self._monitor_thread.start()
            self._monitoring = True
            logger.info("[SLEEP_MONITOR] STARTED: Windows power event monitoring active")
    def stop_monitoring(self) -> None:
        if self._monitoring:
            if self._stop_event:
                self._stop_event.set()
            if self._monitor_thread and self._monitor_thread.is_alive():
                self._monitor_thread.join(timeout=2.0)
            self._monitoring = False
            logger.info("[SLEEP_MONITOR] STOPPED: Windows power event monitoring deactivated")
    def is_monitoring(self) -> bool:
        return self._monitoring
    def _monitor_power_events(self):
        """Monitor Windows power events using PowerShell"""
        try:
            # Simple approach: Poll power status changes using PowerShell
            import subprocess
            import time

            logger.debug("[SLEEP_MONITOR] WINDOWS_MONITOR: starting PowerShell power event monitoring")
            # Poll power status changes
            prev_power_status = self._get_power_status()
            while not self._stop_event.is_set():
                try:
                    current_power_status = self._get_power_status()
                    # Simple heuristic: if we can't get power status, system might be suspending
                    if prev_power_status is not None and current_power_status is None:
                        logger.info("[SLEEP_MONITOR] SUSPEND_DETECTED: Windows power status unavailable - likely suspending")
                        self.on_suspend()
                    elif prev_power_status is None and current_power_status is not None:
                        logger.info("[SLEEP_MONITOR] RESUME_DETECTED: Windows power status restored - likely resumed")
                        self.on_resume()
                    prev_power_status = current_power_status
                except Exception as e:
                    logger.warning(f"[SLEEP_MONITOR] WINDOWS_ERROR: power monitoring error - {e}")
                # Poll every 5 seconds
                self._stop_event.wait(5.0)
        except Exception as e:
            logger.error(f"[SLEEP_MONITOR] WINDOWS_INIT_ERROR: failed to start power monitoring - {e}")
    def _get_power_status(self) -> bool:
        """Get current power status using PowerShell - returns None if unavailable"""
        try:
            import subprocess
            result = subprocess.run([
                'powershell', '-Command',
                'Get-WmiObject -Class Win32_Battery | Select-Object -First 1 | Select-Object -ExpandProperty BatteryStatus'
            ], capture_output=True, timeout=3, text=True)
            return result.returncode == 0 and result.stdout.strip()
        except Exception:
            return None


def create_sleep_monitor(on_suspend: Callable[[], None], on_resume: Callable[[], None]) -> SleepMonitor:
    """Factory to create appropriate sleep monitor for the current platform"""

    # Force mock in test environments
    if _is_test_environment():
        logger.info("[SLEEP_MONITOR] FACTORY: creating mock monitor for test environment")
        return MockSleepMonitor(on_suspend, on_resume)

    system = platform.system().lower()

    if system == "linux":
        try:
            # Try enhanced monitor with systemd inhibitor support first
            monitor = SystemdInhibitorSleepMonitor(on_suspend, on_resume)
            if monitor._check_inhibitor_support():
                logger.info("[SLEEP_MONITOR] FACTORY: creating systemd inhibitor monitor with CUDA protection")
                return monitor
            else:
                logger.warning("[SLEEP_MONITOR] FACTORY: systemd inhibitors not available - using basic DBus monitor")
                return LinuxDBusSleepMonitor(on_suspend, on_resume)
        except ImportError:
            logger.warning("[SLEEP_MONITOR] FACTORY: DBus not available, sleep monitoring disabled")
    elif system == "darwin":
        # TODO: Implement MacOS monitoring
        logger.warning("[SLEEP_MONITOR] FACTORY: MacOS sleep monitoring not yet implemented")
    elif system == "windows":
        try:
            logger.info("[SLEEP_MONITOR] FACTORY: creating Windows power event monitor")
            return WindowsPowerEventSleepMonitor(on_suspend, on_resume)
        except Exception as e:
            logger.warning(f"[SLEEP_MONITOR] FACTORY: Windows sleep monitoring failed to initialize - {e}")
    else:
        logger.warning(f"[SLEEP_MONITOR] FACTORY: sleep monitoring not supported on {system}")

    # Return None for unsupported platforms or failed imports
    # The application should handle None gracefully
    return None


def _is_test_environment() -> bool:
    """Detect if we're running in a test environment"""
    import sys

    # Check for unittest or pytest
    unittest_running = 'unittest' in sys.modules and any('test' in arg.lower() for arg in sys.argv)

    return (
        os.getenv('PYTEST_CURRENT_TEST') is not None or
        os.getenv('CI') == 'true' or
        os.getenv('GITHUB_ACTIONS') == 'true' or
        os.getenv('WITTICISM_FORCE_MOCK_SLEEP') == 'true' or
        unittest_running
    )
