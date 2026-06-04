from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import DATABASE_BACKEND, SessionLocal
from app.core.security import decode_token, hash_password, verify_password
from app.core.uploads import save_uploaded_image
from app.core.roles import (
    ROLE_TRAIN_VERIFIER,
    ROLE_UNIVERSITY_AGENT,
    has_role,
    normalize_role,
)

router = APIRouter(prefix="/users", tags=["users"])

PROFILE_UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads" / "profiles"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )
    return authorization.split(" ", 1)[1].strip()


def _is_account_active(value) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) == 1
    return str(value).lower() in ("1", "true", "t")


def _mfa_enabled_value(value) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) == 1
    return str(value).lower() in ("1", "true", "t")


class UserUpdateRequest(BaseModel):
    first_name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    last_name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=30)
    date_of_birth: Optional[str] = Field(default=None, max_length=32)


class UserPasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=4, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


def _current_user_id(authorization: str | None, db: Session) -> int:
    token = _extract_bearer_token(authorization)
    try:
        payload = decode_token(token)
        return int(payload.get("sub", "0"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


@router.get("/me")
def me(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    user_id = _current_user_id(authorization, db)

    row = db.execute(
        text(
            """
            SELECT user_id, first_name, last_name, email, phone, date_of_birth, role, is_active,
                   mfa_enabled, university_name, profile_photo_path
            FROM users
            WHERE user_id = :user_id
            """
        ),
        {"user_id": user_id},
    ).mappings().first()

    if not row or not _is_account_active(row.get("is_active")):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return {
        "user_id": row["user_id"],
        "first_name": row["first_name"],
        "last_name": row["last_name"],
        "email": row["email"],
        "phone": row.get("phone"),
        "date_of_birth": row.get("date_of_birth"),
        "university_name": row.get("university_name"),
        "has_profile_photo": bool(row.get("profile_photo_path")),
        "role": normalize_role(row["role"]),
        "mfa_enabled": _mfa_enabled_value(row.get("mfa_enabled")),
    }


@router.get("/{user_id}/profile-photo")
def get_user_profile_photo(
    user_id: int,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    viewer_id = _current_user_id(authorization, db)
    viewer = db.execute(
        text("SELECT user_id, role FROM users WHERE user_id = :user_id"),
        {"user_id": viewer_id},
    ).mappings().first()
    if not viewer:
        raise HTTPException(status_code=404, detail="User not found")

    row = db.execute(
        text("SELECT user_id, profile_photo_path FROM users WHERE user_id = :user_id"),
        {"user_id": user_id},
    ).mappings().first()
    if not row or not row.get("profile_photo_path"):
        raise HTTPException(status_code=404, detail="Profile photo not found")

    viewer_role = normalize_role(viewer["role"])
    can_access = (
        viewer_id == user_id
        or has_role(viewer_role, ROLE_UNIVERSITY_AGENT)
        or has_role(viewer_role, ROLE_TRAIN_VERIFIER)
    )
    if not can_access:
        raise HTTPException(status_code=403, detail="Access denied")

    file_path = Path(row["profile_photo_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Profile photo file not found")

    return FileResponse(path=file_path)


@router.put("/me")
def update_me(
    payload: UserUpdateRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(authorization, db)

    row = db.execute(
        text("SELECT user_id, is_active FROM users WHERE user_id = :user_id"),
        {"user_id": user_id},
    ).mappings().first()

    if not row or not _is_account_active(row.get("is_active")):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    updates: dict[str, Any] = {}
    if payload.first_name is not None:
        updates["first_name"] = payload.first_name
    if payload.last_name is not None:
        updates["last_name"] = payload.last_name
    if payload.phone is not None:
        updates["phone"] = payload.phone
    if payload.date_of_birth is not None:
        updates["date_of_birth"] = payload.date_of_birth

    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    params = {**updates, "user_id": user_id}

    db.execute(
        text(f"UPDATE users SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE user_id = :user_id"),
        params,
    )
    db.commit()

    return me(authorization=authorization, db=db)


@router.put("/me/password")
def change_password(
    payload: UserPasswordChangeRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(authorization, db)

    row = db.execute(
        text("SELECT password_hash FROM users WHERE user_id = :user_id"),
        {"user_id": user_id},
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not verify_password(payload.current_password, row["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")

    db.execute(
        text("UPDATE users SET password_hash = :h, updated_at = CURRENT_TIMESTAMP WHERE user_id = :user_id"),
        {"h": hash_password(payload.new_password), "user_id": user_id},
    )
    db.commit()

    return {"message": "Password updated"}


@router.put("/me/profile-photo")
def update_profile_photo(
    profile_photo: UploadFile = File(...),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(authorization, db)

    active_cred = db.execute(
        text("SELECT id FROM user_credentials WHERE user_id = :uid AND status = 'active' LIMIT 1"),
        {"uid": user_id},
    ).mappings().first()
    if active_cred:
        raise HTTPException(
            status_code=403,
            detail="Poza de profil nu mai poate fi modificată după ce identitatea a fost aprobată.",
        )

    photo_path = save_uploaded_image(profile_photo, PROFILE_UPLOAD_DIR, prefix="profile")
    if not photo_path:
        raise HTTPException(status_code=400, detail="Imaginea nu a putut fi salvată")

    db.execute(
        text("UPDATE users SET profile_photo_path = :path, updated_at = CURRENT_TIMESTAMP WHERE user_id = :user_id"),
        {"path": str(photo_path), "user_id": user_id},
    )
    db.commit()
    return {"message": "Poza de profil actualizată"}


@router.get("/me/export")
def export_me(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    user_id = _current_user_id(authorization, db)

    user_row = db.execute(
        text(
            """
            SELECT user_id, first_name, last_name, email, phone, date_of_birth, role, is_active,
                   created_at, updated_at, mfa_enabled
            FROM users
            WHERE user_id = :user_id
            """
        ),
        {"user_id": user_id},
    ).mappings().first()

    if not user_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    export: dict[str, Any] = {
        "user": {
            "user_id": user_row["user_id"],
            "first_name": user_row["first_name"],
            "last_name": user_row["last_name"],
            "email": user_row["email"],
            "phone": user_row.get("phone"),
            "date_of_birth": user_row.get("date_of_birth"),
            "role": normalize_role(user_row["role"]),
            "is_active": bool(user_row["is_active"]) if user_row["is_active"] is not None else True,
            "mfa_enabled": _mfa_enabled_value(user_row.get("mfa_enabled")),
            "created_at": str(user_row.get("created_at")) if user_row.get("created_at") is not None else None,
            "updated_at": str(user_row.get("updated_at")) if user_row.get("updated_at") is not None else None,
        },
        "source_documents": [],
        "notifications": [],
        "user_credentials": [],
    }

    for key, sql in (
        (
            "source_documents",
            "SELECT id, document_type, document_number_masked, status, uploaded_at FROM source_documents WHERE user_id = :uid",
        ),
        (
            "notifications",
            "SELECT id, category, title, message, is_read, created_at FROM notifications WHERE user_id = :uid",
        ),
        (
            "user_credentials",
            "SELECT id, credential_type, claim_value, status, issued_at, valid_until FROM user_credentials WHERE user_id = :uid",
        ),
    ):
        try:
            rows = db.execute(text(sql), {"uid": user_id}).mappings().all()
            export[key] = [dict(r) for r in rows]
        except (SQLAlchemyError, Exception):
            export[key] = []

    return export


@router.delete("/me")
def delete_me(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    user_id = _current_user_id(authorization, db)

    inactive = False if DATABASE_BACKEND == "postgresql" else 0
    db.execute(
        text("UPDATE users SET is_active = :inactive, updated_at = CURRENT_TIMESTAMP WHERE user_id = :user_id"),
        {"inactive": inactive, "user_id": user_id},
    )
    db.commit()

    return {"message": "Account deactivated", "user_id": user_id}
