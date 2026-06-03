from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import DATABASE_BACKEND, SessionLocal
from app.core.security import (
    create_access_token,
    decode_token,
    generate_totp_qr,
    generate_totp_secret,
    hash_password,
    verify_password,
    verify_totp_code,
)
from app.core.roles import normalize_role

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=4, max_length=128)
    totp_code: str | None = Field(default=None, max_length=16)


class RegisterRequest(BaseModel):
    first_name: str = Field(min_length=2, max_length=100)
    last_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class MFAEnableRequest(BaseModel):
    code: str = Field(min_length=6, max_length=16)


class MFADisableRequest(BaseModel):
    password: str = Field(min_length=4, max_length=128)


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


def _is_demo_login_allowed(password_hash: str, provided_password: str) -> bool:
    return "demo_hash" in (password_hash or "") and provided_password == "demo"


def _mfa_is_enabled(value) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) == 1
    return str(value).lower() in ("1", "true", "t")


def _account_active(value) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) != 0
    return str(value).lower() not in ("0", "false", "f", "no", "n")


@router.post("/register")
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.execute(
        text("SELECT user_id FROM users WHERE email = :email"),
        {"email": payload.email.lower()},
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    password_hash = hash_password(payload.password)

    created = db.execute(
        text(
            """
            INSERT INTO users (first_name, last_name, email, password_hash, role, is_active)
            VALUES (:first_name, :last_name, :email, :password_hash, 'passenger', true)
            RETURNING user_id, first_name, last_name, email, role
            """
        ),
        {
            "first_name": payload.first_name,
            "last_name": payload.last_name,
            "email": payload.email.lower(),
            "password_hash": password_hash,
        },
    ).mappings().first()

    db.commit()

    return {
        "message": "Account created successfully",
        "user": {**dict(created), "role": normalize_role(created["role"])},
    }


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    row = db.execute(
        text(
            """
            SELECT user_id, first_name, last_name, email, password_hash, role, is_active,
                   mfa_secret, mfa_enabled
            FROM users
            WHERE email = :email
            """
        ),
        {"email": payload.email.lower()},
    ).mappings().first()

    if not row or not _account_active(row.get("is_active")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    password_ok = verify_password(payload.password, row["password_hash"]) or _is_demo_login_allowed(
        row["password_hash"], payload.password
    )

    if not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if _mfa_is_enabled(row.get("mfa_enabled")):
        secret = row.get("mfa_secret") or ""
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="MFA is enabled but secret is missing; contact support",
            )
        code = (payload.totp_code or "").strip().replace(" ", "")
        if not code:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="MFA_REQUIRED",
            )
        if not verify_totp_code(secret, code, window=settings.TOTP_WINDOW):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid MFA code",
            )

    access_token = create_access_token(
        data={"sub": str(row["user_id"]), "role": normalize_role(row["role"])},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "user_id": row["user_id"],
            "first_name": row["first_name"],
            "last_name": row["last_name"],
            "email": row["email"],
            "role": normalize_role(row["role"]),
        },
    }


@router.post("/mfa/setup")
def mfa_setup(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    token = _extract_bearer_token(authorization)

    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub", "0"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    row = db.execute(
        text(
            """
            SELECT user_id, email, mfa_enabled
            FROM users
            WHERE user_id = :user_id
            """
        ),
        {"user_id": user_id},
    ).mappings().first()

    if not row or not row.get("email"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if _mfa_is_enabled(row.get("mfa_enabled")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is already enabled. Disable it first before generating a new secret.",
        )

    secret = generate_totp_secret()
    mfa_off = False if DATABASE_BACKEND == "postgresql" else 0
    db.execute(
        text("UPDATE users SET mfa_secret = :secret, mfa_enabled = :mfa_off WHERE user_id = :user_id"),
        {"secret": secret, "mfa_off": mfa_off, "user_id": user_id},
    )
    db.commit()

    qr_data_url = generate_totp_qr(secret, row["email"])
    return {
        "message": "Scan the QR code with your authenticator app, then call /auth/mfa/verify with a code.",
        "qr_data_url": qr_data_url,
        "secret_base32": secret,
    }


@router.post("/mfa/verify")
def mfa_verify(
    payload: MFAEnableRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    token = _extract_bearer_token(authorization)

    try:
        payload_jwt = decode_token(token)
        user_id = int(payload_jwt.get("sub", "0"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    row = db.execute(
        text("SELECT mfa_secret, mfa_enabled FROM users WHERE user_id = :user_id"),
        {"user_id": user_id},
    ).mappings().first()

    if not row or not row.get("mfa_secret"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Run /auth/mfa/setup first",
        )

    if _mfa_is_enabled(row.get("mfa_enabled")):
        return {"message": "MFA is already enabled", "mfa_enabled": True}

    if not verify_totp_code(row["mfa_secret"], payload.code.strip().replace(" ", ""), window=settings.TOTP_WINDOW):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid MFA code")

    mfa_on = True if DATABASE_BACKEND == "postgresql" else 1
    db.execute(
        text("UPDATE users SET mfa_enabled = :mfa_on WHERE user_id = :user_id"),
        {"mfa_on": mfa_on, "user_id": user_id},
    )
    db.commit()

    return {"message": "MFA enabled successfully", "mfa_enabled": True}


@router.post("/mfa/disable")
def mfa_disable(
    payload: MFADisableRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    token = _extract_bearer_token(authorization)

    try:
        payload_jwt = decode_token(token)
        user_id = int(payload_jwt.get("sub", "0"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    row = db.execute(
        text("SELECT password_hash, mfa_enabled FROM users WHERE user_id = :user_id"),
        {"user_id": user_id},
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not verify_password(payload.password, row["password_hash"]) and not _is_demo_login_allowed(
        row["password_hash"], payload.password
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")

    mfa_off = False if DATABASE_BACKEND == "postgresql" else 0
    db.execute(
        text(
            """
            UPDATE users
            SET mfa_enabled = :mfa_off, mfa_secret = NULL
            WHERE user_id = :user_id
            """
        ),
        {"mfa_off": mfa_off, "user_id": user_id},
    )
    db.commit()

    return {"message": "MFA disabled", "mfa_enabled": False}
