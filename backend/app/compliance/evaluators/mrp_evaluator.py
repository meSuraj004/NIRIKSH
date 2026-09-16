"""
Deterministic MRP Evaluator for Legal Metrology (Packaged Commodities) Rules, 2011 (Rule 6(1)(e), Rule 2(m)).
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
from ..utils.price_parser import parse_mrp_declaration, ParsedPrice


class MRPEvaluator(BaseParameterEvaluator):
    """Evaluates Maximum Retail Price (MRP) against LMPC 2011 statutory rules."""

    def evaluate(self, product_data: ProductDataInput, context: Optional[Dict[str, Any]] = None) -> ParameterEvaluationResult:
        pricing = product_data.pricing_and_quantity or {}
        raw_mrp = pricing.get("mrp")
        num_mrp_direct = pricing.get("mrp_numerical_inr")
        raw_usp = pricing.get("unit_sale_price")
        ocr_lines = product_data.raw_ocr_lines or []

        # Parse MRP and fallback across raw OCR lines if needed
        parsed_price: Optional[ParsedPrice] = parse_mrp_declaration(raw_mrp, fallback_lines=ocr_lines)

        # Fallback if numerical MRP was directly passed
        if parsed_price and parsed_price.numeric_value is None and num_mrp_direct is not None:
            try:
                parsed_price.numeric_value = float(num_mrp_direct)
            except (ValueError, TypeError):
                pass

        sub_check_results: List[SubCheckResult] = []
        failure_reasons: List[str] = []
        remediation_steps: List[str] = []

        # 1. MRP-PRESENCE Check
        check_def_presence = next((sc for sc in self.rule.sub_checks if sc.sub_check_id == "MRP-PRESENCE"), None)
        has_presence = bool(raw_mrp or (parsed_price and parsed_price.numeric_value is not None))
        if has_presence:
            sub_check_results.append(SubCheckResult(
                sub_check_id="MRP-PRESENCE",
                name="MRP Declaration Presence",
                status=ComplianceStatus.PASSED,
                severity=Severity.CRITICAL,
                mandatory=True,
                details=f"MRP declaration found on package: '{raw_mrp or parsed_price.raw_text}'",
                extracted_value=raw_mrp or parsed_price.raw_text
            ))
        else:
            sub_check_results.append(SubCheckResult(
                sub_check_id="MRP-PRESENCE",
                name="MRP Declaration Presence",
                status=ComplianceStatus.FAILED,
                severity=Severity.CRITICAL,
                mandatory=True,
                details=check_def_presence.failure_reason if check_def_presence else "No MRP declaration found.",
                error_code="ERR_MRP_MISSING",
                remediation=check_def_presence.remediation if check_def_presence else None
            ))
            failure_reasons.append("No Maximum Retail Price (MRP) declaration was found on the package.")
            if check_def_presence and check_def_presence.remediation:
                remediation_steps.append(check_def_presence.remediation)

        # If completely missing, return early with FAILED
        if not has_presence or not parsed_price:
            return ParameterEvaluationResult(
                parameter=self.rule.parameter,
                rule_id=self.rule.rule_id,
                rule_title=self.rule.rule_title,
                section_reference=self.rule.section_reference,
                status=ComplianceStatus.FAILED,
                confidence_score=1.0,
                extracted_raw_value=None,
                extracted_normalized_value=None,
                findings="Mandatory MRP declaration is missing from the package label.",
                sub_checks=sub_check_results,
                failure_reasons=failure_reasons,
                remediation_steps=remediation_steps
            )

        # 2. MRP-PREFIX Check
        check_def_prefix = next((sc for sc in self.rule.sub_checks if sc.sub_check_id == "MRP-PREFIX"), None)
        if parsed_price.has_mrp_prefix:
            sub_check_results.append(SubCheckResult(
                sub_check_id="MRP-PREFIX",
                name="Statutory MRP Terminology/Prefix",
                status=ComplianceStatus.PASSED,
                severity=Severity.MAJOR,
                mandatory=True,
                details="Legally compliant prefix found ('MRP' / 'Maximum Retail Price').",
                extracted_value=parsed_price.raw_text
            ))
        else:
            sub_check_results.append(SubCheckResult(
                sub_check_id="MRP-PREFIX",
                name="Statutory MRP Terminology/Prefix",
                status=ComplianceStatus.FAILED,
                severity=Severity.MAJOR,
                mandatory=True,
                details="Declaration lacks the statutory prefix 'MRP' or 'Maximum Retail Price'.",
                extracted_value=parsed_price.raw_text,
                error_code="ERR_MRP_INVALID_PREFIX",
                remediation=check_def_prefix.remediation if check_def_prefix else None
            ))
            failure_reasons.append("Price is declared without mandatory 'MRP' or 'Maximum Retail Price' prefix.")
            if check_def_prefix and check_def_prefix.remediation:
                remediation_steps.append(check_def_prefix.remediation)

        # 3. MRP-TAX-INCLUSION Check
        check_def_tax = next((sc for sc in self.rule.sub_checks if sc.sub_check_id == "MRP-TAX-INCLUSION"), None)
        if parsed_price.has_tax_declaration:
            sub_check_results.append(SubCheckResult(
                sub_check_id="MRP-TAX-INCLUSION",
                name="Inclusive of All Taxes Declaration",
                status=ComplianceStatus.PASSED,
                severity=Severity.CRITICAL,
                mandatory=True,
                details="Compliant tax inclusion declaration found ('incl. of all taxes' / 'inclusive of all taxes').",
                extracted_value=parsed_price.raw_text
            ))
        else:
            sub_check_results.append(SubCheckResult(
                sub_check_id="MRP-TAX-INCLUSION",
                name="Inclusive of All Taxes Declaration",
                status=ComplianceStatus.FAILED,
                severity=Severity.CRITICAL,
                mandatory=True,
                details="Price declaration does not state '(incl. of all taxes)' or 'inclusive of all taxes' as required by Rule 6(1)(e).",
                extracted_value=parsed_price.raw_text,
                error_code="ERR_MRP_MISSING_TAX_DECLARATION",
                remediation=check_def_tax.remediation if check_def_tax else None
            ))
            failure_reasons.append("MRP declaration lacks the mandatory 'incl. of all taxes' clause.")
            if check_def_tax and check_def_tax.remediation:
                remediation_steps.append(check_def_tax.remediation)

        # 4. MRP-CURRENCY-INDICATOR Check
        check_def_curr = next((sc for sc in self.rule.sub_checks if sc.sub_check_id == "MRP-CURRENCY-INDICATOR"), None)
        if parsed_price.has_valid_currency:
            sub_check_results.append(SubCheckResult(
                sub_check_id="MRP-CURRENCY-INDICATOR",
                name="Valid Currency Symbol/Representation",
                status=ComplianceStatus.PASSED,
                severity=Severity.MAJOR,
                mandatory=True,
                details=f"Recognized Indian currency symbol found: '{parsed_price.currency}'",
                extracted_value=parsed_price.currency
            ))
        else:
            sub_check_results.append(SubCheckResult(
                sub_check_id="MRP-CURRENCY-INDICATOR",
                name="Valid Currency Symbol/Representation",
                status=ComplianceStatus.FAILED,
                severity=Severity.MAJOR,
                mandatory=True,
                details="Price lacks recognized Indian currency symbol (₹, Rs., INR).",
                extracted_value=parsed_price.raw_text,
                error_code="ERR_MRP_INVALID_CURRENCY",
                remediation=check_def_curr.remediation if check_def_curr else None
            ))
            failure_reasons.append("Missing Indian currency symbol (₹ / Rs.).")
            if check_def_curr and check_def_curr.remediation:
                remediation_steps.append(check_def_curr.remediation)

        # 5. MRP-NUMERIC-VALUE Check
        check_def_num = next((sc for sc in self.rule.sub_checks if sc.sub_check_id == "MRP-NUMERIC-VALUE"), None)
        if parsed_price.numeric_value is not None and parsed_price.numeric_value > 0:
            sub_check_results.append(SubCheckResult(
                sub_check_id="MRP-NUMERIC-VALUE",
                name="Positive Non-Zero Numerical Price",
                status=ComplianceStatus.PASSED,
                severity=Severity.CRITICAL,
                mandatory=True,
                details=f"Valid positive numerical price parsed: ₹{parsed_price.numeric_value:.2f}",
                extracted_value=parsed_price.numeric_value
            ))
        else:
            sub_check_results.append(SubCheckResult(
                sub_check_id="MRP-NUMERIC-VALUE",
                name="Positive Non-Zero Numerical Price",
                status=ComplianceStatus.FAILED,
                severity=Severity.CRITICAL,
                mandatory=True,
                details="Declared MRP numeric value is missing, zero, or unparsable.",
                extracted_value=parsed_price.numeric_value,
                error_code="ERR_MRP_INVALID_NUMERIC",
                remediation=check_def_num.remediation if check_def_num else None
            ))
            failure_reasons.append("Invalid or missing numeric price value.")
            if check_def_num and check_def_num.remediation:
                remediation_steps.append(check_def_num.remediation)

        # 6. MRP-ROUNDING Check (Non-mandatory / Warning)
        if parsed_price.numeric_value is not None:
            if parsed_price.is_rounded_properly:
                sub_check_results.append(SubCheckResult(
                    sub_check_id="MRP-ROUNDING",
                    name="Price Rounding Compliance",
                    status=ComplianceStatus.PASSED,
                    severity=Severity.WARNING,
                    mandatory=False,
                    details=f"Price ₹{parsed_price.numeric_value:.2f} satisfies 50-paise / integer rupee rounding rule.",
                    extracted_value=parsed_price.numeric_value
                ))
            else:
                sub_check_results.append(SubCheckResult(
                    sub_check_id="MRP-ROUNDING",
                    name="Price Rounding Compliance",
                    status=ComplianceStatus.CONDITIONAL_PASS,
                    severity=Severity.WARNING,
                    mandatory=False,
                    details=f"Price ₹{parsed_price.numeric_value:.2f} is not rounded to nearest 50 paise or integer rupee.",
                    extracted_value=parsed_price.numeric_value,
                    error_code="WARN_MRP_ROUNDING"
                ))

        # 7. MRP-UNIT-SALE-PRICE Check (Informational / Verification)
        usp_declared = bool(raw_usp or parsed_price.unit_sale_price_raw)
        if usp_declared:
            usp_val_str = raw_usp or parsed_price.unit_sale_price_raw
            sub_check_results.append(SubCheckResult(
                sub_check_id="MRP-UNIT-SALE-PRICE",
                name="Unit Sale Price (USP) Declaration",
                status=ComplianceStatus.PASSED,
                severity=Severity.MAJOR,
                mandatory=False,
                details=f"Unit Sale Price correctly declared: '{usp_val_str}'",
                extracted_value=usp_val_str
            ))

        # Determine overall parameter status
        critical_or_major_failures = [
            sc for sc in sub_check_results
            if sc.mandatory and sc.status == ComplianceStatus.FAILED
        ]
        overall_status = ComplianceStatus.PASSED if not critical_or_major_failures else ComplianceStatus.FAILED

        findings_summary = (
            f"MRP declaration ₹{parsed_price.numeric_value:.2f} is fully compliant with Rule 6(1)(e)."
            if overall_status == ComplianceStatus.PASSED
            else f"MRP declaration non-compliant: {len(critical_or_major_failures)} mandatory check(s) failed."
        )

        return ParameterEvaluationResult(
            parameter=self.rule.parameter,
            rule_id=self.rule.rule_id,
            rule_title=self.rule.rule_title,
            section_reference=self.rule.section_reference,
            status=overall_status,
            confidence_score=1.0,
            extracted_raw_value=raw_mrp or parsed_price.raw_text,
            extracted_normalized_value={
                "price_inr": parsed_price.numeric_value,
                "currency": parsed_price.currency,
                "has_tax_clause": parsed_price.has_tax_declaration,
                "has_mrp_prefix": parsed_price.has_mrp_prefix,
                "unit_sale_price": raw_usp or parsed_price.unit_sale_price_raw
            },
            findings=findings_summary,
            sub_checks=sub_check_results,
            failure_reasons=failure_reasons,
            remediation_steps=remediation_steps
        )
