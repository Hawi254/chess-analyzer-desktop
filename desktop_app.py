# chess_analysis_project/desktop_app.py
"""
The main entry point and Presenter for the Chess Analyzer Desktop application.
"""

import structlog
from typing import List, Optional

from PySide6.QtCore import QSettings, Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QFileDialog, QVBoxLayout, QMainWindow,
                               QWidget, QToolBar, QMessageBox)

from app_controller import AppController
from chess_analyzer.config.settings import settings
from chess_analyzer.services.database_manager import DatabaseManager
from chess_analyzer.types import GameReportRow, RunReport
from chess_analyzer.utils.qt_logging import QLogEmitter
from state.app_state import AppState
from views.annotated_game_view import AnnotatedGameView
from views.game_report_view import GameReportView, ReportDisplayState
from views.run_analysis_view import RunAnalysisView, UIState # Import the new state enum
from views.statistics_dashboard_view import StatisticsDashboardView
from views.shared.shared_widgets import ExpandingStackedWidget


logger = structlog.get_logger(__name__)


class MainWindow(QMainWindow):
    """The main application window, acting as a container and presenter."""

    def __init__(self, log_emitter: QLogEmitter, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Chess Analyzer")
        self.setGeometry(100, 100, 1200, 800)
        
        self.log_emitter = log_emitter

        self.db_manager = DatabaseManager(settings.default_db_path)
        self._pending_ply_selection: Optional[int] = None
        self.app_state = AppState()
        self.controller = AppController(self.app_state, self.db_manager)

        # --- CRITICAL: Connect signals BEFORE creating widgets that might rely on them ---
        self.db_manager.db_ready.connect(self._on_db_ready)
        self.db_manager.db_error.connect(self._on_db_error)
        
        self._create_toolbar()
        self.stacked_widget = ExpandingStackedWidget()
        
        main_container = QWidget()
        central_layout = QVBoxLayout(main_container)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.addWidget(self.stacked_widget)
        self.setCentralWidget(main_container)
        
        # Instantiate all views
        self.run_analysis_view = RunAnalysisView()
        self.game_report_view = GameReportView(self.app_state)
        self.annotated_game_view = AnnotatedGameView(self.app_state)
        self.statistics_dashboard = StatisticsDashboardView()
        
        # Add views to the stacked widget
        self.stacked_widget.addWidget(self.run_analysis_view)
        self.stacked_widget.addWidget(self.game_report_view)
        self.stacked_widget.addWidget(self.annotated_game_view)
        self.stacked_widget.addWidget(self.statistics_dashboard)
        
        # --- Set the initial UI state ---
        self.run_analysis_view.set_ui_state(UIState.INITIALIZING)
        
        self._setup_connections()
        self._load_settings()
        
        logger.info("Application initialized.", show_in_gui=True)

    @Slot()
    def _on_db_ready(self):
        """Slot to enable the UI once the database is confirmed ready."""
        self.statusBar().showMessage("Database ready.", 5000)
        self.run_analysis_view.set_ui_state(UIState.IDLE)

    @Slot(str)
    def _on_db_error(self, error_message: str):
        """Slot to handle and display database initialization errors."""
        self.statusBar().showMessage(f"Database Error: {error_message}", 0)
        QMessageBox.critical(
            self, "Database Initialization Failed",
            f"A critical error occurred while initializing the database:\n\n"
            f"{error_message}\n\n"
            "The application will not function correctly and will now close."
        )
        self.close()

    def _create_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)
        
        action_run = QAction("Run Analysis", self)
        action_run.triggered.connect(lambda: self.stacked_widget.setCurrentWidget(self.run_analysis_view))
        toolbar.addAction(action_run)
        
        action_report = QAction("Game Report", self)
        # --- MODIFIED: Connect to a dedicated handler method ---
        action_report.triggered.connect(self._on_game_report_requested)
        toolbar.addAction(action_report)
        
        action_stats = QAction("Dashboard", self)
        action_stats.triggered.connect(self._on_dashboard_requested)
        toolbar.addAction(action_stats)

    def _setup_connections(self):
        """Connect signals from views to controller and from controller to views."""
        # --- UI Actions -> Presenter/Controller Logic ---
        self.run_analysis_view.start_analysis_requested.connect(self._handle_start_request)
        self.run_analysis_view.cancel_analysis_requested.connect(self._handle_cancel_request)
        self.run_analysis_view.browse_button.clicked.connect(self._browse_for_files)
        self.run_analysis_view.status_update_requested.connect(self.statusBar().showMessage)

        # --- Backend Progress -> Presenter Logic ---
        self.controller.progress.connect(self._on_progress_update)
        self.controller.finished.connect(self._on_analysis_finished)
        self.controller.error.connect(self._on_analysis_error)
        
        # --- NEW: Connections for lazy-loading game report ---
        self.controller.initial_report_ready.connect(self._on_initial_report_ready)
        self.controller.report_page_ready.connect(self.game_report_view.game_report_model.append_data)
        self.game_report_view.game_report_model.more_data_requested.connect(self.controller.request_more_report_data)
        # --- NEW: Connection for loading a single game ---
        self.controller.game_data_loaded.connect(self._on_game_data_loaded)
        
        # --- State Changes & Navigation ---
        # --- REWORKED: Connect game selection to a new handler in the presenter ---
        self.game_report_view.game_selected.connect(self._on_game_selection_requested)
        self.annotated_game_view.back_requested.connect(self._on_back_to_report)

        # --- Logging ---
        self.log_emitter.log_generated.connect(self.run_analysis_view.append_log_message)

        # --- REFACTORED: Connect controller signals DIRECTLY to the dashboard view ---
        dashboard = self.statistics_dashboard
        self.controller.kpi_data_ready.connect(dashboard.update_kpis)
        self.controller.trend_data_ready.connect(dashboard.plot_accuracy_trend)
        self.controller.opening_table_ready.connect(dashboard.update_opening_table)
        self.controller.dissonance_data_ready.connect(dashboard.update_dissonance_panel)
        self.controller.blunder_reel_data_ready.connect(dashboard.update_blunder_reel)

        # Connect internal dashboard signals for navigation
        # --- REWORKED: Connect dashboard game selection to the main on-demand handler ---
        dashboard.command_center_view.filters_changed.connect(self.request_dashboard_update)
        dashboard.command_center_view.game_selected.connect(self._on_game_selection_requested)
        dashboard.crucible_view.game_selected_with_ply.connect(self._on_game_and_ply_selected)
        dashboard.arsenal_view.game_selected_with_ply.connect(self._on_game_and_ply_selected)
        dashboard.performance_calendar_view.data_requested.connect(self.request_dashboard_update)
        # --- NEW: Connect calendar game selection to the main handler ---
        dashboard.performance_calendar_view.game_selected.connect(self._on_game_selection_requested)
        # DECOUPLED: The presenter now intercepts the request to add full filter context.
        dashboard.arsenal_view.dissonance_data_requested.connect(self._on_dissonance_requested)

    def _load_settings(self):
        settings_store = QSettings("ChessAnalyzerOrg", "ChessAnalyzerDesktop")
        # DECOUPLED: Call a setter on the view.
        config = {
            "player_name": settings_store.value("user/player_name", ""),
            "depth": settings_store.value("analysis/depth", 11, type=int),
            "multipv": settings_store.value("analysis/multipv", 3, type=int),
            "last_file": settings_store.value("paths/last_pgn_file", "")
        }
        self.run_analysis_view.set_config(config)

    def _save_settings(self):
        settings_store = QSettings("ChessAnalyzerOrg", "ChessAnalyzerDesktop")
        # DECOUPLED: Call a getter on the view.
        config = self.run_analysis_view.get_config()
        settings_store.setValue("user/player_name", config.get("user_player_name"))
        settings_store.setValue("analysis/depth", config.get("depth"))
        settings_store.setValue("analysis/multipv", config.get("multipv"))
        if pgn_file := config.get("pgn_file"):
            settings_store.setValue("paths/last_pgn_file", pgn_file)

    def _on_progress_update(self, current: int, total: int):
        self.run_analysis_view.update_progress(current, total)
        self.statusBar().showMessage(f"Analyzing game {current} of {total}...")

    @Slot()
    def _on_dashboard_requested(self):
        """
        Switches to the dashboard view and triggers a data update.
        This method is triggered by the main toolbar action.
        """
        self.stacked_widget.setCurrentWidget(self.statistics_dashboard)
        self.request_dashboard_update()

    @Slot()
    def request_dashboard_update(self):
        """Gathers all filters and requests a statistics update from the controller."""
        # DECOUPLED: Call a getter on the view.
        player_name = self.run_analysis_view.get_player_name()
        if not player_name:
            QMessageBox.warning(self, "Player Name Required", "Please enter your player name on the 'Run Analysis' tab before viewing the dashboard.")
            self.stacked_widget.setCurrentWidget(self.run_analysis_view)
            return

        self.statistics_dashboard.set_loading_state(True)
        
        # DECOUPLED: Call the view's public method to get its filter state.
        dashboard_filters = self.statistics_dashboard.command_center_view.get_current_filters()
        calendar_filters = self.statistics_dashboard.performance_calendar_view.get_current_filters()

        all_filters = {
            "player_name": player_name,
            **dashboard_filters,
            **calendar_filters
        }
        logger.info("UI: Dashboard update requested with filters", filters=all_filters)
        self.controller.request_statistics_update(all_filters)
        
    # --- NEW: Handler for Game Report tab request ---
    def _on_game_report_requested(self):
        """Handles the request to view the game report, triggering a data load."""
        self.stacked_widget.setCurrentWidget(self.game_report_view)
        self.game_report_view.set_display_state(ReportDisplayState.LOADING)
        
        # The game report is always filtered by the currently configured player.
        player_name = self.run_analysis_view.get_player_name()
        if not player_name:
            QMessageBox.warning(self, "Player Name Required", "Please enter your player name on the 'Run Analysis' tab before viewing the game report.")
            self.stacked_widget.setCurrentWidget(self.run_analysis_view)
            return
            
        filters = {"player_name": player_name}
        page_size = self.game_report_view.game_report_model.FETCH_BATCH_SIZE
        self.controller.request_initial_game_report(filters, page_size)
        
    # --- NEW: Handler for when the initial page of report data is ready ---
    @Slot(dict, int, list)
    def _on_initial_report_ready(self, filters: dict, total_count: int, first_page_data: List[GameReportRow]):
        """
        Receives the initial data for the report, resets the model,
        and sets the final view state (content or empty).
        """
        model = self.game_report_view.game_report_model
        # Pass the filters to the model so it can use them for subsequent `fetchMore` requests.
        model.begin_new_report(total_count, filters)
        model.append_data(first_page_data)
        
        if total_count > 0:
            self.game_report_view.set_display_state(ReportDisplayState.CONTENT)
        else:
            self.game_report_view.set_display_state(ReportDisplayState.EMPTY)
            
    # --- NEW: Handler for when a game is selected in the report view ---
    @Slot(str)
    def _on_game_selection_requested(self, game_id: str):
        """Handles the request to view a single game, triggering an on-demand fetch."""
        self.stacked_widget.setCurrentWidget(self.annotated_game_view)
        self.annotated_game_view.set_display_state(AnnotatedGameView.DisplayState.LOADING)
        self.controller.request_annotated_game(game_id)

    # --- NEW: Handler for when the full game data has been loaded ---
    @Slot(object)
    def _on_game_data_loaded(self, game_object):
        """
        Receives the fully parsed game object, passes it to the AppState,
        and switches the AnnotatedGameView to show the content.
        """
        # Determine the initial ply. Default to 0 if no ply was pending.
        initial_ply = self._pending_ply_selection or 0
        
        # Atomically set the game and the correct initial ply in the AppState.
        # This prevents the UI from flashing to ply 0 first.
        self.app_state.set_current_game(game_object, initial_ply=initial_ply)
        
        # Now that the state is correct, show the content.
        self.annotated_game_view.set_display_state(AnnotatedGameView.DisplayState.CONTENT)
        
        # Clear the pending selection now that it has been used.
        self._pending_ply_selection = None
        
    def _handle_start_request(self, config: dict):
        self.run_analysis_view.set_ui_state(UIState.RUNNING)
        self.controller.start_analysis(config)

    def _handle_cancel_request(self):
        logger.warning("Cancel request received from user.", show_in_gui=True)
        self.controller.cancel_analysis()
    
    def _browse_for_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Open PGN Files", "", "PGN Files (*.pgn);;All Files (*)")
        self.run_analysis_view.file_list_widget.clear()
        if file_paths:
            self.run_analysis_view.file_list_widget.addItems(file_paths)

    def _on_analysis_finished(self, report: RunReport):
        """
        Handles the completed analysis run, checking the report for warnings.
        The `report` argument is now a RunReport instance.
        """
        self.run_analysis_view.set_ui_state(UIState.IDLE)
        self.statusBar().showMessage(f"Analysis complete. Processed {report.processed_game_count} games.", 10000)

        if report.processed_game_count > 0 and not report.user_found_in_games:
            user_name = self.run_analysis_view.username_input.text().strip()
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setWindowTitle("Player Name Not Found")
            msg_box.setText(f"The name \"{user_name}\" was not found in any of the analyzed games.")
            msg_box.setInformativeText(
                "The analysis is complete, but the statistics dashboard for this user will be empty. "
                "Please ensure the name exactly matches the 'White' or 'Black' tags in the PGN file (case is ignored)."
            )
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.exec()
        
        # --- NEW: Refresh the game report view with the new data ---
        self._on_game_report_requested()
        
    def _on_game_and_ply_selected(self, game_id: str, ply: int):
        logger.debug("Game and ply selection received by presenter.", game_id=game_id, ply=ply)
        self._pending_ply_selection = ply
        self._on_game_selection_requested(game_id)
        
    def _on_back_to_report(self):
        self.stacked_widget.setCurrentWidget(self.game_report_view)

    @Slot(int)
    def _on_dissonance_requested(self, opening_id: int):
        """
        Handles the request for cognitive dissonance data from the Arsenal view.
        This presenter method is responsible for assembling the complete filter
        context before calling the controller.
        """
        player_name = self.run_analysis_view.get_player_name()
        if not player_name:
            # This should ideally not happen if the dashboard is visible, but is a safe guard.
            return

        dashboard_filters = self.statistics_dashboard.command_center_view.get_current_filters()
        all_filters = {
            "player_name": player_name,
            **dashboard_filters
        }
        self.controller.request_dissonance_data(opening_id, all_filters)

    def _on_analysis_error(self, error_message: str):
        self.run_analysis_view.set_ui_state(UIState.IDLE)
        logger.error("Analysis failed.", error=error_message, show_in_gui=True)
        self.statusBar().showMessage(f"Error: {error_message}", 10000)

    def closeEvent(self, event):
        logger.info("Close event received. Shutting down services...")
        self._save_settings()
        self.controller.shutdown_workers()
        self.db_manager.shutdown()
        super().closeEvent(event)