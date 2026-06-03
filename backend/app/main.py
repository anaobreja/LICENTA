"""
FastAPI Backend - Sistem Gestionare Identitate Digitală Călători
Main application entry point
"""

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session

from app.core.database import engine, SessionLocal
from app.core.config import settings
from app.routers import auth, users, identity


# Event handlers
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Application Starting...")
    # Create tables if not exist
    # Base.metadata.create_all(bind=engine)
    yield
    # Shutdown
    print("🛑 Application Shutting Down...")


# Create FastAPI app
app = FastAPI(
    title="Railway Digital Identity Platform",
    description="Platform for managing digital identity and travel rights validation",
    version="1.0.0",
    docs_url="/docs",
    lifespan=lifespan
)


# CORS Configuration
# CORS Configuration
# In development allow all origins to simplify testing from a public HTTPS tunnel (localtunnel/ngrok).
if settings.DEBUG:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# Health Check Endpoint
@app.get("/health")
async def health_check():
    """Check if API is running"""
    return {
        "status": "healthy",
        "service": "Railway Digital Identity Platform",
        "version": "1.0.0"
    }


# Database Dependency
def get_db():
    """Dependency to get DB session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Welcome to Railway Digital Identity Platform",
        "docs": "/docs",
        "health": "/health"
    }


# Routes will be imported here
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(identity.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )

