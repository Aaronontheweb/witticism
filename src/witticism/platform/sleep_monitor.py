import logging
import os
import platform
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
