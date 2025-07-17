"""
Centralized Prometheus metrics definitions for the Chess Analyzer application.

This module uses the prometheus-client library to define all metrics that will
be exposed by the application for monitoring and alerting. Grouping them here
provides a single, clear overview of the application's instrumentation points.
"""
from prometheus_client import Counter, Gauge, Histogram

# A common prefix for all application-specific metrics.
PREFIX = "chess_analyzer"

# --- Game Processing Metrics ---

GAMES_PROCESSED_TOTAL = Counter(
    f"{PREFIX}_games_processed_total",
    "Total number of games successfully processed and written to output.",
)

GAMES_SKIPPED_TOTAL = Counter(
    f"{PREFIX}_games_skipped_total",
    "Total number of games skipped for any reason.",
    ["reason"],  # e.g., reason="already_processed", "no_target_player"
)

GAMES_WITH_ERRORS_TOTAL = Counter(
    f"{PREFIX}_games_with_errors_total",
    "Total number of games that failed processing due to a critical error.",
    ["error_type"], # e.g., error_type="PgnIntegrityError", "EngineAnalysisError"
)

GAME_PROCESSING_DURATION_SECONDS = Histogram(
    f"{PREFIX}_game_processing_duration_seconds",
    "Histogram of the time taken to fully process a single game.",
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, float("inf"))
)

# --- Engine & Cache Metrics ---

FEN_ANALYSES_TOTAL = Counter(
    f"{PREFIX}_fen_analyses_total",
    "Total number of FEN analyses requested.",
    ["source"],  # e.g., source="cache_hit", "engine_run"
)

ENGINE_ANALYSIS_DURATION_SECONDS = Histogram(
    f"{PREFIX}_engine_analysis_duration_seconds",
    "Histogram of the time taken for an engine to analyze a single FEN."
)

ENGINE_INSTANCES_IN_POOL = Gauge(
    f"{PREFIX}_engine_instances_in_pool",
    "Current number of healthy engine instances in the pool."
)

ENGINE_INSTANCES_FAILED_TOTAL = Counter(
    f"{PREFIX}_engine_instances_failed_total",
    "Total number of engine instances that failed and were retired."
)

# --- Persistence & Queue Metrics ---

PERSISTENCE_QUEUE_DEPTH = Gauge(
    f"{PREFIX}_persistence_queue_depth",
    "Current number of items in the training data persistence queue.",
)

DB_BATCH_WRITE_DURATION_SECONDS = Histogram(
    f"{PREFIX}_db_batch_write_duration_seconds",
    "Histogram of the time taken to write a batch of data to a database.",
    ["db_type"], # e.g., db_type="cache", "training"
)

DB_TRANSIENT_ERRORS_TOTAL = Counter(
    f"{PREFIX}_db_transient_errors_total",
    "Total number of transient database errors that triggered a retry.",
    ["db_type"] # e.g., db_type="cache", "training"
)