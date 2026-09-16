"""
=============================================================================
Packaging Analysis & Multi-Image Pipeline Package
=============================================================================
Provides:
  1. ProductLabelAggregator:
     - Groq LLM-powered multi-angle information synthesizer.
     - Merges transcripts across front, back, sides, and bottom stamps into
       standardized LMPC / FSSAI regulatory JSON sections.
     - Generates executive Markdown compliance summaries.
  2. UnifiedPackagingPipeline:
     - Master controller orchestrating Preprocessing -> Vision OCR -> Multi-View
       Aggregation -> Result Persistence.
=============================================================================
"""

from .aggregator import ProductLabelAggregator
from .unified_pipeline import UnifiedPackagingPipeline

__all__ = [
    "ProductLabelAggregator",
    "UnifiedPackagingPipeline"
]
