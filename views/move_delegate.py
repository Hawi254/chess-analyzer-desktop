# chess_analysis_project/views/move_delegate.py
"""
Defines a custom delegate for rendering moves in the Annotated Game View.
"""
import re
from typing import Any, Dict

from PySide6.QtCore import QRect, Qt, QSize
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPixmap
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle

CLASSIFICATION_RE = re.compile(r"\{\[(.+?)\]\}")
ANALYSIS_RE = re.compile(r"\[Analyse(.+?)\]")

STYLE_DATA: Dict[str, Dict[str, Any]] = {
    "Brilliant": {"icon_path": ":/icon_brilliant", "color": QColor("#2ECC71")},
    "Great Move": {"icon_path": ":/icon_great", "color": QColor("#3498DB")},
    "Mistake": {"icon_path": ":/icon_mistake", "color": QColor("#F39C12")},
    "Blunder": {"icon_path": ":/icon_blunder", "color": QColor("#E74C3C")},
}

class MoveInfoDelegate(QStyledItemDelegate):
    """A delegate for drawing richly formatted move information in a QListWidget."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap_cache: Dict[str, QPixmap] = {}

        # --- CORRECTED: Instantiate and store fonts and metrics in __init__ for efficiency ---
        self._main_font = QFont()
        self._main_font.setBold(True)
        self._fm_main = QFontMetrics(self._main_font)

        self._engine_font = QFont("monospace", 9)
        self._fm_engine = QFontMetrics(self._engine_font)
        # -----------------------------------------------------------------------------------

    def _get_pixmap(self, path: str) -> QPixmap:
        """Lazy-loads a QPixmap from a resource path and caches it."""
        if path not in self._pixmap_cache:
            pixmap = QPixmap(path)
            if pixmap.isNull():
                print(f"Warning: Could not load pixmap from resource path: {path}")
            self._pixmap_cache[path] = pixmap
        return self._pixmap_cache[path]

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()
        
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        
        item_data = index.data(Qt.ItemDataRole.UserRole)
        if not item_data:
            painter.restore()
            return

        move_san = item_data.get("san", "")
        comment = item_data.get("comment", "")
        
        classification_match = CLASSIFICATION_RE.search(comment)
        classification = classification_match.group(1) if classification_match else None
        
        style = STYLE_DATA.get(classification, {})
        icon_path = style.get("icon_path")
        icon = self._get_pixmap(icon_path) if icon_path else None
        color = style.get("color", option.palette.text().color())
        
        padding = 5
        icon_size = 16 
        
        current_x = option.rect.x() + padding
        total_height = option.rect.height()
        content_y = option.rect.y()
        
        if icon and not icon.isNull():
            icon_y = content_y + (total_height - icon_size) / 2
            painter.drawPixmap(
                int(current_x), int(icon_y),
                icon.scaled(icon_size, icon_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )
            current_x += icon_size + padding
            
        analysis_match = ANALYSIS_RE.search(comment) 
        has_engine_line = bool(analysis_match)
        
        if has_engine_line:
            text_block_height = self._fm_main.height() + self._fm_engine.height() 
            text_y = content_y + (total_height - text_block_height) / 2 + self._fm_main.ascent()
        else:
            text_y = content_y + (total_height - self._fm_main.height()) / 2 + self._fm_main.ascent()

        painter.setFont(self._main_font)
        painter.setPen(color)
        painter.drawText(int(current_x), int(text_y), move_san)
        
        if has_engine_line:
            engine_text = f"[Analyse{analysis_match.group(1)}]" 
            engine_y = text_y + self._fm_engine.height()
            
            # --- CORRECTED: Use the stored font object directly ---
            painter.setFont(self._engine_font)
            painter.setPen(option.palette.text().color())
            painter.drawText(int(current_x), int(engine_y), engine_text)
            
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        item_data = index.data(Qt.ItemDataRole.UserRole)
        if not item_data:
            return super().sizeHint(option, index)

        # Calculate height needed for the text with word wrapping
        move_san = item_data.get("san", "")
        comment = item_data.get("comment", "")
        
        text_width = option.rect.width() - (4 * 5) # Approximate padding/icon width

        # Base height from the main move SAN
        main_rect = self._fm_main.boundingRect(QRect(0, 0, text_width, 0), Qt.TextFlag.TextWordWrap, move_san)
        total_height = main_rect.height()
        
        # Add height for engine analysis line if it exists
        analysis_match = ANALYSIS_RE.search(comment)
        if analysis_match:
            engine_text = f"[Analyse{analysis_match.group(1)}]"
            engine_rect = self._fm_engine.boundingRect(QRect(0, 0, text_width, 0), Qt.TextFlag.TextWordWrap, engine_text)
            total_height += engine_rect.height()

        return QSize(option.rect.width(), total_height + 10) # Add padding