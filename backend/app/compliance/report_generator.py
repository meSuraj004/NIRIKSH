"""
=============================================================================
Statutory Legal Compliance Report Formatter & Generator
=============================================================================
Module: rule_engine.report_generator
Purpose:
  Generates clean, structured, and legally authoritative Markdown reports from
  LMPC 2011 Rule Engine ComplianceReport instances or dictionaries.
=============================================================================
"""

from typing import Dict, Any, Union
from .models import ComplianceReport, ComplianceStatus, Severity


def _format_status_emoji(status: Union[ComplianceStatus, str]) -> str:
    s = status.value if isinstance(status, ComplianceStatus) else str(status)
    if s == "PASSED":
        return "✅ PASSED"
    elif s == "FAILED":
        return "❌ FAILED"
    elif s == "CONDITIONAL_PASS":
        return "⚠️ CONDITIONAL PASS"
    elif s == "REVIEW":
        return "🔍 REVIEW"
    elif s == "NOT_APPLICABLE":
        return "⚪ NOT APPLICABLE"
    return f"ℹ️ {s}"


def _format_severity_tag(severity: Union[Severity, str]) -> str:
    sev = severity.value if isinstance(severity, Severity) else str(severity)
    if sev == "CRITICAL":
        return "`🔴 CRITICAL`"
    elif sev == "MAJOR":
        return "`🟠 MAJOR`"
    elif sev == "WARNING":
        return "`🟡 WARNING`"
    return "`🔵 INFO`"


def generate_legal_markdown_report(report_data: Union[ComplianceReport, Dict[str, Any]]) -> str:
    """
    Constructs a comprehensive statutory legal compliance markdown document
    based on the evaluated rules from Legal Metrology (Packaged Commodities) Rules, 2011.

    Args:
        report_data: ComplianceReport pydantic model or serialized dictionary.

    Returns:
        str: Formatted Markdown legal report.
    """
    if isinstance(report_data, ComplianceReport):
        data = report_data.model_dump()
    elif isinstance(report_data, dict):
        data = report_data
    else:
        raise ValueError(f"Expected ComplianceReport or dict, got {type(report_data)}")

    session_id = data.get("session_id", "N/A")
    eval_time = data.get("evaluation_timestamp", "N/A")
    rulebook_ver = data.get("rulebook_version", "2011.amended.2023")
    summary = data.get("summary", {})
    commodity = data.get("commodity_profile", {})
    param_results = data.get("parameter_results", {})
    audit_trail = data.get("audit_trail", [])

    overall_verdict = summary.get("overall_verdict", "UNKNOWN")
    verdict_badge = _format_status_emoji(overall_verdict)

    md = []
    md.append("# ⚖️ STATUTORY COMPLIANCE & LEGAL METROLOGY REPORT")
    md.append(f"**Governing Act:** *Legal Metrology (Packaged Commodities) Rules, 2011 (as amended)*  ")
    md.append(f"**Rulebook Version:** `{rulebook_ver}` | **Evaluation Timestamp:** `{eval_time}`  ")
    md.append(f"**Session Identifier:** `{session_id}`\n")
    md.append("---")

    # 1. Executive Summary
    md.append("## 📊 1. Executive Compliance Summary\n")
    md.append(f"> ### **OVERALL STATUTORY VERDICT: {verdict_badge}**\n")

    md.append("| Metric | Value | Statutory Significance |")
    md.append("| :--- | :--- | :--- |")
    md.append(f"| **Total Parameters Evaluated** | `{summary.get('total_parameters_evaluated', 0)}` | Key mandatory declarations tested |")
    md.append(f"| **Parameters Passed** | `{summary.get('passed_parameters', 0)}` | Compliant with statutory standards |")
    md.append(f"| **Parameters Failed** | `{summary.get('failed_parameters', 0)}` | Violations requiring immediate remediation |")
    md.append(f"| **Parameters Not Applicable** | `{summary.get('not_applicable_parameters', 0)}` | Exempt based on commodity category |")
    md.append(f"| **Critical Violations** | `{summary.get('critical_violations_count', 0)}` | Severe breaches (Missing MRP, Mfg date, etc.) |")
    md.append(f"| **Major Violations** | `{summary.get('major_violations_count', 0)}` | Formatting / missing mandatory clauses |")
    md.append(f"| **Advisory Warnings** | `{summary.get('warnings_count', 0)}` | Technical guidelines / non-blocking |")
    md.append("")

    # 2. Commodity Profile
    md.append("## 🏷️ 2. Commodity Classification & Legal Profile\n")
    cat = commodity.get("detected_category", "General Packaged Commodity")
    is_consumable = commodity.get("is_consumable", False)
    conf = commodity.get("confidence", 1.0)
    rationale = commodity.get("classification_rationale", "Standard commodity classification.")

    md.append(f"- **Detected Category:** **{cat}** (Confidence: `{conf * 100:.0f}%`)")
    md.append(f"- **Consumable / Perishable Good:** **{'Yes (Subject to Expiry / Best Before rules)' if is_consumable else 'No (Exempt from Expiry rules)'}**")
    md.append(f"- **FSSAI License Detected:** {'Yes' if commodity.get('fssai_present') else 'No / Not Required for Non-Food'}")
    md.append(f"- **Classification Legal Rationale:** {rationale}\n")
    md.append("---")

    # 3. Parameter Breakdown
    md.append("## 📋 3. Detailed Parameter Compliance Breakdown\n")

    for param_key, param_data in param_results.items():
        title = param_data.get("rule_title", param_key.upper())
        sec = param_data.get("section_reference", "LMPC 2011")
        status = param_data.get("status", "UNKNOWN")
        raw_val = param_data.get("extracted_raw_value")
        norm_val = param_data.get("extracted_normalized_value")
        findings = param_data.get("findings", "")
        sub_checks = param_data.get("sub_checks", [])
        failures = param_data.get("failure_reasons", [])
        remediation = param_data.get("remediation_steps", [])

        md.append(f"### ▶ {title}")
        md.append(f"**Statutory Reference:** `{sec}`  ")
        md.append(f"**Compliance Status:** {_format_status_emoji(status)}  ")
        md.append(f"**Extracted Raw Value:** `{raw_val if raw_val is not None else 'NOT FOUND'}`  ")
        if norm_val is not None:
            md.append(f"**Parsed Normalized Value:** `{norm_val}`  ")
        md.append(f"**Evaluation Findings:** {findings}\n")

        # Sub-checks table
        if sub_checks:
            md.append("#### Statutory Sub-Checks:")
            md.append("| Sub-Check | Severity | Mandatory | Status | Legal Observation |")
            md.append("| :--- | :--- | :---: | :---: | :--- |")
            for sc in sub_checks:
                sc_name = sc.get("name", "Check")
                sc_sev = _format_severity_tag(sc.get("severity", "MAJOR"))
                sc_mand = "Yes" if sc.get("mandatory") else "No"
                sc_stat = _format_status_emoji(sc.get("status", "PASSED"))
                sc_det = sc.get("details", "")
                md.append(f"| {sc_name} | {sc_sev} | {sc_mand} | {sc_stat} | {sc_det} |")
            md.append("")

        # Failure Callouts
        if failures:
            md.append("> ❌ **Statutory Violations Identified:**")
            for f in failures:
                md.append(f"> - {f}")
            md.append("")

        # Remediation Steps
        if remediation:
            md.append("> 🛠️ **Remediation & Rectification Guidance:**")
            for r in remediation:
                md.append(f"> - {r}")
            md.append("")

        md.append("---\n")

    # 4. Legal Audit Trail
    md.append("## 📜 4. Statutory Audit Trail\n")
    for log_item in audit_trail:
        md.append(f"- `{log_item}`")
    md.append("")

    return "\n".join(md)
