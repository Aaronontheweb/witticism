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
            logger.info("DBus sleep monitoring initialized")
        except ImportError:
            logger.error("pydbus not available - cannot monitor sleep events")
            raise

    def start_monitoring(self) -> None:
        if not self._monitoring:
            self.login_manager.PrepareForSleep.connect(self._on_prepare_for_sleep)
            self._monitoring = True
            logger.info("Started DBus sleep monitoring")

    def stop_monitoring(self) -> None:
        if self._monitoring:
            # Note: pydbus doesn't have easy disconnect, but this is fine for our use case
            self._monitoring = False
            logger.info("Stopped DBus sleep monitoring")

    def is_monitoring(self) -> bool:
        return self._monitoring

    def _on_prepare_for_sleep(self, suspending: bool):
        """Handle DBus PrepareForSleep signal"""
        if suspending:
            logger.info("System is suspending")
            self.on_suspend()
        else:
            logger.info("System resumed from suspend")
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
        if suspending:
            logger.info("Suspend detected - acquiring inhibitor lock for CUDA cleanup")

            # CRITICAL: Start inhibitor BEFORE cleanup to delay suspend
            inhibitor_acquired = self._acquire_inhibitor()

            try:
                # Now we have guaranteed time to clean up safely
                logger.info("Performing CUDA cleanup with suspend protection")
                self.on_suspend()
                logger.info("CUDA cleanup completed - releasing inhibitor")
            except Exception as e:
                logger.error(f"Suspend cleanup failed: {e}")
            finally:
                # ALWAYS release lock, even on failure - system must be able to suspend
                if inhibitor_acquired:
                    self._release_inhibitor()

        else:
            logger.info("System resumed from suspend")
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

            logger.debug(f"Acquired suspend inhibitor (max {self.cleanup_timeout}s delay)")
            return True
        except Exception as e:
            logger.error(f"Failed to acquire suspend inhibitor: {e}")
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
                logger.warning(f"Error releasing inhibitor: {e}")
            finally:
                self.inhibitor_process = None
                logger.debug("Released suspend inhibitor")

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
        logger.debug("Started mock sleep monitoring")

    def stop_monitoring(self) -> None:
        self._monitoring = False
        logger.debug("Stopped mock sleep monitoring")

    def is_monitoring(self) -> bool:
        return self._monitoring

    # Test control methods
    def simulate_suspend(self):
        """Test method to simulate suspend event"""
        if self._monitoring:
            logger.debug("Simulating suspend event")
            self.suspend_calls.append(True)
            self.on_suspend()

    def simulate_resume(self):
        """Test method to simulate resume event"""
        if self._monitoring:
            logger.debug("Simulating resume event")
            self.resume_calls.append(True)
            self.on_resume()


def create_sleep_monitor(on_suspend: Callable[[], None], on_resume: Callable[[], None]) -> SleepMonitor:
    """Factory to create appropriate sleep monitor for the current platform"""

    # Force mock in test environments
    if _is_test_environment():
        logger.info("Creating mock sleep monitor for testing")
        return MockSleepMonitor(on_suspend, on_resume)

    system = platform.system().lower()

    if system == "linux":
        try:
            # Try enhanced monitor with systemd inhibitor support first
            monitor = SystemdInhibitorSleepMonitor(on_suspend, on_resume)
            if monitor._check_inhibitor_support():
                logger.info("Creating systemd inhibitor sleep monitor (CUDA protection)")
                return monitor
            else:
                logger.warning("Systemd inhibitors not available - using basic DBus monitor")
                return LinuxDBusSleepMonitor(on_suspend, on_resume)
        except ImportError:
            logger.warning("DBus not available, sleep monitoring disabled")
    elif system == "darwin":
        # TODO: Implement MacOS monitoring
        logger.warning("MacOS sleep monitoring not yet implemented")
    elif system == "windows":
        # TODO: Implement Windows monitoring
        logger.warning("Windows sleep monitoring not yet implemented")
    else:
        logger.warning(f"Sleep monitoring not supported on {system}")

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
