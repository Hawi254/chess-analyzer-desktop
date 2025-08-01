# chess_analysis_project/views/dashboard/performance_calendar_view.py
"""
Defines the "Performance Calendar" tab for the main statistics dashboard.
"""
import json
from PySide6.QtCore import Slot, Signal, Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox,
                               QListWidget, QListWidgetItem, QPushButton, QFrame)
import structlog

from views.dashboard.calendar_heatmap_widget import CalendarHeatmapWidget
from views.shared.shared_widgets import CardWidget, StretchySplitter
from views.dashboard.trend_summary_card import TrendSummaryCard
from views.dashboard.insights_panel_widget import InsightsPanelWidget

logger = structlog.get_logger(__name__)

# ====================================================================================
# Main Performance Calendar View Class
# ====================================================================================

class PerformanceCalendarView(QWidget):
    """The UI for the Performance Calendar tab."""
    game_selected = Signal(str) # Emits game_id when a game in the list is double-clicked
    data_requested = Signal(dict) # Emits filter dictionary when filters change

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._create_widgets()
        self._create_layout()
        self._connect_signals()
        self._set_initial_messages() # Set initial messages for cards

    def _set_initial_messages(self):
        """Set initial messages for cards and panels on startup."""
        self.game_list_card.show_message("Click a period on the calendar to see games.")
        self.insights_panel_card.show_message("No insights to display.")
        self.trend_summary_card.avg_acc_card.set_value("N/A")
        self.trend_summary_card.games_card.set_value("N/A")
        self.trend_summary_card.best_streak_card.set_value("N/A")
        self.trend_summary_card.worst_week_card.set_value("N/A")
        self.trend_summary_card.avg_acc_card.set_sparkline_data([])
        self.trend_summary_card.games_card.set_sparkline_data([])
        self.trend_summary_card.best_streak_card.set_sparkline_data([])
        self.trend_summary_card.worst_week_card.set_sparkline_data([])

    def _create_widgets(self):
        """Instantiate UI widgets."""
        # --- Filter Controls ---
        self.date_range_combo = QComboBox()
        self.date_range_combo.addItems(["All Time", "Last 6 Months", "Last 3 Months"])
        self.date_range_combo.setMinimumContentsLength(10) # Ensure consistent width
        self.date_range_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)

        self.granularity_combo = QComboBox()
        self.granularity_combo.addItems(["Weekly", "Daily", "Monthly"]) # Weekly is default
        self.granularity_combo.setMinimumContentsLength(10) # Ensure consistent width
        self.granularity_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)

        self.metric_combo = QComboBox()
        self.metric_combo.addItems(["Accuracy", "Win Rate"])
        self.metric_combo.setMinimumContentsLength(10) # Ensure consistent width
        self.metric_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)

        self.settings_button = QPushButton("⚙ Settings")
        self.settings_button.setFlat(True) # Make it look like a text button

        # --- Main Content Widgets ---
        self.splitter = StretchySplitter(Qt.Orientation.Horizontal)
        self.trend_summary_card = TrendSummaryCard()
        self.trend_summary_card.setMinimumHeight(120) # Set minimum height

        self.calendar_heatmap = CalendarHeatmapWidget()
        self.calendar_heatmap.setMinimumHeight(200) # Set minimum height
        
        self.game_list_card = CardWidget("Games") # Initial title
        self.game_list_widget = QListWidget()
        self.game_list_card.set_content(self.game_list_widget)

        self.insights_panel_widget = InsightsPanelWidget()
        self.insights_panel_card = CardWidget("Insights")
        self.insights_panel_card.set_content(self.insights_panel_widget)

    def _create_layout(self):
        """Arrange widgets in the layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # --- Filter Bar ---
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10) # Add some spacing between the group and the settings button

        # Group the combo boxes with subtle separators
        filter_group_layout = QHBoxLayout()
        filter_group_layout.setSpacing(0)
        filter_group_layout.setContentsMargins(0, 0, 0, 0)

        filter_group_layout.addWidget(self.date_range_combo)
        # Use a QFrame as a subtle vertical separator
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.Shape.VLine)
        separator1.setFrameShadow(QFrame.Shadow.Sunken)
        filter_group_layout.addWidget(separator1)
        filter_group_layout.addWidget(self.granularity_combo)
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.VLine)
        separator2.setFrameShadow(QFrame.Shadow.Sunken)
        filter_group_layout.addWidget(separator2)
        filter_group_layout.addWidget(self.metric_combo)
        filter_group_layout.addWidget(self.settings_button) # Move settings button here

        filter_layout.addStretch() # Push everything to the right
        filter_layout.addLayout(filter_group_layout)

        # --- Main Content Layout ---
        # Create a vertical splitter for the main content areas
        self.vertical_splitter = StretchySplitter(Qt.Orientation.Vertical)
        self.trend_summary_card.setMinimumHeight(120)
        self.calendar_heatmap.setMinimumHeight(200)

        # Bottom section: Games List and Insights Panel in a splitter
        self.bottom_splitter = StretchySplitter(Qt.Orientation.Horizontal)
        self.game_list_card.setMinimumHeight(100)
        self.insights_panel_card.setMinimumHeight(100)
        self.bottom_splitter.addWidget(self.game_list_card)
        self.bottom_splitter.addWidget(self.insights_panel_card)
        # Remove setSizes, use stretch for proportional sizing
        self.bottom_splitter.setStretchFactor(0, 1)
        self.bottom_splitter.setStretchFactor(1, 1)

        self.vertical_splitter.addWidget(self.trend_summary_card)
        self.vertical_splitter.addWidget(self.calendar_heatmap)
        self.vertical_splitter.addWidget(self.bottom_splitter)
        self.vertical_splitter.setStretchFactor(0, 1) # Trend & Summary
        self.vertical_splitter.setStretchFactor(1, 2) # Calendar Heatmap
        self.vertical_splitter.setStretchFactor(2, 1) # Bottom Splitter

        main_layout.addLayout(filter_layout)
        main_layout.addWidget(self.vertical_splitter) # Add the main vertical splitter

    def _connect_signals(self):
        """Connect widget signals to handler slots."""
        self.calendar_heatmap.period_clicked.connect(self._on_period_clicked)
        self.game_list_widget.itemDoubleClicked.connect(
            lambda item: self.game_selected.emit(item.data(Qt.ItemDataRole.UserRole))
        )
        self.date_range_combo.currentIndexChanged.connect(self._on_filter_changed)
        self.granularity_combo.currentIndexChanged.connect(self._on_filter_changed)
        self.metric_combo.currentIndexChanged.connect(self._on_filter_changed)

    @Slot(list, str)
    def _on_period_clicked(self, games: list, date_key: str):
        """Handles a click on the calendar, populating the game list with rich info."""
        self.game_list_widget.clear()
        if not games:
            self.game_list_card.show_message("No games in this period.")
            self.insights_panel_card.show_message("No insights for this period.")
            self.game_list_card.set_title(f"Games in {date_key}")
            self.insights_panel_card.set_title(f"Insights for {date_key}")
            return

        for game_data in games:
            game_id = game_data.get('game_id')
            opponent_rating = game_data.get('opponent_rating', '????')
            result = game_data.get('result')
            player_color = game_data.get('player_color')

            # Determine win/loss/draw from the player's perspective
            if result == '1/2-1/2':
                result_str = "Draw"
            elif (result == '1-0' and player_color == 'White') or \
                 (result == '0-1' and player_color == 'Black'):
                result_str = "Win"
            else:
                result_str = "Loss"

            display_text = f"vs Opponent ({opponent_rating}) - {result_str}"
            
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, game_id) # Store the ID for navigation
            self.game_list_widget.addItem(item)

        self.game_list_card.set_title(f"Games in {date_key}")
        self.game_list_card.show_content()
        # Insights panel will be updated by plot_accuracy_trend or another signal
        self.insights_panel_card.set_title(f"Insights for {date_key}")
        self.insights_panel_card.show_content()

    @Slot()
    def _on_filter_changed(self):
        """Gathers current filter settings and emits a signal to request new data."""
        self.data_requested.emit(self.get_current_filters())

    def get_current_filters(self) -> dict:
        """
        Returns the current filter settings from the calendar view. This provides a
        public API for the presenter to get the view's state without coupling.
        """
        date_range = self.date_range_combo.currentText()
        return {
            "date_range": date_range if date_range != "All Time" else None,
            "granularity": self.granularity_combo.currentText(),
            "metric": self.metric_combo.currentText()
        }

    @Slot(bool)
    def set_loading_state(self, is_loading: bool):
        """Sets the view to a loading state."""
        # A more robust implementation might use a QStackedWidget or overlay
        self.setEnabled(not is_loading)
        if is_loading:
            self.calendar_heatmap.set_data({}, "Weekly", "Accuracy") # Clear the calendar
            self.game_list_card.show_loading()

    @Slot(list)
    def plot_accuracy_trend(self, data: list):
        # --- REWORKED: This slot is now generic for any trend data ---
        logger.debug("PerformanceCalendarView received trend data.", item_count=len(data))
        
        if not data:
            self.calendar_heatmap.set_data({}, "Weekly", "Accuracy") # Reset with defaults
            self.game_list_card.show_message("No data for this period.")
            self.trend_summary_card.avg_acc_card.set_value("N/A")
            self.trend_summary_card.games_card.set_value("N/A")
            self.trend_summary_card.best_streak_card.set_value("N/A")
            self.trend_summary_card.worst_week_card.set_value("N/A")
            self.trend_summary_card.avg_acc_card.set_sparkline_data([])
            self.trend_summary_card.games_card.set_sparkline_data([])
            self.trend_summary_card.best_streak_card.set_sparkline_data([])
            self.trend_summary_card.worst_week_card.set_sparkline_data([])
            self.set_loading_state(False)
            return

        # The backend now returns a generic 'date_key' and 'metric_value'.
        # We now parse the games_json string into a list of dicts.
        heatmap_data = {}
        sparkline_data = []
        total_games = 0
        total_metric_value = 0
        
        for item in data:
            if date_key := item.get('date_key'):
                games_list = json.loads(item.get('games_json', '[]'))
                metric_value = item.get('metric_value', 0)
                num_games = len(games_list)

                heatmap_data[date_key] = {**item, 'games': games_list}
                sparkline_data.append(metric_value)
                total_games += num_games
                total_metric_value += metric_value * num_games # Assuming metric_value is an average for the period

        # Calculate average accuracy (simple average for now, can be weighted later)
        avg_accuracy = (total_metric_value / total_games) if total_games > 0 else 0
        
        # Placeholder for best streak and worst week - these would require more complex logic
        best_streak = "N/A"
        worst_week = "N/A"

        # Get current filter settings to pass to the widget for context
        filters = self.get_current_filters()
        granularity = filters.get("granularity", "Weekly")
        metric_name = filters.get("metric", "Accuracy")

        self.calendar_heatmap.set_data(heatmap_data, granularity, metric_name)
        self.game_list_card.show_message("Click a period on the calendar to see games.")
        self.trend_summary_card.avg_acc_card.set_value(f"{avg_accuracy:.1f}%")
        self.trend_summary_card.games_card.set_value(str(total_games))
        self.trend_summary_card.best_streak_card.set_value(best_streak)
        self.trend_summary_card.worst_week_card.set_value(worst_week)
        self.trend_summary_card.avg_acc_card.set_sparkline_data(sparkline_data)
        self.trend_summary_card.games_card.set_sparkline_data(sparkline_data)
        self.trend_summary_card.best_streak_card.set_sparkline_data(sparkline_data)
        self.trend_summary_card.worst_week_card.set_sparkline_data(sparkline_data)
        # Dummy insights for now
        dummy_insights = [
            "Win 80% as White on Mondays.",
            "Accuracy dips 5% on weekends.",
            "Best month: July (avg. 78%)."
        ]
        self.insights_panel_widget.update_insights(dummy_insights)
        self.set_loading_state(False)