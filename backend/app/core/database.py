
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings
# Engine + Session
def _create_engine(database_url: str):
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://", "postgresql+psycopg2://")):
        raise RuntimeError(
            f"DATABASE_URL trebuie sa fie PostgreSQL (postgresql://...). "
            f"Primit: {database_url[:30]}..."
        )

    return create_engine(
        database_url,
        echo=settings.DEBUG,
        pool_size=10,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=3600,
    )

engine = _create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Backend identifier folosit in cod pentru compatibilitate cu importurile existente.
# Toate ramurile "if DATABASE_BACKEND == 'sqlite'" au fost eliminate.
DATABASE_BACKEND = "postgresql"
# Startup verification — ne asiguram ca schema e prezenta
REQUIRED_TABLES = [
    "users",
    "universities",
    "issuers",
    "source_documents",
    "document_reviews",
    "user_credentials",
    "digital_cards",
    "card_presentations",
    "card_verifications",
    "notifications",
    "railway_operators",
    "routes",
    "stations",
    "trains",
    "tickets",
    "subscriptions",
    "travel_entitlements",
    "qr_tokens",
    "validations",
]

def verify_schema_loaded() -> None:
    """
    Verifica la pornire ca schema PostgreSQL este incarcata.
    Daca lipseste o tabela esentiala, ridica RuntimeError cu mesaj clar.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                """
            )
        ).fetchall()
        existing = {r[0] for r in rows}

    missing = [t for t in REQUIRED_TABLES if t not in existing]
    if missing:
        raise RuntimeError(
            "Schema PostgreSQL incompleta. Tabele lipsa: "
            + ", ".join(missing)
            + ". Ruleaza `docker-compose up` care incarca automat "
            "database/schema.sql + database/seed_demo.sql la prima pornire. "
            "Daca DB-ul a fost initializat cu o versiune veche, sterge "
            "volumul postgres_data si reporneste: "
            "`docker-compose down -v && docker-compose up`."
        )
# Helpers folositi de seed-uri / health checks
def get_user_count() -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT COUNT(*) FROM users")).scalar() or 0
