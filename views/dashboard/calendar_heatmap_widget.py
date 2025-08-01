"""
Defines a custom widget to display a calendar-style heatmap of performance.
"""
import calendar
from datetime import date, timedelta

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QToolTip, QWidget


class CalendarHeatmapWidget(QWidget):
    """A widget that paints a GitHub-style daily heatmap of performance."""

    # --- REWORKED: Signal is now generic for any time period ---
    period_clicked = Signal(list)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumHeight(180)
        self.setMouseTracking(True)

        # Data is now generic: {'date_key': {'metric_value': X, 'game_count': Y, 'game_ids': [...]}}
        self._data = {}
        self._granularity = "Weekly"
        self._metric_name = "Accuracy"
        # Maps a QRect to a specific day's data for tooltips and clicks
        self._cell_rects = {}

        # --- NEW: User-defined color scale for performance tiers ---
        self._color_scale = [
            QColor("#EBEDEF"),  # No data
            QColor("#A93226"),  # Very Low: Dark, desaturated red
            QColor("#2980B9"),  # Medium: Rich, standard blue
            QColor("#A9DFBF"),  # Good: Pleasant, light green
            QColor("#1E8449"),  # Excellent: Strong, dark green
        ]
        self._font = QFont("Arial", 8)
        self._month_font = QFont("Arial", 9)

    # --- REWORKED: Method now accepts context from the view ---
    def set_data(self, data: dict, granularity: str, metric_name: str):
        """Sets the data for the heatmap and triggers a repaint."""
        self._data = data
        self._granularity = granularity
        self._metric_name = metric_name
        self.update()

    def paintEvent(self, event):
        """Draws the entire calendar heatmap based on a rolling 53-week period."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        if not self._data:
            painter.setFont(self._font)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Awaiting Game Analysis...")
            return

        self._cell_rects.clear()

        # Define grid geometry
        x_offset = 30  # Space for day labels
        y_offset = 25  # Space for month labels
        legend_height = 15 # Approximate height for the legend area

        # --- REWORKED: Calculate cell size based on both width and height ---
        # This ensures the heatmap scales correctly and doesn't overflow.
        available_width = self.width() - x_offset
        available_height = self.height() - y_offset - legend_height
        
        # We have 53 columns (weeks) and 7 rows (days)
        cell_size_by_width = available_width / 53
        cell_size_by_height = available_height / 7
        
        cell_size = min(cell_size_by_width, cell_size_by_height)

        # --- Corrected Drawing Logic: Rolling 53-Week Period ---
        today = date.today()
        # Start from the Sunday of the current week to align columns properly
        start_date = today - timedelta(days=today.weekday() + 1)
        # Go back 52 more weeks to get a total of 53 columns
        start_date -= timedelta(weeks=52)

        month_positions = {}

        # Iterate through 53 weeks (columns) and 7 days (rows)
        for week_index in range(53):
            # Track the current month to draw labels
            first_day_of_week = start_date + timedelta(weeks=week_index)
            month = first_day_of_week.month
            if month not in month_positions:
                month_positions[month] = week_index

            for day_index in range(7):
                current_date = start_date + timedelta(weeks=week_index, days=day_index)
                
                # Skip drawing days that are in the future
                if current_date > today:
                    continue

                # --- REWORKED: Dynamic key generation based on granularity ---
                if self._granularity == "Weekly":
                    iso_year, iso_week, _ = current_date.isocalendar()
                    date_key = f"{iso_year}-{iso_week:02d}"
                elif self._granularity == "Monthly":
                    date_key = current_date.strftime('%Y-%m')
                else: # Daily
                    date_key = current_date.strftime('%Y-%m-%d')
                
                period_data = self._data.get(date_key)

                metric_value = period_data.get('metric_value') if period_data else None
                game_count = period_data.get('game_count', 0) if period_data else 0
                color = self._get_color_for_metric_value(metric_value, game_count)
                
                painter.setBrush(color)
                painter.setPen(Qt.PenStyle.NoPen)

                cell_x = x_offset + week_index * cell_size
                cell_y = y_offset + day_index * cell_size

                cell_rect = QRect(int(cell_x), int(cell_y), int(cell_size - 2), int(cell_size - 2))
                painter.drawRoundedRect(cell_rect, 2, 2)
                
                # Store rect with data for this specific day for interactivity
                self._cell_rects[cell_rect] = (current_date, date_key, period_data)

        # Find the column for "Today" and draw a faint vertical line
        today_week_index = -1
        for week_idx in range(53):
            current_date_in_loop = start_date + timedelta(weeks=week_idx)
            if current_date_in_loop.year == today.year and current_date_in_loop.month == today.month and current_date_in_loop.day == today.day:
                today_week_index = week_idx
                break
        
        if today_week_index != -1:
            # Draw "TODAY" label
            today_label = "TODAY"
            painter.setFont(self._font) # Use the regular font for this
            painter.setPen(self.palette().text().color()) # Use text color

            # Calculate position for the label above the column
            label_x = x_offset + today_week_index * cell_size + (cell_size / 2) - (painter.fontMetrics().horizontalAdvance(today_label) / 2)
            label_y = y_offset - 15 # A bit above the cells

            painter.drawText(int(label_x), int(label_y), today_label)


        self._draw_day_labels(painter, y_offset, cell_size)
        self._draw_month_labels(painter, x_offset, cell_size, month_positions)
        self._draw_legend(painter)

    def mousePressEvent(self, event):
        """Handles clicks on a day cell and emits the data for the entire period."""
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            for rect, (_, date_key, period_data) in self._cell_rects.items():
                if rect.contains(pos):
                    # Emit all game IDs for the period if data exists
                    if period_data and 'games' in period_data:
                        self.period_clicked.emit(period_data['games'], date_key)
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Shows a tooltip when hovering over a cell."""
        pos = event.position().toPoint()
        # --- REWORKED: Use generic variable names ---
        for rect, (current_date, date_key, period_data) in self._cell_rects.items():
            if rect.contains(pos):
                if period_data:
                    # --- REWORKED: Dynamic tooltip text ---
                    metric_value = period_data.get('metric_value', 0.0)
                    tooltip_text = (f"<b>{current_date.strftime('%A, %b %d, %Y')}</b><br>"
                                    f"Period: {date_key}<br>"
                                    f"Games in Period: {period_data['game_count']}<br>"
                                    f"{self._metric_name}: {metric_value:.1f}%")
                else:
                    tooltip_text = f"<b>{current_date.strftime('%A, %b %d, %Y')}</b><br>No games played"
                QToolTip.showText(self.mapToGlobal(pos), tooltip_text, self)
                return
        QToolTip.hideText()


    def _draw_day_labels(self, painter: QPainter, y_offset: float, cell_size: float):
        """Draws 'Mon', 'Wed', 'Fri' on the left."""
        painter.setFont(self._font)
        painter.setPen(self.palette().text().color())
        day_labels = ["Mon", "", "Wed", "", "Fri", "", ""]
        for i, label in enumerate(day_labels):
            if label:
                painter.drawText(
                    QRect(0, int(y_offset + i * cell_size), 25, int(cell_size)),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    label
                )
    
    def _draw_month_labels(self, painter: QPainter, x_offset: float, cell_size: float, month_positions: dict):
        """Draws month labels above the heatmap."""
        painter.setFont(self._month_font)
        painter.setPen(self.palette().text().color())
        for month, week_index in month_positions.items():
            cell_x = x_offset + week_index * cell_size
            painter.drawText(
                int(cell_x), 0, int(cell_size * 4), 20,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                calendar.month_abbr[month]
            )

    def _draw_legend(self, painter: QPainter):
        """Draws the color scale legend at the bottom right of the widget."""
        legend_y = self.height() - 15
        legend_cell_size = 10
        legend_spacing = 2
        current_x = self.width() - 10

        painter.setFont(self._font)
        painter.setPen(self.palette().text().color())

        fm = painter.fontMetrics()
        more_label = "More"
        more_width = fm.horizontalAdvance(more_label)
        current_x -= more_width
        painter.drawText(QPoint(current_x, legend_y), more_label)
        current_x -= 5

        for i in range(len(self._color_scale) - 1, 0, -1):
            color = self._color_scale[i]
            current_x -= legend_cell_size
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRect(current_x, legend_y - legend_cell_size, legend_cell_size, legend_cell_size), 2, 2)
            current_x -= legend_spacing

        less_label = "Less"
        current_x -= 5
        current_x -= fm.horizontalAdvance(less_label)
        painter.drawText(QPoint(current_x, legend_y), less_label)

    def _get_color_for_metric_value(self, metric_value: float | None, game_count: int) -> QColor:
        """
        Maps a metric value to color hue and game count to opacity (alpha).
        This dual-encoding allows visualizing both performance and activity level.
        """
        if metric_value is None or game_count == 0:
            return self._color_scale[0]  # Return the 'no data' color

        # 1. Determine base color from metric value using the defined thresholds
        if self._metric_name == "Accuracy":
            if metric_value < 40:
                base_color = self._color_scale[1]
            elif metric_value < 65:
                base_color = self._color_scale[2]
            elif metric_value < 85:
                base_color = self._color_scale[3]
            else:
                base_color = self._color_scale[4]
        elif self._metric_name == "Win Rate":
            if metric_value < 40:
                base_color = self._color_scale[1] # Red for low win rate
            elif metric_value < 60:
                base_color = self._color_scale[2] # Blue for ~50% win rate
            elif metric_value < 75:
                base_color = self._color_scale[3] # Light green for good win rate
            else:
                base_color = self._color_scale[4] # Dark green for excellent win rate
        else:
            # Default case if a new metric is added without defining thresholds
            base_color = self._color_scale[2]

        # 2. Determine opacity from game count to represent density
        min_opacity = 80   # Fairly transparent for a single game
        max_opacity = 255  # Fully opaque for many games

        max_games_for_full_opacity = 10  # At this many games, the cell is solid

        # Linearly interpolate opacity on a scale from 1 to max_games_for_full_opacity
        if game_count >= max_games_for_full_opacity:
            opacity = max_opacity
        else:
            # Clamp game_count to our scale (at least 1)
            clamped_count = max(1, game_count)
            # The formula for linear interpolation: y = y1 + (x - x1) * (y2 - y1) / (x2 - x1)
            opacity = min_opacity + (clamped_count - 1) * (max_opacity - min_opacity) / (max_games_for_full_opacity - 1)

        # Create a new color object from the base and apply the calculated alpha
        final_color = QColor(base_color)
        final_color.setAlpha(int(opacity))

        return final_color