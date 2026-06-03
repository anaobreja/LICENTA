"""
Configuration settings for the application
"""

from pydantic_settings import BaseSettings
from pathlib import Path


ENV_FILE_PATH = Path(__file__).resolve().parents[3] / ".env"

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_SQLITE_PATH = _REPO_ROOT / "railway_demo.db"


class Settings(BaseSettings):
    """Application settings"""

    # Database — implicit SQLite in radacina proiectului (fara PostgreSQL obligatoriu)
    DATABASE_URL: str = f"sqlite:///{_DEFAULT_SQLITE_PATH.as_posix()}"
    
    # JWT
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # App
    DEBUG: bool = True
    APP_NAME: str = "Railway Digital Identity Platform"
    APP_VERSION: str = "1.0.0"
    
    # CORS — include portul folosit de run.py / proxy
    CORS_ORIGINS: list = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:8765",
        "http://localhost:8765",
        "http://127.0.0.1:5000",
        "http://localhost:5000",
    ]
    
    # QR Tokens
    QR_TOKEN_EXPIRY_SECONDS: int = 120  # 2 minutes
    
    # TOTP MFA
    TOTP_WINDOW: int = 1  # Allow 1 window before/after
    
    class Config:
        env_file = str(ENV_FILE_PATH)
        case_sensitive = True
        extra = "ignore"


settings = Settings()

