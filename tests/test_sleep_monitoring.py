import unittest
import os
from unittest.mock import Mock, patch
from src.witticism.platform.sleep_monitor import (
    MockSleepMonitor,
    create_sleep_monitor,
    _is_test_environment
)


class TestSleepMonitoring(unittest.TestCase):
    """Test sleep monitoring functionality"""
    
    def test_mock_sleep_monitor_basic_functionality(self):
        """Test that mock sleep monitor works correctly"""
        suspend_callback = Mock()
        resume_callback = Mock()
        
        monitor = MockSleepMonitor(suspend_callback, resume_callback)
        
        # Initially not monitoring
        self.assertFalse(monitor.is_monitoring())
        
        # Start monitoring
        monitor.start_monitoring()
        self.assertTrue(monitor.is_monitoring())
        
        # Simulate suspend
        monitor.simulate_suspend()
        suspend_callback.assert_called_once()
        self.assertEqual(len(monitor.suspend_calls), 1)
        
        # Simulate resume
        monitor.simulate_resume()
        resume_callback.assert_called_once()
        self.assertEqual(len(monitor.resume_calls), 1)
        
        # Stop monitoring
        monitor.stop_monitoring()
        self.assertFalse(monitor.is_monitoring())
    
    def test_suspend_resume_cycle(self):
        """Test full suspend/resume cycle"""
        suspend_callback = Mock()
        resume_callback = Mock()
        
        monitor = MockSleepMonitor(suspend_callback, resume_callback)
        monitor.start_monitoring()
        
        # Simulate multiple cycles
        for i in range(3):
            monitor.simulate_suspend()
            monitor.simulate_resume()
        
        self.assertEqual(suspend_callback.call_count, 3)
        self.assertEqual(resume_callback.call_count, 3)
        self.assertEqual(len(monitor.suspend_calls), 3)
        self.assertEqual(len(monitor.resume_calls), 3)
    
    def test_no_events_when_not_monitoring(self):
        """Test that events don't fire when not monitoring"""
        suspend_callback = Mock()
        resume_callback = Mock()
        
        monitor = MockSleepMonitor(suspend_callback, resume_callback)
        # Don't start monitoring
        
        monitor.simulate_suspend()
        monitor.simulate_resume()
        
        suspend_callback.assert_not_called()
        resume_callback.assert_not_called()
        self.assertEqual(len(monitor.suspend_calls), 0)
        self.assertEqual(len(monitor.resume_calls), 0)
    
    def test_factory_creates_mock_in_test_environment(self):
        """Test that factory creates mock monitor in test environment"""
        suspend_callback = Mock()
        resume_callback = Mock()
        
        # Should automatically detect test environment
        monitor = create_sleep_monitor(suspend_callback, resume_callback)
        
        self.assertIsInstance(monitor, MockSleepMonitor)
        self.assertIsNotNone(monitor)
    
    @patch.dict(os.environ, {'PYTEST_CURRENT_TEST': 'test_file.py::test_func'})
    def test_is_test_environment_detection(self):
        """Test test environment detection"""
        self.assertTrue(_is_test_environment())
    
    @patch.dict(os.environ, {'CI': 'true'})
    def test_ci_environment_detection(self):
        """Test CI environment detection"""
        self.assertTrue(_is_test_environment())
    
    @patch.dict(os.environ, {'WITTICISM_FORCE_MOCK_SLEEP': 'true'})
    def test_forced_mock_environment(self):
        """Test forced mock environment"""
        self.assertTrue(_is_test_environment())
    
    def test_error_handling_in_callbacks(self):
        """Test that errors in callbacks don't break the monitor"""
        def failing_suspend():
            raise Exception("Suspend callback failed")
        
        def failing_resume():
            raise Exception("Resume callback failed")
        
        monitor = MockSleepMonitor(failing_suspend, failing_resume)
        monitor.start_monitoring()
        
        # These should raise exceptions
        with self.assertRaises(Exception) as cm:
            monitor.simulate_suspend()
        self.assertIn("Suspend callback failed", str(cm.exception))
        
        with self.assertRaises(Exception) as cm:
            monitor.simulate_resume()
        self.assertIn("Resume callback failed", str(cm.exception))
        
        # Monitor should still be functional
        self.assertTrue(monitor.is_monitoring())


class TestSleepMonitorIntegration(unittest.TestCase):
    """Test integration with WhisperX engine (using mock)"""
    
    def test_whisperx_engine_with_sleep_monitoring(self):
        """Test that WhisperX engine can be enhanced with sleep monitoring"""
        try:
            from src.witticism.core.whisperx_engine import WhisperXEngine
        except ImportError as e:
            self.skipTest(f"WhisperX dependencies not available: {e}")
        
        # Create engine (will use mock_whisperx in test environment)
        engine = WhisperXEngine(model_size="tiny")
        
        # Track suspend/resume calls
        suspend_calls = []
        resume_calls = []
        
        def on_suspend():
            suspend_calls.append("suspend")
            # Simulate clearing GPU contexts
            if hasattr(engine, '_on_system_suspend'):
                engine._on_system_suspend()
        
        def on_resume():
            resume_calls.append("resume")
            # Simulate validating GPU contexts
            if hasattr(engine, '_on_system_resume'):
                engine._on_system_resume()
        
        # Create sleep monitor
        monitor = create_sleep_monitor(on_suspend, on_resume)
        monitor.start_monitoring()
        
        # Simulate suspend/resume cycle
        monitor.simulate_suspend()
        monitor.simulate_resume()
        
        self.assertEqual(len(suspend_calls), 1)
        self.assertEqual(len(resume_calls), 1)
        self.assertEqual(suspend_calls[0], "suspend")
        self.assertEqual(resume_calls[0], "resume")
    
    def test_recovery_tracking(self):
        """Test that we can track recovery attempts"""
        recovery_attempts = []
        validation_attempts = []
        
        def mock_recovery():
            recovery_attempts.append(True)
        
        def mock_validation():
            validation_attempts.append(True)
        
        monitor = create_sleep_monitor(mock_recovery, mock_validation)
        monitor.start_monitoring()
        
        # Multiple suspend/resume cycles
        for _ in range(2):
            monitor.simulate_suspend()
            monitor.simulate_resume()
        
        self.assertEqual(len(recovery_attempts), 2)
        self.assertEqual(len(validation_attempts), 2)