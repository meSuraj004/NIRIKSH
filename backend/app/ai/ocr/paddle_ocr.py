"""
=============================================================================
Enhanced Packaging OCR Pipeline (Local Offline PaddleOCR Specialist)
=============================================================================
Module: ocr.paddle_ocr
Purpose:
  Provides 100% offline, high-accuracy multi-scale packaging OCR using PaddleOCR v4.
  Specialized for curved surfaces, reflective plastic, fine legal print, and tabular text.

Key Pipeline Steps:
  1. Illumination Normalization & Cylindrical Lateral Ramp:
     - Normalizes uneven lighting and curved lateral shadows along container edges.
  2. Multi-Pass Scanning:
     - Pass A: Global high-resolution DBNet detection (det_limit_side_len=1920).
     - Pass B: Lower-region fine-print deep scan for micro-text and statutory notices.
     - Pass C: High-contrast gamma pass for stamped dot-matrix dates & batch numbers.
  3. Perspective Rectification (Dewarping):
     - 4-point perspective transformation flattens curved text on cylindrical bottles.
  4. 2D Spatial Layout Reconstruction:
     - Clusters detected tokens into natural lines and aligned columns for tables.
=============================================================================
"""

import os
import sys
import site
import cv2
import numpy as np
import math
from difflib import SequenceMatcher
from typing import List, Dict, Tuple, Optional, Any

PaddleOCR = None

def _ensure_paddle_dlls():
    """Ensure Windows discovers Paddle and MKL runtime DLLs on demand."""
    global PaddleOCR
    if PaddleOCR is not None:
        return
    for p in site.getsitepackages():
        paddle_libs = os.path.join(p, 'paddle', 'libs')
        if os.path.exists(paddle_libs):
            os.environ['PATH'] = paddle_libs + ';' + os.environ.get('PATH', '')
            if hasattr(os, 'add_dll_directory'):
                try:
                    os.add_dll_directory(paddle_libs)
                except Exception:
                    pass
    try:
        from paddleocr import PaddleOCR as _PaddleOCR
        PaddleOCR = _PaddleOCR
    except ImportError:
        PaddleOCR = None


# =============================================================================
# 1. PREPROCESSING FOR DENSE & CURVED PACKAGING
# =============================================================================

def advanced_dense_packaging_preprocess(image_bgr: np.ndarray) -> np.ndarray:
    """
    Non-backfiring preprocessing specialized for dense, closely-spaced packaging text:
      1. LAB color space separation and bilateral filtering on L-channel.
      2. Large-kernel Gaussian background division flattens shadows without clipping highlights.
      3. Stroke-conserving micro-CLAHE expands dynamic range for faint text.
      4. Cylindrical lateral margin ramp restores luminosity on left and right 18% margins.
      5. Sub-pixel micro-definition tightens stroke edges.

    Args:
        image_bgr: Input packaging image (BGR numpy array).

    Returns:
        np.ndarray: Enhanced BGR image ready for PaddleOCR detection.
    """
    h, w = image_bgr.shape[:2]

    # 1. LAB color space separation
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    # 2. Bilateral edge-preserving filter on L-channel
    denoised_l = cv2.bilateralFilter(l, d=5, sigmaColor=18, sigmaSpace=18)

    # 3. Background illumination normalization
    bg_field = cv2.GaussianBlur(denoised_l, (65, 65), 0)
    norm_l = cv2.divide(denoised_l, np.maximum(bg_field, 1), scale=140.0)
    norm_l = np.clip(norm_l, 0, 255).astype(np.uint8)

    # 4. Balanced micro-CLAHE (no character haloing)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    clahe_l = clahe.apply(norm_l)

    # 5. Cylindrical lateral margin ramp (left 18% and right 18%)
    margin_w = max(8, int(w * 0.18))
    l_float = clahe_l.astype(np.float32)
    for col in range(margin_w):
        factor = 1.0 + 0.12 * (1.0 - col / float(margin_w))
        l_float[:, col] = np.clip(l_float[:, col] * factor, 0, 255)
    for col in range(w - margin_w, w):
        factor = 1.0 + 0.12 * ((col - (w - margin_w)) / float(margin_w))
        l_float[:, col] = np.clip(l_float[:, col] * factor, 0, 255)
    l_final = np.clip(l_float, 0, 255).astype(np.uint8)

    # 6. Recombine LAB channels
    merged = cv2.merge((l_final, a, b))
    enhanced_bgr = cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)

    # 7. Gentle, zero-halo stroke definition
    fine_blur = cv2.GaussianBlur(enhanced_bgr, (0, 0), sigmaX=0.8)
    crisp = cv2.addWeighted(enhanced_bgr, 1.20, fine_blur, -0.20, 0)
    return crisp


def enhance_for_dense_stamps_and_print(image_bgr: np.ndarray) -> np.ndarray:
    """
    Grayscale gamma correction and adaptive contrast pass for faint stamped dates.

    Args:
        image_bgr: Input BGR image.

    Returns:
        np.ndarray: High-contrast 3-channel image for date stamp recognition.
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    denoised = cv2.bilateralFilter(gray, d=5, sigmaColor=20, sigmaSpace=20)

    gamma = 1.12
    inv_gamma = 1.0 / gamma
    lut_table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in np.arange(0, 256)]).astype('uint8')
    gamma_corrected = cv2.LUT(denoised, lut_table)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    clahe_img = clahe.apply(gamma_corrected)
    return cv2.cvtColor(clahe_img, cv2.COLOR_GRAY2BGR)


# =============================================================================
# 2. PERSPECTIVE DEWARPING & GEOMETRY UTILITIES
# =============================================================================

def dewarp_polygon_crop(image_bgr: np.ndarray, poly_points: List[List[float]], target_h: int = 48) -> Optional[np.ndarray]:
    """
    Applies a 4-point perspective transformation to flatten curved / tilted
    quadrilaterals on cylindrical containers into straight horizontal text strips.

    Args:
        image_bgr: Source image array.
        poly_points: 4-point polygon vertices [[x1,y1], [x2,y2], [x3,y3], [x4,y4]].
        target_h: Height of output rectified horizontal strip.

    Returns:
        Optional[np.ndarray]: Rectified horizontal text strip image.
    """
    src_pts = np.array(poly_points, dtype=np.float32)

    w_top = np.linalg.norm(src_pts[0] - src_pts[1])
    w_bot = np.linalg.norm(src_pts[3] - src_pts[2])
    max_w = max(int(max(w_top, w_bot)), 16)

    h_left = np.linalg.norm(src_pts[0] - src_pts[3])
    h_right = np.linalg.norm(src_pts[1] - src_pts[2])
    max_h = max(int(max(h_left, h_right)), 12)

    scale = target_h / float(max_h)
    dst_w = max(16, int(max_w * scale))

    dst_pts = np.array([
        [0, 0],
        [dst_w - 1, 0],
        [dst_w - 1, target_h - 1],
        [0, target_h - 1]
    ], dtype=np.float32)

    try:
        M = cv2.getPerspectiveTransform(src_pts, dst_pts)
        warped = cv2.warpPerspective(
            image_bgr, M, (dst_w, target_h),
            flags=cv2.INTER_LANCZOS4,
            borderMode=cv2.BORDER_REPLICATE
        )
        return warped
    except Exception:
        x1 = int(max(0, np.min(src_pts[:, 0])))
        y1 = int(max(0, np.min(src_pts[:, 1])))
        x2 = int(min(image_bgr.shape[1], np.max(src_pts[:, 0])))
        y2 = int(min(image_bgr.shape[0], np.max(src_pts[:, 1])))
        crop = image_bgr[y1:y2, x1:x2]
        if crop.size > 0:
            return cv2.resize(crop, (dst_w, target_h), interpolation=cv2.INTER_CUBIC)
        return None


def polygon_to_bbox(polygon: List[List[float]]) -> Tuple[float, float, float, float]:
    """Converts 4-point polygon coordinates to bounding box tuple (x1, y1, x2, y2)."""
    poly = np.array(polygon, dtype=np.float32)
    x1 = float(np.min(poly[:, 0]))
    y1 = float(np.min(poly[:, 1]))
    x2 = float(np.max(poly[:, 0]))
    y2 = float(np.max(poly[:, 1]))
    return (x1, y1, x2, y2)


def calculate_iou(box1: Tuple[float, float, float, float], box2: Tuple[float, float, float, float]) -> float:
    """Calculates Intersection over Union (IoU) between two bounding boxes."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area1 = max(1.0, (box1[2] - box1[0]) * (box1[3] - box1[1]))
    area2 = max(1.0, (box2[2] - box2[0]) * (box2[3] - box2[1]))

    union = area1 + area2 - intersection
    return intersection / union if union > 0 else 0.0


def calculate_containment(box1: Tuple[float, float, float, float], box2: Tuple[float, float, float, float]) -> float:
    """Calculates containment ratio: intersection area / min(area1, area2)."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area1 = max(1.0, (box1[2] - box1[0]) * (box1[3] - box1[1]))
    area2 = max(1.0, (box2[2] - box2[0]) * (box2[3] - box2[1]))
    return intersection / min(area1, area2)


def text_similarity(str1: str, str2: str) -> float:
    """Calculates normalized string similarity ratio between 0.0 and 1.0."""
    s1 = "".join(str1.lower().split())
    s2 = "".join(str2.lower().split())
    if not s1 or not s2:
        return 0.0
    return SequenceMatcher(None, s1, s2).ratio()


def deduplicate_detections(detections: List[Dict[str, Any]], iou_thresh: float = 0.45, text_sim_thresh: float = 0.55) -> List[Dict[str, Any]]:
    """
    Eliminates redundant detections from multi-pass / regional scans while retaining the
    most complete, highest-confidence transcription.
    """
    if not detections:
        return []

    cleaned_candidates = []
    for d in detections:
        t = d["text"].strip()
        if len(t) <= 1 and not t.isdigit() and d["confidence"] < 0.60:
            continue
        if len(t) <= 2 and d["confidence"] < 0.45 and not t.isdigit():
            continue
        cleaned_candidates.append(d)

    sorted_dets = sorted(cleaned_candidates, key=lambda d: (d["confidence"], len(d["text"])), reverse=True)
    kept = []

    for cand in sorted_dets:
        cand_box = cand["bbox"]
        cand_text = cand["text"]

        is_duplicate = False
        for existing in kept:
            ex_box = existing["bbox"]
            ex_text = existing["text"]

            iou = calculate_iou(cand_box, ex_box)
            containment = calculate_containment(cand_box, ex_box)
            sim = text_similarity(cand_text, ex_text)

            if iou > 0.55 or (iou > iou_thresh and sim > text_sim_thresh):
                is_duplicate = True
                break

            if containment > 0.70:
                if sim > 0.35 or cand_text in ex_text or ex_text in cand_text:
                    is_duplicate = True
                    break

        if not is_duplicate:
            kept.append(cand)

    return kept


# =============================================================================
# 3. 2D SPATIAL LAYOUT & TABLE RECONSTRUCTION
# =============================================================================

def reconstruct_2d_layout(detections: List[Dict[str, Any]], image_width: Optional[int] = None) -> Tuple[List[Dict[str, Any]], str, List[str]]:
    """
    Reconstructs reading flow and tabular columns from spatial coordinates.

    Args:
        detections: List of individual token detections.
        image_width: Width of image in pixels.

    Returns:
        Tuple[List[Dict], str, List[str]]: (ordered_detections, full_text_multiline, text_lines_list)
    """
    if not detections:
        return [], "", []

    w_img = image_width or max(d["bbox"][2] for d in detections)

    left_items = [d for d in detections if d["bbox"][0] < w_img * 0.58]
    right_items = [d for d in detections if d["bbox"][0] >= w_img * 0.58]

    def cluster_items_into_lines(items):
        if not items:
            return []
        sorted_items = sorted(items, key=lambda d: (d["bbox"][1] + d["bbox"][3]) / 2.0)
        lines = []
        curr_line = []

        for item in sorted_items:
            cy = (item["bbox"][1] + item["bbox"][3]) / 2.0
            bh = item["bbox"][3] - item["bbox"][1]

            if not curr_line:
                curr_line.append(item)
                continue

            ref_cy = np.median([(d["bbox"][1] + d["bbox"][3]) / 2.0 for d in curr_line])
            ref_h = np.median([(d["bbox"][3] - d["bbox"][1]) for d in curr_line])

            if abs(cy - ref_cy) < max(8, ref_h * 0.45):
                curr_line.append(item)
            else:
                curr_line.sort(key=lambda d: d["bbox"][0])
                lines.append(curr_line)
                curr_line = [item]

        if curr_line:
            curr_line.sort(key=lambda d: d["bbox"][0])
            lines.append(curr_line)
        return lines

    left_lines = cluster_items_into_lines(left_items)
    right_lines = cluster_items_into_lines(right_items)

    def render_line_strings(lines):
        formatted = []
        for line in lines:
            line_str = ""
            for i, item in enumerate(line):
                if i == 0:
                    line_str = item["text"]
                else:
                    prev = line[i - 1]
                    gap = item["bbox"][0] - prev["bbox"][2]
                    avg_char_w = max(5, (prev["bbox"][2] - prev["bbox"][0]) / max(1, len(prev["text"])))
                    if gap > 2.0 * avg_char_w:
                        spaces = " " * min(8, max(2, int(gap / avg_char_w)))
                        line_str += spaces + item["text"]
                    else:
                        line_str += " " + item["text"]
            if line_str.strip():
                formatted.append(line_str)
        return formatted

    left_formatted = render_line_strings(left_lines)
    right_formatted = render_line_strings(right_lines)

    all_lines = left_formatted[:]
    if right_formatted:
        all_lines.append("")
        all_lines.extend(right_formatted)

    full_text = "\n".join(all_lines)

    ordered_detections = []
    for line in left_lines + right_lines:
        ordered_detections.extend(line)

    return ordered_detections, full_text, all_lines


# =============================================================================
# 4. ENHANCED PACKAGING OCR CLASS CONTROLLER
# =============================================================================

class EnhancedPackagingOCR:
    """
    High-accuracy multi-scale packaging OCR engine specialized for dense & curved packaging.
    """

    def __init__(self, use_gpu: bool = True, drop_score: float = 0.20):
        """
        Initializes the PaddleOCR model with DBNet detection parameters tuned for packaging.
        """
        _ensure_paddle_dlls()
        if PaddleOCR is None:
            raise RuntimeError("PaddleOCR package is not installed.")

        print("[INFO] Initializing PP-OCRv6 Medium Packaging Engine...")
        self.ocr = PaddleOCR(
            text_detection_model_name='PP-OCRv6_medium_det',
            text_recognition_model_name='PP-OCRv6_medium_rec',
            use_angle_cls=True,
            use_gpu=use_gpu,
            det_limit_side_len=1920,
            det_limit_type='max',
            det_db_score_mode='slow',
            det_db_thresh=0.18,
            det_db_box_thresh=0.40,
            det_db_unclip_ratio=1.35,
            drop_score=drop_score,
            show_log=False
        )
        print("[INFO] PP-OCRv6 Medium Packaging Engine ready.")

    def _run_paddle_raw(self, image_bgr: np.ndarray, offset_x: int = 0, offset_y: int = 0) -> List[Dict[str, Any]]:
        """Runs PaddleOCR inference and maps polygon coordinates back to global canvas space."""
        if image_bgr is None or image_bgr.size == 0:
            return []

        results = self.ocr.ocr(image_bgr, cls=True)
        if not results or results[0] is None:
            return []

        detections = []
        for line in results[0]:
            poly_points, (text, conf) = line
            text_str = text.strip()
            if not text_str:
                continue

            global_poly = [[float(pt[0] + offset_x), float(pt[1] + offset_y)] for pt in poly_points]
            x1, y1, x2, y2 = polygon_to_bbox(global_poly)

            detections.append({
                "text": text_str,
                "confidence": float(conf),
                "polygon": global_poly,
                "bbox": (int(x1), int(y1), int(x2), int(y2)),
                "height_px": int(y2 - y1),
                "width_px": int(x2 - x1)
            })

        return detections

    def _dewarp_and_enhance_crops(self, image_bgr: np.ndarray, detections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Selectively dewarps tilted/curved polygons and re-recognizes micro-text at standard 48px height."""
        enhanced_detections = []

        for det in detections:
            poly = det["polygon"]
            conf = det["confidence"]
            text = det["text"]
            bh = det["height_px"]

            tilt = abs(poly[0][1] - poly[1][1]) if len(poly) >= 2 else 0
            if conf < 0.85 or tilt > 3 or bh < 18:
                warped = dewarp_polygon_crop(image_bgr, poly, target_h=48)
                if warped is not None:
                    try:
                        rec_res = self.ocr.ocr(warped, det=False, cls=True)
                        if rec_res and rec_res[0] and rec_res[0][0]:
                            r_text, r_conf = rec_res[0][0]
                            r_text = r_text.strip()
                            if r_text and (r_conf > conf or (len(r_text) > len(text) and r_conf > 0.50)):
                                det["text"] = r_text
                                det["confidence"] = float(r_conf)
                    except Exception:
                        pass

            enhanced_detections.append(det)

        return enhanced_detections

    def process_image(
        self,
        image_bgr: np.ndarray,
        enable_tiling: bool = False,
        tile_size: Tuple[int, int] = (720, 720),
        enable_multipass: bool = True
    ) -> Dict[str, Any]:
        """
        Executes the full multi-pass packaging OCR pipeline.
        """
        if image_bgr is None or image_bgr.size == 0:
            return {"text_lines": [], "full_text": "", "detections": []}

        h, w = image_bgr.shape[:2]
        all_detections = []

        # Pass A: Global illumination-normalized scan
        img_prep = advanced_dense_packaging_preprocess(image_bgr)
        dets_global = self._run_paddle_raw(img_prep, offset_x=0, offset_y=0)
        all_detections.extend(dets_global)

        # Pass B: Lower-Region Fine-Print Deep Scan
        if h > 300:
            bottom_y1 = int(h * 0.35)
            bottom_crop = img_prep[bottom_y1:, :]
            dets_bottom = self._run_paddle_raw(bottom_crop, offset_x=0, offset_y=bottom_y1)
            all_detections.extend(dets_bottom)

        # Pass C: Stamped Dates & Grayscale High-Contrast Scan
        if enable_multipass:
            img_stamps = enhance_for_dense_stamps_and_print(image_bgr)
            dets_stamps = self._run_paddle_raw(img_stamps, offset_x=0, offset_y=0)
            all_detections.extend(dets_stamps)

        # Deduplication & Containment Filtering
        deduped = deduplicate_detections(all_detections, iou_thresh=0.45, text_sim_thresh=0.55)

        # Perspective Polygon Dewarping
        dewarped_dets = self._dewarp_and_enhance_crops(img_prep, deduped)

        # 2D Spatial Layout & Table Alignment
        ordered_dets, full_text, text_lines = reconstruct_2d_layout(dewarped_dets, image_width=w)

        return {
            "image_size": (w, h),
            "total_items_detected": len(ordered_dets),
            "detections": ordered_dets,
            "text_lines": text_lines,
            "full_text": full_text
        }

    def render_visual_overlay(self, image_bgr: np.ndarray, detections: List[Dict[str, Any]]) -> np.ndarray:
        """Draws bounding polygon overlays and text badges for visual inspection."""
        canvas = image_bgr.copy()

        for idx, det in enumerate(detections):
            poly = np.array(det["polygon"], dtype=np.int32).reshape((-1, 1, 2))
            conf = det["confidence"]
            text = det["text"]
            x1, y1, x2, y2 = det["bbox"]

            if conf >= 0.85:
                color = (0, 255, 0)
            elif conf >= 0.65:
                color = (0, 215, 255)
            else:
                color = (0, 100, 255)

            cv2.polylines(canvas, [poly], isClosed=True, color=color, thickness=2)

            badge_label = f"[{idx+1}] {text} ({conf:.2f})"
            font_scale = 0.45
            font_thick = 1
            (tw, th), _ = cv2.getTextSize(badge_label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thick)

            by1 = max(0, y1 - th - 6)
            by2 = max(th + 6, y1)
            bx2 = min(canvas.shape[1], x1 + tw + 6)

            cv2.rectangle(canvas, (x1, by1), (bx2, by2), (20, 20, 20), -1)
            cv2.putText(canvas, badge_label, (x1 + 3, by2 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, font_thick, cv2.LINE_AA)

        return canvas
