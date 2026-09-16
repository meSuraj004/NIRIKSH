from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import require_any_role
from app.database import get_db
from app.models import Report

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db), _: object = Depends(require_any_role)):
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")

    if report.file_path and Path(report.file_path).exists():
        return FileResponse(report.file_path, media_type="text/markdown")
    if report.content:
        return {"id": report.id, "inspection_id": report.inspection_id, "format": report.format, "content": report.content}
    raise HTTPException(status_code=404, detail="Report content not available")
