#!/usr/bin/env python3
"""
Test script to verify the code changes were implemented correctly.

This validates:
1. Sleep monitoring is enabled before CUDA validation in main.py
2. System tray is created early for notifications
3. Dependency validation is integrated

Run with: python test_code_changes.py
"""

import sys
import re
from pathlib import Path

def test_sleep_monitoring_before_cuda():
    """Test that sleep monitoring comes before CUDA validation in the code"""
    print("\n=== Testing Sleep Monitoring Before CUDA Validation ===")
    
    main_py = Path('src/witticism/main.py')
    if not main_py.exists():
        print("❌ main.py not found")
        return False
    
    content = main_py.read_text()
    lines = content.split('\n')
    
    sleep_monitor_line = None
    cuda_validation_line = None
    
    for i, line in enumerate(lines):
        if 'enable_sleep_monitoring' in line:
            sleep_monitor_line = i
        if 'validate_and_clean_cuda_at_startup' in line:
            cuda_validation_line = i
    
    if sleep_monitor_line is None:
        print("❌ Sleep monitoring call not found")
        return False
    
    if cuda_validation_line is None:
        print("❌ CUDA validation call not found") 
        return False
    
    if sleep_monitor_line < cuda_validation_line:
        print(f"✓ Sleep monitoring (line {sleep_monitor_line}) before CUDA validation (line {cuda_validation_line})")
        return True
    else:
        print(f"❌ Sleep monitoring (line {sleep_monitor_line}) after CUDA validation (line {cuda_validation_line})")
        return False

def test_early_system_tray():
    """Test that system tray is created early in initialization"""
    print("\n=== Testing Early System Tray Creation ===")
    
    main_py = Path('src/witticism/main.py')
    content = main_py.read_text()
    lines = content.split('\n')
    
    tray_early_line = None
    engine_init_line = None
    
    for i, line in enumerate(lines):
        if 'TRAY_EARLY_INIT' in line:
            tray_early_line = i
        if 'WhisperXEngine(' in line:
            engine_init_line = i
    
    if tray_early_line is None:
        print("❌ Early tray initialization not found")
        return False
    
    if engine_init_line is None:
        print("❌ Engine initialization not found")
        return False
    
    if tray_early_line < engine_init_line:
        print(f"✓ System tray created early (line {tray_early_line}) before engine (line {engine_init_line})")
        return True
    else:
        print(f"❌ System tray (line {tray_early_line}) not before engine (line {engine_init_line})")
        return False

def test_dependency_validation_first():
    """Test that dependency validation happens first"""
    print("\n=== Testing Dependency Validation First ===")
    
    main_py = Path('src/witticism/main.py')
    content = main_py.read_text()
    lines = content.split('\n')
    
    dependency_check_line = None
    tray_init_line = None
    
    for i, line in enumerate(lines):
        if 'DEPENDENCY_CHECK' in line:
            dependency_check_line = i
        if 'TRAY_EARLY_INIT' in line:
            tray_init_line = i
    
    if dependency_check_line is None:
        print("❌ Dependency check not found")
        return False
    
    if tray_init_line is None:
        print("❌ Tray initialization not found")
        return False
    
    if dependency_check_line < tray_init_line:
        print(f"✓ Dependency validation (line {dependency_check_line}) before tray init (line {tray_init_line})")
        return True
    else:
        print(f"❌ Dependency validation (line {dependency_check_line}) not before tray init (line {tray_init_line})")
        return False

def test_dependency_validator_exists():
    """Test that dependency validator file was created"""
    print("\n=== Testing Dependency Validator Exists ===")
    
    validator_py = Path('src/witticism/core/dependency_validator.py')
    if not validator_py.exists():
        print("❌ dependency_validator.py not found")
        return False
    
    content = validator_py.read_text()
    
    # Check for key classes and methods
    required_elements = [
        'class DependencyValidator',
        'def validate_all',
        'def has_fatal_issues',
        'def print_report',
        'DependencyType.REQUIRED',
        'DependencyResult'
    ]
    
    missing = []
    for element in required_elements:
        if element not in content:
            missing.append(element)
    
    if missing:
        print(f"❌ Missing elements in dependency validator: {missing}")
        return False
    
    print("✓ Dependency validator file exists with required functionality")
    return True

def test_adr_document_exists():
    """Test that ADR document was created"""
    print("\n=== Testing ADR Document Exists ===")
    
    adr_file = Path('docs/adr/001-component-initialization-architecture.md')
    if not adr_file.exists():
        print("❌ ADR document not found")
        return False
    
    content = adr_file.read_text()
    
    # Check for key sections
    required_sections = [
        '# ADR-001: Component Initialization Architecture',
        '## Context',
        '## Decision',
        '### Initialization Phases',
        '## Detailed Workflow Documentation',
        '### Developer Workflow',
        '### Operational Workflow',
        '### Troubleshooting Workflow'
    ]
    
    missing = []
    for section in required_sections:
        if section not in content:
            missing.append(section)
    
    if missing:
        print(f"❌ Missing sections in ADR: {missing}")
        return False
    
    print("✓ ADR document exists with comprehensive workflow documentation")
    return True

def test_late_tray_creation_removed():
    """Test that late system tray creation was removed from run() method"""
    print("\n=== Testing Late Tray Creation Removed ===")
    
    main_py = Path('src/witticism/main.py')
    content = main_py.read_text()
    
    # Look for the old pattern where tray was created late
    run_method_start = content.find('def run(self):')
    if run_method_start == -1:
        print("❌ run() method not found")
        return False
    
    # Get the run method content 
    run_method_content = content[run_method_start:content.find('\n    def ', run_method_start + 1)]
    
    if 'self.tray_app = SystemTrayApp()' in run_method_content:
        print("❌ Late tray creation still present in run() method")
        return False
    
    # Should have a comment about tray already being created
    if 'System tray already created early' in run_method_content:
        print("✓ Late tray creation removed, replaced with explanatory comment")
        return True
    else:
        print("⚠️  Late tray creation removed but no explanatory comment found")
        return True  # Still a success

def main():
    """Run all code validation tests"""
    print("Testing Critical Initialization Code Changes")
    print("=" * 50)
    
    tests = [
        test_dependency_validation_first,
        test_early_system_tray,
        test_sleep_monitoring_before_cuda,
        test_dependency_validator_exists,
        test_adr_document_exists,
        test_late_tray_creation_removed
    ]
    
    passed = 0
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                print(f"❌ Test {test.__name__} failed")
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
    
    print(f"\n{'=' * 50}")
    print(f"Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 All critical initialization code changes are correctly implemented!")
        print("\nKey improvements:")
        print("  - Dependency validation happens first to catch missing requirements")
        print("  - System tray created early for startup error notifications") 
        print("  - Sleep monitoring enabled BEFORE CUDA validation for proper protection")
        print("  - Comprehensive dependency validator with detailed reporting")
        print("  - Architecture Decision Record documenting workflow patterns")
        return 0
    else:
        print("💥 Some code changes are missing or incorrect")
        return 1

if __name__ == "__main__":
    sys.exit(main())