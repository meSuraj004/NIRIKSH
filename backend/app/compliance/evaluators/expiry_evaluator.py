"""
Deterministic Expiry / Best Before / Use By Date Evaluator for LMPC 2011 (Rule 6(1)(da)).
"""

from typing import Dict, Any, Optional, List
from .base_evaluator import BaseParameterEvaluator
from ..models import (
    RuleDefinition,
    ParameterEvaluationResult,
    ProductDataInput,
    SubCheckResult,
    ComplianceStatus,
    Severity
)
from ..utils.date_parser import (
    parse_label_date,
    is_date_chronologically_valid,
    calculate_shelf_life_days,
    ParsedDate
)
from ..utils.commodity_classifier import classify_commodity, CommodityProfile


class ExpiryDateEvaluator(BaseParameterEvaluator):
    """Evaluates Expiry / Best Before / Use By Date against LMPC 2011 statutory rules."""

    def evaluate(self, product_data: ProductDataInput, context: Optional[Dict[str, Any]] = None) -> ParameterEvaluationResult:
        identity = product_data.product_identity or {}
        dates_data = product_data.dates_and_batch or {}
        reg_data = product_data.regulatory_and_certifications or {}
        ingredients_data = product_data.ingredients_and_allergens or {}
        nutritional_data = product_data.nutritional_information or {}
        ocr_lines = product_data.raw_ocr_lines or []
        full_text = product_data.full_text or ""

        # 1. Classify commodity (Consumable vs Non-Consumable)
        profile: CommodityProfile = classify_commodity(
            category=identity.get("category"),
            product_name=identity.get("product_name"),
            ingredients=ingredients_data.get("ingredients_list"),
            nutrients=nutritional_data.get("nutrients"),
            fssai_number=reg_data.get("fssai_license_number"),
            raw_ocr_lines=ocr_lines,
            full_text=full_text
        )

        sub_check_results: List[SubCheckResult] = []
        failure_reasons: List[str] = []
        remediation_steps: List[str] = []

        # EXP-APPLICABILITY Check
        sub_check_results.append(SubCheckResult(
            sub_check_id="EXP-APPLICABILITY",
            name="Consumable / Perishable Commodity Evaluation",
            status=ComplianceStatus.PASSED,
            severity=Severity.INFO,
            mandatory=True,
            details=f"Commodity classified as: '{profile.detected_category}' (Consumable: {profile.is_consumable}). Rationale: {profile.classification_rationale}",
            extracted_value=profile.to_dict()
        ))

        # Handle non-consumable commodities (e.g. Books, Electronics, Stationery)
        if not profile.is_consumable:
            return ParameterEvaluationResult(
                parameter=self.rule.parameter,
                rule_id=self.rule.rule_id,
                rule_title=self.rule.rule_title,
                section_reference=self.rule.section_reference,
                status=ComplianceStatus.NOT_APPLICABLE,
                confidence_score=profile.confidence,
                extracted_raw_value=None,
                extracted_normalized_value=None,
                findings=f"Expiry Date is NOT MANDATORY for non-consumable commodity ({profile.detected_category}). Marked NOT_APPLICABLE.",
                sub_checks=sub_check_results,
                failure_reasons=[],
                remediation_steps=[]
            )

        # For Consumable Commodities: Evaluate Expiry / Best Before / Use By
        raw_exp = dates_data.get("exp_date") or dates_data.get("best_before") or dates_data.get("use_by")
        raw_mfg = dates_data.get("mfg_date") or dates_data.get("manufacturing_date") or dates_data.get("packed_date")

        # Parse expiry date
        parsed_exp: Optional[ParsedDate] = parse_label_date(raw_exp)

        # Fallback: check OCR lines for EXP / Best Before / Use By
        if parsed_exp is None:
            for line in ocr_lines:
                if any(kw in line.upper() for kw in ["EXP", "USE BY", "BEST BEFORE", "EXPIRY"]):
                    parsed = parse_label_date(line)
                    if parsed:
                        parsed_exp = parsed
                        raw_exp = line
                        break

        # Check for cross-reference statements like "FOR USE BY DATE REFER TO BODY / CAP"
        has_refer_to_statement = any(
            "REFER TO" in line.upper() and ("USE BY" in line.upper() or "EXP" in line.upper() or "DATE" in line.upper())
            for line in ocr_lines
        )

        # 2. EXP-PRESENCE Check
        check_def_presence = next((sc for sc in self.rule.sub_checks if sc.sub_check_id == "EXP-PRESENCE"), None)
        has_presence = bool(raw_exp or parsed_exp)

        if has_presence:
            details = f"Expiry / Best Before declaration found: '{raw_exp}'"
            if has_refer_to_statement:
                details += " (Referenced on main label with stamped date)"
            sub_check_results.append(SubCheckResult(
                sub_check_id="EXP-PRESENCE",
                name="Expiry / Best Before Declaration Presence",
                status=ComplianceStatus.PASSED,
                severity=Severity.CRITICAL,
                mandatory=True,
                details=details,
                extracted_value=raw_exp
            ))
        else:
            sub_check_results.append(SubCheckResult(
                sub_check_id="EXP-PRESENCE",
                name="Expiry / Best Before Declaration Presence",
                status=ComplianceStatus.FAILED,
                severity=Severity.CRITICAL,
                mandatory=True,
                details="Consumable product lacks mandatory 'Expiry Date', 'Use By Date', or 'Best Before' declaration (Rule 6(1)(da)).",
                error_code="ERR_EXPIRY_DATE_MISSING",
                remediation=check_def_presence.remediation if check_def_presence else None
            ))
            failure_reasons.append("Mandatory Expiry / Best Before date is missing on consumable commodity.")
            if check_def_presence and check_def_presence.remediation:
                remediation_steps.append(check_def_presence.remediation)

            return ParameterEvaluationResult(
                parameter=self.rule.parameter,
                rule_id=self.rule.rule_id,
                rule_title=self.rule.rule_title,
                section_reference=self.rule.section_reference,
                status=ComplianceStatus.FAILED,
                confidence_score=1.0,
                extracted_raw_value=None,
                extracted_normalized_value=None,
                findings="Consumable product is missing mandatory Expiry/Best Before declaration.",
                sub_checks=sub_check_results,
                failure_reasons=failure_reasons,
                remediation_steps=remediation_steps
            )

        # 3. EXP-DATE-FORMAT Check
        check_def_format = next((sc for sc in self.rule.sub_checks if sc.sub_check_id == "EXP-DATE-FORMAT"), None)
        valid_format = bool(parsed_exp and (parsed_exp.is_period_declaration or (parsed_exp.year > 0 and parsed_exp.month > 0)))

        if valid_format:
            norm_val = (
                f"Period: {parsed_exp.period_months or parsed_exp.period_days} units"
                if parsed_exp.is_period_declaration
                else parsed_exp.formatted_iso
            )
            sub_check_results.append(SubCheckResult(
                sub_check_id="EXP-DATE-FORMAT",
                name="Valid Expiry Date or Period Specification",
                status=ComplianceStatus.PASSED,
                severity=Severity.CRITICAL,
                mandatory=True,
                details=f"Parsed valid expiry specification: {norm_val}",
                extracted_value=norm_val
            ))
        else:
            sub_check_results.append(SubCheckResult(
                sub_check_id="EXP-DATE-FORMAT",
                name="Valid Expiry Date or Period Specification",
                status=ComplianceStatus.FAILED,
                severity=Severity.CRITICAL,
                mandatory=True,
                details=f"Expiry declaration '{raw_exp}' could not be parsed into a valid date or duration.",
                extracted_value=raw_exp,
                error_code="ERR_EXPIRY_INVALID_FORMAT",
                remediation=check_def_format.remediation if check_def_format else None
            ))
            failure_reasons.append(f"Expiry declaration '{raw_exp}' format is invalid.")
            if check_def_format and check_def_format.remediation:
                remediation_steps.append(check_def_format.remediation)

        # 4. EXP-CHRONOLOGICAL-CONSISTENCY Check
        parsed_mfg = parse_label_date(raw_mfg)
        if parsed_exp and parsed_mfg:
            is_valid_chrono, chrono_msg = is_date_chronologically_valid(parsed_mfg, parsed_exp)
            if is_valid_chrono:
                sub_check_results.append(SubCheckResult(
                    sub_check_id="EXP-CHRONOLOGICAL-CONSISTENCY",
                    name="Chronological Consistency (Expiry >= Mfg Date)",
                    status=ComplianceStatus.PASSED,
                    severity=Severity.CRITICAL,
                    mandatory=True,
                    details=f"Logical date ordering validated: {chrono_msg}",
                    extracted_value={"mfg_date": parsed_mfg.formatted_iso, "exp_date": parsed_exp.formatted_iso if not parsed_exp.is_period_declaration else "period"}
                ))
            else:
                sub_check_results.append(SubCheckResult(
                    sub_check_id="EXP-CHRONOLOGICAL-CONSISTENCY",
                    name="Chronological Consistency (Expiry >= Mfg Date)",
                    status=ComplianceStatus.FAILED,
                    severity=Severity.CRITICAL,
                    mandatory=True,
                    details=f"Logical inconsistency: {chrono_msg}",
                    extracted_value={"mfg_date": parsed_mfg.formatted_iso, "exp_date": parsed_exp.formatted_iso},
                    error_code="ERR_EXPIRY_BEFORE_MFG"
                ))
                failure_reasons.append(f"Expiry date occurs before Manufacturing date: {chrono_msg}")

        # 5. EXP-SHELF-LIFE-INTERVAL Check (Warning check)
        if parsed_exp and parsed_mfg:
            shelf_life_days = calculate_shelf_life_days(parsed_mfg, parsed_exp)
            if shelf_life_days is not None:
                if 1 <= shelf_life_days <= 3650:  # 1 day to 10 years
                    sub_check_results.append(SubCheckResult(
                        sub_check_id="EXP-SHELF-LIFE-INTERVAL",
                        name="Reasonable Shelf Life Duration",
                        status=ComplianceStatus.PASSED,
                        severity=Severity.WARNING,
                        mandatory=False,
                        details=f"Computed shelf life interval is {shelf_life_days} days (~{round(shelf_life_days/30, 1)} months).",
                        extracted_value=shelf_life_days
                    ))
                elif shelf_life_days > 3650:
                    sub_check_results.append(SubCheckResult(
                        sub_check_id="EXP-SHELF-LIFE-INTERVAL",
                        name="Reasonable Shelf Life Duration",
                        status=ComplianceStatus.CONDITIONAL_PASS,
                        severity=Severity.WARNING,
                        mandatory=False,
                        details=f"Declared shelf life interval ({shelf_life_days} days) is unusually long (>10 years).",
                        extracted_value=shelf_life_days,
                        error_code="WARN_IMPLAUSIBLE_SHELF_LIFE"
                    ))

        # Overall Status
        critical_failures = [
            sc for sc in sub_check_results
            if sc.mandatory and sc.status == ComplianceStatus.FAILED
        ]
        overall_status = ComplianceStatus.PASSED if not critical_failures else ComplianceStatus.FAILED

        findings_summary = (
            f"Expiry Date declaration ({parsed_exp.formatted_iso if parsed_exp and not parsed_exp.is_period_declaration else raw_exp}) satisfies Rule 6(1)(da)."
            if overall_status == ComplianceStatus.PASSED
            else f"Expiry Date declaration failed {len(critical_failures)} check(s)."
        )

        return ParameterEvaluationResult(
            parameter=self.rule.parameter,
            rule_id=self.rule.rule_id,
            rule_title=self.rule.rule_title,
            section_reference=self.rule.section_reference,
            status=overall_status,
            confidence_score=1.0,
            extracted_raw_value=raw_exp,
            extracted_normalized_value=parsed_exp.formatted_iso if parsed_exp and not parsed_exp.is_period_declaration else raw_exp,
            findings=findings_summary,
            sub_checks=sub_check_results,
            failure_reasons=failure_reasons,
            remediation_steps=remediation_steps
        )
