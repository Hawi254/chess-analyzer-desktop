# chess_analyzer/orchestration/pipeline_factory.py
"""
A factory for creating the game processing pipeline.

This module's sole responsibility is to construct and return the list of
`ProcessingStage` objects in the correct sequential order. This centralization
breaks potential circular dependencies between the main orchestrator (which needs
the pipeline) and the stage implementations (which need services created by the
orchestrator). It acts as a "late binding" mechanism.
"""

from typing import Any, Dict, List

from chess_analyzer.orchestration.pipeline_stages import (
    AnalysisStage, AnnotationStage, ClassificationStage, InitialSetupStage,
    PersistenceStage, SummaryStage
)
from chess_analyzer.types import ProcessingStage

def create_pipeline(services: Dict[str, Any]) -> List[ProcessingStage]:
    """
    Builds and returns the list of processing stages in their correct execution order.
    """
    return [
        # --- CORRECTED: Removed the unused persistence_client dependency ---
        InitialSetupStage(services["pgn_parser_func"]),
        
        AnalysisStage(services["analysis_provider"]),
        ClassificationStage(services["move_classifier"], services["persistence_client"]),
        PersistenceStage(services["persistence_client"]),
        AnnotationStage(services["annotator_client"], services["persistence_client"]),
        SummaryStage(services["narrative_generator_func"], services["persistence_client"]),
    ]