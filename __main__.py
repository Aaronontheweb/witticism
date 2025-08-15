#!/usr/bin/env python3
"""
Entry point for running witticism as a module or with uvx.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from witticism.main import main

if __name__ == "__main__":
    main()