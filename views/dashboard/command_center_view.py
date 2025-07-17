# chess_analysis_project/views/dashboard/command_center_view.py
"""
Defines the "Command Center" tab for the main statistics dashboard.
"""
from datetime import datetime
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QBrush, QPen
from PySide6.QtWidgets import (QGridLayout, QGroupBox, QLabel, QVBoxLayout,
                               QWidget, QHBoxLayout)

from views.charting_components import DateAxis
from views.dashboard.funnel_chart_widget import FunnelChartWidget
from views.shared.card_widget import CardWidget
from views.dashboard.kpi_card_widget import KpiCardWidget
from views.shared.collapsible_card import CollapsibleCardWidget

RESULT_COLOR_CODES = {
    "win": "#2ECC71",  # Green
    "loss": "#E74C3C", # Red
    "draw": "#F39C18", # Orange
}
DEFAULT_POINT_COLOR_CODE = "#1E90FF" # Dodger Blue

class CommandCenterView(QWidget):
    """The UI for the main 'Command Center' dashboard tab."""
    
    game_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')

        self._brush_cache = {}

        self._create_widgets()
        self._create_layout()

    def _create_widgets(self):
        """Instantiate all UI widgets and container cards for this view."""
        self.kpi_accuracy_card = KpiCardWidget("Overall Accuracy")
        self.kpi_record_card = KpiCardWidget("Record (W/L/D)")
        self.kpi_games_card = KpiCardWidget("Total Games")
        
        self.funnel_card = CollapsibleCardWidget("Performance Funnel", start_expanded=False)
        self.funnel_chart = FunnelChartWidget()
        # --- CORRECTED: Use the public API from the CardWidget base class ---
        self.funnel_card.add_widget_to_content(self.funnel_chart)

        self.trend_card = CollapsibleCardWidget("Recent Form (Accuracy Over Time)")
        self.accuracy_trend_plot = pg.PlotWidget(axisItems={'bottom': DateAxis(orientation='bottom')})
        self.trend_legend_label = QLabel("<i>Point Color: Game Result | Point Size: Opponent Rating</i>")
        # --- CORRECTED: Use the public API from the CardWidget base class ---
        self.trend_card.add_widget_to_content(self.accuracy_trend_plot, stretch=1)
        self.trend_card.add_widget_to_content(self.trend_legend_label)

    def _create_layout(self):
        """Arrange all widgets and cards in the layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)

        kpi_layout = QHBoxLayout()
        kpi_layout.addWidget(self.kpi_accuracy_card)
        kpi_layout.addWidget(self.kpi_record_card)
        kpi_layout.addWidget(self.kpi_games_card)
        kpi_layout.addStretch()
        
        main_layout.addLayout(kpi_layout)
        main_layout.addWidget(self.funnel_card)
        main_layout.addWidget(self.trend_card)
        
        main_layout.addStretch(1) # Add stretch to the bottom


    def _get_brush(self, color_code: str) -> QBrush:
        if color_code not in self._brush_cache:
            self._brush_cache[color_code] = pg.mkBrush(color_code + 'B4')
        return self._brush_cache[color_code]

    def _result_to_brush(self, result: str, player_color: str) -> QBrush:
        # (This method is correct)
        pass

    def _rating_to_size(self, rating: int, min_size=8, max_size=20, min_rating=800, max_rating=2800) -> int:
        # (This method is correct)
        pass
    
    def update_kpis(self, data: dict):
        overall_acc = data.get('overall_avg_accuracy')
        recent_acc = data.get('recent_avg_accuracy')
        acc_delta = None
        if overall_acc is not None and recent_acc is not None:
            acc_delta = overall_acc - recent_acc
        self.kpi_accuracy_card.update_value(overall_acc, acc_delta, unit="%")
        
        wins = data.get('overall_wins', 0)
        losses = data.get('overall_losses', 0)
        draws = data.get('overall_draws', 0)
        self.kpi_record_card.update_record(wins, losses, draws)
        
        total_games = data.get('total_games', 0)
        # Refined: Pass integer directly to a potentially improved KpiCardWidget
        self.kpi_games_card.update_value(float(total_games), unit="")
        self.kpi_games_card.value_label.setText(f"<b>{total_games}</b>")

    def update_performance_funnel(self, data: dict):
        # (This method is correct)
        pass

    def plot_accuracy_trend(self, data: list, moving_avg_window: int = 10):
        self.accuracy_trend_plot.clear()
        if not data:
            text_item = pg.TextItem("No game data available for this selection.", color='k', anchor=(0.5, 0.5))
            self.accuracy_trend_plot.addItem(text_item)
            return

        points_data = []
        for d in data:
            try:
                ts = datetime.strptime(d['game_date'], '%Y.%m.%d').timestamp()
                accuracy = d.get('accuracy_percent')
                if accuracy is None: continue
                points_data.append({
                    "pos": (ts, accuracy),
                    "size": self._rating_to_size(d.get('opponent_rating')),
                    "brush": self._result_to_brush(d.get('result', '*'), d.get('player_color', '')),
                    "pen": pg.mkPen(width=1, color='k'),
                    "data": d.get('game_id')
                })
            except (ValueError, TypeError):
                continue
                
        if not points_data:
            text_item = pg.TextItem("No games with valid dates found to plot.", color='k', anchor=(0.5, 0.5))
            self.accuracy_trend_plot.addItem(text_item)
            return

        
        scatter = pg.ScatterPlotItem(points_data)
        scatter.sigClicked.connect(self._on_trend_point_clicked)
        self.accuracy_trend_plot.addItem(scatter)
        self.accuracy_trend_plot.getPlotItem().legend.setVisible(False)
        
        timestamps = [p['pos'][0] for p in points_data]
        accuracies = [p['pos'][1] for p in points_data]
        if len(accuracies) >= moving_avg_window:
            moving_avg = np.convolve(accuracies, np.ones(moving_avg_window), 'valid') / moving_avg_window
            avg_timestamps = timestamps[moving_avg_window - 1:]
            self.accuracy_trend_plot.plot(
                avg_timestamps, moving_avg,
                pen=pg.mkPen(color='k', width=2, style=Qt.PenStyle.DashLine),
                name="Moving Average"
            )

    def _on_trend_point_clicked(self, plot, points):
        if points:
            game_id = points[0].data()
            if game_id:
                self.game_selected.emit(game_id)