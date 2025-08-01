# chess_analysis_project/views/dashboard/blunder_reel_delegate.py
"""
Defines a custom delegate for rendering items in the Blunder Reel.
"""
import chess
import chess.svg
from PySide6.QtCore import QRect, Qt, QSize
from PySide6.QtGui import QFont, QFontMetrics, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle

class BlunderReelDelegate(QStyledItemDelegate):
    """Delegate to draw a mini-board, played move, and correct move."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # --- CORRECTED: Instantiate and store fonts and metrics in __init__ ---
        self._main_font = QFont("Arial", 10, QFont.Weight.Bold)
        self._fm_main = QFontMetrics(self._main_font)

        self._sub_font = QFont("Arial", 9)
        self._fm_sub = QFontMetrics(self._sub_font)
        # --------------------------------------------------------------------

        self.item_padding = 10
        self.board_size = 100

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()
        
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        
        item_data = index.data(Qt.ItemDataRole.UserRole)
        if not item_data:
            painter.restore()
            return
            
        x = option.rect.x() + self.item_padding
        y = option.rect.y() + self.item_padding
        text_x = x + self.board_size + self.item_padding

        fen = item_data.get("fen_before_blunder")
        if fen:
            board = chess.Board(fen)
            last_move = chess.Move.from_uci(item_data.get("played_move_uci")) if "played_move_uci" in item_data else None
            svg_data = chess.svg.board(board, lastmove=last_move, size=self.board_size).encode("utf-8")
            renderer = QSvgRenderer(svg_data)
            renderer.render(painter, QRect(x, y, self.board_size, self.board_size))

        text_y = y
        text_width = option.rect.width() - text_x - self.item_padding

        # --- Draw "You Played" line with wrapping ---
        painter.setFont(self._main_font)
        painter.setPen(option.palette.text().color())
        
        played_move_san = item_data.get("played_move_san", "N/A")
        cpl = item_data.get("cpl", 0)
        played_text = f"You Played: {played_move_san} (CPL: {cpl:.0f})"
        
        played_rect = self._fm_main.boundingRect(QRect(0, 0, text_width, 0), Qt.TextFlag.TextWordWrap, played_text)
        played_rect.moveTo(text_x, text_y)
        painter.drawText(played_rect, Qt.TextFlag.TextWordWrap, played_text)
        text_y += played_rect.height()

        # --- Draw "Correct" line with wrapping ---
        painter.setFont(self._sub_font)
        correct_move_san = item_data.get("correct_move_san", "N/A")
        correct_eval = item_data.get("correct_eval_str", "")
        correct_text = f"Correct: {correct_move_san} ({correct_eval})"
        
        correct_rect = self._fm_sub.boundingRect(QRect(0, 0, text_width, 0), Qt.TextFlag.TextWordWrap, correct_text)
        correct_rect.moveTo(text_x, text_y)
        painter.drawText(correct_rect, Qt.TextFlag.TextWordWrap, correct_text)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        # Get the data to be rendered
        item_data = index.data(Qt.ItemDataRole.UserRole)
        if not item_data:
            return super().sizeHint(option, index)

        # Determine available width for text, accounting for board and padding
        text_width = option.rect.width() - self.board_size - (3 * self.item_padding)
        
        # Calculate height needed for the text with word wrapping
        played_move_san = item_data.get("played_move_san", "N/A")
        cpl = item_data.get("cpl", 0)
        played_text = f"You Played: {played_move_san} (CPL: {cpl:.0f})"
        
        correct_move_san = item_data.get("correct_move_san", "N/A")
        correct_eval = item_data.get("correct_eval_str", "")
        correct_text = f"Correct: {correct_move_san} ({correct_eval})"

        # Use boundingRect to calculate wrapped height
        played_rect = self._fm_main.boundingRect(QRect(0,0, text_width, 0), Qt.TextFlag.TextWordWrap, played_text)
        correct_rect = self._fm_sub.boundingRect(QRect(0,0, text_width, 0), Qt.TextFlag.TextWordWrap, correct_text)
        
        text_height = played_rect.height() + correct_rect.height()
        
        # The hint is the max of the board height or the calculated text height
        final_height = max(self.board_size, text_height) + (2 * self.item_padding)
        
        return QSize(option.rect.width(), final_height)