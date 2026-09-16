"""
=============================================================================
Vision & Image Preprocessing Package
=============================================================================
Provides:
  1. PackagingImagePreprocessor:
     - YOLOv8 Object Localization & Margin Expansion.
     - 2x Super-Resolution Upscaling.
     - Bilateral Edge-Preserving Denoising.
     - LAB CLAHE Contrast Normalization.
     - Gamma Correction & Stroke Sharpening Kernel.
     - Laplacian Variance Sharpness & Lighting Quality Metrics.

  2. CameraManager & Stream Utilities:
     - Thread-safe OpenCV video streaming.
     - Real-time YOLO tracking + Angle/Box Stability filters.
     - Interactive visual HUD overlays & MJPEG frame generation.
=============================================================================
"""

from .preprocessor import PackagingImagePreprocessor
from .camera import (
    CameraManager,
    camera_manager,
    AngleSmoother,
    BoxStability,
    GuidanceStabilizer
)

__all__ = [
    "PackagingImagePreprocessor",
    "CameraManager",
    "camera_manager",
    "AngleSmoother",
    "BoxStability",
    "GuidanceStabilizer"
]
