from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import require_any_role
from app.database import get_db
from app.models import Inspection, Report, User

router = APIRouter(prefix="/api/reports", tags=["reports"])

MEDIA_TYPES = {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


@router.post("/generate/{inspection_id}/{fmt}")
def generate_report(
    inspection_id: int,
    fmt: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_role),
):
    if fmt not in MEDIA_TYPES:
        raise HTTPException(status_code=400, detail="Format must be 'pdf' or 'docx'")

    inspection = db.get(Inspection, inspection_id)
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    if inspection.status.value != "COMPLETED":
        raise HTTPException(status_code=409, detail="Report requires a completed inspection")

    from app.services.report_service import generate_report as build

    path = build(db, inspection, fmt)
    report = Report(inspection_id=inspection.id, format=fmt, file_path=str(path))
    db.add(report)
    db.commit()
    db.refresh(report)
    return {"id": report.id, "inspection_id": inspection.id, "format": fmt, "download_url": f"/api/reports/{report.id}/download"}


@router.get("/{report_id}")
def get_report_meta(report_id: int, db: Session = Depends(get_db), _: User = Depends(require_any_role)):
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.format in MEDIA_TYPES:
        return {"id": report.id, "inspection_id": report.inspection_id, "format": report.format,
                "download_url": f"/api/reports/{report_id}/download"}
    if report.file_path and Path(report.file_path).exists():
        return FileResponse(report.file_path, media_type="text/markdown")
    if report.content:
        return {"id": report.id, "inspection_id": report.inspection_id, "format": report.format, "content": report.content}
    raise HTTPException(status_code=404, detail="Report content not available")


@router.get("/{report_id}/download")
def download_report(report_id: int, db: Session = Depends(get_db), _: User = Depends(require_any_role)):
    report = db.get(Report, report_id)
    if report is None or report.format not in MEDIA_TYPES:
        raise HTTPException(status_code=404, detail="Report not found")
    path = Path(report.file_path or "")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report file missing from storage")
    return FileResponse(path, media_type=MEDIA_TYPES[report.format], filename=path.name)
