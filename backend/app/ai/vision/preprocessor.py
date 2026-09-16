"""
=============================================================================
Vision Preprocessing & Image Enhancement Pipeline
=============================================================================
Module: vision.preprocessor
Purpose:
  Provides standardized ingestion, object localization, and high-precision
  multi-stage enhancement for product packaging images (bottles, cartons, pouches).

Enhancement Pipeline Stages:
  1. Object Localization & Cropping:
     - Detects packaging ROI using YOLOv8 segmentation/detection.
     - Applies safe margin padding (+12%) to prevent clipping peripheral text
       (dates, MRP, barcodes, fssai logos).
  2. Super-Resolution Upscaling:
     - 2x Bicubic upscaling for low-res captures (< 1200px width) to double
       pixel density for fine dot-matrix and legal micro-text.
  3. Bilateral Edge-Preserving Denoising:
     - Suppresses sensor noise and texture grain while preserving crisp font edges.
  4. LAB-Space Dynamic Contrast Enhancement (CLAHE):
     - Normalizes uneven lighting and shadows without character haloing.
  5. Unsharp Masking & Gamma Correction:
     - Gamma correction (gamma=1.2) enhances faint printed stamps.
     - Custom 3x3 high-pass filter sharpens character strokes.
  6. Quality Assessment:
     - Computes Laplacian variance for blur detection.
     - Computes luminance & specular glare ratios for lighting verification.
=============================================================================
"""

import os
import cv2
import numpy as np
import time
from datetime import datetime
from typing import Union, List, Dict, Tuple, Optional, Any
import torch

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

# Default path constants


class PackagingImagePreprocessor:
    """
    Standardized Preprocessor for Product Packaging Images.
    Prepares raw camera frames or uploaded images for optimal downstream OCR accuracy.
    """

    def __init__(self, model_path: str, save_dir: str):
        """
        Initializes the image preprocessor and loads the YOLO object detection model.

        Args:
            model_path: Path or filename for the YOLOv8 segmentation/detection model.
            save_dir: Directory path where enhanced images will be saved.
        """
        self.save_dir = save_dir
        os.makedirs(self.save_dir, exist_ok=True)

        # Device selection: Use CUDA GPU if available for accelerated inference
        if torch.cuda.is_available():
            self.device = 0
            self.use_half = True
        else:
            self.device = "cpu"
            self.use_half = False

        # Load YOLO model instance
        self.model = None
        self._load_yolo_model(model_path)

    def _load_yolo_model(self, model_path: str):
        """
        Loads the YOLO model if available; gracefully falls back to full-image processing if missing.

        Args:
            model_path: Model weights file path (e.g., 'yolov8n-seg.pt' or 'yolov8n.pt').
        """
        if YOLO is None:
            print("[Preprocessor] Ultralytics YOLO package not installed. Operating in full-frame mode.")
            return

        resolved_path = model_path
        if not os.path.exists(resolved_path):
            # Check relative to SIH project root directory
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            candidate = os.path.join(root_dir, model_path)
            if os.path.exists(candidate):
                resolved_path = candidate

        try:
            if os.path.exists(resolved_path):
                self.model = YOLO(resolved_path)
                print(f"[Preprocessor] YOLO model loaded from: {resolved_path}")
            else:
                # Fallback attempt for standard weights
                print(f"[Preprocessor] Model not found at '{model_path}'. Attempting default 'yolov8n.pt'...")
                self.model = YOLO("yolov8n.pt")
        except Exception as e:
            print(f"[WARN] Could not load YOLO model ({e}). Will process images in full-frame fallback mode.")
            self.model = None

    @staticmethod
    def check_sharpness(image: np.ndarray) -> Tuple[float, bool]:
        """
        Calculates the Laplacian variance score on an image ROI to assess focus sharpness.

        Algorithm:
          1. Converts the image to single-channel 8-bit grayscale.
          2. Computes the 2nd order spatial derivative using the 64-bit float Laplacian kernel.
          3. Measures the variance: sharp images with defined text edges yield high variance.

        Args:
            image: Input image (BGR or Grayscale numpy array).

        Returns:
            Tuple[float, bool]: (laplacian_variance_score, is_sharp_boolean)
        """
        if image is None or image.size == 0:
            return 0.0, False

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        is_sharp = score >= 65.0
        return score, is_sharp

    @staticmethod
    def check_lighting(image: np.ndarray) -> Tuple[str, float]:
        """
        Evaluates the illumination balance and specular glare on the packaging image.

        Metrics:
          - Mean brightness: Average pixel luminance (0 to 255).
          - Glare ratio: Fraction of over-saturated white pixels (> 245) indicative of reflections.

        Args:
            image: Input image (BGR numpy array).

        Returns:
            Tuple[str, float]: (lighting_status_string, mean_brightness_value)
        """
        if image is None or image.size == 0:
            return "NORMAL", 128.0

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        mean_brightness = float(np.mean(gray))
        glare_ratio = float(np.mean(gray > 245))

        if mean_brightness < 40:
            return "TOO DARK", mean_brightness
        elif glare_ratio > 0.09:
            return "GLARE DETECTED", mean_brightness
        else:
            return "GOOD", mean_brightness

    @staticmethod
    def enhance_image(crop_image: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Executes the High-Precision Multi-Stage Label Enhancement pipeline.

        Produces two output image representations:
          1. Color-Enhanced Image: Preserves vibrant packaging colors and brand artwork.
          2. OCR-Ready Image: Maximizes stroke contrast, flattens glare, and elevates micro-text.

        Args:
            crop_image: Cropped packaging region (BGR numpy array).

        Returns:
            Tuple[np.ndarray, np.ndarray]: (enhanced_color_bgr, ocr_ready_grayscale)
        """
        if crop_image is None or crop_image.size == 0:
            return crop_image, crop_image

        h, w = crop_image.shape[:2]

        # -------------------------------------------------------------
        # Step 1: 2x Super-Resolution Upscaling
        # Doubles pixel density for fine text and dot-matrix stamps
        # -------------------------------------------------------------
        scale = 2 if w < 1200 else 1
        if scale > 1:
            upscaled = cv2.resize(crop_image, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)
        else:
            upscaled = crop_image.copy()

        # -------------------------------------------------------------
        # Step 2: Bilateral Denoising
        # Smooths surface texture/noise while keeping sharp letter boundaries
        # -------------------------------------------------------------
        denoised = cv2.bilateralFilter(upscaled, d=7, sigmaColor=35, sigmaSpace=35)

        # -------------------------------------------------------------
        # Step 3: LAB Space CLAHE Color Enhancement & Unsharp Masking
        # Enhances local luminance (L channel) without shifting chromaticity (A/B)
        # -------------------------------------------------------------
        lab = cv2.cvtColor(denoised, cv2.COLOR_BGR2LAB)
        l_chan, a_chan, b_chan = cv2.split(lab)
        clahe_color = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_enhanced = clahe_color.apply(l_chan)
        color_enhanced = cv2.cvtColor(cv2.merge((l_enhanced, a_chan, b_chan)), cv2.COLOR_LAB2BGR)

        # Subtle unsharp masking for edge crispness
        gaussian_color = cv2.GaussianBlur(color_enhanced, (0, 0), sigmaX=1.5)
        color_final = cv2.addWeighted(color_enhanced, 1.4, gaussian_color, -0.4, 0)

        # -------------------------------------------------------------
        # Step 4: High-Definition OCR Grayscale Conversion
        # -------------------------------------------------------------
        gray = cv2.cvtColor(color_final, cv2.COLOR_BGR2GRAY)

        # Gamma correction: Expands dynamic range for faint dot-matrix stamps (MFD/EXP/MRP)
        gamma = 1.2
        inv_gamma = 1.0 / gamma
        lut_table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in np.arange(0, 256)]).astype('uint8')
        gamma_corrected = cv2.LUT(gray, lut_table)

        # Adaptive Local Contrast (CLAHE on grayscale)
        clahe_ocr = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
        ocr_clahe = clahe_ocr.apply(gamma_corrected)

        # Text Stroke Sharpening Kernel (emphasizes stroke definition)
        kernel = np.array([
            [0, -0.4, 0],
            [-0.4, 2.6, -0.4],
            [0, -0.4, 0]
        ], dtype=np.float32)
        ocr_final = cv2.filter2D(ocr_clahe, -1, kernel)

        return color_final, ocr_final

    def detect_and_crop(self, image_bgr: np.ndarray, margin_ratio: float = 0.12) -> Tuple[np.ndarray, dict]:
        """
        Detects the product packaging boundary and crops the region of interest.
        Expands the bounding box by margin_ratio (default 12%) to ensure peripheral
        text (MRP, batch codes, dates, regulatory marks) is not clipped.

        Args:
            image_bgr: Full input image (BGR numpy array).
            margin_ratio: Padding ratio to expand the bounding box outwards.

        Returns:
            Tuple[np.ndarray, dict]: (cropped_image_bgr, detection_metadata_dict)
        """
        h, w = image_bgr.shape[:2]
        best_box = None
        best_class = "Product Package"
        best_conf = 0.0

        # Perform YOLO inference if model is loaded
        if self.model is not None:
            try:
                results = self.model(image_bgr, verbose=False, conf=0.20, imgsz=640, device=self.device)
                if results and len(results) > 0 and results[0].boxes is not None and len(results[0].boxes) > 0:
                    boxes = results[0].boxes
                    # Find candidate with highest confidence or largest area
                    max_area = 0
                    for box in boxes:
                        coords = box.xyxy[0].cpu().numpy().astype(int)
                        conf = float(box.conf[0].cpu().numpy())
                        cls_id = int(box.cls[0].cpu().numpy())
                        cls_name = results[0].names.get(cls_id, "Product")

                        bx1, by1, bx2, by2 = coords
                        area = (bx2 - bx1) * (by2 - by1)
                        if area > max_area and area > (w * h * 0.01):
                            max_area = area
                            best_box = (int(bx1), int(by1), int(bx2), int(by2))
                            best_class = cls_name
                            best_conf = conf
            except Exception as e:
                print(f"[Preprocessor] YOLO detection error ({e}). Falling back to full frame.")

        # Fallback if no valid object detected
        if best_box is None:
            return image_bgr, {
                "detected": False,
                "class_name": best_class,
                "confidence": 0.0,
                "box": (0, 0, w, h),
                "full_frame_used": True
            }

        # Apply safety margin expansion
        x1, y1, x2, y2 = best_box
        bw, bh = x2 - x1, y2 - y1
        pad_x = int(bw * margin_ratio)
        pad_y = int(bh * margin_ratio)

        x1_pad = max(0, x1 - pad_x)
        y1_pad = max(0, y1 - pad_y)
        x2_pad = min(w, x2 + pad_x)
        y2_pad = min(h, y2 + pad_y)

        cropped = image_bgr[y1_pad:y2_pad, x1_pad:x2_pad].copy()
        if cropped.size == 0:
            return image_bgr, {"detected": False, "box": (0, 0, w, h), "full_frame_used": True}

        return cropped, {
            "detected": True,
            "class_name": best_class,
            "confidence": round(best_conf, 2),
            "original_box": best_box,
            "box": (x1_pad, y1_pad, x2_pad, y2_pad),
            "full_frame_used": False
        }

    def process_image(
        self,
        image_input: Union[str, np.ndarray],
        source_label: str = "upload",
        auto_crop: bool = True
    ) -> Dict[str, Any]:
        """
        Unified image processing entrypoint. Accepts a file path or BGR numpy array.
        Executes localization, quality checks, multi-stage enhancement, and disk persistence.

        Args:
            image_input: File path (str) or BGR image (np.ndarray).
            source_label: Identifier label (e.g. 'view_1', 'front', 'upload').
            auto_crop: Whether to perform YOLO object detection and ROI cropping.

        Returns:
            Dict[str, Any]: Structured dictionary with processed metadata, quality scores, and file paths.
        """
        original_path = None
        if isinstance(image_input, str):
            original_path = os.path.abspath(image_input)
            if not os.path.exists(original_path):
                raise FileNotFoundError(f"Image not found at: {original_path}")
            raw_bgr = cv2.imread(original_path)
            if raw_bgr is None:
                raise ValueError(f"Failed to read image from: {original_path}")
        else:
            raw_bgr = image_input

        orig_h, orig_w = raw_bgr.shape[:2]

        # -------------------------------------------------------------
        # 1. Object Localization & Bounding Box Cropping
        # -------------------------------------------------------------
        if auto_crop:
            cropped_bgr, detection_info = self.detect_and_crop(raw_bgr)
        else:
            cropped_bgr = raw_bgr
            detection_info = {"detected": False, "box": (0, 0, orig_w, orig_h), "full_frame_used": True}

        # -------------------------------------------------------------
        # 2. Quality Metrics Assessment
        # -------------------------------------------------------------
        sharpness, is_sharp = self.check_sharpness(cropped_bgr)
        lighting, brightness = self.check_lighting(cropped_bgr)

        # -------------------------------------------------------------
        # 3. Multi-Stage High-Precision Enhancement
        # -------------------------------------------------------------
        enhanced_color, ocr_ready = self.enhance_image(cropped_bgr)

        # -------------------------------------------------------------
        # 4. Save Enhanced Artifacts to Disk
        # -------------------------------------------------------------
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
        class_clean = detection_info.get("class_name", "product").replace(" ", "_")

        color_filename = f"{source_label}_{class_clean}_{timestamp}_color.png"
        ocr_filename = f"{source_label}_{class_clean}_{timestamp}_ocr.png"

        color_path = os.path.join(self.save_dir, color_filename)
        ocr_path = os.path.join(self.save_dir, ocr_filename)

        cv2.imwrite(color_path, enhanced_color)
        cv2.imwrite(ocr_path, ocr_ready)

        return {
            "source_path": original_path,
            "source_type": source_label,
            "original_resolution": (orig_w, orig_h),
            "processed_resolution": (enhanced_color.shape[1], enhanced_color.shape[0]),
            "detection": detection_info,
            "quality": {
                "sharpness_score": round(sharpness, 1),
                "is_sharp": is_sharp,
                "lighting_status": lighting,
                "mean_brightness": round(brightness, 1)
            },
            "saved_color_path": color_path,
            "saved_ocr_path": ocr_path,
            "enhanced_color_img": enhanced_color,
            "ocr_ready_img": ocr_ready
        }

    def process_batch(self, image_inputs: List[Union[str, np.ndarray]], source_label: str = "batch") -> List[Dict[str, Any]]:
        """
        Sequentially processes a list of images.

        Args:
            image_inputs: List of image file paths or numpy arrays.
            source_label: Base label prefix for batch indexing.

        Returns:
            List[Dict[str, Any]]: List of processed image results.
        """
        results = []
        for i, img in enumerate(image_inputs):
            res = self.process_image(img, source_label=f"{source_label}_{i+1}")
            results.append(res)
        return results
