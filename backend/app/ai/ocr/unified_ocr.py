"""
=============================================================================
Unified OCR Module for Product Packaging
=============================================================================
Module: ocr.unified_ocr
Purpose:
  Provides a single abstracted OCR interface allowing seamless runtime switching
  between cloud-based Vision-Language OCR (Groq) and local neural OCR (PaddleOCR).

Supported Engines:
  1. "GROQ": Ultra-fast Vision-Language OCR (Qwen 3.8-27B on Groq LPUs).
             Exceptional recognition of dot-matrix stamped dates and fine print.
  2. "PADDLE": 100% Offline neural OCR (PaddleOCR v4 DBNet).
               Generates exact polygon bounding boxes, line heights, and coordinates.

Usage:
  from ocr import UnifiedOCR

  ocr = UnifiedOCR(engine_mode="GROQ")  # or "PADDLE"
  result = ocr.process_image("path/to/image.png")
  print(result["text_lines"])
=============================================================================
"""

import os
import cv2
import time
from typing import Union, List, Dict, Any, Optional

from .groq_ocr import FastGroqVisionOCR
from .paddle_ocr import EnhancedPackagingOCR

DEFAULT_OCR_ENGINE = "GROQ"


class UnifiedOCR:
    """
    Unified OCR Manager that switches dynamically between Groq Vision and Local PaddleOCR.
    """

    def __init__(self, engine_mode: str = DEFAULT_OCR_ENGINE, groq_api_key: Optional[str] = None):
        """
        Initializes the Unified OCR manager.

        Args:
            engine_mode: Initial engine choice ('GROQ' or 'PADDLE').
            groq_api_key: Optional explicit Groq API key.
        """
        self.engine_mode = engine_mode.upper()
        self._paddle_engine = None
        self._groq_engine = None
        self.groq_api_key = groq_api_key

        print(f"[INFO] Initializing Unified OCR with active engine: {self.engine_mode}")
        self._load_engine()

    def set_engine(self, engine_mode: str):
        """Switches the active OCR engine at runtime ('GROQ' or 'PADDLE')."""
        self.engine_mode = engine_mode.upper()
        print(f"[INFO] Switched OCR Engine to: {self.engine_mode}")
        self._load_engine()

    def _load_engine(self):
        """Lazy loads the selected engine to optimize memory and startup time."""
        if self.engine_mode == "GROQ":
            if self._groq_engine is None:
                self._groq_engine = FastGroqVisionOCR()
        elif self.engine_mode == "PADDLE":
            if self._paddle_engine is None:
                self._paddle_engine = EnhancedPackagingOCR(use_gpu=True, drop_score=0.20)
        else:
            raise ValueError(f"Unsupported OCR engine mode: '{self.engine_mode}'. Use 'GROQ' or 'PADDLE'.")

    def process_image(self, image_input: Union[str, cv2.Mat, Any]) -> Dict[str, Any]:
        """
        Processes an image using the active engine and returns a standardized OCR dictionary.

        Args:
            image_input: File path or OpenCV image array.

        Returns:
            Dict[str, Any]: Standardized OCR schema containing engine, latency, text_lines, full_text, detections.
        """
        if isinstance(image_input, str):
            if not os.path.exists(image_input):
                raise FileNotFoundError(f"Image not found: {image_input}")
            img_bgr = cv2.imread(image_input)
            if img_bgr is None:
                raise ValueError(f"Could not read image from: {image_input}")
        else:
            img_bgr = image_input

        t0 = time.time()

        if self.engine_mode == "GROQ":
            raw_res = self._groq_engine.extract_text(img_bgr)
            elapsed = raw_res.get("latency_sec", round(time.time() - t0, 2))

            return {
                "engine": "GROQ",
                "latency_sec": elapsed,
                "total_lines": raw_res.get("total_lines", len(raw_res.get("text_lines", []))),
                "text_lines": raw_res.get("text_lines", []),
                "full_text": raw_res.get("full_text", ""),
                "token_usage": raw_res.get("token_usage", {}),
                "detections": []
            }

        elif self.engine_mode == "PADDLE":
            raw_res = self._paddle_engine.process_image(
                img_bgr,
                enable_tiling=True,
                tile_size=(720, 720),
                enable_multipass=True
            )
            elapsed = round(time.time() - t0, 2)

            return {
                "engine": "PADDLE",
                "latency_sec": elapsed,
                "total_lines": raw_res.get("total_items_detected", len(raw_res.get("text_lines", []))),
                "text_lines": raw_res.get("text_lines", []),
                "full_text": raw_res.get("full_text", ""),
                "detections": raw_res.get("detections", []),
                "token_usage": {}
            }

    def render_visual_overlay(self, image_bgr: cv2.Mat, result: Dict[str, Any]) -> cv2.Mat:
        """
        Renders visual bounding boxes (for Paddle) or telemetry badge (for Groq).
        """
        canvas = image_bgr.copy()

        if result["engine"] == "PADDLE" and result.get("detections"):
            return self._paddle_engine.render_visual_overlay(canvas, result["detections"])

        elif result["engine"] == "GROQ":
            h, w = canvas.shape[:2]
            overlay = canvas.copy()
            cv2.rectangle(overlay, (0, 0), (w, 40), (20, 20, 20), -1)
            cv2.addWeighted(overlay, 0.7, canvas, 0.3, 0, canvas)

            label = f"Engine: GROQ Vision | Lines: {result['total_lines']} | Latency: {result['latency_sec']}s"
            cv2.putText(canvas, label, (15, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)
            return canvas

        return canvas
