# chess_analysis_project/views/dashboard/state_graph_widget.py
"""
Defines a custom QWidget for displaying a state transition graph for game flow analysis.
"""
import numpy as np
import pyqtgraph as pg
from PySide6.QtGui import QFont, QShowEvent
from PySide6.QtWidgets import QWidget, QVBoxLayout

import structlog

logger = structlog.get_logger(__name__)

class StateGraphWidget(QWidget):
    """A widget that paints a state transition graph using pyqtgraph."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._is_data_stale = False
        self._setup_ui()
        self._define_graph_layout()

    def _setup_ui(self):
        """Initializes the pyqtgraph components."""
        self.graph_layout = pg.GraphicsLayoutWidget()
        self.plot_item = self.graph_layout.addPlot()
        self.plot_item.hideAxis('left')
        self.plot_item.hideAxis('bottom')
        self.plot_item.setAspectLocked(lock=False)
        # Disable mouse interaction for a static, informational graph
        self.plot_item.setMouseEnabled(x=False, y=False)

        self.graph_item = pg.GraphItem()
        self.plot_item.addItem(self.graph_item)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.graph_layout)

        self.text_items = []

    def _define_graph_layout(self):
        """Defines the static positions and styles for the graph nodes."""
        self.node_positions = {
            'Winning': np.array([0, 4]), 'Better': np.array([0, 2]),
            'Equal': np.array([0, 0]), 'Worse': np.array([0, -2]),
            'Losing': np.array([0, -4]), 'Game Won': np.array([4, 4]),
            'Game Lost': np.array([4, -4]), 'Game Drawn': np.array([4, 0]),
        }
        self.node_styles = {
            'Winning': {'symbol': 'o', 'size': 30, 'brush': pg.mkBrush(color='#2ECC71'), 'pen': 'k'},
            'Better': {'symbol': 'o', 'size': 25, 'brush': pg.mkBrush(color='#ABEBC6'), 'pen': 'k'},
            'Equal': {'symbol': 's', 'size': 20, 'brush': pg.mkBrush(color='#F5B041'), 'pen': 'k'},
            'Worse': {'symbol': 'o', 'size': 25, 'brush': pg.mkBrush(color='#F5B7B1'), 'pen': 'k'},
            'Losing': {'symbol': 'o', 'size': 30, 'brush': pg.mkBrush(color='#E74C3C'), 'pen': 'k'},
            'Game Won': {'symbol': 'star', 'size': 35, 'brush': pg.mkBrush(color='#2ECC71'), 'pen': 'k'},
            'Game Lost': {'symbol': 'star', 'size': 35, 'brush': pg.mkBrush(color='#E74C3C'), 'pen': 'k'},
            'Game Drawn': {'symbol': 'star', 'size': 35, 'brush': pg.mkBrush(color='#F39C18'), 'pen': 'k'},
        }
        self.node_font = QFont("Arial", 10, QFont.Weight.Bold)
        self.edge_font = QFont("Arial", 8)

    def clear_graph(self):
        """Removes all old text items from the plot."""
        for item in self.text_items:
            self.plot_item.removeItem(item)
        self.text_items.clear()
        self.graph_item.setData(pos=np.empty((0, 2)), adj=np.empty((0, 2)))

    def set_data(self, transition_data: dict):
        """Processes the transition matrix and updates the graph visualization."""
        self.clear_graph()
        if not transition_data:
            msg = pg.TextItem("No data to display for Game Flow analysis.", color='k', anchor=(0.5, 0.5))
            msg.setPos(0, 0)
            self.plot_item.addItem(msg)
            self.text_items.append(msg)
            return

        state_names = list(self.node_positions.keys())
        state_to_idx = {name: i for i, name in enumerate(state_names)}
        pos = np.array([self.node_positions[name] for name in state_names])
        adj, pens = [], []
        totals = {state: sum(targets.values()) for state, targets in transition_data.items()}

        for from_state, targets in transition_data.items():
            if from_state not in state_to_idx: continue
            from_idx = state_to_idx[from_state]
            total_from = totals.get(from_state, 1)

            for to_state, count in targets.items():
                if to_state not in state_to_idx or count == 0: continue
                to_idx = state_to_idx[to_state]
                adj.append((from_idx, to_idx))

                probability = count / total_from
                width = 1 + probability * 8
                alpha = 50 + int(probability * 205)
                pens.append(pg.mkPen(color=(0, 0, 0, alpha), width=width))

                if probability > 0.02:
                    label_pos = (self.node_positions[from_state] + self.node_positions[to_state]) / 2
                    if from_state == to_state:
                        label_pos += np.array([1.2, 0])
                    label = pg.TextItem(f"{probability:.0%}", color='k', anchor=(0.5, 0.5))
                    label.setFont(self.edge_font)
                    label.setPos(label_pos[0], label_pos[1])
                    self.plot_item.addItem(label)
                    self.text_items.append(label)

        symbols = [self.node_styles[name]['symbol'] for name in state_names]
        sizes = [self.node_styles[name]['size'] for name in state_names]
        brushes = [self.node_styles[name]['brush'] for name in state_names]

        for name, position in self.node_positions.items():
            label = pg.TextItem(name, color='k', anchor=(0.5, -0.7))
            label.setFont(self.node_font)
            label.setPos(position[0], position[1])
            self.plot_item.addItem(label)
            self.text_items.append(label)

        self.graph_item.setData(
            pos=pos, adj=np.array(adj) if adj else np.empty((0, 2)),
            pen=pens, size=sizes, symbol=symbols, brush=brushes
        )

        # --- Definitive Fix for Rendering Race Condition ---
        # Set a flag indicating new data has been loaded. The auto-ranging
        # will be triggered by the showEvent if the widget is hidden, or
        # immediately if it's already visible.
        self._is_data_stale = True
        if self.isVisible():
            self.plot_item.autoRange()
            self._is_data_stale = False

    def showEvent(self, event: QShowEvent):
        """
        Overrides QWidget.showEvent to trigger auto-ranging only when the
        widget becomes visible and has stale data. This is the definitive
        fix for the "cramped corner" bug.
        """
        super().showEvent(event)
        if self._is_data_stale:
            self.plot_item.autoRange()
            self._is_data_stale = False
            