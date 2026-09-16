"""
Deterministic Manufacturing / Packing Date Evaluator for LMPC 2011 (Rule 6(1)(d), Explanation I).
"""

from typing import Dict, Any, Optional, List
from datetime import date, timedelta
from .base_evaluator import BaseParameterEvaluator
from ..models import (
    RuleDefinition,
    ParameterEvaluationResult,
    ProductDataInput,
    SubCheckResult,
    ComplianceStatus,
    Severity
)
from ..utils.date_parser import parse_label_date, ParsedDate


class ManufacturingDateEvaluator(BaseParameterEvaluator):
    """Evaluates Date of Manufacture / Packing / Import against LMPC 2011 statutory rules."""

    def evaluate(self, product_data: ProductDataInput, context: Optional[Dict[str, Any]] = None) -> ParameterEvaluationResult:
        dates_data = product_data.dates_and_batch or {}
        raw_mfg = dates_data.get("mfg_date") or dates_data.get("manufacturing_date") or dates_data.get("packed_date")
        ocr_lines = product_data.raw_ocr_lines or []
        full_text = product_data.full_text or ""

        # Parse declared date
        parsed_mfg: Optional[ParsedDate] = parse_label_date(raw_mfg)

        # Fallback: scan OCR lines for MFD / Mfg patterns if not present directly
        if parsed_mfg is None:
            for line in ocr_lines:
                if any(kw in line.upper() for kw in ["MFG", "MFD", "PKD", "PACKED", "DATE OF MFG"]):
                    parsed = parse_label_date(line)
                    if parsed:
                        parsed_mfg = parsed
                        raw_mfg = line
                        break

        # Check for cross-reference statements like "FOR MFG. DATE REFER TO BODY / CAP"
        has_refer_to_statement = any(
            "REFER TO" in line.upper() and ("MFG" in line.upper() or "DATE" in line.upper())
            for line in ocr_lines
        )

        sub_check_results: List[SubCheckResult] = []
        failure_reasons: List[str] = []
        remediation_steps: List[str] = []

        # 1. MFG-PRESENCE Check
        check_def_presence = next((sc for sc in self.rule.sub_checks if sc.sub_check_id == "MFG-PRESENCE"), None)
        has_presence = bool(raw_mfg or parsed_mfg)

        if has_presence:
            presence_details = f"Manufacturing / Packing date declaration found: '{raw_mfg}'"
            if has_refer_to_statement:
                presence_details += " (Accompanied by cross-reference statement 'refer to body/cap')"
            sub_check_results.append(SubCheckResult(
                sub_check_id="MFG-PRESENCE",
                name="Manufacturing/Packing Date Declaration Presence",
                status=ComplianceStatus.PASSED,
                severity=Severity.CRITICAL,
                mandatory=True,
                details=presence_details,
                extracted_value=raw_mfg
            ))
        else:
            sub_check_results.append(SubCheckResult(
                sub_check_id="MFG-PRESENCE",
                name="Manufacturing/Packing Date Declaration Presence",
                status=ComplianceStatus.FAILED,
                severity=Severity.CRITICAL,
                mandatory=True,
                details="No date of manufacture, packing, or import found on the package.",
                error_code="ERR_MFG_DATE_MISSING",
                remediation=check_def_presence.remediation if check_def_presence else None
            ))
            failure_reasons.append("Mandatory Month and Year of Manufacture / Packing is missing.")
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
                findings="Mandatory date of manufacture/packing missing from label.",
                sub_checks=sub_check_results,
                failure_reasons=failure_reasons,
                remediation_steps=remediation_steps
            )

        # 2. MFG-PREFIX Check
        check_def_prefix = next((sc for sc in self.rule.sub_checks if sc.sub_check_id == "MFG-PREFIX"), None)
        has_qualifier = False
        if raw_mfg:
            raw_upper = str(raw_mfg).upper()
            has_qualifier = any(kw in raw_upper for kw in ["MFG", "MFD", "PKD", "PACKED", "DATE", "MANUFACTURED"])
        if not has_qualifier and has_refer_to_statement:
            # Stamped on body/cap with a standard reference on label satisfies qualifier requirement under LMPC practice
            has_qualifier = True

        if has_qualifier:
            sub_check_results.append(SubCheckResult(
                sub_check_id="MFG-PREFIX",
                name="Manufacturing/Packing Qualifying Prefix",
                status=ComplianceStatus.PASSED,
                severity=Severity.MAJOR,
                mandatory=True,
                details="Identified with qualifying prefix ('MFD' / 'MFG' / 'PKD' or referenced on label).",
                extracted_value=raw_mfg
            ))
        else:
            sub_check_results.append(SubCheckResult(
                sub_check_id="MFG-PREFIX",
                name="Manufacturing/Packing Qualifying Prefix",
                status=ComplianceStatus.CONDITIONAL_PASS,
                severity=Severity.MAJOR,
                mandatory=True,
                details="Date is present but lacks explicit 'MFD' / 'PKD' prefix on the standalone token.",
                extracted_value=raw_mfg,
                error_code="WARN_MFG_PREFIX_MISSING"
            ))

        # 3. MFG-DATE-FORMAT Check
        check_def_format = next((sc for sc in self.rule.sub_checks if sc.sub_check_id == "MFG-DATE-FORMAT"), None)
        if parsed_mfg and (parsed_mfg.year > 0 and parsed_mfg.month > 0):
            sub_check_results.append(SubCheckResult(
                sub_check_id="MFG-DATE-FORMAT",
                name="Standard Month and Year Format",
                status=ComplianceStatus.PASSED,
                severity=Severity.CRITICAL,
                mandatory=True,
                details=f"Parsed valid month and year: {parsed_mfg.formatted_iso}",
                extracted_value=parsed_mfg.formatted_iso
            ))
        else:
            sub_check_results.append(SubCheckResult(
                sub_check_id="MFG-DATE-FORMAT",
                name="Standard Month and Year Format",
                status=ComplianceStatus.FAILED,
                severity=Severity.CRITICAL,
                mandatory=True,
                details=f"Unable to parse manufacturing date '{raw_mfg}' into valid month and year.",
                extracted_value=raw_mfg,
                error_code="ERR_MFG_INVALID_DATE_FORMAT",
                remediation=check_def_format.remediation if check_def_format else None
            ))
            failure_reasons.append(f"Manufacturing date '{raw_mfg}' is not in a valid date/month-year format.")
            if check_def_format and check_def_format.remediation:
                remediation_steps.append(check_def_format.remediation)

        # 4. MFG-TEMPORAL-PLAUSIBILITY Check
        # Allows up to 90 days lead-time into future relative to reference evaluation date
        if parsed_mfg and parsed_mfg.year > 0:
            eval_date = date.today()
            # If evaluation context specifies a session timestamp (e.g. 2026-08-28), use that as reference
            if product_data.timestamp and len(product_data.timestamp) >= 8:
                try:
                    ts = product_data.timestamp
                    eval_date = date(int(ts[:4]), int(ts[4:6]), int(ts[6:8]))
                except ValueError:
                    pass

            max_future_allowed = eval_date + timedelta(days=90)
            mfg_as_date = parsed_mfg.as_date

            if mfg_as_date <= max_future_allowed:
                sub_check_results.append(SubCheckResult(
                    sub_check_id="MFG-TEMPORAL-PLAUSIBILITY",
                    name="Temporal Plausibility (Not Distant Future)",
                    status=ComplianceStatus.PASSED,
                    severity=Severity.CRITICAL,
                    mandatory=True,
                    details=f"Manufacturing date {parsed_mfg.formatted_iso} is within valid timeline.",
                    extracted_value=parsed_mfg.formatted_iso
                ))
            else:
                sub_check_results.append(SubCheckResult(
                    sub_check_id="MFG-TEMPORAL-PLAUSIBILITY",
                    name="Temporal Plausibility (Not Distant Future)",
                    status=ComplianceStatus.FAILED,
                    severity=Severity.CRITICAL,
                    mandatory=True,
                    details=f"Manufacturing date {parsed_mfg.formatted_iso} is excessively far in the future (>90 days from evaluation date).",
                    extracted_value=parsed_mfg.formatted_iso,
                    error_code="ERR_MFG_FUTURE_DATE"
                ))
                failure_reasons.append(f"Manufacturing date {parsed_mfg.formatted_iso} is impossible/future-dated.")

        # Determine overall parameter status
        critical_failures = [
            sc for sc in sub_check_results
            if sc.mandatory and sc.status == ComplianceStatus.FAILED
        ]
        overall_status = ComplianceStatus.PASSED if not critical_failures else ComplianceStatus.FAILED

        findings_summary = (
            f"Manufacturing date declaration ({parsed_mfg.formatted_iso if parsed_mfg else raw_mfg}) satisfies Rule 6(1)(d)."
            if overall_status == ComplianceStatus.PASSED
            else f"Manufacturing date declaration failed {len(critical_failures)} check(s)."
        )

        return ParameterEvaluationResult(
            parameter=self.rule.parameter,
            rule_id=self.rule.rule_id,
            rule_title=self.rule.rule_title,
            section_reference=self.rule.section_reference,
            status=overall_status,
            confidence_score=1.0,
            extracted_raw_value=raw_mfg,
            extracted_normalized_value=parsed_mfg.formatted_iso if parsed_mfg else None,
            findings=findings_summary,
            sub_checks=sub_check_results,
            failure_reasons=failure_reasons,
            remediation_steps=remediation_steps
        )
