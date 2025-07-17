# chess_analysis_project/views/shared/card_widget.py
"""
Defines a reusable 'Card' container widget with consistent styling.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QLabel,
                               QVBoxLayout, QWidget)

class CardWidget(QFrame):
    """
    A reusable QFrame styled as a modern card with a title and drop shadow,
    acting as a base container for dashboard components.
    """
    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        
        self.setObjectName("CardWidget")
        self.setStyleSheet("""
            #CardWidget {
                background-color: palette(window);
                border: 1px solid palette(mid);
                border-radius: 8px;
            }
        """)
        
        # --- DEFINITIVE FIX: Assign the layout to an instance attribute ---
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(15, 15, 15, 15)
        self._main_layout.setSpacing(10)
        
        self.title_label = None
        if title:
            self.title_label = QLabel(f"<b>{title}</b>")
            font = self.title_label.font()
            font.setPointSize(14)
            self.title_label.setFont(font)
            self._main_layout.addWidget(self.title_label, alignment=Qt.AlignmentFlag.AlignTop)

        self.content_widget = QFrame(self)
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 5, 0, 0)
        self._main_layout.addWidget(self.content_widget, stretch=1)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(2, 2)
        self.setGraphicsEffect(shadow)

    def add_widget_to_content(self, widget: QWidget, stretch: int = 0, alignment=Qt.AlignmentFlag.AlignLeft):
        """Public method for subclasses to add widgets to the card's content area."""
        self.content_layout.addWidget(widget, stretch, alignment)

    def replace_title_widget(self, new_widget: QWidget):
        """Replaces the default title QLabel with a custom widget."""
        if self.title_label:
            # This line will now work correctly
            self._main_layout.replaceWidget(self.title_label, new_widget)
            self.title_label.deleteLater()
            self.title_label = new_widget