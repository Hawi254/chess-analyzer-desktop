# chess_analysis_project/desktop_app.py
"""
The main entry point and Presenter for the Chess Analyzer Desktop application.
"""
import os
import sys

import structlog
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QApplication, QFileDialog, QVBoxLayout, QMainWindow,
                               QStackedWidget, QWidget, QToolBar, QMessageBox)

from app_controller import AppController
from chess_analyzer.config.settings import settings
from chess_analyzer.services.database_manager import DatabaseManager
from chess_analyzer.utils.qt_logging import QLogEmitter
from chess_analyzer.types import RunReport
from state.app_state import AppState
from views.annotated_game_view import AnnotatedGameView
from views.game_report_view import GameReportView
from views.run_analysis_view import RunAnalysisView
from views.statistics_dashboard_view import StatisticsDashboardView
from views.shared.custom_widgets import ExpandingStackedWidget


logger = structlog.get_logger(__name__)


class MainWindow(QMainWindow):
    """The main application window, acting as a container and presenter."""

    def __init__(self, log_emitter: QLogEmitter):
        super().__init__()
        self.setWindowTitle("Chess Analyzer")
        self.setGeometry(100, 100, 1200, 800)
        
        self.log_emitter = log_emitter

        self.db_manager = DatabaseManager(settings.default_db_path)
        self.db_manager.initialize_db()

        self.app_state = AppState()
        self.controller = AppController(self.app_state, self.db_manager)
        
        self._create_toolbar()

        main_container = QWidget()
        self.setCentralWidget(main_container)
        central_layout = QVBoxLayout(main_container)
        central_layout.setContentsMargins(0, 0, 0, 0)

        # --- CORRECTED: Use our new ExpandingStackedWidget ---
        self.stacked_widget = ExpandingStackedWidget()
        central_layout.addWidget(self.stacked_widget)
        # ---------------------------------------------------
        
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
        
        self._setup_connections()
        self._load_settings()
        
        logger.info("Application initialized.", show_in_gui=True)
    
    def _create_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)
        
        action_run = QAction("Run Analysis", self)
        action_run.triggered.connect(lambda: self.stacked_widget.setCurrentWidget(self.run_analysis_view))
        toolbar.addAction(action_run)
        
        action_report = QAction("Game Report", self)
        action_report.triggered.connect(lambda: self.stacked_widget.setCurrentWidget(self.game_report_view))
        toolbar.addAction(action_report)
        
        action_stats = QAction("Dashboard", self)
        action_stats.triggered.connect(self._on_dashboard_requested)
        toolbar.addAction(action_stats)

    def _setup_connections(self):
        """Connect signals from views to controller and from controller to views."""
        # UI Actions -> Presenter/Controller Logic
        self.run_analysis_view.start_analysis_requested.connect(self._handle_start_request)
        self.run_analysis_view.cancel_analysis_requested.connect(self._handle_cancel_request)
        self.run_analysis_view.browse_button.clicked.connect(self._browse_for_files)
        self.run_analysis_view.status_update_requested.connect(self.statusBar().showMessage)

        # Backend Progress -> Presenter Logic
        self.controller.progress.connect(self._on_progress_update)
        self.controller.finished.connect(self._on_analysis_finished)
        self.controller.error.connect(self._on_analysis_error)
        
        # State Changes & Navigation
        self.app_state.results_updated.connect(self._on_results_updated)
        self.app_state.game_selected.connect(self._on_game_selected)
        self.game_report_view.game_selected.connect(self.app_state.select_game)
        self.annotated_game_view.back_requested.connect(self._on_back_to_report)

        # Logging
        self.log_emitter.log_generated.connect(self.run_analysis_view.append_log_message)

        # Dashboard Data Delegation & Interactivity
        cc_view = self.statistics_dashboard.command_center_view
        arsenal_view = self.statistics_dashboard.arsenal_view
        crucible_view = self.statistics_dashboard.crucible_view

        self.controller.kpi_data_ready.connect(cc_view.update_kpis)
        self.controller.trend_data_ready.connect(cc_view.plot_accuracy_trend)
        self.controller.funnel_data_ready.connect(cc_view.update_performance_funnel)
        self.controller.opening_table_ready.connect(arsenal_view.update_opening_table)
        self.controller.dissonance_data_ready.connect(arsenal_view.update_dissonance_panel)
        self.controller.decision_matrix_data_ready.connect(crucible_view.plot_decision_matrix)
        self.controller.tactical_signature_data_ready.connect(crucible_view.plot_tactical_signature)
        self.controller.blunder_reel_data_ready.connect(crucible_view.update_blunder_reel)

        arsenal_view.dissonance_data_requested.connect(self.controller.request_dissonance_data)
        cc_view.game_selected.connect(self.app_state.select_game)
        crucible_view.game_selected_with_ply.connect(self._on_game_and_ply_selected)
    
    def _load_settings(self):
        settings_store = QSettings("ChessAnalyzerOrg", "ChessAnalyzerDesktop")
        self.run_analysis_view.username_input.setText(settings_store.value("user/player_name", ""))
        self.run_analysis_view.depth_spinbox.setValue(settings_store.value("analysis/depth", 11, type=int))
        self.run_analysis_view.multipv_spinbox.setValue(settings_store.value("analysis/multipv", 3, type=int))
        last_file = settings_store.value("paths/last_pgn_file", "")
        if last_file and os.path.exists(last_file):
            self.run_analysis_view.file_list_widget.addItem(last_file)

    def _save_settings(self):
        settings_store = QSettings("ChessAnalyzerOrg", "ChessAnalyzerDesktop")
        settings_store.setValue("user/player_name", self.run_analysis_view.username_input.text())
        settings_store.setValue("analysis/depth", self.run_analysis_view.depth_spinbox.value())
        settings_store.setValue("analysis/multipv", self.run_analysis_view.multipv_spinbox.value())
        if self.run_analysis_view.file_list_widget.count() > 0:
            settings_store.setValue("paths/last_pgn_file", self.run_analysis_view.file_list_widget.item(0).text())

    def _on_progress_update(self, current: int, total: int):
        self.run_analysis_view.update_progress(current, total)
        self.statusBar().showMessage(f"Analyzing game {current} of {total}...")

    def _on_dashboard_requested(self):
        self.stacked_widget.setCurrentWidget(self.statistics_dashboard)
        # In Phase 4, these filters would be read from UI controls on the dashboard.
        filters = {"time_control": None, "color": None}
        self.controller.request_statistics_update(filters)
        
    def _handle_start_request(self, config: dict):
        self.run_analysis_view.set_ui_for_analysis(is_running=True)
        self.controller.start_analysis(config)

    def _handle_cancel_request(self):
        logger.warning("Cancel request received from user.", show_in_gui=True)
        self.controller.cancel_analysis()
    
    def _browse_for_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Open PGN Files", "", "PGN Files (*.pgn);;All Files (*)")
        self.run_analysis_view.file_list_widget.clear()
        if file_paths:
            self.run_analysis_view.file_list_widget.addItems(file_paths)

    def _on_analysis_finished(self, report: RunReport): # Type hint is now correct
        """
        Handles the completed analysis run, checking the report for warnings.
        The `report` argument is now a fully reconstructed RunReport instance.
        """
        # --- The code here is now simpler and more robust ---
        self.run_analysis_view.set_ui_for_analysis(is_running=False)
        self.statusBar().showMessage(f"Analysis complete. Processed {report.processed_game_count} games.", 10000)

        # Check for user not found warning
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
        
        # In the future, we could iterate through report.warnings here as well.

    def _on_results_updated(self):
        self.stacked_widget.setCurrentWidget(self.game_report_view)
        
    def _on_game_selected(self, game_id: str):
        self.stacked_widget.setCurrentWidget(self.annotated_game_view)

    def _on_game_and_ply_selected(self, game_id: str, ply: int):
        self.app_state.select_game(game_id)
        # Using a zero-delay timer is a robust way to ensure the view switch happens
        # before the ply selection signal is processed.
        QTimer.singleShot(0, lambda: self.app_state.select_ply(ply))
        self.stacked_widget.setCurrentWidget(self.annotated_game_view)
        
    def _on_back_to_report(self):
        self.stacked_widget.setCurrentWidget(self.game_report_view)

    def _on_analysis_error(self, error_message: str):
        self.run_analysis_view.set_ui_for_analysis(is_running=False)
        logger.error("Analysis failed.", error=error_message, show_in_gui=True)
        self.statusBar().showMessage(f"Error: {error_message}", 10000) # Show error for 10s

    def closeEvent(self, event):
        logger.info("Close event received. Shutting down services...")
        self._save_settings()
        self.controller.shutdown_workers()
        self.db_manager.shutdown()
        super().closeEvent(event)