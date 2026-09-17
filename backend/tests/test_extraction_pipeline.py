"""Phase 2 pipeline-integrity tests.

All AI outputs here are MOCKED fixtures (no real Groq credentials are used);
the extraction, attribution, persistence and rule-engine integration paths run
for real.
"""

import os
import sys
import uuid
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.models import Declaration, Inspection, InspectionStatus
from conftest import TestSession, client

HEADERS = None


def setup_module(module):
    global HEADERS
    from conftest import signup_and_login

    HEADERS = signup_and_login("phase2@example.com")


# --- mocked OCR transcripts (stand in for real Groq Vision OCR output) ---

BISCUIT_VIEWS = [
    "BRITANNIA GOOD DAY BUTTER COOKIES\nMRP Rs.30 (Inclusive of all taxes)\nNet Qty. 250 g\nMFG 02/2026",
    "Manufactured by Britannia Industries Ltd\nBest Before 6 months from packaging\nFSSAI Lic. No. 10012021000123",
]
JUICE_VIEWS = [
    "REAL FRUIT POWER MANGO\nMRP ₹65.00 (incl. of all taxes)\nNet Volume 1 L",
    "Marketed by Dabur India Ltd\nUse By Nov 2026\nBatch X9921",
]
SOAP_VIEWS = [
    "LUX SOAP\nNet Wt. 100 g",
    "No MRP printed on this panel",
]

AGG_BISCUIT = {
    "product_identity": {"brand_name": "Britannia", "product_name": "Good Day Butter Cookies", "category": "Packaged Food"},
    "manufacturer_and_marketer": {"manufactured_by": "Britannia Industries Ltd", "country_of_origin": None},
    "dates_and_batch": {"mfg_date": "02/2026", "exp_date": None, "best_before": "6 months from packaging"},
    "pricing_and_quantity": {"mrp": "Rs.30 (Inclusive of all taxes)", "mrp_numerical_inr": 30, "net_quantity": "250 g"},
    "compliance_summary": {"detected_mandatory_fields": ["mrp"], "missing_or_unclear_fields": ["exp_date"]},
}
AGG_JUICE = {
    "product_identity": {"brand_name": "Real", "product_name": "Fruit Power Mango", "category": "Beverage"},
    "manufacturer_and_marketer": {"manufactured_by": None, "marketed_by": "Dabur India Ltd"},
    "dates_and_batch": {"mfg_date": None, "exp_date": "Nov 2026"},
    "pricing_and_quantity": {"mrp": "₹65.00 (incl. of all taxes)", "mrp_numerical_inr": 65, "net_quantity": "1 L"},
    "compliance_summary": {"detected_mandatory_fields": ["mrp"], "missing_or_unclear_fields": ["mfg_date"]},
}
# LLM invented a manufacturer that appears in NO transcript; MRP is missing entirely.
AGG_SOAP = {
    "product_identity": {"brand_name": "Lux", "product_name": "Soap", "category": "Personal Care"},
    "manufacturer_and_marketer": {"manufactured_by": "Hindustan Unilever Ltd"},
    "pricing_and_quantity": {"mrp": None, "net_quantity": "100 g"},
    "compliance_summary": {},
}


def _mock_result(views, aggregated):
    return {
        "per_image_results": [
            {
                "full_text": text,
                "text_lines": text.splitlines(),
                "ocr_total_lines": len(text.splitlines()),
                "ocr_latency_sec": 0.4,
                "token_usage": {"total_tokens": 100},
                "source_path": f"view_{i + 1}.jpg",
                "saved_color_path": None,
                "saved_ocr_path": None,
            }
            for i, text in enumerate(views)
        ],
        "aggregated_data": aggregated,
        "aggregator_meta": {"model_used": "mock-model", "latency_sec": 1.0},
        "markdown_report": f"# mock report for {aggregated['product_identity']['brand_name']}",
        "legal_report_markdown": "# mock legal report",
        "total_pipeline_time_sec": 1.5,
    }


def _run_mocked_inspection(views, aggregated):
    res = client.post("/api/inspections", json={"notes": "phase2"}, headers=HEADERS)
    inspection_id = res.json()["id"]

    storage = os.path.join(BASE_DIR, "..", "storage", "test")
    os.makedirs(storage, exist_ok=True)
    image_ids = []
    for i in range(len(views)):
        path = os.path.join(storage, f"{inspection_id}_{i}_{uuid.uuid4().hex[:6]}.jpg")
        with open(path, "wb") as fh:
            fh.write(b"fake-jpeg")
        with open(path, "rb") as fh:
            img_res = client.post(
                f"/api/inspections/{inspection_id}/images",
                files={"files": (f"view_{i}.jpg", fh, "image/jpeg")},
                headers=HEADERS,
            )
        image_ids.append(img_res.json()[0]["id"])

    from app.compliance.engine import RuleEngine

    pipeline_result = _mock_result(views, aggregated)
    compliance = RuleEngine().evaluate(pipeline_result)
    pipeline_result["compliance_report"] = compliance.model_dump()
    pipeline_result["legal_report_markdown"] = "# mock legal report"

    with patch(
        "app.services.inspection_service._get_pipeline",
        return_value=type("FakePipeline", (), {"run_on_images": staticmethod(lambda *a, **k: pipeline_result)}),
    ), patch("app.database.SessionLocal", TestSession):
        client.post(f"/api/inspections/{inspection_id}/process", headers=HEADERS)

    db = TestSession()
    try:
        inspection = db.get(Inspection, inspection_id)
        declarations = {
            d.field_name: d
            for d in db.query(Declaration).filter(Declaration.inspection_id == inspection_id).all()
        }
        reports = [r.id for r in inspection.reports]
        report_bodies = [(r.format, r.file_path, bool(r.content)) for r in inspection.reports]
        inspection = db.get(Inspection, inspection_id)
        return inspection, declarations, image_ids, report_bodies, len(reports)
    finally:
        db.close()


class TestEvidenceExtraction:
    def test_source_attribution_and_evidence_verification(self):
        from app.ai.pipeline.extraction import build_declarations

        rows = build_declarations(
            AGG_BISCUIT,
            [{"view_index": 0, "text": BISCUIT_VIEWS[0]}, {"view_index": 1, "text": BISCUIT_VIEWS[1]}],
        )
        by_name = {r["field_name"]: r for r in rows}

        # MRP text appears only in view 0 -> attributed there
        assert by_name["pricing_and_quantity.mrp"]["source_view"] == 0
        assert by_name["pricing_and_quantity.mrp"]["status"] == "DETECTED"
        # manufacturer appears only in view 1
        assert by_name["manufacturer_and_marketer.manufactured_by"]["source_view"] == 1
        # missing fields stay null + NOT_DETECTED
        assert by_name["manufacturer_and_marketer.country_of_origin"]["value"] is None
        assert by_name["manufacturer_and_marketer.country_of_origin"]["status"] == "NOT_DETECTED"
        assert by_name["dates_and_batch.exp_date"]["status"] == "NOT_DETECTED"

    def test_llm_invented_value_marked_uncertain(self):
        from app.ai.pipeline.extraction import build_declarations

        rows = build_declarations(
            AGG_SOAP,
            [{"view_index": 0, "text": SOAP_VIEWS[0]}, {"view_index": 1, "text": SOAP_VIEWS[1]}],
        )
        by_name = {r["field_name"]: r for r in rows}

        assert by_name["manufacturer_and_marketer.manufactured_by"]["status"] == "UNCERTAIN"
        assert by_name["manufacturer_and_marketer.manufactured_by"]["source_view"] is None
        assert by_name["pricing_and_quantity.mrp"]["status"] == "NOT_DETECTED"
        assert by_name["pricing_and_quantity.mrp"]["value"] is None

    def test_deterministic_repeats(self):
        from app.ai.pipeline.extraction import build_declarations

        evidence = [{"view_index": 0, "text": BISCUIT_VIEWS[0]}, {"view_index": 1, "text": BISCUIT_VIEWS[1]}]
        assert build_declarations(AGG_BISCUIT, evidence) == build_declarations(AGG_BISCUIT, evidence)


class TestCrossInspectionIsolation:
    def test_independent_products_keep_independent_values(self):
        biscuit, biscuit_decls, biscuit_imgs, biscuit_reports, _ = _run_mocked_inspection(BISCUIT_VIEWS, AGG_BISCUIT)
        juice, juice_decls, juice_imgs, _, _ = _run_mocked_inspection(JUICE_VIEWS, AGG_JUICE)
        soap, soap_decls, _, _, _ = _run_mocked_inspection(SOAP_VIEWS, AGG_SOAP)

        assert biscuit.status == InspectionStatus.COMPLETED
        assert juice.status == InspectionStatus.COMPLETED
        assert soap.status == InspectionStatus.COMPLETED

        # different MRP values remain different
        assert biscuit_decls["pricing_and_quantity.mrp"].value == "Rs.30 (Inclusive of all taxes)"
        assert juice_decls["pricing_and_quantity.mrp"].value == "₹65.00 (incl. of all taxes)"
        # different quantities remain different
        assert biscuit_decls["pricing_and_quantity.net_quantity"].value == "250 g"
        assert juice_decls["pricing_and_quantity.net_quantity"].value == "1 L"
        assert soap_decls["pricing_and_quantity.net_quantity"].value == "100 g"
        # manufacturers are not copied between products
        assert "Britannia" in biscuit_decls["manufacturer_and_marketer.manufactured_by"].value
        assert "Britannia" not in (juice_decls["manufacturer_and_marketer.manufactured_by"].value or "")
        assert "Dabur" not in (biscuit_decls["manufacturer_and_marketer.manufactured_by"].value or "")

        # missing fields remain NOT_DETECTED/null in the DB
        assert juice_decls["dates_and_batch.mfg_date"].value is None
        assert juice_decls["dates_and_batch.mfg_date"].status.value == "NOT_DETECTED"
        assert soap_decls["pricing_and_quantity.mrp"].status.value == "NOT_DETECTED"

        # source image attribution is correct
        assert biscuit_decls["pricing_and_quantity.mrp"].source_image_id == biscuit_imgs[0]
        assert biscuit_decls["manufacturer_and_marketer.manufactured_by"].source_image_id == biscuit_imgs[1]
        assert juice_decls["dates_and_batch.exp_date"].source_image_id == juice_imgs[1]

        # confidence is never fabricated
        for d in list(biscuit_decls.values()) + list(juice_decls.values()):
            assert d.confidence is None

        # no fabricated report file path from a previous scan; content persisted in DB
        for fmt, file_path, has_content in biscuit_reports:
            assert fmt == "markdown"
            assert file_path is None
            assert has_content

    def test_declarations_feed_compliance_engine(self):
        # The same aggregated payloads must be valid rule-engine inputs.
        from app.compliance.engine import RuleEngine
        from app.compliance.models import ComplianceStatus

        engine = RuleEngine()

        def with_views(session_id, views, aggregated):
            return engine.evaluate({
                "session_id": session_id,
                "aggregated_data": aggregated,
                "per_image_results": [{"text_lines": v.splitlines(), "full_text": v} for v in views],
            })

        biscuit = with_views("iso-b", BISCUIT_VIEWS, AGG_BISCUIT)
        juice = with_views("iso-j", JUICE_VIEWS, AGG_JUICE)
        soap = with_views("iso-s", SOAP_VIEWS, AGG_SOAP)

        assert biscuit.parameter_results["mrp"].status == ComplianceStatus.PASSED
        assert juice.parameter_results["mrp"].status == ComplianceStatus.PASSED
        # soap has no MRP detected anywhere -> manual review, not a fake FAIL/PASS
        assert soap.parameter_results["mrp"].status == ComplianceStatus.REVIEW
        assert soap.summary.overall_verdict == ComplianceStatus.REVIEW
