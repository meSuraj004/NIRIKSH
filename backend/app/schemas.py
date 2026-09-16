from pydantic import BaseModel, EmailStr, Field

from app.models import CheckStatus, DeclarationStatus, InspectionStatus, UserRole


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8)


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: UserRole

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class InspectionCreate(BaseModel):
    product_id: int | None = None
    notes: str | None = None


class InspectionOut(BaseModel):
    id: int
    status: InspectionStatus
    notes: str | None
    product_id: int | None
    inspector_id: int | None
    error_message: str | None

    model_config = {"from_attributes": True}


class ProductImageOut(BaseModel):
    id: int
    file_path: str
    original_filename: str | None
    content_type: str | None
    size_bytes: int | None
    source_type: str

    model_config = {"from_attributes": True}


class InspectionDetail(InspectionOut):
    images: list[ProductImageOut] = []


class ProductOut(BaseModel):
    id: int
    name: str | None
    brand_name: str | None
    category: str | None
    net_quantity: str | None
    mrp: str | None
    manufacturer: str | None

    model_config = {"from_attributes": True}


class RuleOut(BaseModel):
    id: int
    rule_id: str
    title: str
    section_reference: str | None
    parameter: str | None
    description: str | None
    mandatory: bool
    rulebook_version: str | None

    model_config = {"from_attributes": True}


class DeclarationOut(BaseModel):
    field_name: str
    value: str | None
    status: DeclarationStatus
    confidence: float | None
    bbox: dict | None
    source_image_id: int | None
    extraction_method: str | None

    model_config = {"from_attributes": True}


class ComplianceCheckOut(BaseModel):
    parameter: str | None
    status: CheckStatus
    extracted_value: str | None
    findings: str | None
    details: dict | None

    model_config = {"from_attributes": True}


class ViolationOut(BaseModel):
    error_code: str | None
    severity: str | None
    description: str | None
    remediation: str | None

    model_config = {"from_attributes": True}


class OCRResultOut(BaseModel):
    image_id: int
    engine: str | None
    model: str | None
    raw_text: str | None
    line_count: int | None
    latency_sec: float | None

    model_config = {"from_attributes": True}


class InspectionResults(BaseModel):
    inspection_id: int
    status: InspectionStatus
    declarations: list[DeclarationOut]
    compliance_checks: list[ComplianceCheckOut]
    violations: list[ViolationOut]
    ocr_results: list[OCRResultOut]


class ReportOut(BaseModel):
    id: int
    inspection_id: int
    format: str
    file_path: str | None
    created_at: str

    model_config = {"from_attributes": True}
