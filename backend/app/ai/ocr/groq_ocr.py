"""
=============================================================================
Ultra-Fast Groq Vision OCR Engine (Qwen 3.8-27B)
=============================================================================
Module: ocr.groq_ocr
Purpose:
  Provides sub-2-second layout-preserving OCR on packaging images using
  Qwen-3.8-27B vision-language model executed on Groq LPU hardware with
  automatic multi-key rate-limit rotation.

Key Capabilities:
  1. Faithful Character Preservation:
     - Captures dot-matrix stamped numbers (MFD, EXP, BATCH, MRP) accurately.
     - Detects fine regulatory micro-text (4pt-6pt fonts) and multilingual scripts.
  2. Spatial Layout Preservation:
     - Maintains tabular column alignment (Nutrition facts, tables) and line breaks.
  3. Low Latency:
     - Encodes images to optimized 960px base64 JPEG payload (quality 88) for rapid
       network transfer and sub-2s inference.
=============================================================================
"""

import os
import cv2
import json
import base64
import time
from typing import Union, List, Dict, Any, Optional
from groq import Groq

from .key_manager import key_manager, GroqKeyManager
from app.config import settings


# Model & Encoding Constants
DEFAULT_VISION_MODEL = settings.ocr_model
OPTIMAL_MAX_DIM = 960          # Image dimension limit for optimal OCR legibility vs latency
JPEG_QUALITY = 88              # High quality compression preserving fine character stems
MAX_COMPLETION_TOKENS = 1200   # Token limit accommodating dense nutrition & legal panels


class FastGroqVisionOCR:
    """
    Ultra-low latency, layout-preserving Groq Vision OCR Engine with Multi-Key Rotation.
    """

    def __init__(self, key_mgr: Optional[GroqKeyManager] = None, model: str = DEFAULT_VISION_MODEL):
        """
        Initializes the Groq Vision OCR engine.

        Args:
            key_mgr: GroqKeyManager instance for key pooling (defaults to global key_manager).
            model: Groq vision model identifier (default: 'qwen/qwen3.8-27b').
        """
        self.key_manager = key_mgr or key_manager
        self.model = model

    def _encode_image(self, image_input: Union[str, cv2.Mat, Any], max_dim: int = OPTIMAL_MAX_DIM) -> str:
        """
        Loads and encodes an image into a compact JPEG base64 payload.

        Args:
            image_input: File path (str) or BGR image (cv2.Mat / np.ndarray).
            max_dim: Maximum width or height constraint.

        Returns:
            str: Base64-encoded JPEG image string.
        """
        if isinstance(image_input, str):
            if not os.path.exists(image_input):
                raise FileNotFoundError(f"Image not found: {image_input}")
            img = cv2.imread(image_input)
            if img is None:
                raise ValueError(f"Could not read image: {image_input}")
        else:
            img = image_input

        h, w = img.shape[:2]
        if max(h, w) > max_dim:
            scale = max_dim / float(max(h, w))
            new_w, new_h = int(w * scale), int(h * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
        _, buffer = cv2.imencode('.jpg', img, encode_param)
        return base64.b64encode(buffer).decode('utf-8')

    def extract_text(self, image_input: Union[str, cv2.Mat, Any]) -> Dict[str, Any]:
        """
        Runs layout-preserving OCR on a product packaging image.

        Args:
            image_input: File path or OpenCV image array.

        Returns:
            Dict[str, Any]: Dictionary containing full_text, text_lines, token_usage, latency_sec.
        """
        t0 = time.time()
        base64_image = self._encode_image(image_input)

        # Pure OCR Layout-Preserving System Prompt
        system_instruction = (
            "You are a specialized High-Precision Optical Character Recognition (OCR) Engine "
            "for consumer product packaging and legal metrology compliance verification.\n"
            "Task: Transcribe ALL text, numbers, symbols, barcodes, and tables visible in the image verbatim.\n"
            "Rules:\n"
            "1. Transcribe line-by-line exactly as written on the package.\n"
            "2. Pay special attention to dot-matrix stamps (MFD, EXP, USE BY, BATCH NO, LOT, MRP, Rs, ₹).\n"
            "3. Extract all fine legal print, FSSAI numbers, ingredient lists, net quantities, and addresses.\n"
            "4. For tables (Nutrition Information), preserve columns using pipe '|' or clear spacing.\n"
            "5. Do NOT add conversational commentary, summaries, or Markdown bolding (**). Output raw transcribed text only."
        )

        user_content = [
            {
                "type": "text",
                "text": "Extract and transcribe all text from this product packaging image with complete accuracy."
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                }
            }
        ]

        def call_groq(client: Groq):
            return client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.0,  # Zero temperature for maximum deterministic OCR precision
                max_completion_tokens=MAX_COMPLETION_TOKENS
            )

        # Execute via KeyManager to handle rate-limiting and rotation automatically
        response = self.key_manager.execute_with_retry(call_groq)
        latency = round(time.time() - t0, 2)

        raw_text = response.choices[0].message.content or ""
        text_lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

        usage = {}
        if hasattr(response, "usage") and response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }

        return {
            "engine": "FastGroqVisionOCR",
            "model": self.model,
            "latency_sec": latency,
            "total_lines": len(text_lines),
            "text_lines": text_lines,
            "full_text": raw_text,
            "token_usage": usage
        }
