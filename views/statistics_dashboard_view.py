# chess_analysis_project/views/statistics_dashboard_view.py
"""
Defines the main container for the 'Player's Mind' statistics dashboard.
"""
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

# --- Import all three fully implemented view components ---
from views.dashboard.command_center_view import CommandCenterView
from views.dashboard.arsenal_view import ArsenalView
from views.dashboard.crucible_view import CrucibleView
from views.dashboard.performance_calendar_view import PerformanceCalendarView


class StatisticsDashboardView(QWidget):
    """
    A container widget that uses a QTabWidget to organize the various
    statistical views. It provides a clean API of slots for the MainWindow
    to delegate data to the correct child tab.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self._create_widgets()
        self._create_layout()
        # No internal signal connections are needed here, as the MainWindow,
        # acting as the top-level Presenter, orchestrates all interactions.

    def _create_widgets(self):
        """Create the main tab widget and instantiate the actual tab pages."""
        self.tab_widget = QTabWidget()

        # Instantiate the real, functional views for all tabs
        self.command_center_view = CommandCenterView()
        self.arsenal_view = ArsenalView()
        self.crucible_view = CrucibleView()
        self.performance_calendar_view = PerformanceCalendarView()
        
        # Add the functional views as tabs with user-friendly names
        self.tab_widget.addTab(self.command_center_view, "Command Center")
        self.tab_widget.addTab(self.arsenal_view, "Arsenal (Openings)")
        self.tab_widget.addTab(self.performance_calendar_view, "Performance Calendar")
        self.tab_widget.addTab(self.crucible_view, "Crucible (Decisions)")

    def _create_layout(self):
        """The main layout simply contains the tab widget."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0) # Use the full space of the parent
        main_layout.addWidget(self.tab_widget)

    def set_loading_state(self, is_loading: bool):
        """
        Sets the entire dashboard to a loading state by delegating
        the command to each of its child tab views.
        """
        for i in range(self.tab_widget.count()):
            view = self.tab_widget.widget(i)
            if hasattr(view, 'set_loading_state'):
                view.set_loading_state(is_loading)

    # --- Public Slots for Populating Child Views ---
    # These slots provide a clean, high-level API for the MainWindow to delegate data.

    def update_kpis(self, data: dict):
        """Delegates KPI data to the Command Center tab."""
        self.command_center_view.update_kpis(data)
    
    def plot_accuracy_trend(self, data: list):
        """Delegates trend data to the new Performance Calendar tab."""
        self.performance_calendar_view.plot_accuracy_trend(data)

    def update_opening_table(self, data: list):
        """Delegates opening performance data to the Arsenal tab."""
        self.arsenal_view.update_opening_table(data)
        
    def update_dissonance_panel(self, data: list):
        """Delegates cognitive dissonance data to the Arsenal tab."""
        self.arsenal_view.update_dissonance_panel(data)

    def update_blunder_reel(self, data: list):
        """Delegates blunder reel data to the Crucible tab."""
        self.crucible_view.update_blunder_reel(data)
