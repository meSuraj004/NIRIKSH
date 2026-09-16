"""
=============================================================================
OCR (Optical Character Recognition) Package
=============================================================================
Provides:
  1. GroqKeyManager & key_manager:
     - Thread-safe Groq API key pool management.
     - Dynamic rate-limit handling with automatic cooldown & key rotation.
  2. FastGroqVisionOCR:
     - Sub-2-second layout-preserving OCR via Qwen-3.8-27B on Groq LPUs.
     - Specialized in fine print, dot-matrix stamps, and multilingual text.
  3. EnhancedPackagingOCR:
     - 100% offline local PaddleOCR v4 engine.
     - Curved edge polygon perspective rectification and lateral lighting ramp.
     - 2D spatial layout reconstruction & table alignment.
  4. UnifiedOCR:
     - Engine abstraction layer enabling seamless switching between GROQ and PADDLE.
=============================================================================
"""

from .key_manager import GroqKeyManager, key_manager
from .groq_ocr import FastGroqVisionOCR
from .paddle_ocr import EnhancedPackagingOCR
from .unified_ocr import UnifiedOCR

__all__ = [
    "GroqKeyManager",
    "key_manager",
    "FastGroqVisionOCR",
    "EnhancedPackagingOCR",
    "UnifiedOCR"
]
