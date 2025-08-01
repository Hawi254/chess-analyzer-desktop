# chess_analyzer/orchestration/pipeline_stages.py
"""
Defines the individual, sequential stages of the game analysis pipeline.

Each stage is a class that conforms to the `ProcessingStage` protocol. It
performs a specific, well-defined part of the overall workflow, such as
parsing the game, fetching engine evaluations, classifying moves, or generating
a summary. The pipeline is executed by passing a mutable `GameContext` object
from one stage to the next, with each stage reading from and writing to it.
"""

import asyncio
import statistics
from typing import Callable, Dict, List, Optional, TYPE_CHECKING

import chess
import chess.pgn
import structlog

from chess_analyzer.core import (board_analyzer, chess_utils, game_phaser,
                                 move_characterizer, stats_updater,
                                 summary_aggregator, time_parser)
from chess_analyzer.core.chess_utils import get_material_diff, interpret_engine_score
from chess_analyzer.orchestration.annotator_client import build_annotation_context as build_anno_ctx
from chess_analyzer.tracing import trace_stage
from chess_analyzer.types import (GameContext, MoveAnalysisContext,
                                  MoveEvaluations, PreviousMoveContext,
                                  QueuedAnnotatedGame, QueuedGameComplete,
                                  QueuedGameStat, QueuedMove, QueuedPosition,
                                  QueuedStatUpdate, ProcessingStage,
                                  GameSlice, GameSummary,
                                  RawEngineLine)

if TYPE_CHECKING:
    from chess_analyzer.config.settings import AnalysisSettings
    from chess_analyzer.core.move_classifier import MoveClassifier
    from chess_analyzer.core.pgn_parser import PgnParser
    from chess_analyzer.orchestration.annotator_client import AnnotatorClient
    from chess_analyzer.orchestration.persistence_client import PersistenceClient
    from chess_analyzer.services.analysis_provider import AnalysisProvider
    
    NarrativeGeneratorFunc = Callable[[GameSummary, "AnalysisSettings"], str]

logger = structlog.get_logger(__name__)

# --- Helper Functions ---

def _calculate_eval_std_dev(lines: List["RawEngineLine"], settings: "AnalysisSettings") -> Optional[float]:
    """Calculates the standard deviation of the top N engine evaluation scores."""
    if settings.multipv < 2 or len(lines) < 2:
        return None
    scores = [s for s in (interpret_engine_score(line, settings) for line in lines) if s is not None]
    if len(scores) < 2:
        return None
    return round(statistics.stdev(scores), 2)

def _build_move_analysis_context(
    slice: "GameSlice", context: GameContext, 
    previous_move_context: Optional[PreviousMoveContext],
    time_spent: Optional[float]
) -> Optional[MoveAnalysisContext]:
    """Constructs the `MoveAnalysisContext` needed for the `MoveClassifier`."""
    board = chess.Board(slice.fen_before)
    analysis_before = context.analysis_results.get(slice.fen_before)
    board.push(slice.move)
    analysis_after = context.analysis_results.get(board.fen())

    if not (analysis_before and analysis_after and analysis_before.top_engine_lines and analysis_after.top_engine_lines):
        logger.warning("Missing engine analysis for ply, cannot build move context.", ply=slice.ply)
        return None
    
    eval_before = interpret_engine_score(analysis_before.top_engine_lines[0], context.settings)
    eval_after = interpret_engine_score(analysis_after.top_engine_lines[0], context.settings)
    
    # Restore the board to its state *before* the move for the context.
    board.pop()

    return MoveAnalysisContext(
        board=board, move=slice.move, 
        evaluations=MoveEvaluations(eval_before=eval_before, eval_after=eval_after),
        move_characteristics=move_characterizer.characterize_move(board, slice.move),
        top_engine_lines=analysis_before.top_engine_lines, 
        settings=context.settings,
        previous_move_context=previous_move_context, 
        time_spent_seconds=time_spent
    )

# --- Pipeline Stage Implementations ---

class InitialSetupStage(ProcessingStage):
    """Parses the raw PGN into the application's data contracts."""
    def __init__(self, pgn_parser_func: "PgnParser"):
        self._parser_func = pgn_parser_func
    
    @trace_stage
    async def execute(self, context: GameContext) -> GameContext:
        context.parsed_game = self._parser_func(context.raw_game)
        return context

class AnalysisStage(ProcessingStage):
    """Fetches all external data needed for analysis: engine evals and historical stats."""
    def __init__(self, provider: "AnalysisProvider"):
        self._provider = provider
    
    @trace_stage
    async def execute(self, context: GameContext) -> GameContext:
        if not context.parsed_game or not context.parsed_game.unique_fens:
            return context
        
        # Fetch engine analysis and historical position stats concurrently
        analysis_task = asyncio.create_task(
            self._provider.get_analyses_for_fens(context.parsed_game.unique_fens, context.engine_service)
        )
        stats_task = asyncio.create_task(
            context.persistence_service.get_position_stats_batch(context.parsed_game.unique_fens)
        )
        
        context.analysis_results, context.position_stats = await asyncio.gather(analysis_task, stats_task)
        return context

class ClassificationStage(ProcessingStage):
    """Classifies each move in the game and queues position data for persistence."""
    def __init__(self, classifier: "MoveClassifier", client: "PersistenceClient"):
        self._classifier = classifier
        self._client = client

    @trace_stage
    async def execute(self, context: GameContext) -> GameContext:
        # --- START OF CORRECTED TIME CALCULATION LOGIC ---
        
        # This dictionary will store the last known clock time for each player ('w' and 'b').
        last_clock: Dict[str, Optional[float]] = {'w': None, 'b': None}
        
        # Initialize the clock from the TimeControl header if available.
        if time_control_str := context.raw_game.headers.get("TimeControl"):
            try:
                base_time_seconds = float(time_control_str.split('+')[0])
                last_clock['w'] = base_time_seconds
                last_clock['b'] = base_time_seconds
            except (ValueError, IndexError):
                logger.warning("Could not parse initial time from TimeControl header.", tc=time_control_str)

        time_spent_per_move: List[Optional[float]] = []
        time_increment = chess_utils.get_time_increment(context.raw_game.headers.get("TimeControl", "0+0"))

        for slice in context.parsed_game.slices:
            player_color = slice.player_color  # Use 'w' or 'b' directly as the key
            time_spent = None
            
            # Pass the entire comment to the robust parser.
            current_clk_seconds = time_parser.parse_clk_comment_to_seconds(slice.pgn_node.comment)
            
            if current_clk_seconds is not None:
                previous_player_clk = last_clock[player_color]
                
                if previous_player_clk is not None:
                    # Calculate the time spent.
                    time_spent = previous_player_clk - current_clk_seconds + time_increment
                    
                    # Ensure time spent is non-negative.
                    if time_spent < 0:
                        # This can happen on the first move if the PGN clock tag is weird.
                        # We'll log it but use a fallback.
                        logger.debug("Negative time spent calculated, falling back to None.",
                                     prev_clk=previous_player_clk, curr_clk=current_clk_seconds)
                        time_spent = None
                
                # Update the last known clock time for the current player.
                last_clock[player_color] = current_clk_seconds
            
            time_spent_per_move.append(time_spent)
        
        # --- END OF CORRECTED TIME CALCULATION LOGIC ---

        last_move_result = None
        # Now, loop through the slices again to build the contexts, using our pre-calculated times.
        for i, slice in enumerate(context.parsed_game.slices):
            time_spent = time_spent_per_move[i]
            
            prev_move_ctx = PreviousMoveContext(classification=last_move_result.classification) if last_move_result else None
            move_context = _build_move_analysis_context(slice, context, prev_move_ctx, time_spent)
            
            if move_context is None:
                last_move_result = None
                continue
            
            context.move_evaluations.append(move_context.evaluations)
            
            # Determine the game phase once for the current position.
            game_phase = game_phaser.determine_game_phase(move_context.board, context.settings).value
            
            position_payload = {
                "fen": slice.fen_before, "player_to_move": slice.player_color,
                "material_balance": int(get_material_diff(move_context.board, chess.WHITE) * 100),
                "game_phase": game_phase,
                "game_id": context.game_id
            }
            await self._client.queue_item(QueuedPosition(position_payload=position_payload))

            result = self._classifier.classify_move(move_context)
            
            # Pass the game_phase to the enrichment function.
            enriched_result = board_analyzer.enrich_analysis_with_san(
                move_context.board, result, move_context.top_engine_lines, context.settings, game_phase
            )
            context.enriched_analyses.append(enriched_result)
            
            eval_std_dev = _calculate_eval_std_dev(move_context.top_engine_lines, context.settings)
            stats = context.position_stats.get(slice.fen_before)
            stat_update = stats_updater.calculate_new_position_stats(slice.fen_before, stats, result, eval_std_dev, context.settings)
            context.stat_updates.append(stat_update)
            last_move_result = result
            
        return context
    
class PersistenceStage(ProcessingStage):
    """Queues all remaining analysis artifacts for batch database insertion."""
    def __init__(self, client: "PersistenceClient"):
        self._client = client
    
    @trace_stage
    async def execute(self, context: GameContext) -> GameContext:
        if not context.parsed_game:
            return context
        
        last_line_san = ""
        for update in context.stat_updates:
            await self._client.queue_item(QueuedStatUpdate(game_id=context.game_id, stats_payload=update))
            
        for i, enriched in enumerate(context.enriched_analyses):
            slice = context.parsed_game.slices[i]
            result = enriched.classification

            # --- NEW: Generate move_san and the cumulative line_san ---
            board = chess.Board(slice.fen_before)
            move_san = board.san(slice.move)

            if slice.player_color == 'w':
                # It's White's move, add the move number.
                current_line_san = f"{last_line_san} {slice.move_number}. {move_san}".strip()
            else:
                # It's Black's move, just add the move SAN.
                current_line_san = f"{last_line_san} {move_san}".strip()
            last_line_san = current_line_san
            # --- END NEW ---

            post_move_eval = None
            if i < len(context.move_evaluations):
                post_move_eval = context.move_evaluations[i].eval_after

            best_move_san = None
            if enriched.formatted_engine_lines:
                best_move_san = enriched.formatted_engine_lines[0].move_san

            await self._client.queue_item(QueuedMove(move_payload={
                "game_id": context.game_id, "fen": slice.fen_before, "ply": slice.ply, "move_uci": slice.move.uci(),
                "move_san": move_san, "line_san": current_line_san, "cpl": result.centipawn_loss,
                "classification": result.classification.value if result.classification else "N/A",
                "time_spent_seconds": result.time_spent_seconds,
                "is_reciprocal_blunder": result.is_reciprocal_blunder,
                "best_move_san": best_move_san,
                "post_move_eval": post_move_eval, # Add to payload
                "game_phase": enriched.game_phase
            }))

        return context

class SummaryStage(ProcessingStage):
    """Generates the final game summary, narrative, and queues game-level stats."""
    def __init__(self, narrative_generator_func: "NarrativeGeneratorFunc", client: "PersistenceClient"):
        self._gen = narrative_generator_func
        self._client = client
    
    @trace_stage
    async def execute(self, context: GameContext) -> GameContext:
        if not context.parsed_game:
            return context

        context.summary = summary_aggregator.aggregate_game_summary(context, context.settings)
        if not context.summary:
            return context
        
        context.summary.narrative = self._gen(context.summary, context.settings)
        
        raw_headers = context.raw_game.headers
        def safe_get_rating(headers, key):
            v = headers.get(key, "0")
            return int(v) if v.isdigit() else 0
        
        user_name = context.run_config.user_player_name
        is_white_user = user_name and context.summary.metadata.white_player.strip().lower() == user_name.strip().lower()
        is_black_user = user_name and context.summary.metadata.black_player.strip().lower() == user_name.strip().lower()
        
        time_category = chess_utils.categorize_time_control(raw_headers.get("TimeControl"))
        result = context.summary.metadata.result
        termination = chess_utils.determine_game_termination(context.raw_game)

        # White player stats payload
        white_payload = {
            "game_id": context.game_id, "player_name": context.summary.metadata.white_player,
            "player_color": "White", "is_user_game": 1 if is_white_user else 0,
            "date": context.summary.metadata.date, "game_time": context.summary.metadata.time,
            "time_control_category": time_category,
            "opponent_rating": safe_get_rating(raw_headers, "BlackElo"),
            "eval_volatility": context.summary.stats.eval_volatility,
            "accuracy_percent": context.summary.stats.white.accuracy_percent, "result": result,
            "termination": termination,
            "opening_name": context.summary.metadata.opening
        }
        await self._client.queue_item(QueuedGameStat(game_stat_payload=white_payload))
        
        # Black player stats payload
        black_payload = {
            "game_id": context.game_id, "player_name": context.summary.metadata.black_player,
            "player_color": "Black", "is_user_game": 1 if is_black_user else 0,
            "date": context.summary.metadata.date, "game_time": context.summary.metadata.time,
            "time_control_category": time_category,
            "opponent_rating": safe_get_rating(raw_headers, "WhiteElo"),
            "eval_volatility": context.summary.stats.eval_volatility,
            "accuracy_percent": context.summary.stats.black.accuracy_percent, "result": result,
            "termination": termination,
            "opening_name": context.summary.metadata.opening
        }
        await self._client.queue_item(QueuedGameStat(game_stat_payload=black_payload))
        
        await self._client.queue_item(QueuedGameComplete(game_id=context.game_id))
        return context

class AnnotationStage(ProcessingStage):
    """Adds all generated analysis as comments to the PGN game object."""
    def __init__(self, annotator: "AnnotatorClient", client: "PersistenceClient"):
        self._annotator = annotator
        self._client = client
    
    @trace_stage
    async def execute(self, context: GameContext) -> GameContext:
        if not context.enriched_analyses:
            return context
        
        # Start from the root node of the game.
        current_node = context.raw_game
        for enriched_result in context.enriched_analyses:
            # Advance to the node corresponding to the move being annotated.
            current_node = current_node.next()
            if current_node is None:
                break
            user_comment, clk_tag = self._annotator.prepare_comment_parts(current_node.comment)
            anno_ctx = build_anno_ctx(
                enriched_analysis=enriched_result, user_comment=user_comment,
                clk_tag=clk_tag, settings=context.settings
            )
            current_node.comment = self._annotator.generate_pgn_node_comment(anno_ctx)
            
        context.annotated_game = context.raw_game
        
        # --- NEW: Queue the fully annotated game PGN for persistence ---
        if context.annotated_game:
            pgn_text = str(context.annotated_game)
            payload = QueuedAnnotatedGame(game_id=context.game_id, pgn_text=pgn_text)
            logger.info(
                "AnnotationStage: Preparing to queue annotated game.",
                game_id=context.game_id,
                pgn_text_len=len(pgn_text)
            )
            await self._client.queue_item(payload)
            logger.info(
                "AnnotationStage: Successfully queued annotated game for persistence.",
                game_id=context.game_id
            )
            
        return context

async def run_game_processing_pipeline(
    context: GameContext,
    stages: List[ProcessingStage],
    shutdown_event: asyncio.Event
) -> GameContext:
    """Executes a list of processing stages sequentially on a GameContext."""
    current_context = context
    for stage in stages:
        # Check for shutdown signal before executing the next stage.
        if shutdown_event.is_set():
            logger.warning("Shutdown signaled, aborting game processing pipeline.", game_id=context.game_id)
            # Mark the context to prevent it from being counted as a success
            current_context.summary = None
            current_context.annotated_game = None
            break
        
        current_context = await stage.execute(current_context)
    return current_context