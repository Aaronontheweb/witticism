from PyQt5.QtGui import QIcon, QPixmap, QPainter, QFont, QColor
from PyQt5.QtCore import Qt


def create_witticism_icon(size: int = 64, color: str = "green") -> QIcon:
    """Create the Witticism icon programmatically.

    Args:
        size: Icon size in pixels
        color: Icon color ("green", "red", "yellow", "gray", "orange")

    Returns:
        QIcon: The generated icon
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # Map color names to QColor
    color_map = {
        "green": QColor(76, 175, 80),
        "red": QColor(244, 67, 54),
        "yellow": QColor(255, 193, 7),
        "gray": QColor(158, 158, 158),
        "orange": QColor(255, 152, 0)
    }

    # Calculate circle dimensions based on size
    margin = size // 8
    circle_size = size - (2 * margin)

    # Background circle
    painter.setBrush(color_map.get(color, QColor(76, 175, 80)))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(margin, margin, circle_size, circle_size)

    # Text
    painter.setPen(Qt.white)
    font_size = size // 3
    font = QFont("Arial", font_size, QFont.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "W")

    painter.end()

    return QIcon(pixmap)
