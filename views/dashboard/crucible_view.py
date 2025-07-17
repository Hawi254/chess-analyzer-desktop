# chess_analysis_project/views/dashboard/crucible_view.py
"""
Defines the "Crucible" tab for tactical and psychological analysis.
"""
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPointF, Signal, Qt
from PySide6.QtGui import QBrush, QPen
from PySide6.QtWidgets import (QGroupBox, QHBoxLayout, QListWidget,
                               QListWidgetItem, QSplitter, QVBoxLayout,
                               QWidget)

from views.dashboard.blunder_reel_delegate import BlunderReelDelegate
from views.shared.custom_widgets import StretchySplitter
from views.shared.card_widget import CardWidget

CLASSIFICATION_COLOR_CODES = {
    "Blunder": "#DC3232",   # Red
    "Mistake": "#F0961E", # Orange
    "Inaccuracy": "#C8C832",# Yellow
}
DEFAULT_BRUSH_COLOR_CODE = "#1E90FF"

class CrucibleView(QWidget):
    """The UI for the 'Crucible' dashboard tab."""
    
    game_selected_with_ply = Signal(str, int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')
        self._brush_cache = {}

        self._create_widgets()
        self._create_layout()
        self._connect_signals()

    def _create_widgets(self):
        self.splitter = StretchySplitter(Qt.Orientation.Vertical)
        self.decision_matrix_plot = pg.PlotWidget()
        self.tactical_heatmap_plot = pg.PlotWidget()
        self.blunder_reel_list = QListWidget()
        self.blunder_reel_list.setItemDelegate(BlunderReelDelegate(self))

    def _create_layout(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        top_splitter = StretchySplitter(Qt.Orientation.Horizontal)

        # --- CORRECTED: Use the correct `add_widget_to_content` method ---
        matrix_card = CardWidget("Decision-Making Matrix")
        matrix_card.add_widget_to_content(self.decision_matrix_plot)
        top_splitter.addWidget(matrix_card)

        heatmap_card = CardWidget("Tactical Signature")
        heatmap_card.add_widget_to_content(self.tactical_heatmap_plot)
        top_splitter.addWidget(heatmap_card)

        blunder_reel_card = CardWidget("Worst Blunder Reel")
        blunder_reel_card.add_widget_to_content(self.blunder_reel_list)
        
        self.splitter.addWidget(top_splitter)
        self.splitter.addWidget(blunder_reel_card)
        self.splitter.setSizes([450, 250])
        
        main_layout.addWidget(self.splitter)

    def _connect_signals(self):
        self.blunder_reel_list.itemClicked.connect(self._on_blunder_reel_item_clicked)

    def _on_blunder_reel_item_clicked(self, item: QListWidgetItem):
        """Emits a signal to navigate to the specific move in a game."""
        blunder_data = item.data(Qt.ItemDataRole.UserRole)
        if blunder_data and 'game_id' in blunder_data and 'ply' in blunder_data:
            self.game_selected_with_ply.emit(
                blunder_data['game_id'],
                blunder_data['ply']
            )


    def _get_brush(self, color_code: str) -> QBrush:
        if color_code not in self._brush_cache:
            self._brush_cache[color_code] = pg.mkBrush(color_code + 'B4')
        return self._brush_cache[color_code]

    def plot_decision_matrix(self, data: list):
        self.decision_matrix_plot.clear()

        if not data:
            text_item = pg.TextItem("No data available.\nRun analysis with MultiPV > 1.", color='k', anchor=(0.5, 0.5))
            self.decision_matrix_plot.addItem(text_item)
            return


        points_data = []
        for d in data:
            cpl = d.get('cpl', 0)
            if cpl is None or cpl < 10: continue
            
            # --- CORRECTED: Use the renamed variable for color codes ---
            color_code = CLASSIFICATION_COLOR_CODES.get(d.get('classification'), DEFAULT_BRUSH_COLOR_CODE)
            points_data.append({
                'pos': (d.get('time_spent_seconds', 0), d.get('eval_std_dev', 0)),
                'size': self._cpl_to_size(cpl), 'pen': {'color': 'k', 'width': 1},
                'brush': self._get_brush(color_code),
                'data': {'game_id': d.get('game_id'), 'ply': d.get('ply')}
            })
            
        if not points_data:
            text_item = pg.TextItem("No significant errors found to plot.", color='k', anchor=(0.5, 0.5))
            self.decision_matrix_plot.addItem(text_item)
            return
        
        scatter = pg.ScatterPlotItem(points_data)
        scatter.setToolTip("CPL: {size:.0f}\nTime: {pos[0]:.1f}s\nVolatility: {pos[1]:.0f}".format)
        scatter.sigClicked.connect(self._on_matrix_point_clicked)
        self.decision_matrix_plot.addItem(scatter)
        
        legend = self.decision_matrix_plot.addLegend()
        # --- CORRECTED: Use the renamed variable for the legend ---
        for name, color_code in CLASSIFICATION_COLOR_CODES.items():
            self.decision_matrix_plot.plot([], [], pen=None, symbol='o', symbolBrush=self._get_brush(color_code), name=name)

    def _on_matrix_point_clicked(self, plot, points):
        if points:
            data = points[0].data()
            if data and 'game_id' in data and 'ply' in data:
                self.game_selected_with_ply.emit(data['game_id'], data['ply'])


    def plot_tactical_signature(self, data: list):
        self.tactical_heatmap_plot.clear()
        if not data:
            text_item = pg.TextItem("No tactical patterns found in errors.", color='k', anchor=(0.5, 0.5))
            self.tactical_heatmap_plot.addItem(text_item)
            return

        # Pivot data into a matrix
        tactic_types = sorted(list(set(d['tactic_type'] for d in data)))
        classifications = ["Mistake", "Blunder"]
        matrix = np.zeros((len(classifications), len(tactic_types)))

        tactic_map = {name: i for i, name in enumerate(tactic_types)}
        class_map = {name: i for i, name in enumerate(classifications)}

        for item in data:
            if item['classification'] in class_map and item['tactic_type'] in tactic_map:
                row = class_map[item['classification']]
                col = tactic_map[item['tactic_type']]
                matrix[row, col] = item['frequency']
        
        # Create ImageItem
        img = pg.ImageItem(image=matrix)
        self.tactical_heatmap_plot.addItem(img)
        
        # Create colormap
        colors = [(0, 0, 0), (255, 0, 0)] # Black to Red
        cmap = pg.ColorMap(pos=np.linspace(0.0, 1.0, 2), color=colors)
        img.setColorMap(cmap)
        
        # Set axis labels
        self.tactical_heatmap_plot.getAxis('bottom').setTicks([list(enumerate(tactic_types))])
        self.tactical_heatmap_plot.getAxis('left').setTicks([list(enumerate(classifications))])
        

    def update_blunder_reel(self, data: list):
        self.blunder_reel_list.clear()

        if not data:
            item = QListWidgetItem("No blunders to display for this selection.")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.blunder_reel_list.addItem(item)
            return


        for blunder_data in data:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, blunder_data)
            self.blunder_reel_list.addItem(item)



    def _cpl_to_size(self, cpl: float, min_size: int = 5, max_size: int = 40) -> float:
        """Maps Centipawn Loss to a bubble size for the plot."""
        # Use a logarithmic scale to handle outliers gracefully
        # A CPL of 10 is the baseline, a CPL of 1000 is a major blunder
        if cpl < 10: return min_size
        # Simple scaling, can be improved with logarithmic or power scaling
        scaled_size = min_size + (cpl / 1000) * (max_size - min_size)
        return min(scaled_size, max_size)