"""
FastAPI Backend - Sistem Gestionare Identitate Digitala Calatori
Main application entry point.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import SessionLocal, verify_schema_loaded
from app.routers import auth, crypto_keys, identity, tickets, users
from app.routers import map as map_router
# Lifespan: la startup verificam ca schema PostgreSQL este incarcata
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Railway Digital Identity Platform starting...")
    try:
        verify_schema_loaded()
        print("Schema PostgreSQL OK")
    except RuntimeError as exc:
        print(f"SCHEMA ERROR: {exc}")
        raise
    yield
    print("Shutting down.")

app = FastAPI(
    title="Railway Digital Identity Platform",
    description="Platform for managing digital identity and travel rights validation",
    version="1.0.0",
    docs_url="/docs",
    lifespan=lifespan,
)
# CORS
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
        allow_origin_regex=(
            r"http://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}|"
            r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
            r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})(:\d+)?$"
        ),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
# Health Check
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "Railway Digital Identity Platform",
        "version": settings.APP_VERSION,
        "database": "postgresql",
    }

@app.get("/")
async def root():
    return {
        "message": "Welcome to Railway Digital Identity Platform",
        "docs": "/docs",
        "health": "/health",
    }
# Database Dependency (folosit de unele rute care nu importa get_db din router)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
# Routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(identity.router)
app.include_router(tickets.router)
app.include_router(map_router.router)
app.include_router(crypto_keys.router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
