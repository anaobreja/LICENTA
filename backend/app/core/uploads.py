"""Shared helpers for uploaded images (documents, profile photos)."""

from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_PHOTO_SIZE_BYTES = 5 * 1024 * 1024


def save_uploaded_image(photo: UploadFile, upload_dir: Path, prefix: str = "img") -> str:
    if photo.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Doar imagini JPG, PNG sau WEBP sunt acceptate",
        )

    ext = Path(photo.filename or "photo").suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        ext = ".jpg"

    payload = photo.file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Fisierul incarcat este gol")
    if len(payload) > MAX_PHOTO_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Fisierul depaseste 5MB")

    upload_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{prefix}_{uuid4().hex}{ext}"
    file_path = upload_dir / file_name
    file_path.write_bytes(payload)
    return str(file_path)
