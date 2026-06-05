
from pydantic_settings import BaseSettings
from pathlib import Path

ENV_FILE_PATH = Path(__file__).resolve().parents[3] / ".env"

class Settings(BaseSettings):
    """Application settings (citite din .env)."""
    # DATABASE — PostgreSQL only
    # Default valoarea presupune docker-compose (host = "postgres").
    # Pentru rulare locala (python run.py) suprascrii cu localhost in .env.
    DATABASE_URL: str = "postgresql+psycopg://railway:railway_dev@postgres:5432/railway_db"
    # JWT — REQUIRED, fara fallback
    SECRET_KEY: str  # OBLIGATORIU in .env, altfel aplicatia nu porneste
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 ore pentru demo
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # App
    DEBUG: bool = True
    APP_NAME: str = "Railway Digital Identity Platform"
    APP_VERSION: str = "1.0.0"
    # CORS — porturile folosite de run.py / proxy / Vite
    CORS_ORIGINS: list = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:8765",
        "http://localhost:8765",
        "http://127.0.0.1:5000",
        "http://localhost:5000",
    ]
    # QR Tokens
    QR_TOKEN_EXPIRY_SECONDS: int = 120  # 2 minute
    # TOTP MFA
    TOTP_WINDOW: int = 1  # +/- 1 fereastra de 30s

    class Config:
        env_file = str(ENV_FILE_PATH)
        case_sensitive = True
        extra = "ignore"

settings = Settings()
