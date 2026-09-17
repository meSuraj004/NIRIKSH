"""
=============================================================================
Unified Packaging Pipeline Controller
=============================================================================
Module: pipeline.unified_pipeline
Purpose:
  Unifies the complete multi-image packaging lifecycle:
    1. Ingestion & Preprocessing: YOLOv8 packaging ROI localization + Multi-Stage
       Enhancement (2x Super-Res, Bilateral Denoising, CLAHE, Stroke Sharpening).
    2. Primary Vision OCR: Ultra-fast Groq Vision Model (Qwen 3.8-27B) with multi-key rotation.
    3. Multi-Image Synthesis: Groq LLM Aggregator structuring all angles into
       standardized Legal Metrology & FSSAI packaging sections.
    4. Persistence: Outputs structured JSON, Markdown compliance report, and enhanced images.
=============================================================================
"""

import os
import cv2
import time
from datetime import datetime
from typing import List, Dict, Any, Union, Optional

from app.config import settings

from app.ai.vision.preprocessor import PackagingImagePreprocessor
from app.ai.ocr.groq_ocr import FastGroqVisionOCR
from app.ai.ocr.key_manager import key_manager
from .aggregator import ProductLabelAggregator
from app.compliance import RuleEngine, generate_legal_markdown_report


class UnifiedPackagingPipeline:
    """
    End-to-End Multi-Image Packaging OCR & Compliance Pipeline Coordinator.
    """

    def __init__(self, captured_dir: str):
        """
        Initializes preprocessor, OCR engine, LLM aggregator, and statutory rule engine components.

        Args:
            captured_dir: Directory where per-inspection enhanced images are saved.
        """
        self.captured_dir = captured_dir
        os.makedirs(self.captured_dir, exist_ok=True)

        print("[Pipeline] Initializing modular pipeline components...")
        self.preprocessor = PackagingImagePreprocessor(model_path=str(settings.yolo_model_path), save_dir=self.captured_dir)
        self.ocr_engine = FastGroqVisionOCR(key_mgr=key_manager)
        self.aggregator = ProductLabelAggregator(key_mgr=key_manager)
        self.rule_engine = RuleEngine()
        print("[Pipeline] All pipeline components initialized and ready.")

    def run_on_images(
        self,
        image_inputs: List[Union[str, cv2.Mat]],
        session_name: Optional[str] = None,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Executes the complete unified pipeline on an arbitrary list of packaging images.

        Args:
            image_inputs: List of image file paths or OpenCV numpy arrays.
            session_name: Optional custom session identifier.
            progress_callback: Optional callback receiving (message_str, progress_float_0_to_1).

        Returns:
            Dict[str, Any]: Complete pipeline result payload with per-image OCR and aggregated schema.
        """
        start_time = time.time()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_id = session_name or f"session_{timestamp}"

        if not image_inputs:
            raise ValueError("No images provided to pipeline.")

        total_imgs = len(image_inputs)
        print(f"\n{'='*70}")
        print(f"  STARTING MODULAR PACKAGING PIPELINE - SESSION: {session_id}")
        print(f"  Total Images to Process: {total_imgs}")
        print(f"{'='*70}")

        per_image_results = []

        # -------------------------------------------------------------
        # STAGE 1 & 2: Preprocessing & Vision OCR per Image View
        # -------------------------------------------------------------
        for idx, img_input in enumerate(image_inputs):
            view_num = idx + 1
            source_label = f"view_{view_num}"

            if progress_callback:
                progress_callback(f"Preprocessing image {view_num}/{total_imgs}...", (view_num - 0.5) / (total_imgs + 1))

            print(f"\n[Stage 1/2] Processing Image {view_num}/{total_imgs}...")
            # 1. Preprocess & Enhance
            prep_res = self.preprocessor.process_image(img_input, source_label=source_label)

            # 2. Vision OCR on OCR-ready image
            ocr_target = prep_res["saved_ocr_path"]
            print(f"[Stage 2/2] Running Groq Vision OCR on {os.path.basename(ocr_target)}...")

            if progress_callback:
                progress_callback(f"Running Groq Vision OCR on image {view_num}/{total_imgs}...", view_num / (total_imgs + 1))

            ocr_res = self.ocr_engine.extract_text(ocr_target)
            print(f"  -> Extracted {ocr_res['total_lines']} lines in {ocr_res['latency_sec']}s")

            item_data = {
                "view_index": view_num,
                "source_path": prep_res.get("source_path"),
                "source_type": source_label,
                "resolution_original": prep_res["original_resolution"],
                "resolution_processed": prep_res["processed_resolution"],
                "detection": prep_res["detection"],
                "quality": prep_res["quality"],
                "saved_color_path": prep_res["saved_color_path"],
                "saved_ocr_path": prep_res["saved_ocr_path"],
                "ocr_latency_sec": ocr_res["latency_sec"],
                "ocr_total_lines": ocr_res["total_lines"],
                "token_usage": ocr_res["token_usage"],
                "text_lines": ocr_res["text_lines"],
                "full_text": ocr_res["full_text"]
            }
            per_image_results.append(item_data)

        # -------------------------------------------------------------
        # -------------------------------------------------------------
        # STAGE 3: Multi-Image Synthesis & Section Formatting
        # -------------------------------------------------------------
        print(f"\n[Stage 3/4] Combining {total_imgs} views via Groq Aggregator...")
        if progress_callback:
            progress_callback("Synthesizing multi-angle data into structured sections...", 0.88)

        agg_res = self.aggregator.aggregate_ocr_transcripts(per_image_results)

        # Build base payload
        pipeline_output = {
            "session_id": session_id,
            "timestamp": timestamp,
            "total_images_processed": total_imgs,
            "per_image_results": per_image_results,
            "aggregated_data": agg_res["structured_data"],
            "markdown_report": agg_res["markdown_report"],
            "aggregator_meta": {
                "model_used": agg_res["model_used"],
                "latency_sec": agg_res["latency_sec"],
                "token_usage": agg_res["token_usage"]
            },
            "key_manager_status": key_manager.get_status_summary()
        }

        # -------------------------------------------------------------
        # STAGE 4: Statutory Legal Metrology (LMPC 2011) Rule Evaluation
        # -------------------------------------------------------------
        print(f"\n[Stage 4/4] Evaluating LMPC 2011 statutory compliance rules...")
        if progress_callback:
            progress_callback("Evaluating statutory compliance against LMPC 2011 rules...", 0.95)

        compliance_dict = {}
        legal_md_report = ""
        try:
            compliance_rep = self.rule_engine.evaluate(pipeline_output)
            compliance_dict = compliance_rep.model_dump()
            legal_md_report = generate_legal_markdown_report(compliance_rep)
            print(f"  -> Rule Evaluation Verdict: {compliance_rep.summary.overall_verdict.value} "
                  f"(Passed: {compliance_rep.summary.passed_parameters}, "
                  f"Failed: {compliance_rep.summary.failed_parameters})")
        except Exception as e:
            print(f"[WARN] Rule Engine evaluation encountered error: {e}")
            compliance_dict = {"error": str(e)}
            legal_md_report = f"# ⚖️ Statutory Legal Report - Evaluation Error\n\n```\n{e}\n```"

        pipeline_output["compliance_report"] = compliance_dict
        pipeline_output["legal_report_markdown"] = legal_md_report

        total_time = round(time.time() - start_time, 2)
        pipeline_output["total_pipeline_time_sec"] = total_time


        return pipeline_output
