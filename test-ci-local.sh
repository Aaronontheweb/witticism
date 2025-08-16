#!/bin/bash
# Test CI checks locally before pushing

echo "🧪 Testing CI checks locally..."
echo

# 1. Syntax check
echo "1️⃣ Checking Python syntax..."
find src -name "*.py" -type f | xargs python3 -m py_compile 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Syntax check passed"
else
    echo "❌ Syntax errors found"
    exit 1
fi
echo

# 2. Version check
echo "2️⃣ Checking version import..."
PYTHONPATH=src python3 -c "from witticism import __version__; print(f'✅ Version: {__version__}')"
if [ $? -ne 0 ]; then
    echo "❌ Version import failed"
    exit 1
fi
echo

# 3. pyproject.toml validation
echo "3️⃣ Validating pyproject.toml..."
python3 -c "import tomllib; tomllib.load(open('pyproject.toml', 'rb')); print('✅ pyproject.toml is valid')"
if [ $? -ne 0 ]; then
    echo "❌ pyproject.toml is invalid"
    exit 1
fi
echo

# 4. Check for obvious import errors
echo "4️⃣ Checking for import errors..."
PYTHONPATH=src python3 -c "
import sys
sys.path.insert(0, 'src')
errors = []
modules = [
    'witticism',
    'witticism.core.config_manager',
    'witticism.ui.system_tray',
    'witticism.utils.output_manager'
]
for module in modules:
    try:
        __import__(module)
        print(f'  ✓ {module}')
    except ImportError as e:
        if 'torch' in str(e) or 'whisperx' in str(e) or 'PyQt5' in str(e):
            print(f'  ⚠️  {module} (missing ML/GUI deps - OK for CI)')
        else:
            print(f'  ❌ {module}: {e}')
            errors.append(module)
if errors:
    sys.exit(1)
"
echo

echo "✅ All CI checks passed locally!"
echo "   Safe to push to GitHub"