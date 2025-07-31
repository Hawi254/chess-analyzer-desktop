# chess_analysis_project/views/dashboard/opening_table_delegate.py
"""
Custom delegate for rendering cells in the Opening Performance table.
"""
from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

class OpeningTableDelegate(QStyledItemDelegate):
    """
    Handles custom painting for the Opening Performance QTableView,
    adding data bars and color scales to specific columns.
    """

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        """
        Overrides the default paint method to draw custom cell visuals.
        """
        # Ensure default selections and focus rectangles are drawn.
        super().paint(painter, option, index)

        # Column-specific drawing logic
        column = index.column()
        model = index.model()
        
        # --- Step 2: "Win %" Column - Data Bar ---
        # Assuming "Win %" is at column 2 (0-indexed: Name, Games, Win %)
        if column == 2: 
            # Retrieve the numeric win percentage value.
            # We use EditRole to get the raw number, not the formatted string.
            win_pct = model.data(index, Qt.ItemDataRole.EditRole)
            if isinstance(win_pct, (int, float)):
                # Define bar color
                bar_color = QColor(34, 139, 34, 100) # Semi-transparent forest green

                # Calculate the width of the data bar.
                bar_width = option.rect.width() * (win_pct / 100.0)
                
                # Create the rectangle for the bar.
                bar_rect = option.rect
                bar_rect.setWidth(bar_width)

                # Draw the bar.
                painter.fillRect(bar_rect, bar_color)

        # --- Step 2: "Avg. Accuracy" Column - Color Scale ---
        # Assuming "Avg. Accuracy" is at column 3
        if column == 3:
            # Retrieve the numeric accuracy value.
            accuracy = model.data(index, Qt.ItemDataRole.EditRole)
            if isinstance(accuracy, (int, float)):
                # Calculate the background color based on the value.
                cell_color = self._get_color_for_value(accuracy)
                
                # Fill the cell's background with the calculated color.
                painter.fillRect(option.rect, cell_color)
        
        # We must call the parent paint method again AFTER our custom background fill
        # to ensure the text and other elements are drawn on top.
        # But we must prevent it from drawing its own background again.
        option.state &= ~QStyle.StateFlag.State_HasFocus # Remove focus rect to avoid double draw
        option.backgroundBrush = QColor(0,0,0,0) # Make original background transparent
        super().paint(painter, option, index)


    def _get_color_for_value(self, value, min_val=50, max_val=100):
        """
        Maps a value to a color on a red-yellow-green gradient.
        Values below min_val are red, values above max_val are green.
        """
        # Clamp the value to the specified range.
        value = max(min_val, min(value, max_val))
        
        # Normalize the value to a 0-1 range.
        normalized = (value - min_val) / (max_val - min_val)

        # Linear interpolation from red (0) to green (1)
        # Hue: 0 is red, 120 is green. So we scale normalized value to hue.
        hue = normalized * 120
        
        color = QColor.fromHsvF(hue / 360.0, 0.7, 1.0)
        color.setAlpha(80) # Set a semi-transparent alpha
        return color