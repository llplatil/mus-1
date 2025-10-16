from pathlib import Path
from .qt import QPixmap, QPalette, QBrush, QColor, QPainter, Qt


def apply_watermark_background(widget):
    """Apply a grayscale, semi-transparent MUS1 logo watermark as the widget background."""
    try:
        logo_path = Path(__file__).parent / "themes" / "m1logo no background.png"
        pixmap = QPixmap(str(logo_path))
        if pixmap.isNull():
            _fallback_plain_background(widget)
            return

        image = pixmap.toImage()
        # Convert to grayscale and darken while preserving alpha
        for y in range(image.height()):
            for x in range(image.width()):
                pixel = QColor(image.pixel(x, y))
                alpha = pixel.alpha()
                if alpha > 0:
                    gray = int(0.299 * pixel.red() + 0.587 * pixel.green() + 0.114 * pixel.blue())
                    gray = max(0, int(gray * 0.5))
                    image.setPixelColor(x, y, QColor(gray, gray, gray, alpha))

        darkened_pixmap = QPixmap.fromImage(image)
        scaled_pixmap = darkened_pixmap.scaled(
            widget.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )

        transparent_pixmap = QPixmap(widget.size())
        transparent_pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(transparent_pixmap)
        painter.setOpacity(0.15)
        offset_x = (scaled_pixmap.width() - widget.width()) // 2
        offset_y = (scaled_pixmap.height() - widget.height()) // 2
        painter.drawPixmap(-offset_x, -offset_y, scaled_pixmap)
        painter.end()

        palette = widget.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(245, 245, 245))
        widget.setPalette(palette)
        widget.setAutoFillBackground(True)

        brush = QBrush(transparent_pixmap)
        palette.setBrush(QPalette.ColorRole.Window, brush)
        widget.setPalette(palette)
    except Exception:
        _fallback_plain_background(widget)


def _fallback_plain_background(widget):
    palette = widget.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor(245, 245, 245))
    widget.setPalette(palette)
    widget.setAutoFillBackground(True)


