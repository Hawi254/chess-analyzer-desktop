from PySide6.QtWidgets import QWidget, QGridLayout
from views.dashboard.mini_stat_card import MiniStatCard

class StatsSummaryGridWidget(QWidget):
    """
    A widget to display a 2x2 grid of summary statistics using MiniStatCard.
    """
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.layout = QGridLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(10)
        self.setStyleSheet("border: 1px dashed #ccc; background-color: #f0f0f0;")

        self._create_stat_cards()

    def _create_stat_cards(self):
        self.avg_acc_card = MiniStatCard("Avg Acc")
        self.games_card = MiniStatCard("Games")
        self.best_streak_card = MiniStatCard("Best Streak")
        self.worst_week_card = MiniStatCard("Worst Week")

        self.layout.addWidget(self.avg_acc_card, 0, 0)
        self.layout.addWidget(self.games_card, 0, 1)
        self.layout.addWidget(self.best_streak_card, 1, 0)
        self.layout.addWidget(self.worst_week_card, 1, 1)

    def update_stats(self, avg_accuracy: str, total_games: str, best_streak: str, worst_week: str):
        """
        Updates the displayed statistics.
        """
        self.avg_acc_card.set_value(avg_accuracy)
        self.games_card.set_value(total_games)
        self.best_streak_card.set_value(best_streak)
        self.worst_week_card.set_value(worst_week)

    def update_sparklines(self, sparkline_data: dict):
        """
        Updates the sparkline data for each mini stat card.
        """
        self.avg_acc_card.set_sparkline_data(sparkline_data.get("avg_acc", []))
        self.games_card.set_sparkline_data(sparkline_data.get("games", []))
        self.best_streak_card.set_sparkline_data(sparkline_data.get("best_streak", []))
        self.worst_week_card.set_sparkline_data(sparkline_data.get("worst_week", []))
