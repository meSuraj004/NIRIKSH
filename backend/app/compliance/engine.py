"""
Main LMPC 2011 Rule Engine Controller.
Coordinates deterministic evaluation of structured OCR label data against statutory rules.
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Union

from .models import (
    RuleBook,
    RuleDefinition,
    ProductDataInput,
    ComplianceReport,
    ComplianceSummary,
    ComplianceStatus,
    ParameterEvaluationResult,
    Severity
)
from .repository import RuleRepository, JSONRuleRepository
from .evaluators.mrp_evaluator import MRPEvaluator
from .evaluators.mfg_date_evaluator import ManufacturingDateEvaluator
from .evaluators.expiry_evaluator import ExpiryDateEvaluator
from .utils.commodity_classifier import classify_commodity


class RuleEngine:
    """
    General deterministic Rule Engine for packaged commodity compliance verification
    based on Legal Metrology (Packaged Commodities) Rules, 2011.
    """

    def __init__(self, repository: Optional[RuleRepository] = None):
        self.repository = repository or JSONRuleRepository()
        self.rulebook: RuleBook = self.repository.load_rulebook()
        self._init_evaluators()

    def _init_evaluators(self):
        """Instantiates evaluators for registered rules."""
        self.evaluators = {}
        for rule in self.rulebook.rules:
            param = rule.parameter.lower()
            if param == "mrp":
                self.evaluators[param] = MRPEvaluator(rule)
            elif param in ("manufacture_date", "mfg_date", "packing_date"):
                self.evaluators["manufacture_date"] = ManufacturingDateEvaluator(rule)
            elif param in ("expiry_date", "exp_date", "best_before"):
                self.evaluators["expiry_date"] = ExpiryDateEvaluator(rule)

    def normalize_input(self, raw_input: Union[Dict[str, Any], ProductDataInput]) -> ProductDataInput:
        """
        Extracts and normalizes product data from either:
          - Standard multi-view OCR session JSON (e.g. session_20260828_192205_data.json)
          - Single product dictionary
          - Direct ProductDataInput instance
        """
        if isinstance(raw_input, ProductDataInput):
            return raw_input

        if not isinstance(raw_input, dict):
            raise ValueError(f"Expected dict or ProductDataInput, received {type(raw_input)}")

        session_id = raw_input.get("session_id")
        timestamp = raw_input.get("timestamp")

        # Collect raw OCR lines across all views if present
        raw_ocr_lines = []
        full_text_chunks = []
        if "per_image_results" in raw_input and isinstance(raw_input["per_image_results"], list):
            for img_res in raw_input["per_image_results"]:
                lines = img_res.get("text_lines") or []
                raw_ocr_lines.extend(lines)
                if img_res.get("full_text"):
                    full_text_chunks.append(img_res["full_text"])

        # If aggregated_data key is present (from Part 1 pipeline)
        if "aggregated_data" in raw_input and isinstance(raw_input["aggregated_data"], dict):
            agg = raw_input["aggregated_data"]
            return ProductDataInput(
                session_id=session_id,
                timestamp=timestamp,
                product_identity=agg.get("product_identity") or {},
                dates_and_batch=agg.get("dates_and_batch") or {},
                pricing_and_quantity=agg.get("pricing_and_quantity") or {},
                ingredients_and_allergens=agg.get("ingredients_and_allergens") or {},
                nutritional_information=agg.get("nutritional_information") or {},
                regulatory_and_certifications=agg.get("regulatory_and_certifications") or {},
                raw_ocr_lines=raw_ocr_lines,
                full_text="\n\n".join(full_text_chunks) if full_text_chunks else raw_input.get("full_text")
            )

        # Direct flattened dictionary
        return ProductDataInput(
            session_id=session_id,
            timestamp=timestamp,
            product_identity=raw_input.get("product_identity") or raw_input.get("identity") or {},
            dates_and_batch=raw_input.get("dates_and_batch") or raw_input.get("dates") or {},
            pricing_and_quantity=raw_input.get("pricing_and_quantity") or raw_input.get("pricing") or {},
            ingredients_and_allergens=raw_input.get("ingredients_and_allergens") or {},
            nutritional_information=raw_input.get("nutritional_information") or {},
            regulatory_and_certifications=raw_input.get("regulatory_and_certifications") or {},
            raw_ocr_lines=raw_ocr_lines or raw_input.get("raw_ocr_lines") or [],
            full_text=raw_input.get("full_text")
        )

    def evaluate(
        self,
        input_data: Union[Dict[str, Any], ProductDataInput],
        parameters_to_evaluate: Optional[List[str]] = None
    ) -> ComplianceReport:
        """
        Executes deterministic evaluation against the LMPC 2011 rulebook.
        Parameters evaluated by default: ['mrp', 'manufacture_date', 'expiry_date'].
        """
        product_data = self.normalize_input(input_data)
        eval_timestamp = datetime.now().isoformat()

        targets = [p.lower() for p in (parameters_to_evaluate or ["mrp", "manufacture_date", "expiry_date"])]

        # Classify commodity profile
        commodity_profile = classify_commodity(
            category=product_data.product_identity.get("category"),
            product_name=product_data.product_identity.get("product_name"),
            ingredients=product_data.ingredients_and_allergens.get("ingredients_list"),
            nutrients=product_data.nutritional_information.get("nutrients"),
            fssai_number=product_data.regulatory_and_certifications.get("fssai_license_number"),
            raw_ocr_lines=product_data.raw_ocr_lines,
            full_text=product_data.full_text
        ).to_dict()

        param_results: Dict[str, ParameterEvaluationResult] = {}
        audit_trail: List[str] = [
            f"Initialized evaluation for session: {product_data.session_id or 'anonymous'}",
            f"Rulebook: {self.rulebook.rulebook_id} (Version: {self.rulebook.version})",
            f"Commodity Classified: {commodity_profile.get('detected_category')} (Consumable: {commodity_profile.get('is_consumable')})"
        ]

        passed_count = 0
        failed_count = 0
        review_count = 0
        na_count = 0
        critical_violations = 0
        major_violations = 0
        warnings_count = 0

        for param in targets:
            evaluator = self.evaluators.get(param)
            if not evaluator:
                audit_trail.append(f"Skipping unregistered parameter: {param}")
                continue

            result = evaluator.evaluate(product_data, context={"commodity_profile": commodity_profile})

            # A FAILED verdict with nothing extracted means the value was never
            # detected (possible OCR failure), so it must go to manual review
            # instead of being reported as a definite violation.
            if (
                result.status == ComplianceStatus.FAILED
                and result.extracted_raw_value is None
                and result.extracted_normalized_value is None
            ):
                result.status = ComplianceStatus.REVIEW
                audit_trail.append(
                    f"Parameter '{param.upper()}': value not detected by extraction; marked REVIEW for manual inspection."
                )

            param_results[param] = result

            audit_trail.append(
                f"Parameter '{param.upper()}': Status={result.status.value} (Rule: {result.section_reference})"
            )

            if result.status == ComplianceStatus.PASSED:
                passed_count += 1
            elif result.status == ComplianceStatus.REVIEW:
                review_count += 1
            elif result.status == ComplianceStatus.NOT_APPLICABLE:
                na_count += 1
            elif result.status == ComplianceStatus.FAILED:
                failed_count += 1

            for sc in result.sub_checks:
                if sc.status == ComplianceStatus.FAILED and sc.mandatory:
                    if sc.severity == Severity.CRITICAL:
                        critical_violations += 1
                    elif sc.severity == Severity.MAJOR:
                        major_violations += 1
                elif sc.severity == Severity.WARNING and sc.status != ComplianceStatus.PASSED:
                    warnings_count += 1

        if failed_count > 0:
            overall_verdict = ComplianceStatus.FAILED
        elif review_count > 0:
            overall_verdict = ComplianceStatus.REVIEW
        else:
            overall_verdict = ComplianceStatus.PASSED

        summary = ComplianceSummary(
            total_parameters_evaluated=len(param_results),
            passed_parameters=passed_count,
            failed_parameters=failed_count,
            review_parameters=review_count,
            not_applicable_parameters=na_count,
            overall_verdict=overall_verdict,
            critical_violations_count=critical_violations,
            major_violations_count=major_violations,
            warnings_count=warnings_count
        )

        return ComplianceReport(
            session_id=product_data.session_id,
            evaluation_timestamp=eval_timestamp,
            rulebook_version=self.rulebook.version,
            commodity_profile=commodity_profile,
            parameter_results=param_results,
            summary=summary,
            audit_trail=audit_trail
        )
