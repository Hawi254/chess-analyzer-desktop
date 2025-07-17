# chess_analysis_project/views/annotated_game_view.py
"""
Defines the Annotated Game View for detailed move-by-move analysis.
"""
import chess
import chess.svg
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (QApplication, QGroupBox, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout, QWidget)

from state.app_state import AppState
from views.move_delegate import MoveInfoDelegate


class AnnotatedGameView(QWidget):
    """The view for displaying a single, annotated chess game."""
    
    back_requested = Signal()

    def __init__(self, app_state: AppState, parent: QWidget | None = None):
        super().__init__(parent)
        self._app_state = app_state
        self._game: chess.pgn.Game | None = None
        self._board = chess.Board()

        self._create_widgets()
        self._create_layout()
        
        # Set up the custom delegate for the move list
        self.move_list.setItemDelegate(MoveInfoDelegate(self))
        
        self._connect_signals()
        
    def _create_widgets(self):
        # Left side
        self.board_widget = QSvgWidget()
        
        # Right side
        self.game_info_label = QLabel()
        self.move_list = QListWidget()
        self.back_button = QPushButton("<< Back to Report")
        self.prev_button = QPushButton("< Prev")
        self.next_button = QPushButton("Next >")
        self.copy_fen_button = QPushButton("Copy FEN")

    def _create_layout(self):
        main_layout = QHBoxLayout(self)
        
        # Left side (Board)
        board_group = QGroupBox("Board")
        board_layout = QVBoxLayout(board_group)
        board_layout.addWidget(self.board_widget)
        main_layout.addWidget(board_group, stretch=2)
        
        # Right side (Info & Moves)
        info_group = QGroupBox("Game Analysis")
        info_layout = QVBoxLayout(info_group)
        info_layout.addWidget(self.game_info_label)
        info_layout.addWidget(self.move_list)
        
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.back_button)
        button_layout.addStretch()
        button_layout.addWidget(self.prev_button)
        button_layout.addWidget(self.next_button)
        button_layout.addStretch()
        button_layout.addWidget(self.copy_fen_button)
        info_layout.addLayout(button_layout)
        
        main_layout.addWidget(info_group, stretch=1)

    def _connect_signals(self):
        self._app_state.game_selected.connect(self._on_game_loaded)
        self._app_state.ply_selected.connect(self._on_ply_changed)
        
        self.move_list.currentRowChanged.connect(self._app_state.select_ply)
        self.back_button.clicked.connect(self.back_requested.emit)
        self.prev_button.clicked.connect(lambda: self._app_state.select_ply(self._app_state.get_current_ply() - 1))
        self.next_button.clicked.connect(lambda: self._app_state.select_ply(self._app_state.get_current_ply() + 1))
        self.copy_fen_button.clicked.connect(self._copy_fen)

    def _on_game_loaded(self, game_id: str):
        """Populates the view when a new game is selected in the AppState."""
        self._game = self._app_state.get_selected_game()
        if not self._game:
            return

        headers = self._game.headers
        info = f"<b>{headers.get('White', '?')}</b> vs <b>{headers.get('Black', '?')}</b> ({headers.get('Result', '*')})"
        self.game_info_label.setText(info)
        
        self.move_list.clear()
        self.move_list.blockSignals(True)
        board = self._game.board()
        
        start_item = QListWidgetItem("Start Position")
        start_item.setData(Qt.ItemDataRole.UserRole, {"san": "Start Position", "comment": ""})
        self.move_list.addItem(start_item)
        
        # --- CORRECTED: Convert the iterator to a list before iterating ---
        mainline_nodes = list(self._game.mainline())
        for i, node in enumerate(mainline_nodes):
        # ----------------------------------------------------------------
            move = node.move
            san = board.san(move)
            board.push(move)
            
            move_num_str = ""
            if board.turn == chess.BLACK:
                move_num_str = f"{board.fullmove_number}. "
            else:
                # --- CORRECTED: Use the list for safe index access ---
                if i == 0 or board.fullmove_number != mainline_nodes[i-1].board().fullmove_number:
                # ----------------------------------------------------
                     move_num_str = f"{board.fullmove_number}... "

            item = QListWidgetItem(f"{move_num_str}{san}")
            item.setData(Qt.ItemDataRole.UserRole, {"san": f"{move_num_str}{san}", "comment": node.comment})
            self.move_list.addItem(item)
            
        self.move_list.blockSignals(False)
        
    def _on_ply_changed(self, ply: int):
        """Updates the board and selection when the ply changes."""
        if not self._game:
            return
            
        # --- CORRECTED: Use proper node traversal instead of .variation() ---
        # Start at the root node (the game object itself)
        node = self._game
        # Step forward `ply` times to get the correct node
        for _ in range(ply):
            # Check if there is a next node to prevent errors at the end of the game
            if node.next():
                node = node.next()
            else:
                # This should not happen if ply is managed correctly, but it's a safe guard.
                break
        # -------------------------------------------------------------------
        
        self._board = node.board()
        
        # Determine last move to highlight it on the board
        last_move = node.move if ply > 0 else None
        
        svg_data = chess.svg.board(self._board, lastmove=last_move).encode("utf-8")
        self.board_widget.load(svg_data)
        
        # Ensure the list widget selection is in sync
        if self.move_list.currentRow() != ply:
            self.move_list.setCurrentRow(ply)

    def _copy_fen(self):
        """Copies the current board's FEN to the clipboard."""
        if self._board:
            QApplication.clipboard().setText(self._board.fen())