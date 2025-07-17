# chess_analysis_project/types.py
"""
A central module for shared data structures and service interfaces (Protocols).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import (Any, Awaitable, Callable, Dict, List, Optional, Protocol, TYPE_CHECKING,
                    runtime_checkable, TypeAlias, Union)

if TYPE_CHECKING:
    import chess
    import chess.pgn
    from chess_analyzer.config.settings import AnalysisSettings, RunConfig

FEN: TypeAlias = str

class MoveClassification(str, Enum):
    BRILLIANT = "Brilliant"; GREAT_MOVE = "Great Move"; BEST_MOVE = "Best Move"
    GOOD_MOVE = "Good Move"; DUBIOUS = "Dubious Move"; INACCURACY = "Inaccuracy"
    MISTAKE = "Mistake"; BLUNDER = "Blunder"

class TacticType(str, Enum):
    MATE_OPPORTUNITY = "MATE_OPPORTUNITY"

class GamePhase(str, Enum):
    OPENING = "Opening"; MIDDLEGAME = "Middlegame"; ENDGAME = "Endgame"

# --- REORDERED AND CORRECTED DATA CONTRACTS ---

@dataclass(frozen=True, slots=True)
class RawEngineLine:
    rank: int; score_cp: Optional[int]; score_mate: Optional[int]; pv: List[str]

@dataclass(frozen=True, slots=True)
class MoveEvaluations:
    eval_before: Optional[float]; eval_after: Optional[float]

@dataclass(frozen=True, slots=True)
class MoveCharacteristics:
    is_capture: bool; is_check: bool; is_castle: bool; is_promotion: bool
    is_en_passant: bool; is_quiet_move: bool; material_delta: int; is_recapture: bool

@dataclass(frozen=True, slots=True)
class ClassificationResult:
    classification: Optional[MoveClassification]; centipawn_loss: Optional[int]
    is_brilliant: bool; is_great_move: bool; is_critical_tactic: bool
    tactic_type: Optional[TacticType]; time_spent_seconds: Optional[float]
    is_reciprocal_blunder: bool = False

@dataclass(frozen=True, slots=True)
class FormattedEngineLine:
    move_san: str; eval_str: str

@dataclass(frozen=True, slots=True)
class PreviousMoveContext:
    classification: Optional[MoveClassification]

@dataclass(frozen=True)
class MoveAnalysisContext:
    board: "chess.Board"; move: "chess.Move"; evaluations: MoveEvaluations
    move_characteristics: MoveCharacteristics; top_engine_lines: List[RawEngineLine]
    settings: "AnalysisSettings"; previous_move_context: Optional[PreviousMoveContext]
    time_spent_seconds: Optional[float]

@dataclass(frozen=True, slots=True)
class EnrichedAnalysis:
    classification: ClassificationResult; formatted_engine_lines: List[FormattedEngineLine]

@dataclass(frozen=True, slots=True)
class AnnotationContext:
    classification: Optional[MoveClassification]; centipawn_loss: Optional[int]
    engine_lines: List[FormattedEngineLine]; user_comment: str; clk_tag: Optional[str]
    multipv_count: int; analysis_depth: int

@dataclass(frozen=True, slots=True)
class GameMetadata:
    white_player: str; black_player: str; result: str; event: str; site: str; date: str
    opening: Optional[str] = None; eco: Optional[str] = None

@dataclass(frozen=True, slots=True)
class PlayerStats:
    acpl: Optional[float]; accuracy_percent: Optional[float]
    move_counts: Dict[MoveClassification, int]

@dataclass(frozen=True)
class GameStatistics:
    white: PlayerStats; black: PlayerStats; opening_name: Optional[str] = None
    eval_volatility: Optional[float] = None
    white_cpls: List[float] = field(default_factory=list, repr=False)
    black_cpls: List[float] = field(default_factory=list, repr=False)

@dataclass
class GameSummary:
    game_id: str; metadata: GameMetadata; stats: GameStatistics
    narrative: Optional[str] = None    

@dataclass(frozen=True)
class ProcessedGameResult:
    annotated_game: Optional["chess.pgn.Game"]; summary: Optional[GameSummary]

@dataclass
class RunReport:
    results: List[ProcessedGameResult]; processed_game_count: int
    user_found_in_games: bool; warnings: List[str] = field(default_factory=list)

@dataclass(frozen=True, slots=True)
class GameSlice:
    ply: int; move_number: int; player_color: str; fen_before: FEN
    move: "chess.Move"; pgn_node: "chess.pgn.GameNode"

@dataclass(frozen=True)
class ParsedGame:
    metadata: GameMetadata; slices: List[GameSlice]; unique_fens: List[FEN]

@dataclass(frozen=True, slots=True)
class CacheKey:
    fen: FEN; depth: int; multipv: int; engine_id: str

@dataclass(frozen=True, slots=True)
class AnalysisResult:
    top_engine_lines: List[RawEngineLine]

@dataclass(frozen=True)
class PositionStats:
    fen: FEN; total_occurrences: int; average_cpl: float; brilliant_count: int
    great_move_count: int; good_move_count: int; dubious_move_count: int
    inaccuracy_count: int; mistake_count: int; blunder_count: int
    is_critical_tactic: bool; tactic_type: Optional[str]
    total_time_spent_seconds: float; move_count_in_time_trouble: int
    eval_std_dev: Optional[float]

@dataclass
class GameContext:
    game_id: str; raw_game: "chess.pgn.Game"; settings: "AnalysisSettings"
    run_config: "RunConfig"; persistence_service: "PersistenceService"
    engine_service: Optional["EngineService"] = None; parsed_game: Optional[ParsedGame] = None
    analysis_results: Dict[FEN, AnalysisResult] = field(default_factory=dict)
    position_stats: Dict[FEN, PositionStats] = field(default_factory=dict)
    enriched_analyses: List[EnrichedAnalysis] = field(default_factory=list)
    stat_updates: List[Dict[str, Any]] = field(default_factory=list)
    annotated_game: Optional["chess.pgn.Game"] = None
    summary: Optional[GameSummary] = None; narrative: Optional[str] = None
    previous_move_eval: Optional[float] = None
    move_evaluations: List[MoveEvaluations] = field(default_factory=list)

@dataclass(frozen=True, slots=True)
class NarrativeContext:
    std_dev_white: float; std_dev_black: float; combined_blunders: int
    white_acpl: Optional[float]; black_acpl: Optional[float]; white_blunders: int
    black_blunders: int; white_player_name: str; black_player_name: str
    game_result: str


# --- PROTOCOLS: Abstract Interfaces for Services ---
# These define the "contracts" that concrete service implementations must adhere to.
# They enable dependency inversion and allow for easy mocking in tests.

class Heuristic(Protocol):
    """Protocol defining the interface for a single, composable classification heuristic."""
    def apply(self, context: "MoveAnalysisContext", result: "ClassificationResult") -> "ClassificationResult": ...

@runtime_checkable
class EngineService(Protocol):
    """Defines the abstract interface for a chess engine service."""
    async def analyze_fens_batch(self, fens: List[str]) -> Dict[str, List[RawEngineLine]]: ...
    async def get_engine_identifier(self) -> str: ...
    async def close(self) -> None: ...
    async def is_healthy(self) -> bool: ...

@runtime_checkable
class CacheService(Protocol):
    """Defines the abstract interface for a key-value analysis cache."""
    async def get_cached_analyses_batch(self, cache_keys: List[CacheKey]) -> Dict[CacheKey, AnalysisResult]: ...
    async def store_analyses_batch(self, results: Dict[CacheKey, AnalysisResult]) -> None: ...

@runtime_checkable
class PersistenceService(Protocol):
    """Defines the abstract interface for the training data persistence layer."""
    async def get_position_stats_batch(self, fens: List[str]) -> Dict[str, PositionStats]: ...
    # Simplified method signatures for brevity in the protocol
    async def upsert_positions_batch(self, positions_data: List[Dict[str, Any]]) -> None: ...
    async def upsert_position_stats_batch(self, stats_data: List[Dict[str, Any]]) -> None: ...
    async def insert_moves_batch(self, moves_data: List[Dict[str, Any]]) -> None: ...
    async def insert_game_stats_batch(self, game_stats_data: List[Dict[str, Any]]) -> None: ...
    async def get_or_create_opening_id(self, name: str) -> int: ...
    async def link_position_to_opening(self, fen: str, opening_id: int) -> None: ...

class ProcessingStage(Protocol):
    """Protocol for a single, named stage in the game processing pipeline."""
    async def execute(self, context: "GameContext") -> "GameContext": ...


# --- QUEUE PAYLOADS: Data Contracts for the Persistence Queue ---

@dataclass(frozen=True, slots=True)
class QueuedPosition:
    """Payload to create or update a base position's data in the persistence layer."""
    position_payload: Dict[str, Any]

@dataclass(frozen=True, slots=True)
class QueuedStatUpdate:
    """Payload to update the aggregated statistics for a single FEN."""
    game_id: str
    stats_payload: Dict[str, Any]

@dataclass(frozen=True, slots=True)
class QueuedMove:
    """Payload to record a single move played in a game."""
    move_payload: Dict[str, Any]

@dataclass(frozen=True, slots=True)
class QueuedGameStat:
    """Payload to record the final aggregated statistics for a game."""
    game_stat_payload: Dict[str, Any]

@dataclass(frozen=True, slots=True)
class QueuedOpeningLink:
    """Payload to link a FEN to a specific opening."""
    game_id: str
    fen: str
    opening_name: str
    eco_code: Optional[str]

@dataclass(frozen=True, slots=True)
class QueuedGameComplete:
    """A sentinel object to signal that all data for a game has been queued."""
    game_id: str

QueuePayload: TypeAlias = Union[
    QueuedPosition, QueuedStatUpdate, QueuedMove, QueuedGameStat, QueuedOpeningLink, QueuedGameComplete
]