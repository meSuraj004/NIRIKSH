"""
Data models for LMPC 2011 Rule Engine.
Defines schemas for rules, inputs, subchecks, parameter results, and compliance reports.
"""

from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ComplianceStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    REVIEW = "REVIEW"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CONDITIONAL_PASS = "CONDITIONAL_PASS"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    WARNING = "WARNING"
    INFO = "INFO"


class SubCheckDefinition(BaseModel):
    sub_check_id: str
    name: str
    description: str
    mandatory: bool = True
    severity: Severity = Severity.MAJOR
    error_code: str
    failure_reason: str
    remediation: Optional[str] = None


class RuleDefinition(BaseModel):
    rule_id: str
    rule_title: str
    legal_act: str = "Legal Metrology (Packaged Commodities) Rules, 2011"
    section_reference: str
    parameter: str  # "mrp" | "manufacture_date" | "expiry_date"
    description: str
    applicability: str = "ALL_PACKAGED_COMMODITIES"
    mandatory: bool = True
    exemptions: List[str] = Field(default_factory=list)
    sub_checks: List[SubCheckDefinition] = Field(default_factory=list)


class RuleBook(BaseModel):
    rulebook_id: str
    title: str
    version: str
    jurisdiction: str = "India"
    governing_body: str
    governing_act: str
    rules: List[RuleDefinition] = Field(default_factory=list)


class SubCheckResult(BaseModel):
    sub_check_id: str
    name: str
    status: ComplianceStatus
    severity: Severity
    mandatory: bool
    details: str
    extracted_value: Optional[Any] = None
    error_code: Optional[str] = None
    remediation: Optional[str] = None


class ParameterEvaluationResult(BaseModel):
    parameter: str  # "mrp" | "manufacture_date" | "expiry_date"
    rule_id: str
    rule_title: str
    section_reference: str
    status: ComplianceStatus
    confidence_score: float = 1.0
    extracted_raw_value: Optional[str] = None
    extracted_normalized_value: Optional[Any] = None
    findings: str
    sub_checks: List[SubCheckResult] = Field(default_factory=list)
    failure_reasons: List[str] = Field(default_factory=list)
    remediation_steps: List[str] = Field(default_factory=list)


class CommodityMetadata(BaseModel):
    brand_name: Optional[str] = None
    product_name: Optional[str] = None
    category: Optional[str] = None
    is_consumable: Optional[bool] = None
    net_quantity: Optional[str] = None
    fssai_present: Optional[bool] = None


class ProductDataInput(BaseModel):
    session_id: Optional[str] = None
    timestamp: Optional[str] = None
    product_identity: Dict[str, Any] = Field(default_factory=dict)
    dates_and_batch: Dict[str, Any] = Field(default_factory=dict)
    pricing_and_quantity: Dict[str, Any] = Field(default_factory=dict)
    ingredients_and_allergens: Dict[str, Any] = Field(default_factory=dict)
    nutritional_information: Dict[str, Any] = Field(default_factory=dict)
    regulatory_and_certifications: Dict[str, Any] = Field(default_factory=dict)
    raw_ocr_lines: List[str] = Field(default_factory=list)
    full_text: Optional[str] = None


class ComplianceSummary(BaseModel):
    total_parameters_evaluated: int
    passed_parameters: int
    failed_parameters: int
    review_parameters: int = 0
    not_applicable_parameters: int
    overall_verdict: ComplianceStatus
    critical_violations_count: int
    major_violations_count: int
    warnings_count: int


class ComplianceReport(BaseModel):
    session_id: Optional[str] = None
    evaluation_timestamp: str
    rulebook_version: str
    commodity_profile: Dict[str, Any] = Field(default_factory=dict)
    parameter_results: Dict[str, ParameterEvaluationResult] = Field(default_factory=dict)
    summary: ComplianceSummary
    audit_trail: List[str] = Field(default_factory=list)
