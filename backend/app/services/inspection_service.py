import json
import threading
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.ai.pipeline.extraction import build_declarations
from app.models import (
    CheckStatus,
    ComplianceCheck,
    Declaration,
    DeclarationStatus,
    Evidence,
    Inspection,
    InspectionStatus,
    OCRResult,
    ProductImage,
    Report,
    Violation,
)

_pipeline = None
_pipeline_lock = threading.Lock()


def _get_pipeline():
    global _pipeline
    with _pipeline_lock:
        if _pipeline is None:
            from app.ai.pipeline.unified_pipeline import UnifiedPackagingPipeline

            _pipeline = UnifiedPackagingPipeline(
                captured_dir=str(settings.storage_dir / "captured"),
            )
        return _pipeline


def _store_compliance(db: Session, inspection: Inspection, compliance_report: dict) -> None:
    for parameter, result in (compliance_report.get("parameter_results") or {}).items():
        status = CheckStatus(result["status"])
        normalized = result.get("extracted_normalized_value")
        extracted = (
            json.dumps(normalized, ensure_ascii=False)
            if normalized is not None
            else result.get("extracted_raw_value")
        )
        check = ComplianceCheck(
            inspection_id=inspection.id,
            parameter=parameter,
            status=status,
            extracted_value=extracted,
            findings=result.get("findings"),
            details={
                "sub_checks": result.get("sub_checks", []),
                "section_reference": result.get("section_reference"),
                "rule_id": result.get("rule_id"),
            },
        )
        db.add(check)
        db.flush()

        for sub in result.get("sub_checks", []):
            if sub.get("status") == "FAILED":
                db.add(Violation(
                    inspection_id=inspection.id,
                    compliance_check_id=check.id,
                    error_code=sub.get("error_code"),
                    severity=sub.get("severity"),
                    description=f"{sub.get('name')}: {sub.get('details')}",
                    remediation=sub.get("remediation"),
                ))


def run_inspection_pipeline(inspection_id: int) -> None:
    """Runs OCR + aggregation + rule evaluation for an inspection and persists results.

    Intended to be executed in a background thread; all state is written to the DB.
    """
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        inspection = db.get(Inspection, inspection_id)
        if inspection is None:
            return
        inspection.status = InspectionStatus.PROCESSING
        db.commit()

        image_paths: list[tuple[ProductImage, str]] = []
        for img in inspection.images:
            path = Path(img.file_path)
            if path.exists():
                image_paths.append((img, str(path)))
        if not image_paths:
            raise ValueError("No image files available on disk for this inspection.")

        pipeline = _get_pipeline()
        result = pipeline.run_on_images(
            image_inputs=[p for _, p in image_paths],
            session_name=f"inspection_{inspection_id}",
        )

        image_by_index = {i: img for i, (img, _) in enumerate(image_paths)}
        agg_meta = result.get("aggregator_meta") or {}
        agg_model = agg_meta.get("model_used")

        for idx, per_image in enumerate(result.get("per_image_results", [])):
            img = image_by_index.get(idx)
            if img is None:
                continue
            db.add(OCRResult(
                image_id=img.id,
                engine=per_image.get("engine"),
                model=agg_model,
                raw_text=per_image.get("full_text"),
                line_count=per_image.get("ocr_total_lines"),
                latency_sec=per_image.get("ocr_latency_sec"),
                token_usage=per_image.get("token_usage"),
            ))
            db.add(Evidence(
                inspection_id=inspection.id,
                image_id=img.id,
                kind="ocr_transcript",
                file_path=per_image.get("saved_ocr_path"),
                meta={
                    "source_path": per_image.get("source_path"),
                    "enhanced_path": per_image.get("saved_color_path"),
                },
            ))

        # Declarations: evidence-verified and attributed to the source image.
        # Nulls stay null and nothing is substituted; values not present in any
        # OCR transcript are marked UNCERTAIN for manual review.
        evidence = [
            {"view_index": idx, "text": per_image.get("full_text") or ""}
            for idx, per_image in enumerate(result.get("per_image_results", []))
        ]
        status_map = {
            "DETECTED": DeclarationStatus.DETECTED,
            "NOT_DETECTED": DeclarationStatus.NOT_DETECTED,
            "UNCERTAIN": DeclarationStatus.UNCERTAIN,
        }
        for row in build_declarations(result.get("aggregated_data") or {}, evidence):
            source_image = image_by_index.get(row["source_view"]) if row["source_view"] is not None else None
            db.add(Declaration(
                inspection_id=inspection.id,
                field_name=row["field_name"],
                value=row["value"],
                status=status_map[row["status"]],
                confidence=None,
                bbox=None,
                source_image_id=source_image.id if source_image else None,
                extraction_method=row["extraction_method"],
            ))

        compliance = result.get("compliance_report")
        if compliance and "error" not in compliance:
            _store_compliance(db, inspection, compliance)

        if result.get("markdown_report") or result.get("legal_report_markdown"):
            report = Report(
                inspection_id=inspection.id,
                format="markdown",
                content="\n\n---\n\n".join(
                    x for x in (result.get("markdown_report"), result.get("legal_report_markdown")) if x
                ),
            )
            db.add(report)
            report.file_path = result.get("saved_legal_report_path")

        inspection.status = InspectionStatus.COMPLETED
        db.commit()
    except Exception as exc:
        db.rollback()
        inspection = db.get(Inspection, inspection_id)
        if inspection is not None:
            inspection.status = InspectionStatus.FAILED
            inspection.error_message = str(exc)
            db.commit()
    finally:
        db.close()
