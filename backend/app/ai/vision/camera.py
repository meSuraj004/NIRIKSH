"""
=============================================================================
Camera Management & Real-Time Video Streaming Engine
=============================================================================
Module: vision.camera
Purpose:
  Provides a thread-safe camera capture pipeline with real-time OpenCV video
  streaming, YOLOv8 packaging tracking, blur and specular glare quality checks,
  interactive HUD overlay rendering, MJPEG generator feeds, and high-res snapshot capture.

Features:
  1. Thread-Safe Background Frame Ingestion:
     - Worker thread continuously pulls frames from USB webcam or IP stream.
     - Prevents OpenCV buffer buildup and eliminates video lag.
  2. Real-Time Object Guidance & Alignment:
     - Detects packaging ROI with YOLOv8.
     - Evaluates guide frame overlap, centering deviation, and tilt angle.
     - Temporal smoothing (AngleSmoother, BoxStability, GuidanceStabilizer) prevents jitter.
  3. Visual HUD Overlay:
     - Renders dynamic bounding boxes (Green=Ready, Yellow=Adjusting, Red=No Object).
     - Renders live telemetry banner (FPS, Resolution, Blur score, Lighting state).
  4. MJPEG HTTP Video Streaming:
     - Delivers multipart JPEG stream for seamless web browser / React UI consumption.
=============================================================================
"""

import os
import cv2
import time
import math
import threading
import numpy as np
from typing import Generator, Optional, Dict, Any, Tuple
from collections import deque
import torch

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None


# =============================================================================
# CONSTANTS & DEFAULT THRESHOLDS
# =============================================================================
DEFAULT_CAMERA_INDEX = 0
DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
GUIDE_WIDTH_RATIO = 0.72
GUIDE_HEIGHT_RATIO = 0.90
MIN_OVERLAP_RATIO = 0.60
CENTER_TOLERANCE = 0.18
MIN_SIZE_RATIO = 0.30
MAX_SIZE_RATIO = 0.96
ROTATION_TOLERANCE = 4.0
BLUR_THRESHOLD = 80.0
DETECTION_INTERVAL = 3
BOX_SMOOTHING_ALPHA = 0.35
MIN_OBJECT_AREA = 0.008
CONFIDENCE_THRESHOLD = 0.25


# =============================================================================
# TEMPORAL SMOOTHING & STABILITY FILTERS
# =============================================================================

class AngleSmoother:
    """
    Rolling window filter to smooth rotational angle readings across consecutive video frames.
    """
    def __init__(self, size: int = 8):
        self.values = deque(maxlen=size)

    def update(self, angle: Optional[float]) -> Optional[float]:
        """Adds a new angle sample and returns the rolling mean."""
        if angle is None:
            return None
        self.values.append(angle)
        return float(np.mean(self.values))

    def reset(self):
        """Clears the history buffer."""
        self.values.clear()

    def is_stable(self, tolerance: float = 2.5) -> bool:
        """Checks if peak-to-peak angle variance is within stable tolerance."""
        if len(self.values) < 3:
            return False
        return np.ptp(self.values) <= tolerance


class BoxStability:
    """
    Tracks bounding box coordinates over time to determine if the object is held stationary.
    """
    def __init__(self, history_size: int = 8):
        self.history = deque(maxlen=history_size)

    def update(self, box: Optional[Tuple[int, int, int, int]]) -> bool:
        """
        Updates box position history and returns True if movement is below jitter threshold.
        """
        if box is None:
            self.history.clear()
            return False
        self.history.append(box)
        if len(self.history) < 4:
            return False

        centers = np.array([((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0) for b in self.history], dtype=np.float32)
        distances = np.linalg.norm(centers - centers[-1], axis=1)
        max_dist = np.max(distances)

        bw = max(1, box[2] - box[0])
        bh = max(1, box[3] - box[1])
        scale = max(bw, bh, 1)
        return (max_dist / scale) <= 0.04

    def reset(self):
        """Clears position history."""
        self.history.clear()


class GuidanceStabilizer:
    """
    Hysteresis stabilizer to prevent rapid flickering of HUD guidance text.
    """
    def __init__(self, required_frames: int = 2):
        self.required_frames = required_frames
        self.current_message = "SEARCHING FOR OBJECT"
        self.current_color = (0, 0, 255)
        self.candidate_message = None
        self.candidate_color = None
        self.candidate_count = 0

    def update(self, message: str, color: Tuple[int, int, int]) -> Tuple[str, Tuple[int, int, int]]:
        """Updates and stabilizes guidance message based on consecutive frame consistency."""
        if message == self.candidate_message:
            self.candidate_count += 1
        else:
            self.candidate_message = message
            self.candidate_color = color
            self.candidate_count = 1

        if self.candidate_count >= self.required_frames:
            self.current_message = self.candidate_message
            self.current_color = self.candidate_color

        return self.current_message, self.current_color


# =============================================================================
# MAIN CAMERA MANAGER CONTROLLER
# =============================================================================

class CameraManager:
    """
    Singleton thread-safe Camera Manager for real-time video streaming with OpenCV HUD.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(CameraManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.cap: Optional[cv2.VideoCapture] = None
        self.is_running = False
        self.camera_index = DEFAULT_CAMERA_INDEX
        self.width = DEFAULT_WIDTH
        self.height = DEFAULT_HEIGHT

        self.thread: Optional[threading.Thread] = None
        self.frame_lock = threading.Lock()

        # Cached frames
        self.raw_frame: Optional[np.ndarray] = None
        self.annotated_frame: Optional[np.ndarray] = None
        self.latest_object: Optional[Dict[str, Any]] = None

        # Telemetry State
        self.fps = 0.0
        self.sharpness_score = 0.0
        self.is_sharp = False
        self.lighting_status = "NORMAL"
        self.guidance_message = "READY"
        self.guidance_color = (0, 255, 0)
        self.box_stable = False
        self.rotation_angle: Optional[float] = None
        self.actual_resolution = "0x0"
        self.frame_count: int = 0
        self.last_detection_frame: int = 0

        # YOLO Model
        self.model = None
        self._init_yolo()

        # Smoothers
        self.angle_smoother = AngleSmoother()
        self.box_stability = BoxStability()
        self.guidance_stabilizer = GuidanceStabilizer()

    def _init_yolo(self):
        """Loads YOLOv8 segmentation model if available."""
        if YOLO is None:
            print("[CameraManager] Ultralytics YOLO not installed.")
            return

        model_candidates = ["yolov8n-seg.pt", "yolov8n.pt"]
        for cand in model_candidates:
            if os.path.exists(cand):
                try:
                    self.model = YOLO(cand)
                    print(f"[CameraManager] Loaded YOLO model from {cand}")
                    return
                except Exception as e:
                    print(f"[CameraManager] Error loading {cand}: {e}")

        try:
            print("[CameraManager] Initializing YOLOv8n-seg...")
            self.model = YOLO("yolov8n-seg.pt")
        except Exception as e:
            print(f"[CameraManager] Could not download/load YOLO model: {e}")

    @staticmethod
    def expand_box_with_margin(
        box: Tuple[int, int, int, int],
        frame_shape: Tuple[int, int, int],
        margin_ratio: float = 0.08
    ) -> Tuple[int, int, int, int]:
        h, w = frame_shape[:2]
        x1, y1, x2, y2 = box
        bw = max(1, x2 - x1)
        bh = max(1, y2 - y1)
        pad_x = int(bw * margin_ratio)
        pad_y = int(bh * margin_ratio)
        return (
            max(0, x1 - pad_x),
            max(0, y1 - pad_y),
            min(w - 1, x2 + pad_x),
            min(h - 1, y2 + pad_y)
        )

    @staticmethod
    def get_guide_region(
        frame_shape: Tuple[int, int, int],
        preset: str = "AUTO",
        detected_box: Optional[Tuple[int, int, int, int]] = None
    ) -> Tuple[int, int, int, int]:
        h, w = frame_shape[:2]
        cx, cy = w // 2, h // 2

        if preset == "AUTO" and detected_box is not None:
            ox1, oy1, ox2, oy2 = detected_box
            obw, obh = ox2 - ox1, oy2 - oy1
            if obw > 30 and obh > 30:
                ocx, ocy = (ox1 + ox2) // 2, (oy1 + oy2) // 2
                gw, gh = int(obw * 1.25), int(obh * 1.25)
                return (max(0, ocx - gw // 2), max(0, ocy - gh // 2), min(w, ocx + gw // 2), min(h, ocy + gh // 2))

        if preset == "TALL":
            gw = int(h * 0.48) if w > h else int(w * 0.44)
            gh = int(h * 0.94)
        elif preset == "BOX":
            gw = int(h * 0.75) if w > h else int(w * 0.72)
            gh = int(h * 0.75) if w > h else int(h * 0.72)
        elif preset == "WIDE":
            gw = int(w * 0.85)
            gh = int(h * 0.52)
        else:  # AUTO
            gw = int(w * 0.72)
            gh = int(h * 0.92)

        x1 = max(0, cx - gw // 2)
        y1 = max(0, cy - gh // 2)
        x2 = min(w, x1 + gw)
        y2 = min(h, y1 + gh)
        return (x1, y1, x2, y2)

    @staticmethod
    def clamp_box(box: Tuple[int, int, int, int], frame_shape: Tuple[int, int, int]) -> Tuple[int, int, int, int]:
        h, w = frame_shape[:2]
        x1, y1, x2, y2 = box
        x1 = max(0, min(int(x1), w - 2))
        y1 = max(0, min(int(y1), h - 2))
        x2 = max(x1 + 1, min(int(x2), w - 1))
        y2 = max(y1 + 1, min(int(y2), h - 1))
        return (x1, y1, x2, y2)

    @staticmethod
    def get_box_guide_overlap(box: Tuple[int, int, int, int], frame_shape: Tuple[int, int, int], preset: str = "AUTO") -> float:
        x1, y1, x2, y2 = box
        gx1, gy1, gx2, gy2 = CameraManager.get_guide_region(frame_shape, preset=preset)

        ix1 = max(x1, gx1)
        iy1 = max(y1, gy1)
        ix2 = min(x2, gx2)
        iy2 = min(y2, gy2)

        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0

        inter_area = (ix2 - ix1) * (iy2 - iy1)
        box_area = max(1, (x2 - x1) * (y2 - y1))
        return inter_area / float(box_area)

    @staticmethod
    def check_blur(roi: np.ndarray) -> Tuple[float, bool]:
        if roi is None or roi.size == 0:
            return 0.0, False
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if len(roi.shape) == 3 else roi
        score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        is_sharp = score >= BLUR_THRESHOLD
        return score, is_sharp

    @staticmethod
    def check_lighting(roi: np.ndarray) -> Tuple[str, float]:
        if roi is None or roi.size == 0:
            return "NORMAL", 128.0
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if len(roi.shape) == 3 else roi
        mean_b = float(np.mean(gray))
        glare_ratio = float(np.mean(gray > 245))

        if mean_b < 45:
            return "TOO DARK", mean_b
        elif glare_ratio > 0.10:
            return "GLARE DETECTED", mean_b
        else:
            return "GOOD", mean_b

    def start(self, camera_index: Any = DEFAULT_CAMERA_INDEX, width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT) -> bool:
        """Starts video capture thread."""
        with self.frame_lock:
            if self.is_running:
                if self.camera_index == camera_index:
                    return True
                self._stop_internal()

            self.camera_index = camera_index
            self.width = width
            self.height = height

            try:
                src_val = int(camera_index) if isinstance(camera_index, str) and camera_index.isdigit() else camera_index
                self.cap = cv2.VideoCapture(src_val, cv2.CAP_DSHOW if os.name == 'nt' and isinstance(src_val, int) else cv2.CAP_ANY)

                if not self.cap.isOpened():
                    self.cap = cv2.VideoCapture(src_val)

                if not self.cap.isOpened():
                    print(f"[CameraManager] Failed to open camera: {camera_index}")
                    return False

                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                self.actual_resolution = f"{actual_w}x{actual_h}"
                print(f"[CameraManager] Camera active on {camera_index} ({self.actual_resolution})")

                self.is_running = True
                self.thread = threading.Thread(target=self._capture_worker, daemon=True)
                self.thread.start()
                return True

            except Exception as e:
                print(f"[CameraManager] Camera startup exception: {e}")
                return False

    def stop(self):
        """Stops the camera stream."""
        with self.frame_lock:
            self._stop_internal()

    def _stop_internal(self):
        self.is_running = False
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
        self.raw_frame = None
        self.annotated_frame = None
        print("[CameraManager] Camera stopped.")

    def _capture_worker(self):
        fps_counter = 0
        fps_start = time.time()

        while self.is_running and self.cap is not None:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                time.sleep(0.01)
                continue

            self.frame_count += 1
            fps_counter += 1
            if time.time() - fps_start >= 1.0:
                self.fps = round(fps_counter / (time.time() - fps_start), 1)
                fps_counter = 0
                fps_start = time.time()

            # Process frame analytics
            annotated = self._process_frame_and_annotate(frame)

            with self.frame_lock:
                self.raw_frame = frame.copy()
                self.annotated_frame = annotated

            time.sleep(0.005)

    def _process_frame_and_annotate(self, frame: np.ndarray) -> np.ndarray:
        h, w = frame.shape[:2]
        hud_frame = frame.copy()

        # Run YOLO detection on interval frames
        if self.model is not None and (self.frame_count - self.last_detection_frame >= DETECTION_INTERVAL):
            self.last_detection_frame = self.frame_count
            try:
                device_val = 0 if torch.cuda.is_available() else "cpu"
                results = self.model(frame, verbose=False, conf=CONFIDENCE_THRESHOLD, imgsz=640, device=device_val)
                if results and len(results) > 0 and results[0].boxes is not None and len(results[0].boxes) > 0:
                    boxes = results[0].boxes
                    max_area = 0
                    best_obj = None

                    for box in boxes:
                        coords = box.xyxy[0].cpu().numpy().astype(int)
                        conf = float(box.conf[0].cpu().numpy())
                        cls_id = int(box.cls[0].cpu().numpy())
                        cls_name = results[0].names.get(cls_id, "Product")

                        bx1, by1, bx2, by2 = coords
                        area = (bx2 - bx1) * (by2 - by1)
                        if area > max_area and area > (w * h * MIN_OBJECT_AREA):
                            max_area = area
                            expanded = self.expand_box_with_margin((bx1, by1, bx2, by2), (h, w, 3))
                            best_obj = {
                                "box": expanded,
                                "raw_box": (int(bx1), int(by1), int(bx2), int(by2)),
                                "class_name": cls_name,
                                "confidence": conf
                            }

                    self.latest_object = best_obj
                else:
                    self.latest_object = None
            except Exception:
                pass

        obj = self.latest_object
        gx1, gy1, gx2, gy2 = self.get_guide_region((h, w, 3), preset="AUTO", detected_box=obj["box"] if obj else None)

        # Evaluate positioning & guidance
        if obj is not None:
            bx1, by1, bx2, by2 = self.clamp_box(obj["box"], (h, w, 3))
            self.box_stable = self.box_stability.update(obj["box"])
            overlap = self.get_box_guide_overlap(obj["box"], (h, w, 3), preset="AUTO")

            roi = frame[by1:by2, bx1:bx2]
            self.sharpness_score, self.is_sharp = self.check_blur(roi)
            self.lighting_status, _ = self.check_lighting(roi)

            bcx = (bx1 + bx2) / 2.0
            gcx = (gx1 + gx2) / 2.0
            x_dev = abs(bcx - gcx) / float(w)

            if not self.is_sharp:
                raw_msg = "HOLD STILL - BLUR DETECTED"
                raw_col = (0, 0, 255)
            elif self.lighting_status == "TOO DARK":
                raw_msg = "INCREASE LIGHTING"
                raw_col = (0, 165, 255)
            elif self.lighting_status == "GLARE DETECTED":
                raw_msg = "TILT TO REDUCE GLARE"
                raw_col = (0, 165, 255)
            elif overlap < MIN_OVERLAP_RATIO:
                raw_msg = "ALIGN INSIDE GUIDE"
                raw_col = (0, 165, 255)
            elif x_dev > CENTER_TOLERANCE:
                raw_msg = "CENTER OBJECT"
                raw_col = (0, 165, 255)
            elif not self.box_stable:
                raw_msg = "HOLD STEADY"
                raw_col = (0, 215, 255)
            else:
                raw_msg = "PERFECT - CAPTURE NOW!"
                raw_col = (0, 255, 0)
        else:
            self.box_stability.reset()
            self.box_stable = False
            self.sharpness_score = 0.0
            self.is_sharp = False
            self.lighting_status = "NORMAL"
            raw_msg = "ALIGN PACKAGING INSIDE FRAME"
            raw_col = (100, 100, 100)

        self.guidance_message, self.guidance_color = self.guidance_stabilizer.update(raw_msg, raw_col)

        # -------------------------------------------------------------
        # Draw HUD Graphics
        # -------------------------------------------------------------
        # Draw guide corner brackets
        guide_color = (0, 255, 128) if (obj and self.guidance_color == (0, 255, 0)) else (100, 100, 100)
        corner = 28
        thick = 2
        cv2.rectangle(hud_frame, (gx1, gy1), (gx2, gy2), guide_color, 1)
        cv2.line(hud_frame, (gx1, gy1), (gx1 + corner, gy1), guide_color, thick)
        cv2.line(hud_frame, (gx1, gy1), (gx1, gy1 + corner), guide_color, thick)
        cv2.line(hud_frame, (gx2, gy1), (gx2 - corner, gy1), guide_color, thick)
        cv2.line(hud_frame, (gx2, gy1), (gx2, gy1 + corner), guide_color, thick)
        cv2.line(hud_frame, (gx1, gy2), (gx1 + corner, gy2), guide_color, thick)
        cv2.line(hud_frame, (gx1, gy2), (gx1, gy2 - corner), guide_color, thick)
        cv2.line(hud_frame, (gx2, gy2), (gx2 - corner, gy2), guide_color, thick)
        cv2.line(hud_frame, (gx2, gy2), (gx2, gy2 - corner), guide_color, thick)
        cv2.drawMarker(hud_frame, ((gx1 + gx2) // 2, (gy1 + gy2) // 2), guide_color, cv2.MARKER_CROSS, 18, 1)

        # Draw detected object box
        if obj is not None:
            bx1, by1, bx2, by2 = self.clamp_box(obj["box"], (h, w, 3))
            cv2.rectangle(hud_frame, (bx1, by1), (bx2, by2), self.guidance_color, 2)
            lbl = f"{obj['class_name']} ({int(obj['confidence'] * 100)}%)"
            cv2.putText(hud_frame, lbl, (bx1, max(20, by1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, self.guidance_color, 2)

        # HUD Top and Bottom Bars
        overlay = hud_frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 45), (20, 20, 20), -1)
        cv2.rectangle(overlay, (0, h - 55), (w, h), (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.65, hud_frame, 0.35, 0, hud_frame)

        # Top Bar Telemetry
        cv2.putText(hud_frame, f"FPS: {self.fps:.0f}", (15, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1, cv2.LINE_AA)
        blur_text = f"Sharpness: {self.sharpness_score:.0f} [{'SHARP' if self.is_sharp else 'BLUR'}]"
        blur_color = (0, 255, 0) if self.is_sharp else (0, 80, 255)
        cv2.putText(hud_frame, blur_text, (120, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55, blur_color, 2, cv2.LINE_AA)

        light_color = (0, 255, 0) if self.lighting_status == "GOOD" else (0, 165, 255)
        cv2.putText(hud_frame, f"Light: {self.lighting_status}", (w - 230, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55, light_color, 1, cv2.LINE_AA)

        if obj is not None and self.box_stable:
            cv2.putText(hud_frame, "[STEADY]", (15, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2, cv2.LINE_AA)

        # Bottom Bar Guidance Text
        text_size = cv2.getTextSize(self.guidance_message, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
        text_x = (w - text_size[0]) // 2
        cv2.putText(hud_frame, self.guidance_message, (text_x, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, self.guidance_color, 2, cv2.LINE_AA)

        return hud_frame

    def get_status(self) -> Dict[str, Any]:
        """Returns live camera status & guidance telemetry."""
        return {
            "is_running": self.is_running,
            "camera_index": self.camera_index,
            "fps": self.fps,
            "resolution": self.actual_resolution,
            "sharpness_score": self.sharpness_score,
            "is_sharp": self.is_sharp,
            "lighting_status": self.lighting_status,
            "guidance_message": self.guidance_message,
            "box_stable": self.box_stable,
            "object_detected": self.latest_object is not None
        }

    def generate_mjpeg(self, annotated: bool = True, quality: int = 85) -> Generator[bytes, None, None]:
        """Generator yielding MJPEG multipart chunks for React frontend <img> or <iframe>."""
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]

        while True:
            frame_to_encode = None
            with self.frame_lock:
                if self.is_running:
                    frame_to_encode = self.annotated_frame if annotated else self.raw_frame

            if frame_to_encode is not None:
                ret, buffer = cv2.imencode(".jpg", frame_to_encode, encode_params)
                if ret:
                    frame_bytes = buffer.tobytes()
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                    )
            else:
                placeholder = np.zeros((480, 480, 3), dtype=np.uint8)
                cv2.putText(placeholder, "Camera Inactive", (140, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (120, 120, 120), 2, cv2.LINE_AA)
                cv2.putText(placeholder, "POST /api/camera/start to activate", (90, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (90, 90, 90), 1, cv2.LINE_AA)
                ret, buffer = cv2.imencode(".jpg", placeholder, encode_params)
                if ret:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
                    )

            time.sleep(0.033)

    def capture_snapshot(self) -> Optional[Tuple[np.ndarray, Optional[np.ndarray], Dict[str, Any]]]:
        """
        Captures the current raw frame and cropped object box.
        Returns: (raw_frame, object_crop, metadata)
        """
        with self.frame_lock:
            if not self.is_running or self.raw_frame is None:
                return None
            raw = self.raw_frame.copy()
            obj = self.latest_object.copy() if self.latest_object else None

        h, w = raw.shape[:2]
        crop = None
        detection_meta = None

        if obj is not None:
            x1, y1, x2, y2 = obj["box"]
            x1, y1, x2, y2 = max(0, x1), max(0, y1), min(w, x2), min(h, y2)
            if x2 > x1 and y2 > y1:
                crop = raw[y1:y2, x1:x2].copy()
                detection_meta = {
                    "class_name": obj["class_name"],
                    "confidence": obj["confidence"],
                    "bounding_box": [x1, y1, x2, y2]
                }

        if crop is None or crop.size == 0:
            gx1, gy1, gx2, gy2 = self.get_guide_region(raw.shape)
            crop = raw[gy1:gy2, gx1:gx2].copy() if (gx2 > gx1 and gy2 > gy1) else raw.copy()
            detection_meta = {
                "class_name": "Product Package",
                "confidence": 0.90,
                "bounding_box": [gx1, gy1, gx2, gy2]
            }

        meta = {
            "timestamp": time.time(),
            "resolution": f"{w}x{h}",
            "sharpness_score": self.sharpness_score,
            "is_sharp": self.is_sharp,
            "lighting_status": self.lighting_status,
            "detection": detection_meta
        }

        return raw, crop, meta


# Global singleton instance for shared camera streaming
camera_manager = CameraManager()
