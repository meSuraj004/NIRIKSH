import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import settings

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_IMAGE_BYTES = 20 * 1024 * 1024


def inspection_dir(inspection_id: int) -> Path:
    path = settings.storage_dir / "inspections" / str(inspection_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


async def save_uploaded_image(inspection_id: int, file: UploadFile) -> Path:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported image type '{ext or 'unknown'}'")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(contents) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds 20 MB limit")

    filename = f"{uuid.uuid4().hex}{ext}"
    dest = inspection_dir(inspection_id) / filename
    dest.write_bytes(contents)
    return dest
