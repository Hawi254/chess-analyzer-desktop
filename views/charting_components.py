# chess_analysis_project/views/charting_components.py
"""
Defines reusable, custom components for use in charting and visualizations.
"""
from datetime import datetime
import pyqtgraph as pg

class DateAxis(pg.AxisItem):
    """A custom axis for displaying dates on a pyqtgraph plot."""
    def tickStrings(self, values, scale, spacing):
        """Converts timestamps to formatted date strings for axis labels."""
        # This check prevents crashing if no ticks are visible
        if not values:
            return []
        try:
            return [datetime.fromtimestamp(value).strftime('%Y-%m-%d') for value in values]
        except (ValueError, TypeError):
            # Gracefully handle cases where values might not be valid timestamps
            return ['' for _ in values]