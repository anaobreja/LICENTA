"""
Security utilities - JWT, password hashing, TOTP
"""

from datetime import datetime, timedelta
from typing import Optional
import jwt
from passlib.context import CryptContext
import pyotp
import qrcode
from io import BytesIO
import base64

from app.core.config import settings

# Password hashing
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12
)


def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


# JWT Token Management
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """Create JWT refresh token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt


def decode_token(token: str) -> dict:
    """Decode and validate JWT token"""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token")


# TOTP MFA
def generate_totp_secret() -> str:
    """Generate new TOTP secret"""
    return pyotp.random_base32()


def get_totp_uri(secret: str, email: str, issuer: str = "Railway") -> str:
    """Get provisioning URI for TOTP (for QR code)"""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(email, issuer_name=issuer)


def generate_totp_qr(secret: str, email: str) -> str:
    """Generate QR code for TOTP setup"""
    uri = get_totp_uri(secret, email)
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(uri)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    
    # Return as base64 for embedding in HTML
    img_base64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{img_base64}"


def verify_totp_code(secret: str, code: str, window: int = 1) -> bool:
    """Verify TOTP code with time window"""
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=window)


# QR Token Generation (for travel validation)
def generate_qr_token() -> str:
    """Generate random QR token"""
    import secrets
    return secrets.token_urlsafe(32)


def hash_qr_token(token: str) -> str:
    """Hash QR token for storage (don't store plaintext)"""
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()

