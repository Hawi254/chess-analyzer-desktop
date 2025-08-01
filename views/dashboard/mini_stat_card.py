from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt

class MiniStatCard(QFrame):
    """
    A small card widget to display a single statistic with an optional mini-sparkline.
    """
    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)
        self.setContentsMargins(5, 5, 5, 5)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(2)

        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("font-size: 10px; color: #555;")
        self.layout.addWidget(self.title_label)

        self.value_label = QLabel("N/A")
        self.value_label.setAlignment(Qt.AlignCenter)
        self.value_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.layout.addWidget(self.value_label)

        # Placeholder for mini-sparkline
        self.sparkline_placeholder = QLabel("Mini-Sparkline")
        self.sparkline_placeholder.setAlignment(Qt.AlignCenter)
        self.sparkline_placeholder.setStyleSheet("border: 1px dashed #eee; background-color: #f9f9f9; font-size: 8px;")
        self.sparkline_placeholder.setMinimumHeight(30)
        self.layout.addWidget(self.sparkline_placeholder)

    def set_value(self, value: str):
        self.value_label.setText(value)

    def set_sparkline_data(self, data: list):
        # This would eventually render a small sparkline chart
        if data:
            self.sparkline_placeholder.setText(f"Sparkline ({len(data)} pts)")
        else:
            self.sparkline_placeholder.setText("No data")
