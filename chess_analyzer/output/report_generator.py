# chess_analyzer/output/report_generator.py
"""
Provides a service for writing the final analysis summary to a CSV file.

This module contains the `ReportGenerator`, a "dumb" I/O service that is
responsible only for formatting and writing data to a CSV report. It contains
no business logic and relies on the core application to provide it with
pre-structured `GameSummary` objects.
"""

import csv
from pathlib import Path
from typing import List, TYPE_CHECKING, Dict, Any

import structlog

from chess_analyzer.exceptions import ReportGenerationError
from chess_analyzer.types import MoveClassification, GameSummary

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)

class ReportGenerator:
    """A stateless service that writes a list of game summaries to a CSV report file."""

    # Define the CSV headers in a structured, grouped way for maintainability.
    _STATIC_HEADERS: List[str] = [
        "GameID", "White", "Black", "Result", "Opening", "Event", "Site", "Date",
    ]
    _PLAYER_METRIC_HEADERS: List[str] = [
        "White_ACPL", "White_Accuracy", "Black_ACPL", "Black_Accuracy",
        "White_Blunders", "White_Mistakes", "White_Inaccuracies", "White_Dubious", "White_Good", "White_Best", "White_Brilliants", "White_GreatMoves",
        "Black_Blunders", "Black_Mistakes", "Black_Inaccuracies", "Black_Dubious", "Black_Good", "Black_Best", "Black_Brilliants", "Black_GreatMoves",
    ]
    _GAME_METRIC_HEADERS: List[str] = ["Eval_Volatility"]
    _NARRATIVE_HEADERS: List[str] = ["Narrative"]
    
    _CSV_HEADERS: List[str] = (
        _STATIC_HEADERS + _PLAYER_METRIC_HEADERS + 
        _GAME_METRIC_HEADERS + _NARRATIVE_HEADERS
    )

    def generate_csv_report_from_summaries(self, summaries: List[GameSummary], output_path: Path) -> None:
        """
        Generates and writes a CSV summary report from a list of GameSummary objects.

        Args:
            summaries: A list of completed `GameSummary` objects.
            output_path: The `pathlib.Path` to write the final CSV report to.
        
        Raises:
            ReportGenerationError: If the CSV file cannot be written.
        """
        if not summaries:
            logger.warning("No completed summaries to generate a report for. Skipping.")
            return

        report_data: List[Dict[str, Any]] = []
        for summary in summaries:
            s, m, st = summary, summary.metadata, summary.stats
            # Flatten the nested summary object into a single dictionary row.
            row = {
                "GameID": s.game_id, "White": m.white_player, "Black": m.black_player, "Result": m.result,
                "Opening": st.opening_name, "Event": m.event, "Site": m.site, "Date": m.date,
                "White_ACPL": f"{st.white.acpl:.2f}" if st.white.acpl is not None else "N/A",
                "White_Accuracy": st.white.accuracy_percent,
                "Black_ACPL": f"{st.black.acpl:.2f}" if st.black.acpl is not None else "N/A",
                "Black_Accuracy": st.black.accuracy_percent,
                "White_Blunders": st.white.move_counts.get(MoveClassification.BLUNDER, 0),
                "White_Mistakes": st.white.move_counts.get(MoveClassification.MISTAKE, 0),
                "White_Inaccuracies": st.white.move_counts.get(MoveClassification.INACCURACY, 0),
                "White_Dubious": st.white.move_counts.get(MoveClassification.DUBIOUS, 0),
                "White_Good": st.white.move_counts.get(MoveClassification.GOOD_MOVE, 0),
                "White_Best": st.white.move_counts.get(MoveClassification.BEST_MOVE, 0),
                "White_Brilliants": st.white.move_counts.get(MoveClassification.BRILLIANT, 0),
                "White_GreatMoves": st.white.move_counts.get(MoveClassification.GREAT_MOVE, 0),
                "Black_Blunders": st.black.move_counts.get(MoveClassification.BLUNDER, 0),
                "Black_Mistakes": st.black.move_counts.get(MoveClassification.MISTAKE, 0),
                "Black_Inaccuracies": st.black.move_counts.get(MoveClassification.INACCURACY, 0),
                "Black_Dubious": st.black.move_counts.get(MoveClassification.DUBIOUS, 0),
                "Black_Good": st.black.move_counts.get(MoveClassification.GOOD_MOVE, 0),
                "Black_Best": st.black.move_counts.get(MoveClassification.BEST_MOVE, 0),
                "Black_Brilliants": st.black.move_counts.get(MoveClassification.BRILLIANT, 0),
                "Black_GreatMoves": st.black.move_counts.get(MoveClassification.GREAT_MOVE, 0),
                "Eval_Volatility": st.eval_volatility,
                "Narrative": s.narrative,
            }
            report_data.append(row)

        logger.info("Writing CSV report.", path=str(output_path), num_rows=len(report_data))
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w", newline="", encoding="utf-8") as csvfile:
                # Use DictWriter to map the dictionary keys directly to CSV columns.
                writer = csv.DictWriter(csvfile, fieldnames=self._CSV_HEADERS, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(report_data)
            logger.info("Successfully generated CSV report.", path=str(output_path))
        except IOError as e:
            raise ReportGenerationError(f"Failed to write CSV report to {output_path}") from e