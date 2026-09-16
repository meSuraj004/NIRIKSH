import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    OFFICER = "OFFICER"
    REVIEWER = "REVIEWER"


class InspectionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DeclarationStatus(str, enum.Enum):
    DETECTED = "DETECTED"
    NOT_DETECTED = "NOT_DETECTED"
    UNCERTAIN = "UNCERTAIN"


class CheckStatus(str, enum.Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    REVIEW = "REVIEW"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.OFFICER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    inspections: Mapped[list["Inspection"]] = relationship(back_populates="inspector")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255), index=True)
    brand_name: Mapped[str | None] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(255))
    net_quantity: Mapped[str | None] = mapped_column(String(100))
    mrp: Mapped[str | None] = mapped_column(String(100))
    manufacturer: Mapped[str | None] = mapped_column(String(255))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    inspections: Mapped[list["Inspection"]] = relationship(back_populates="product")


class Inspection(Base):
    __tablename__ = "inspections"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[InspectionStatus] = mapped_column(Enum(InspectionStatus), default=InspectionStatus.DRAFT)
    notes: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)

    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    inspector_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    product: Mapped[Product | None] = relationship(back_populates="inspections")
    inspector: Mapped[User | None] = relationship(back_populates="inspections")
    images: Mapped[list["ProductImage"]] = relationship(back_populates="inspection", cascade="all, delete-orphan")
    declarations: Mapped[list["Declaration"]] = relationship(back_populates="inspection", cascade="all, delete-orphan")
    compliance_checks: Mapped[list["ComplianceCheck"]] = relationship(back_populates="inspection", cascade="all, delete-orphan")
    violations: Mapped[list["Violation"]] = relationship(back_populates="inspection", cascade="all, delete-orphan")
    reports: Mapped[list["Report"]] = relationship(back_populates="inspection", cascade="all, delete-orphan")


class ProductImage(Base):
    __tablename__ = "product_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspections.id"), index=True)
    file_path: Mapped[str] = mapped_column(String(500))
    original_filename: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    source_type: Mapped[str] = mapped_column(String(50), default="upload")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    inspection: Mapped[Inspection] = relationship(back_populates="images")
    ocr_results: Mapped[list["OCRResult"]] = relationship(back_populates="image", cascade="all, delete-orphan")


class OCRResult(Base):
    __tablename__ = "ocr_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("product_images.id"), index=True)
    engine: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(100))
    raw_text: Mapped[str | None] = mapped_column(Text)
    line_count: Mapped[int | None] = mapped_column(Integer)
    latency_sec: Mapped[float | None] = mapped_column(Float)
    token_usage: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    image: Mapped[ProductImage] = relationship(back_populates="ocr_results")


class Declaration(Base):
    __tablename__ = "declarations"

    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspections.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(100), index=True)
    value: Mapped[str | None] = mapped_column(Text)
    status: Mapped[DeclarationStatus] = mapped_column(Enum(DeclarationStatus), default=DeclarationStatus.NOT_DETECTED)
    confidence: Mapped[float | None] = mapped_column(Float)
    bbox: Mapped[dict | None] = mapped_column(JSON)
    source_image_id: Mapped[int | None] = mapped_column(ForeignKey("product_images.id"))
    extraction_method: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    inspection: Mapped[Inspection] = relationship(back_populates="declarations")


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    section_reference: Mapped[str | None] = mapped_column(String(100))
    parameter: Mapped[str | None] = mapped_column(String(100), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    mandatory: Mapped[bool] = mapped_column(Boolean, default=True)
    rulebook_version: Mapped[str | None] = mapped_column(String(50))
    definition: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    compliance_checks: Mapped[list["ComplianceCheck"]] = relationship(back_populates="rule")


class ComplianceCheck(Base):
    __tablename__ = "compliance_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspections.id"), index=True)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("rules.id"))
    parameter: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[CheckStatus] = mapped_column(Enum(CheckStatus))
    extracted_value: Mapped[str | None] = mapped_column(Text)
    findings: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    inspection: Mapped[Inspection] = relationship(back_populates="compliance_checks")
    rule: Mapped[Rule | None] = relationship(back_populates="compliance_checks")
    violations: Mapped[list["Violation"]] = relationship(back_populates="compliance_check")


class Violation(Base):
    __tablename__ = "violations"

    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspections.id"), index=True)
    compliance_check_id: Mapped[int | None] = mapped_column(ForeignKey("compliance_checks.id"))
    error_code: Mapped[str | None] = mapped_column(String(100))
    severity: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    remediation: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    inspection: Mapped[Inspection] = relationship(back_populates="violations")
    compliance_check: Mapped[ComplianceCheck | None] = relationship(back_populates="violations")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspections.id"), index=True)
    image_id: Mapped[int | None] = mapped_column(ForeignKey("product_images.id"))
    ocr_result_id: Mapped[int | None] = mapped_column(ForeignKey("ocr_results.id"))
    kind: Mapped[str] = mapped_column(String(50), default="ocr_transcript")
    file_path: Mapped[str | None] = mapped_column(String(500))
    meta: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspections.id"), index=True)
    format: Mapped[str] = mapped_column(String(20), default="json")
    file_path: Mapped[str | None] = mapped_column(String(500))
    content: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    inspection: Mapped[Inspection] = relationship(back_populates="reports")


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
