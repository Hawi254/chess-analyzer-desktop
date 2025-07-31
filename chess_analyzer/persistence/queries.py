# chess_analyzer/persistence/queries.py
"""
Defines explicit, self-contained Query Objects for all dashboard data fetches.

This pattern replaces generic filter dictionaries with strongly-typed objects,
encapsulating the logic for building SQL clauses and parameters. This makes the
data access layer more robust, type-safe, and easier to extend.
"""
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple


@dataclass(frozen=True, slots=True)
class BaseDashboardQuery:
    """A base class for all dashboard queries, containing common filters."""
    player_name: str
    time_control: Optional[str] = None
    color: Optional[str] = None

    def build_clause(self, table_alias: str = "gs") -> Tuple[str, List[Any]]:
        """
        Builds a SQL WHERE clause and parameters from the query's attributes.
        This is the core logic that replaces the generic _build_filter_clause method.
        """
        params: List[Any] = []
        where_clauses: List[str] = []

        # Player name is always required for dashboard queries.
        where_clauses.append(f"{table_alias}.player_name = ?")
        params.append(self.player_name)

        if self.time_control:
            where_clauses.append(f"{table_alias}.time_control_category = ?")
            params.append(self.time_control)
        
        # The 'color' filter is handled by subclasses that need it.
        if self.color and self._should_use_color_filter():
            where_clauses.append(f"{table_alias}.player_color = ?")
            params.append(self.color)

        return f"WHERE {' AND '.join(where_clauses)}", params

    def _should_use_color_filter(self) -> bool:
        """Determines if the color filter should be applied. Overridden by subclasses."""
        return True


@dataclass(frozen=True, slots=True)
class KpiQuery(BaseDashboardQuery):
    """Query for high-level KPIs, which should always ignore the color filter."""
    def _should_use_color_filter(self) -> bool:
        # Explicitly state that KPIs are calculated across all games, regardless of color.
        return False


@dataclass(frozen=True, slots=True)
class AccuracyTrendQuery(BaseDashboardQuery):
    """Query for the calendar heatmap, which respects the color filter."""
    granularity: str = "Weekly"
    metric: str = "Accuracy"
    date_range: Optional[str] = None


@dataclass(frozen=True, slots=True)
class OpeningPerformanceQuery(BaseDashboardQuery):
    """Query for the opening performance table."""
    pass  # Inherits default behavior

@dataclass(frozen=True, slots=True)
class BlunderReelQuery(BaseDashboardQuery):
    """Query for the blunder reel, which respects the color filter."""
    limit: int = 20

@dataclass(frozen=True, slots=True)
class CognitiveDissonanceQuery(BaseDashboardQuery):
    """Query for cognitive dissonance, which respects the color filter."""
    # These are keyword-only to resolve the TypeError caused by a non-default
    # argument (`opening_id`) following default arguments in the base class.
    opening_id: int = field(kw_only=True)
    limit: int = field(default=5, kw_only=True)