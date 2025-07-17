# chess_analysis_project/views/dashboard/kpi_card_widget.py
"""
Defines a specialized, reusable card for displaying a single KPI.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from views.shared.card_widget import CardWidget

class KpiCardWidget(CardWidget):
    """A specialized CardWidget for displaying a main value and a delta."""
    
    def __init__(self, title: str, parent: QWidget | None = None):
        # Call the base class constructor. It sets up the title and content area.
        super().__init__(title, parent=parent)
        
        # Create the widgets specific to this KPI card
        self.value_label = QLabel("...")
        self.delta_label = QLabel(u"\u00A0") # Use non-breaking space for consistent alignment

        # Style these specific widgets
        value_font = self.value_label.font()
        value_font.setPointSize(28)
        value_font.setBold(True)
        self.value_label.setFont(value_font)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.delta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.delta_label.setTextFormat(Qt.TextFormat.RichText)

        # --- CORRECTED: Call the correct method from the parent class ---
        # Add the widgets to the content area provided by the CardWidget base class.
        self.add_widget_to_content(self.value_label, alignment=Qt.AlignmentFlag.AlignCenter, stretch=1)
        self.add_widget_to_content(self.delta_label, alignment=Qt.AlignmentFlag.AlignCenter)
        # The title is now handled by the base class, so we don't add it here.

        
    def update_value(self, value: float | None, delta: float | None = None, unit: str = ""):
        """Updates the card with a new value and calculates the delta display."""
        if value is None:
            self.value_label.setText("N/A")
            self.delta_label.setText("")
            return
            
        self.value_label.setText(f"{value:.1f}{unit}")
        
        if delta is None:
            self.delta_label.setText(u"\u00A0") # Non-breaking space for spacing
            return
            
        if delta > 0.01:
            arrow = u"\u25B2" # Up arrow
            color = "#2ECC71" # Green
            sign = "+"
        elif delta < -0.01:
            arrow = u"\u25BC" # Down arrow
            color = "#E74C3C" # Red
            sign = ""
        else:
            arrow = ""
            color = "#95A5A6" # Grey
            sign = ""
        
        delta_text = f"{sign}{delta:.1f}{unit}"
        self.delta_label.setText(f"<font color='{color}'>{arrow} {delta_text}</font>")
        self.delta_label.setToolTip(f"Change compared to previous 20 games")

    def update_record(self, wins: int, losses: int, draws: int):
        """Special method to update the W/L/D record card with colors."""
        self.value_label.setText(
            f"<font color='#2ECC71'>{wins}</font> / "
            f"<font color='#E74C3C'>{losses}</font> / "
            f"<font color='#F39C18'>{draws}</font>"
        )
        self.value_label.setTextFormat(Qt.TextFormat.RichText)
        self.delta_label.setText(u"\u00A0")