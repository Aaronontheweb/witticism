#!/usr/bin/env python3
"""Generate Witticism icon as PNG file."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from PyQt5.QtWidgets import QApplication
from witticism.ui.icon_utils import create_witticism_icon

def main():
    app = QApplication(sys.argv)
    
    # Generate icons at different sizes
    sizes = [16, 24, 32, 48, 64, 128, 256, 512]
    
    assets_dir = Path(__file__).parent.parent / "assets"
    assets_dir.mkdir(exist_ok=True)
    
    for size in sizes:
        icon = create_witticism_icon(size)
        pixmap = icon.pixmap(size, size)
        
        # Save as PNG
        filename = assets_dir / f"witticism_{size}x{size}.png"
        pixmap.save(str(filename), "PNG")
        print(f"Generated {filename}")
    
    # Also generate a main icon at 512x512
    main_icon = create_witticism_icon(512)
    main_pixmap = main_icon.pixmap(512, 512)
    main_filename = assets_dir / "witticism.png"
    main_pixmap.save(str(main_filename), "PNG")
    print(f"Generated {main_filename}")

if __name__ == "__main__":
    main()