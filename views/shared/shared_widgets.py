# chess_analysis_project/views/shared/card_widget.py
"""
Defines shared, reusable custom Qt widgets for the application.
"""
from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QLabel,
                               QStackedLayout, QVBoxLayout, QWidget, QToolButton,
                               QSplitter, QStackedWidget, QSizePolicy)

class ExpandingStackedWidget(QStackedWidget):
    """A QStackedWidget that correctly hints its size based on the current widget."""
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setSizePolicy(policy)
        self.currentChanged.connect(self.updateGeometry)

    def sizeHint(self) -> QSize:
        return self.currentWidget().sizeHint() if self.currentWidget() else super().sizeHint()

    def minimumSizeHint(self) -> QSize:
        return self.currentWidget().minimumSizeHint() if self.currentWidget() else super().minimumSizeHint()

class StretchySplitter(QSplitter):
    """A QSplitter that does not collapse its children, allowing for flexible layouts."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setChildrenCollapsible(False)

class CardWidget(QFrame):
    """
    A state-aware card that can be optionally collapsed and can display a
    loading message, an empty message, or its main content widget.
    """
    def __init__(self, title: str, collapsible: bool = False, start_expanded: bool = True, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("CardWidget")
        self.setStyleSheet("""
            #CardWidget {
                background-color: palette(window);
                border: 1px solid palette(midlight);
                border-radius: 8px;
            }

        """)
        # self.setMinimumHeight(150) # Removed to allow parent layouts to control minimum height

        self._is_collapsible = collapsible
        
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(12, 8, 12, 8) # Adjusted top/bottom padding
        self._main_layout.setSpacing(8)

        # The content_area holds the widgets added by the user of this card.
        self._title_widget = self._create_title_widget(title, start_expanded)
        
        self._stack = QStackedLayout()
        self.message_label = QLabel()
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message_label.setWordWrap(True)
        self._stack.addWidget(self.message_label)
        self.content_area = QWidget()
        self._stack.addWidget(self.content_area)

        self._main_layout.addWidget(self._title_widget)
        self._main_layout.addLayout(self._stack, stretch=1)

        if self._is_collapsible:
            self._animation = QPropertyAnimation(self.content_area, b"maximumHeight")
            self._animation.finished.connect(self._on_animation_finished)
            self.toggle_button.clicked.connect(self._toggle_content)
            if not start_expanded:
                self.content_area.setVisible(False)
                self.content_area.setMaximumHeight(0)

        self._apply_effects()
        self.show_loading()

    def _create_title_widget(self, title: str, start_expanded: bool) -> QWidget:
        if self._is_collapsible:
            self.toggle_button = QToolButton()
            self.toggle_button.setStyleSheet("QToolButton { border: none; font-weight: bold; }")
            self.toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            self.toggle_button.setArrowType(Qt.ArrowType.DownArrow if start_expanded else Qt.ArrowType.RightArrow)
            self.toggle_button.setText(title)
            self.toggle_button.setCheckable(True)
            self.toggle_button.setChecked(start_expanded)
            font = self.toggle_button.font()
            font.setPointSize(14)
            self.toggle_button.setFont(font)
            return self.toggle_button
        else:
            label = QLabel(f"<b>{title}</b>")
            font = label.font()
            font.setPointSize(14)
            label.setFont(font)
            return label

    def _toggle_content(self, checked: bool):
        self.toggle_button.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)

        # If expanding, make the content area visible immediately so its size can be calculated.
        if checked:
            self.content_area.setVisible(True)

        self._animation.setDuration(300)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._animation.setStartValue(self.content_area.height())
        self._animation.setEndValue(self.content_area.sizeHint().height() if checked else 0)
        self._animation.start()

    def _on_animation_finished(self):
        """Hides the content area only after it has fully collapsed."""
        if self.content_area.height() == 0:
            self.content_area.setVisible(False)

    def set_content_layout(self, layout: QVBoxLayout):
        old_layout = self.content_area.layout()
        if old_layout:
            QWidget().setLayout(old_layout)
        self.content_area.setLayout(layout)

    def set_content(self, widget: QWidget):
        """A convenience method to set a single widget as the card's content."""
        # This helper encapsulates the layout management for a single widget.
        new_layout = QVBoxLayout()
        new_layout.setContentsMargins(0, 0, 0, 0)
        new_layout.addWidget(widget)

        old_layout = self.content_area.layout()
        if old_layout:
            QWidget().setLayout(old_layout) # Properly dispose of the old layout
        self.content_area.setLayout(new_layout)

    def show_loading(self):
        self.message_label.setText("Loading...")
        self.message_label.setStyleSheet("color: palette(placeholder-text);")
        self._stack.setCurrentWidget(self.message_label)

    def show_message(self, text: str):
        self.message_label.setText(text)
        self._stack.setCurrentWidget(self.message_label)

    def show_content(self):
        self._stack.setCurrentWidget(self.content_area)

    def _apply_effects(self):
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 70))
        shadow.setOffset(2, 2)
        self.setGraphicsEffect(shadow)

    def set_title(self, new_title: str):
        """Allows for dynamically updating the card's title."""
        # The title widget can be either a QToolButton or a QLabel.
        # Both of them have a setText() method.
        # We need to handle the bolding for the QLabel case.
        
        if self._is_collapsible:
            # For the QToolButton, we just set its text.
            self.toggle_button.setText(new_title)
        else:
            # For the QLabel, we need to find it and set its text with bold tags.
            # We can find it because it's the direct child of the main layout.
            title_widget = self._main_layout.itemAt(0).widget()
            if isinstance(title_widget, QLabel):
                title_widget.setText(f"<b>{new_title}</b>")