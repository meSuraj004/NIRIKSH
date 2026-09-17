from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pathlib import Path
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_any_role, require_officer
from app.database import get_db
from app.models import Inspection, InspectionStatus, Product, ProductImage, User
from app.schemas import (
    InspectionCreate,
    InspectionDetail,
    InspectionOut,
    InspectionResults,
    ProductImageOut,
)
from app.services.file_storage import save_uploaded_image
from app.services.inspection_service import run_inspection_pipeline

router = APIRouter(prefix="/api/inspections", tags=["inspections"])


def _get_owned_inspection(inspection_id: int, db: Session) -> Inspection:
    inspection = db.get(Inspection, inspection_id)
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return inspection


@router.post("", response_model=InspectionOut, status_code=201)
def create_inspection(
    payload: InspectionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_officer),
):
    if payload.product_id is not None and db.get(Product, payload.product_id) is None:
        raise HTTPException(status_code=404, detail="Product not found")

    inspection = Inspection(
        product_id=payload.product_id,
        notes=payload.notes,
        inspector_id=user.id,
        status=InspectionStatus.DRAFT,
    )
    db.add(inspection)
    db.commit()
    db.refresh(inspection)
    return inspection


@router.get("", response_model=list[InspectionOut])
def list_inspections(
    db: Session = Depends(get_db),
    user: User = Depends(require_any_role),
):
    return db.query(Inspection).order_by(Inspection.created_at.desc()).limit(200).all()


@router.get("/{inspection_id}", response_model=InspectionDetail)
def get_inspection(
    inspection_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_any_role),
):
    inspection = _get_owned_inspection(inspection_id, db)
    return inspection


@router.post("/{inspection_id}/images", response_model=list[ProductImageOut], status_code=201)
async def upload_images(
    inspection_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_officer),
):
    inspection = _get_owned_inspection(inspection_id, db)
    if inspection.status == InspectionStatus.PROCESSING:
        raise HTTPException(status_code=409, detail="Inspection is currently processing")

    saved = []
    for file in files:
        path = await save_uploaded_image(inspection_id, file)
        image = ProductImage(
            inspection_id=inspection.id,
            file_path=str(path),
            original_filename=file.filename,
            content_type=file.content_type,
            size_bytes=path.stat().st_size,
            source_type="upload",
        )
        db.add(image)
        saved.append(image)
    db.commit()
    for image in saved:
        db.refresh(image)
    return saved


@router.get("/{inspection_id}/images/{image_id}/file")
def get_image_file(
    inspection_id: int,
    image_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_role),
):
    image = db.get(ProductImage, image_id)
    if image is None or image.inspection_id != inspection_id:
        raise HTTPException(status_code=404, detail="Image not found")
    path = Path(image.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image file missing from storage")
    media_type = image.content_type or "application/octet-stream"
    return FileResponse(path, media_type=media_type)


@router.post("/{inspection_id}/process", response_model=InspectionOut)
def process_inspection(
    inspection_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_officer),
):
    inspection = _get_owned_inspection(inspection_id, db)
    if inspection.status == InspectionStatus.PROCESSING:
        raise HTTPException(status_code=409, detail="Inspection is already processing")
    if not inspection.images:
        raise HTTPException(status_code=400, detail="Upload images before processing")

    inspection.status = InspectionStatus.PROCESSING
    inspection.error_message = None
    db.commit()
    background_tasks.add_task(run_inspection_pipeline, inspection.id)
    return inspection


@router.get("/{inspection_id}/results", response_model=InspectionResults)
def get_results(
    inspection_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_any_role),
):
    inspection = _get_owned_inspection(inspection_id, db)
    if inspection.status != InspectionStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"Results not available: inspection status is {inspection.status.value}",
        )
    return InspectionResults(
        inspection_id=inspection.id,
        status=inspection.status,
        declarations=inspection.declarations,
        compliance_checks=inspection.compliance_checks,
        violations=inspection.violations,
        ocr_results=[r for img in inspection.images for r in img.ocr_results],
    )
