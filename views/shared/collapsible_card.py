# chess_analysis_project/views/shared/collapsible_card.py
"""
Defines a reusable 'Card' container widget that can be collapsed and expanded.
"""
from PySide6.QtCore import (QEasingCurve, QPropertyAnimation, QParallelAnimationGroup,
                          Qt, Signal)
from PySide6.QtWidgets import (QFrame, QScrollArea, QToolButton,
                               QVBoxLayout, QWidget)

from views.shared.card_widget import CardWidget

class CollapsibleCardWidget(CardWidget):
    """
    A CardWidget that contains a toggle button to expand or collapse its
    content area with a smooth animation.
    """
    def __init__(self, title: str, start_expanded: bool = True, parent: QWidget | None = None):
        super().__init__(title, parent)

        self.toggle_button = QToolButton()
        self._setup_ui(start_expanded)
        self._create_animation()
        # --- CORRECTED: Add the missing method definition before calling it ---
        self._connect_signals()

    def _setup_ui(self, start_expanded: bool):
        """Sets up the toggle button and configures the content area."""
        self.toggle_button.setStyleSheet("QToolButton { border: none; font-weight: bold; }")
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.ArrowType.DownArrow if start_expanded else Qt.ArrowType.RightArrow)
        
        original_title = self.title_label.text() if self.title_label else ""
        self.toggle_button.setText(original_title)
        
        font = self.toggle_button.font()
        font.setPointSize(14)
        self.toggle_button.setFont(font)

        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(start_expanded)

        self.replace_title_widget(self.toggle_button)
        
        if not start_expanded:
            self.content_widget.setVisible(False)

    def _create_animation(self):
        """Creates the animation for expanding and collapsing the content."""
        self.animation = QPropertyAnimation(self.content_widget, b"maximumHeight")
        self.animation.setDuration(300)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad)

    # --- CORRECTED: The missing method is now implemented ---
    def _connect_signals(self):
        """Connects the toggle button to the animation logic."""
        self.toggle_button.clicked.connect(self.toggle_content)

    def toggle_content(self, checked: bool):
        """Toggles the visibility of the content area with an animation."""
        arrow_type = Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
        self.toggle_button.setArrowType(arrow_type)
        
        # Determine the content's natural height to animate towards
        content_height = self.content_widget.sizeHint().height()
        
        start_value = self.content_widget.height()
        end_value = content_height if checked else 0
        
        # If expanding, make it visible before the animation starts
        if checked:
            self.content_widget.setVisible(True)

        self.animation.setStartValue(start_value)
        self.animation.setEndValue(end_value)
        self.animation.start()
        
        # If collapsing, hide it after the animation finishes
        if not checked:
            # Use a separate connection to avoid conflicts
            def hide_on_finish():
                self.content_widget.setVisible(False)
                # Disconnect to prevent this from running on the next animation
                try:
                    self.animation.finished.disconnect(hide_on_finish)
                except (TypeError, RuntimeError):
                    pass
            self.animation.finished.connect(hide_on_finish)