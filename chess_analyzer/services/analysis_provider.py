# chess_analyzer/services/analysis_provider.py
"""
Provides a high-level service for fetching engine analyses.

This module contains the `AnalysisProvider`, which acts as a coordinator for
obtaining engine evaluations. It implements the "cache-aside" pattern:
1. It first checks a `CacheService` for a pre-computed analysis.
2. On a cache miss, it calls an `EngineService` to perform the analysis.
3. It then stores the new result in the cache for future requests.

This decouples the main application logic from the details of caching and
engine interaction, providing a single, simple interface for getting analysis results.
"""

from typing import Dict, List, TYPE_CHECKING

import structlog

from chess_analyzer.types import AnalysisResult, CacheKey, FEN, EngineService

if TYPE_CHECKING:
    from chess_analyzer.config.settings import AnalysisSettings
    from chess_analyzer.types import CacheService

logger = structlog.get_logger(__name__)


class AnalysisProvider:
    """A coordinator service that provides engine analyses using a cache-aside strategy."""

    def __init__(self, cache_service: "CacheService", settings: "AnalysisSettings"):
        """
        Initializes the AnalysisProvider.

        Args:
            cache_service: An object conforming to the `CacheService` protocol.
            settings: The application's analysis settings (depth, multipv, etc.).
        """
        self._cache = cache_service
        self._settings = settings

    async def get_analyses_for_fens(
        self, fens: List[FEN], engine: EngineService
    ) -> Dict[FEN, AnalysisResult]:
        """
        Gets engine analyses for a list of FENs, utilizing a cache.

        This method orchestrates the cache check, engine analysis for misses,
        and cache update.

        Args:
            fens: A list of FEN strings to analyze.
            engine: An acquired `EngineService` instance to use for new analyses.

        Returns:
            A dictionary mapping each requested FEN to its `AnalysisResult`.
        """
        if not fens:
            return {}

        engine_id = await engine.get_engine_identifier()
        
        # Create a list of cache keys based on the FENs and current analysis settings.
        all_cache_keys = [
            CacheKey(
                fen=fen,
                depth=self._settings.depth,
                multipv=self._settings.multipv,
                engine_id=engine_id,
            )
            for fen in fens
        ]

        logger.debug("Checking cache for FENs.", num_fens=len(fens))
        cached_results = await self._cache.get_cached_analyses_batch(all_cache_keys)
        logger.debug("Cache check complete.", num_hits=len(cached_results))

        # Determine which keys were not found in the cache.
        missed_keys = [key for key in all_cache_keys if key not in cached_results]

        # If all results were found in the cache, we can return immediately.
        if not missed_keys:
            return {key.fen: result for key, result in cached_results.items()}

        # For the cache misses, run a new engine analysis.
        missed_fens = [key.fen for key in missed_keys]
        logger.info("Requesting new engine analysis.", num_cache_misses=len(missed_fens))
        new_engine_analysis = await engine.analyze_fens_batch(missed_fens)

        # Prepare the new results to be stored in the cache.
        results_to_store: Dict[CacheKey, AnalysisResult] = {}
        key_map = {key.fen: key for key in missed_keys}
        for fen, engine_lines in new_engine_analysis.items():
            if fen in key_map:
                results_to_store[key_map[fen]] = AnalysisResult(top_engine_lines=engine_lines)
        
        if results_to_store:
            logger.debug("Storing new results in cache.", num_new_results=len(results_to_store))
            await self._cache.store_analyses_batch(results_to_store)
        
        # Combine the cached results with the newly generated results.
        final_results_by_key = cached_results | results_to_store
        
        # Return a dictionary mapping FEN to result, as the caller expects.
        return {key.fen: result for key, result in final_results_by_key.items()}