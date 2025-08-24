# Initialization Architecture Refactoring Plan

## Overview

This document outlines specific code changes needed to implement the phase-based initialization architecture described in ADR-001.

## Immediate Action Items

### 1. Critical Ordering Fix (Quick Win)

**Problem**: Sleep monitor enabled after CUDA validation  
**File**: `src/witticism/main.py:140-166`  
**Fix**: Move sleep monitor initialization before CUDA validation

```python
# CURRENT (lines 140-166):
if self.engine.device == "cuda":
    logger.info("[WITTICISM] CUDA_VALIDATION: performing startup health check")
    cuda_healthy = self.engine.validate_and_clean_cuda_at_startup()
    # ... validation logic
    
# Enable sleep monitoring for proactive CUDA recovery  
try:
    logger.info("[WITTICISM] SLEEP_MONITORING: enabling proactive suspend/resume detection")
    self.engine.enable_sleep_monitoring()

# SHOULD BE (reordered):
# Enable sleep monitoring BEFORE any CUDA operations
try:
    logger.info("[WITTICISM] SLEEP_MONITORING: enabling proactive suspend/resume detection") 
    self.engine.enable_sleep_monitoring()
except Exception as e:
    logger.warning(f"[WITTICISM] SLEEP_MONITORING_FAILED: initialization failed - {e}")

# Now CUDA validation with sleep monitoring protection
if self.engine.device == "cuda":
    logger.info("[WITTICISM] CUDA_VALIDATION: performing startup health check")
    cuda_healthy = self.engine.validate_and_clean_cuda_at_startup()
```

### 2. Early System Tray (Quick Win)

**Problem**: System tray created after all initialization, can't show startup errors  
**File**: `src/witticism/main.py:287-288`  
**Fix**: Create minimal system tray early for notifications

```python
# Add to initialize_components() method around line 124:
def initialize_components(self):
    try:
        # Create minimal system tray EARLY for startup notifications
        logger.info("[WITTICISM] TRAY_INIT: creating early notification system")
        self.tray_app = SystemTrayApp()
        self.tray_app.set_config_manager(self.config_manager)  # For basic notifications
        
        # Initialize WhisperX engine
        model_size = self.args.model or self.config_manager.get("model.size", "base")
        # ... rest of engine init

# Remove the late tray creation in run() method (line 287-288)
# Update setup_connections() to handle already-created tray
```

### 3. Dependency Validation (Medium Priority)

**Problem**: Silent failures when dependencies missing  
**New File**: `src/witticism/core/dependency_validator.py`

```python
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum
import logging

class DependencyType(Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    PLATFORM_SPECIFIC = "platform_specific"

@dataclass
class DependencyResult:
    name: str
    available: bool
    version: Optional[str] = None
    error_message: Optional[str] = None
    dependency_type: DependencyType = DependencyType.REQUIRED

class DependencyValidator:
    """Validates system and Python dependencies before initialization"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def validate_all(self) -> List[DependencyResult]:
        """Validate all dependencies and return results"""
        results = []
        results.extend(self._validate_python_deps())
        results.extend(self._validate_system_deps()) 
        results.extend(self._validate_platform_deps())
        return results
    
    def _validate_python_deps(self) -> List[DependencyResult]:
        """Check Python package dependencies"""
        deps = [
            ("torch", DependencyType.REQUIRED),
            ("whisperx", DependencyType.REQUIRED),
            ("PyQt5", DependencyType.REQUIRED),
            ("pydbus", DependencyType.PLATFORM_SPECIFIC),  # Linux only
            ("pyaudio", DependencyType.REQUIRED),
        ]
        
        results = []
        for dep_name, dep_type in deps:
            try:
                import importlib
                module = importlib.import_module(dep_name)
                version = getattr(module, '__version__', 'unknown')
                results.append(DependencyResult(dep_name, True, version, None, dep_type))
            except ImportError as e:
                results.append(DependencyResult(dep_name, False, None, str(e), dep_type))
        
        return results
    
    def _validate_system_deps(self) -> List[DependencyResult]:
        """Check system dependencies"""
        import subprocess
        import platform
        
        results = []
        
        # Check for systemd-inhibit on Linux
        if platform.system().lower() == "linux":
            try:
                result = subprocess.run(['systemd-inhibit', '--help'], 
                                      capture_output=True, timeout=2)
                available = result.returncode == 0
                results.append(DependencyResult("systemd-inhibit", available, None, None, 
                                              DependencyType.OPTIONAL))
            except Exception as e:
                results.append(DependencyResult("systemd-inhibit", False, None, str(e),
                                              DependencyType.OPTIONAL))
        
        return results
    
    def _validate_platform_deps(self) -> List[DependencyResult]:
        """Check platform-specific dependencies"""
        import platform
        
        results = []
        system = platform.system().lower()
        
        if system == "linux":
            # Check for DBus availability
            try:
                import pydbus
                bus = pydbus.SystemBus()
                results.append(DependencyResult("dbus", True, None, None, 
                                              DependencyType.PLATFORM_SPECIFIC))
            except Exception as e:
                results.append(DependencyResult("dbus", False, None, str(e),
                                              DependencyType.PLATFORM_SPECIFIC))
        
        return results
    
    def report_issues(self, results: List[DependencyResult]) -> None:
        """Log dependency issues with appropriate severity"""
        for result in results:
            if not result.available:
                if result.dependency_type == DependencyType.REQUIRED:
                    self.logger.error(f"[DEPENDENCY] MISSING_REQUIRED: {result.name} - {result.error_message}")
                elif result.dependency_type == DependencyType.PLATFORM_SPECIFIC:
                    self.logger.warning(f"[DEPENDENCY] MISSING_PLATFORM: {result.name} - feature will be disabled")
                else:
                    self.logger.info(f"[DEPENDENCY] MISSING_OPTIONAL: {result.name} - enhanced features unavailable")
            else:
                self.logger.debug(f"[DEPENDENCY] AVAILABLE: {result.name} version {result.version}")
```

## Full Architecture Implementation (Larger Effort)

### Phase 1: Create Initialization Framework

**New File**: `src/witticism/core/initialization_manager.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any
import logging

class InitPhase(Enum):
    BOOTSTRAP = "bootstrap"
    PLATFORM = "platform" 
    CORE_ENGINE = "core_engine"
    INTEGRATION = "integration"
    INTERFACE = "interface"
    ACTIVATION = "activation"

class ErrorType(Enum):
    FATAL = "fatal"
    RECOVERABLE = "recoverable"
    DEGRADED = "degraded"

@dataclass
class InitializationError:
    phase: InitPhase
    component: str
    error_type: ErrorType
    message: str
    recovery_action: Optional[str] = None
    user_guidance: Optional[str] = None

@dataclass
class InitializationContext:
    """Context passed between initialization phases"""
    config_manager: Any
    logger: logging.Logger
    tray_app: Optional[Any] = None
    engine: Optional[Any] = None
    dependency_results: Optional[List] = None
    args: Optional[Any] = None

class ComponentInitializer(ABC):
    """Base class for component initialization"""
    
    @property
    @abstractmethod
    def phase(self) -> InitPhase:
        """Which phase this component belongs to"""
        
    @property
    @abstractmethod
    def component_name(self) -> str:
        """Name of this component"""
    
    @property
    def required_dependencies(self) -> List[str]:
        """Components that must be available"""
        return []
        
    @property  
    def optional_dependencies(self) -> List[str]:
        """Components that enhance functionality but aren't required"""
        return []
        
    @abstractmethod
    def initialize(self, context: InitializationContext) -> Any:
        """Initialize component with provided context"""
        pass
        
    def validate_dependencies(self, context: InitializationContext) -> List[str]:
        """Check if dependencies are available, return list of missing ones"""
        missing = []
        # Implementation would check context for required components
        return missing

class InitializationManager:
    """Orchestrates phase-based component initialization"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.components: Dict[InitPhase, List[ComponentInitializer]] = {}
        self.context = InitializationContext(None, self.logger)
        self.errors: List[InitializationError] = []
    
    def register_component(self, component: ComponentInitializer):
        """Register a component for initialization"""
        phase = component.phase
        if phase not in self.components:
            self.components[phase] = []
        self.components[phase].append(component)
    
    def initialize_all(self, initial_context: InitializationContext) -> bool:
        """Run all initialization phases"""
        self.context = initial_context
        
        phases = [
            InitPhase.BOOTSTRAP,
            InitPhase.PLATFORM, 
            InitPhase.CORE_ENGINE,
            InitPhase.INTEGRATION,
            InitPhase.INTERFACE,
            InitPhase.ACTIVATION
        ]
        
        for phase in phases:
            success = self._initialize_phase(phase)
            if not success and self._phase_is_required(phase):
                self.logger.error(f"[INIT_MANAGER] PHASE_FAILED: {phase.value} failed, aborting")
                return False
                
        return True
    
    def _initialize_phase(self, phase: InitPhase) -> bool:
        """Initialize all components in a phase"""
        if phase not in self.components:
            return True  # No components in this phase
            
        self.logger.info(f"[INIT_MANAGER] PHASE_START: {phase.value}")
        
        for component in self.components[phase]:
            try:
                # Validate dependencies
                missing_deps = component.validate_dependencies(self.context)
                if missing_deps:
                    error = InitializationError(
                        phase=phase,
                        component=component.component_name,
                        error_type=ErrorType.FATAL,
                        message=f"Missing required dependencies: {missing_deps}",
                        user_guidance="Please check installation and requirements"
                    )
                    self.errors.append(error)
                    return False
                
                # Initialize component
                self.logger.info(f"[INIT_MANAGER] COMPONENT_INIT: {component.component_name}")
                result = component.initialize(self.context)
                
                # Store result in context for other components
                setattr(self.context, component.component_name.lower().replace('-', '_'), result)
                
            except Exception as e:
                error = InitializationError(
                    phase=phase,
                    component=component.component_name,
                    error_type=self._classify_error(e, component),
                    message=str(e),
                    recovery_action=self._get_recovery_action(e, component),
                    user_guidance=self._get_user_guidance(e, component)
                )
                self.errors.append(error)
                
                if error.error_type == ErrorType.FATAL:
                    return False
                    
        self.logger.info(f"[INIT_MANAGER] PHASE_COMPLETE: {phase.value}")
        return True
    
    def _phase_is_required(self, phase: InitPhase) -> bool:
        """Check if phase is required for basic functionality"""
        required_phases = {InitPhase.BOOTSTRAP, InitPhase.CORE_ENGINE}
        return phase in required_phases
    
    def _classify_error(self, error: Exception, component: ComponentInitializer) -> ErrorType:
        """Classify error based on component and error type"""
        # This would contain specific logic for different error types
        if "CUDA" in str(error) or "cuda" in str(error):
            return ErrorType.RECOVERABLE  # Can fallback to CPU
        elif "PyQt" in str(error):
            return ErrorType.FATAL  # GUI framework required
        else:
            return ErrorType.DEGRADED  # Assume graceful degradation possible
    
    def _get_recovery_action(self, error: Exception, component: ComponentInitializer) -> Optional[str]:
        """Get automatic recovery action for error"""
        if "CUDA" in str(error):
            return "fallback_to_cpu"
        return None
    
    def _get_user_guidance(self, error: Exception, component: ComponentInitializer) -> Optional[str]:
        """Get user-friendly guidance for error"""
        if "CUDA" in str(error):
            return "GPU error detected. Application will continue using CPU mode. Consider restarting after suspend/resume cycles."
        elif "pydbus" in str(error):
            return "Sleep monitoring unavailable. CUDA protection during suspend/resume may not work."
        return None
```

### Migration Strategy

1. **Start with critical fixes** (Items 1-2 above) - these are low risk, high impact
2. **Add dependency validation** (Item 3) - improves diagnostics immediately  
3. **Gradually migrate to framework** - wrap existing components in ComponentInitializer
4. **Test extensively** - each component migration should be thoroughly tested
5. **Keep rollback option** - maintain ability to use old initialization during transition

## Benefits

This refactoring will solve the persistent ordering issues by:

1. **Enforcing correct initialization order** through dependency management
2. **Enabling early error notification** through early system tray creation  
3. **Preventing silent failures** through comprehensive dependency validation
4. **Providing consistent error recovery** through standardized patterns
5. **Making debugging easier** through structured error reporting

The phased approach allows implementing critical fixes immediately while working toward the full architectural improvement over time.