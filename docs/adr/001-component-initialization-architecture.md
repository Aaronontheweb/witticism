# ADR-001: Component Initialization Architecture

**Status:** Proposed  
**Date:** 2025-08-23  
**Context:** Addressing persistent ordering and dependency issues in application initialization

## Context

Witticism has experienced recurring issues with component initialization ordering that have led to:

1. **CUDA state corruption** - Sleep monitoring not active during CUDA validation at startup
2. **Silent failure cascades** - Missing dependencies causing components to fail quietly
3. **Notification timing issues** - System tray unavailable when startup errors occur
4. **Inconsistent error recovery** - Ad-hoc patterns for handling initialization failures
5. **Dependency coupling** - Implicit dependencies between components without clear contracts

### Root Cause Analysis

The current initialization follows a linear sequence without explicit dependency management:
```
Config → Engine → CUDA Validation → Models → Sleep Monitor → Audio → Pipeline → Tray → Connections
```

This creates several anti-patterns:
- **Critical components initialized too late** (system tray, sleep monitor)
- **Risky operations happening without safety nets** (CUDA validation before sleep monitor)  
- **No standardized error recovery** (each component handles failures differently)
- **Silent dependency failures** (missing PyGObject, DBus, etc.)

## Decision

We will implement a **Phase-Based Initialization Architecture** with explicit dependency management and standardized error handling patterns.

### Core Principles

1. **Explicit Dependencies** - Components declare their dependencies and initialization requirements
2. **Early Safety Nets** - Critical safety systems (tray notifications, sleep monitoring) available before risky operations
3. **Graceful Degradation** - Clear rules for when failures are fatal vs. recoverable
4. **Standardized Error Recovery** - Consistent patterns for fallback and recovery
5. **Dependency Validation** - Early detection and reporting of missing dependencies

### Initialization Phases

#### Phase 1: Bootstrap (Always Required)
- **Purpose**: Establish minimal runtime environment
- **Components**: Logging, configuration, singleton enforcement
- **Failure Handling**: Fatal - cannot continue
- **Dependencies**: None

#### Phase 2: Platform (Safety First)
- **Purpose**: Establish platform-specific safety and notification systems
- **Components**: Minimal system tray, sleep monitoring factory, dependency validation
- **Failure Handling**: Degrade gracefully with warnings
- **Dependencies**: PyQt5, platform libraries (optional)

#### Phase 3: Core Engine (Protected Initialization)  
- **Purpose**: Initialize compute engine with full error recovery context
- **Components**: WhisperX engine, CUDA validation, model loading
- **Failure Handling**: Automatic CPU fallback with user notification
- **Dependencies**: System tray (for notifications), sleep monitor (for CUDA protection)

#### Phase 4: Integration (Service Layer)
- **Purpose**: Initialize supporting services and pipelines
- **Components**: Audio capture, transcription pipeline, output management
- **Failure Handling**: Fatal for core services, degrade for optional features
- **Dependencies**: Engine, configuration

#### Phase 5: Interface (User Interaction)
- **Purpose**: Enable user interface and interaction systems
- **Components**: Hotkey management, full system tray functionality, UI connections
- **Failure Handling**: Degrade gracefully, maintain core functionality
- **Dependencies**: All previous phases

#### Phase 6: Activation (Service Start)
- **Purpose**: Start all services and enter operational mode
- **Components**: Service activation, final health checks, user notifications
- **Failure Handling**: Report issues but attempt to continue
- **Dependencies**: All previous phases

### Dependency Declaration Pattern

Components will declare dependencies using a standard interface:

```python
class ComponentInitializer:
    @property
    def required_dependencies(self) -> List[str]:
        """Components that must be available"""
        
    @property  
    def optional_dependencies(self) -> List[str]:
        """Components that enhance functionality but aren't required"""
        
    def validate_dependencies(self) -> DependencyResult:
        """Check if dependencies are available"""
        
    def initialize(self, context: InitializationContext) -> InitResult:
        """Initialize component with provided context"""
        
    def get_health_check(self) -> HealthCheck:
        """Provide ongoing health monitoring"""
```

### Error Recovery Patterns

#### Pattern 1: Fatal Errors (Bootstrap/Integration)
- Missing core dependencies (PyQt5, Python modules)
- Configuration corruption beyond repair
- Core service initialization failures

#### Pattern 2: Automatic Recovery (Core Engine)  
- CUDA failures → CPU fallback
- Model loading failures → Fallback model
- Network issues → Offline mode

#### Pattern 3: Graceful Degradation (Platform/Interface)
- Missing optional dependencies → Disable feature with notification
- UI failures → Continue with minimal interface
- Performance issues → Reduced functionality mode

### Standardized Error Reporting

All initialization errors follow this structure:
```python
@dataclass
class InitializationError:
    phase: InitPhase
    component: str
    error_type: ErrorType  # FATAL, RECOVERABLE, DEGRADED
    message: str
    recovery_action: Optional[str]
    user_guidance: Optional[str]
```

## Detailed Workflow Documentation

### Developer Workflow: Adding New Components

When adding a new component to Witticism, follow this standardized workflow:

#### Step 1: Determine Component Phase
```python
# Ask these questions to determine the correct phase:
# 1. Does this component provide safety/notification capabilities? → Phase 2 (Platform)
# 2. Does this component perform risky operations (CUDA, model loading)? → Phase 3 (Core Engine) 
# 3. Does this component integrate with other services? → Phase 4 (Integration)
# 4. Does this component provide user interaction? → Phase 5 (Interface)
# 5. Does this component start/activate services? → Phase 6 (Activation)
```

#### Step 2: Declare Dependencies
```python
class MyComponentInitializer(ComponentInitializer):
    @property
    def required_dependencies(self) -> List[str]:
        # CRITICAL: Components that MUST be available
        return ["config_manager", "system_tray"]  # Will fail initialization if missing
        
    @property  
    def optional_dependencies(self) -> List[str]:
        # OPTIONAL: Components that enhance functionality
        return ["sleep_monitor", "hotkey_manager"]  # Will degrade gracefully if missing
```

#### Step 3: Implement Initialization with Error Handling
```python
def initialize(self, context: InitializationContext) -> Any:
    """Initialize component following error handling patterns"""
    
    # Pattern 1: Validate Critical Dependencies
    if not hasattr(context, 'config_manager') or not context.config_manager:
        raise InitializationError(
            phase=self.phase,
            component=self.component_name,
            error_type=ErrorType.FATAL,
            message="ConfigManager is required but not available",
            user_guidance="This indicates a critical system error. Please restart the application."
        )
    
    # Pattern 2: Handle Optional Dependencies Gracefully
    sleep_monitor = getattr(context, 'sleep_monitor', None)
    if not sleep_monitor:
        context.logger.warning(f"[{self.component_name}] Sleep monitoring unavailable - CUDA protection disabled")
        # Continue with reduced functionality
    
    # Pattern 3: Implement Risky Operations with Recovery
    try:
        # Risky operation (e.g., CUDA, model loading, network call)
        result = self._perform_risky_operation(context)
        
    except CudaError as e:
        # Automatic recovery for known error types
        context.logger.warning(f"[{self.component_name}] CUDA failed, falling back to CPU: {e}")
        result = self._fallback_to_cpu(context)
        
    except NetworkError as e:
        # Graceful degradation for network issues
        context.logger.info(f"[{self.component_name}] Network unavailable, enabling offline mode: {e}")
        result = self._enable_offline_mode(context)
        
    except Exception as e:
        # Unknown errors - provide clear guidance
        raise InitializationError(
            phase=self.phase,
            component=self.component_name,
            error_type=ErrorType.RECOVERABLE,  # or FATAL depending on component
            message=f"Unexpected error during initialization: {e}",
            recovery_action="restart_component",
            user_guidance="Try restarting the application. If this persists, check logs for details."
        )
    
    return result
```

#### Step 4: Add Health Monitoring (Future Enhancement)
```python
def get_health_check(self) -> HealthCheck:
    """Provide ongoing health monitoring for this component"""
    return HealthCheck(
        component=self.component_name,
        status=self._current_status(),
        last_check=datetime.now(),
        metrics=self._collect_metrics()
    )
```

### Operational Workflow: Handling Initialization Failures

#### For End Users:
```
1. Application fails to start
2. System tray shows clear error notification (if available)
3. Error message provides specific next steps:
   - "GPU error detected → Application running in CPU mode"
   - "Audio device unavailable → Check audio settings" 
   - "Critical system error → Restart required"
4. User can access diagnostics via tray menu
```

#### For Developers/Support:
```
1. Check structured logs for initialization sequence:
   [INIT_MANAGER] PHASE_START: platform
   [SYSTEM_TRAY] COMPONENT_INIT: creating early notification system
   [SLEEP_MONITOR] COMPONENT_INIT: enabling proactive suspend/resume detection
   [INIT_MANAGER] PHASE_COMPLETE: platform
   
2. Identify failed component and phase from error logs:
   [INIT_MANAGER] COMPONENT_FAILED: whisperx_engine in core_engine phase
   [WHISPERX_ENGINE] CUDA_ERROR: out of memory, falling back to CPU
   
3. Use error classification to determine severity:
   - FATAL → Application cannot continue, user must fix environment
   - RECOVERABLE → Application attempted automatic recovery
   - DEGRADED → Application continues with reduced functionality
```

### Configuration Workflow: Environment-Specific Settings

#### Development Environment
```python
# Force mock components for testing
WITTICISM_FORCE_MOCK_SLEEP=true
WITTICISM_DEV_MODE=true  # Enables additional logging and validation

# Skip optional dependencies
WITTICISM_SKIP_CUDA=true  # Force CPU mode
WITTICISM_SKIP_SLEEP_MONITOR=true  # Disable sleep monitoring
```

#### Production Environment  
```python
# Enable full error recovery
WITTICISM_ENABLE_AUTO_RECOVERY=true

# Configure dependency timeouts
WITTICISM_DEPENDENCY_TIMEOUT=10  # seconds to wait for optional dependencies

# Enable comprehensive health monitoring
WITTICISM_HEALTH_CHECK_INTERVAL=30  # seconds between health checks
```

#### CI/CD Environment
```python
# Use minimal component set for testing
WITTICISM_CI_MODE=true  # Automatically detected by initialization system

# Override platform detection
WITTICISM_FORCE_PLATFORM=mock  # Use mock implementations for all platform components
```

### Troubleshooting Workflow: Common Issues

#### Issue: "Application won't start after suspend/resume"
```
Root Cause: CUDA context corrupted during suspend, sleep monitor not active during startup
Solution Workflow:
1. Check logs for: [CUDA_VALIDATION] performing startup health check
2. Look for: [SLEEP_MONITOR] enabling proactive suspend/resume detection  
3. Verify order: Sleep monitor MUST be enabled BEFORE CUDA validation
4. Expected recovery: [CUDA_FALLBACK] switching to CPU mode
```

#### Issue: "Silent startup failures"  
```
Root Cause: Missing dependencies not properly detected and reported
Solution Workflow:
1. Check logs for: [DEPENDENCY] MISSING_REQUIRED or MISSING_OPTIONAL
2. Look for: [INIT_MANAGER] PHASE_FAILED messages
3. Verify: Each component properly declares its dependencies
4. Expected behavior: Clear error messages with user guidance
```

#### Issue: "Inconsistent initialization behavior"
```
Root Cause: Race conditions or timing-dependent initialization 
Solution Workflow:
1. Check logs for phase completion order
2. Verify: All phases complete before next phase starts
3. Look for: [INIT_MANAGER] PHASE_COMPLETE messages in correct order
4. Expected behavior: Deterministic initialization regardless of system timing
```

## Implementation Strategy

### Phase 1: Create initialization framework
1. Define `InitializationManager` with phase-based orchestration
2. Create `ComponentInitializer` interface and base classes
3. Implement dependency validation system

### Phase 2: Migrate existing components
1. Wrap existing initialization in `ComponentInitializer` implementations
2. Add explicit dependency declarations
3. Standardize error handling

### Phase 3: Add safety improvements
1. Early system tray initialization for notifications
2. Sleep monitor activation before any CUDA operations
3. Comprehensive dependency validation

### Phase 4: Enhanced error recovery
1. Implement automatic CPU fallback with proper notification
2. Add graceful degradation for optional features
3. Create user-friendly error guidance

## Consequences

### Positive
- **Eliminates ordering issues** - Dependencies enforced automatically
- **Improves error resilience** - Standardized recovery patterns
- **Better user experience** - Early notifications, clear error messages
- **Easier debugging** - Explicit dependency chains and error reporting
- **Future-proof architecture** - Easy to add new components with proper dependency management

### Negative
- **Increased complexity** - More infrastructure code
- **Migration effort** - Existing code needs refactoring
- **Learning curve** - Team needs to understand new patterns

### Risks
- **Over-engineering** - Framework could become too complex
- **Migration bugs** - Risk of introducing new issues during refactoring

### Mitigation
- **Incremental migration** - Wrap existing code first, refactor later
- **Comprehensive testing** - Test all initialization paths and failure modes
- **Clear documentation** - Document patterns and examples
- **Rollback plan** - Keep existing initialization as fallback during transition

## Monitoring

- **Initialization timing metrics** - Track phase completion times
- **Dependency failure rates** - Monitor which dependencies fail most often
- **Error recovery success** - Track automatic recovery effectiveness
- **User impact metrics** - Monitor startup success rates and user-reported issues

## Related ADRs

- ADR-002: Error Recovery and User Guidance (pending)
- ADR-003: Health Monitoring and Diagnostics (pending)