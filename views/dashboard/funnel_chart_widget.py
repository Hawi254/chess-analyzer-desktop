# chess_analysis_project/views/dashboard/funnel_chart_widget.py
"""
Defines a custom QWidget for displaying a simple, horizontal funnel chart.
"""
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

class FunnelChartWidget(QWidget):
    """A widget that paints a horizontal performance funnel."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumHeight(100)
        self._data = {
            "Total Games": 0,
            "Advantage from Opening": 0,
            "Converted to Win": 0,
        }
        self._colors = [QColor("#3498DB"), QColor("#2ECC71"), QColor("#F1C40F")]

    def set_data(self, total_games: int, advantage_games: int, wins: int):
        """Updates the data for the funnel chart and triggers a repaint."""
        self._data["Total Games"] = total_games
        self._data["Advantage from Opening"] = advantage_games
        self._data["Converted to Win"] = wins
        self.update() # Schedule a repaint

    def paintEvent(self, event):
        """Custom paint event to draw the funnel."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        total_games = self._data["Total Games"]
        if total_games == 0:
            painter.setPen(QPen(self.palette().color(self.foregroundRole())))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Awaiting Game Analysis...")
            return
        
        w = self.width()
        h = self.height()
        padding = 10
        
        # Draw each trapezoid segment of the funnel
        max_height = h - 2 * padding
        
        # Segment 1: Total Games
        path1 = QPainterPath()
        path1.moveTo(padding, padding)
        path1.lineTo(w - padding, padding)
        path1.lineTo(w - padding, h - padding)
        path1.lineTo(padding, h - padding)
        path1.closeSubpath()
        painter.fillPath(path1, self._colors[0])
        
        # Segment 2: Advantage Games
        if total_games > 0:
            adv_ratio = self._data["Advantage from Opening"] / total_games
            adv_height = max_height * adv_ratio
            adv_y_offset = (max_height - adv_height) / 2
            path2 = QPainterPath()
            path2.moveTo(padding, padding + adv_y_offset)
            path2.lineTo(w - padding, padding)
            path2.lineTo(w - padding, h - padding)
            path2.lineTo(padding, padding + max_height - adv_y_offset)
            path2.closeSubpath()
            painter.fillPath(path2, self._colors[1])
        
        # Segment 3: Converted Wins
        if self._data["Advantage from Opening"] > 0:
            win_ratio = self._data["Converted to Win"] / self._data["Advantage from Opening"]
            win_height = adv_height * win_ratio
            win_y_offset = (max_height - win_height) / 2
            path3 = QPainterPath()
            path3.moveTo(padding, padding + win_y_offset)
            path3.lineTo(w - padding, padding + adv_y_offset)
            path3.lineTo(w - padding, padding + max_height - win_y_offset)
            path3.lineTo(padding, padding + max_height - win_y_offset)
            path3.closeSubpath()
            painter.fillPath(path3, self._colors[2])
            
        # Draw labels
        painter.setPen(QPen(Qt.GlobalColor.black))
        painter.drawText(QRect(padding, padding, w - 2*padding, h - 2*padding), Qt.AlignmentFlag.AlignCenter, 
                         f"Total: {self._data['Total Games']}\n"
                         f"Advantage: {self._data['Advantage from Opening']}\n"
                         f"Converted: {self._data['Converted to Win']}")