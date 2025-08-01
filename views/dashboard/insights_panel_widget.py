from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea
from PySide6.QtCore import Qt

class InsightsPanelWidget(QWidget):
    """
    A widget to display a list of insights.
    """
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(5)
        self.layout.setAlignment(Qt.AlignTop)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(5)
        self.content_layout.setAlignment(Qt.AlignTop)

        self.scroll_area.setWidget(self.content_widget)
        self.layout.addWidget(self.scroll_area)

        self.update_insights([]) # Initialize with no insights

    def update_insights(self, insights: list[str]):
        """
        Updates the displayed insights.
        """
        # Clear existing insights
        for i in reversed(range(self.content_layout.count())):
            widget = self.content_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

        if not insights:
            no_insights_label = QLabel("No insights available for this period.")
            no_insights_label.setAlignment(Qt.AlignCenter)
            no_insights_label.setStyleSheet("color: #888; font-style: italic;")
            self.content_layout.addWidget(no_insights_label)
        else:
            for insight_text in insights:
                icon = ""
                if "Win" in insight_text or "Best" in insight_text or "positive" in insight_text:
                    icon = "🔥" # Positive trend/streak
                elif "Accuracy" in insight_text or "statistics" in insight_text or "avg" in insight_text:
                    icon = "📊" # General statistics
                elif "dips" in insight_text or "negative" in insight_text or "Worst" in insight_text:
                    icon = "📉" # Negative trend/dip
                else:
                    icon = "•" # Default bullet

                label = QLabel(f"{icon} {insight_text}") # Prepend icon
                label.setWordWrap(True)
                self.content_layout.addWidget(label)
        self.content_layout.addStretch()
