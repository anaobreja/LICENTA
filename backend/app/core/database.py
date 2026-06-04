"""
Database configuration and setup
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import time

from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool

from app.core.config import settings


def _attach_sqlite_pragmas(engine) -> None:
    """Reduce 'database is locked' when another process uses the same SQLite file."""

    @event.listens_for(engine, "connect")
    def _on_sqlite_connect(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA busy_timeout=60000")
            cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()


def _initialize_sqlite_demo_data_with_retry(engine, attempts: int = 4) -> None:
    delay = 0.5
    last_err: Exception | None = None
    for i in range(attempts):
        try:
            _initialize_sqlite_demo_data(engine)
            return
        except OperationalError as exc:
            last_err = exc
            if "locked" not in str(exc).lower() or i == attempts - 1:
                raise
            time.sleep(delay)
            delay *= 1.5
    if last_err:
        raise last_err


def _create_engine(database_url: str):
    if database_url.startswith("sqlite"):
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False, "timeout": 30},
            poolclass=NullPool,
        )

    return create_engine(
        database_url,
        echo=settings.DEBUG,
        pool_size=20,
        max_overflow=0,
        pool_pre_ping=True,
    )


def _initialize_sqlite_identity_tables(connection):
    """Create identity-related tables using an existing connection (no nested transaction)."""
    tables = [
        """
        CREATE TABLE IF NOT EXISTS source_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            document_type TEXT NOT NULL,
            document_number_masked TEXT NOT NULL,
            document_image_path TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            university_name TEXT,
            year_of_study INTEGER,
            ci_number TEXT,
            ci_name TEXT,
            ci_date_of_birth TEXT,
            ci_sex TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS document_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            reviewer_id INTEGER NOT NULL,
            decision TEXT NOT NULL,
            notes TEXT,
            reviewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_credentials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            credential_type TEXT NOT NULL,
            claim_value TEXT NOT NULL,
            issuer_id INTEGER,
            status TEXT NOT NULL DEFAULT 'active',
            issued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            valid_until TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS issuers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            issuer_type TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS digital_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            issuer_id INTEGER NOT NULL,
            card_identifier TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'active',
            issued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            valid_until TEXT NOT NULL,
            revoked_at TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS card_presentations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id INTEGER NOT NULL,
            token_value TEXT NOT NULL UNIQUE,
            issued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            used_at TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS card_verifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_presentation_id INTEGER NOT NULL,
            verifier_user_id INTEGER NOT NULL,
            verification_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            result TEXT NOT NULL,
            notes TEXT
        )
        """,
    ]

    for table_sql in tables:
        try:
            connection.exec_driver_sql(table_sql)
        except Exception:
            pass

    # Migrare: adaugă coloane noi dacă lipsesc din baze existente
    for col, col_type in [
        ("university_name", "TEXT"),
        ("year_of_study", "INTEGER"),
        ("ci_number", "TEXT"),
        ("ci_name", "TEXT"),
        ("ci_date_of_birth", "TEXT"),
        ("ci_sex", "TEXT"),
        ("ci_address", "TEXT"),
        ("document_image_path_verso", "TEXT"),
    ]:
        try:
            connection.exec_driver_sql(
                f"ALTER TABLE source_documents ADD COLUMN {col} {col_type}"
            )
        except Exception:
            pass


def _seed_sqlite_demo_identity_card(connection) -> None:
    """Ensure the demo passenger has an active digital card in SQLite."""
    user_row = connection.execute(
        text("SELECT user_id FROM users WHERE email = :email"),
        {"email": "user.demo@railwaydemo.com"},
    ).first()
    if not user_row:
        return

    issuer_row = connection.execute(
        text("SELECT id FROM issuers WHERE name = :name LIMIT 1"),
        {"name": "Railway Digital Identity Authority"},
    ).first()
    if issuer_row:
        issuer_id = issuer_row[0]
    else:
        connection.execute(
            text(
                """
                INSERT INTO issuers (name, issuer_type, is_active)
                VALUES ('Railway Digital Identity Authority', 'transport', 1)
                """
            )
        )
        issuer_id = connection.execute(
            text("SELECT id FROM issuers WHERE name = :name LIMIT 1"),
            {"name": "Railway Digital Identity Authority"},
        ).first()[0]

    connection.execute(
        text(
            """
            INSERT OR IGNORE INTO digital_cards (
                user_id, issuer_id, card_identifier, status, valid_until
            ) VALUES (
                :user_id, :issuer_id, :card_identifier, 'active', :valid_until
            )
            """
        ),
        {
            "user_id": user_row[0],
            "issuer_id": issuer_id,
            "card_identifier": "RDC-DEMO-USER",
            "valid_until": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
        },
    )
def _initialize_sqlite_demo_data(sqlite_engine):
    users_table_sql = """
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        phone TEXT,
        date_of_birth TEXT,
        role TEXT NOT NULL DEFAULT 'passenger',
        is_active INTEGER DEFAULT 1,
        mfa_secret TEXT,
        mfa_enabled INTEGER NOT NULL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """

    # Parola demo pentru toate conturile de test: "demo2026"
    _DEMO_HASH = "$2b$12$HijeaYT9.i7NHMV/w9m4eez/yAa6hzJprroikrkomRWEbSnp7pIgO"
    demo_users = [
        ("Alexandra", "Popescu", "alexandra.popescu@email.com", _DEMO_HASH, "+40721234567", "1995-03-15", "passenger"),
        ("Andrei", "Ionescu", "andrei.ionescu@email.com", _DEMO_HASH, "+40722334455", "2002-07-22", "passenger"),
        ("Ioan", "Vasile", "ioan.vasile@email.com", _DEMO_HASH, "+40723445566", "1955-12-10", "passenger"),
        ("Maria", "Dumitru", "maria.dumitru@email.com", _DEMO_HASH, "+40724556677", "1988-05-18", "passenger"),
        ("George", "Constantinescu", "george.constantinescu@email.com", _DEMO_HASH, "+40725667788", "1978-01-09", "conductor"),
        ("Administrator", "System", "admin@railway.gov.ro", _DEMO_HASH, "+40726778899", "1980-06-20", "admin"),
        ("Demo", "User", "user.demo@railwaydemo.com", _DEMO_HASH, "+40720000001", "1999-01-01", "passenger"),
        ("Demo", "Train", "agent.train@railwaydemo.com", _DEMO_HASH, "+40720000003", "1985-01-01", "conductor"),
        ("Agent", "UPB",   "agent.upb@railwaydemo.com",   _DEMO_HASH, "+40720000004", "1985-01-01", "university_agent"),
        ("Agent", "ASE",   "agent.ase@railwaydemo.com",   _DEMO_HASH, "+40720000005", "1986-01-01", "university_agent"),
        ("Agent", "UNIBUC","agent.unibuc@railwaydemo.com", _DEMO_HASH, "+40720000006", "1987-01-01", "university_agent"),
    ]

    with sqlite_engine.begin() as connection:
        connection.exec_driver_sql(users_table_sql)

        # Tabel universities
        connection.exec_driver_sql("""
            CREATE TABLE IF NOT EXISTS universities (
                university_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                short_name TEXT NOT NULL UNIQUE,
                city TEXT NOT NULL,
                email_domain TEXT,
                contact_email TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.execute(text("""
            INSERT OR IGNORE INTO universities (university_id, name, short_name, city, email_domain, contact_email)
            VALUES (1, 'Universitatea Politehnica București (UPB)', 'UPB', 'București', 'stud.acs.upb.ro', 'secretariat@upb.ro'),
                   (2, 'Academia de Studii Economice', 'ASE', 'București', 'stud.ase.ro', 'secretariat@ase.ro'),
                   (3, 'Universitatea din București', 'UNIBUC', 'București', 'student.unibuc.ro', 'secretariat@unibuc.ro')
        """))

        # Coloana university_id pe users
        try:
            connection.exec_driver_sql("ALTER TABLE users ADD COLUMN university_id INTEGER")
        except Exception:
            pass

        for first_name, last_name, email, password_hash, phone, date_of_birth, role in demo_users:
            connection.execute(
                text(
                    """
                    INSERT OR IGNORE INTO users
                    (first_name, last_name, email, password_hash, phone, date_of_birth, role, is_active)
                    VALUES (:first_name, :last_name, :email, :password_hash, :phone, :date_of_birth, :role, 1)
                    """
                ),
                {
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": email,
                    "password_hash": password_hash,
                    "phone": phone,
                    "date_of_birth": date_of_birth,
                    "role": role,
                },
            )

        # Leagă agenții de universitățile lor
        connection.execute(text("UPDATE users SET university_id = 1 WHERE email = 'agent.upb@railwaydemo.com'"))
        connection.execute(text("UPDATE users SET university_id = 2 WHERE email = 'agent.ase@railwaydemo.com'"))
        connection.execute(text("UPDATE users SET university_id = 3 WHERE email = 'agent.unibuc@railwaydemo.com'"))

        _initialize_sqlite_identity_tables(connection)


def _ensure_source_document_columns(engine, backend: str) -> None:
    columns = [("document_image_path_verso", "TEXT")]
    if backend == "sqlite":
        with engine.begin() as conn:
            rows = conn.execute(text("PRAGMA table_info(source_documents)")).fetchall()
            existing = {r[1] for r in rows}
            for col, col_type in columns:
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE source_documents ADD COLUMN {col} {col_type}"))
    else:
        try:
            with engine.begin() as conn:
                for col, col_type in columns:
                    conn.execute(
                        text(f"ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS {col} {col_type}")
                    )
        except Exception:
            pass


def _ensure_card_presentation_columns(engine, backend: str) -> None:
    """Ensure used_at column exists on card_presentations (single-use QR fix)."""
    if backend == "sqlite":
        with engine.begin() as conn:
            rows = conn.execute(text("PRAGMA table_info(card_presentations)")).fetchall()
            existing = {r[1] for r in rows}
            if "used_at" not in existing:
                conn.execute(text("ALTER TABLE card_presentations ADD COLUMN used_at TEXT"))
    else:
        try:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE card_presentations ADD COLUMN IF NOT EXISTS used_at TIMESTAMP"))
        except Exception:
            pass


def _ensure_user_profile_columns(engine, backend: str) -> None:
    """Add profile photo and university on users when missing."""
    columns = [
        ("profile_photo_path", "TEXT"),
        ("university_name", "TEXT"),
    ]
    if backend == "sqlite":
        with engine.begin() as conn:
            rows = conn.execute(text("PRAGMA table_info(users)")).fetchall()
            existing = {r[1] for r in rows}
            for col, col_type in columns:
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {col_type}"))
    else:
        try:
            with engine.begin() as conn:
                for col, col_type in columns:
                    conn.execute(
                        text(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {col_type}")
                    )
        except Exception:
            pass


def _ensure_user_mfa_columns(engine, backend: str) -> None:
    """Add MFA columns to users when missing (SQLite + PostgreSQL)."""
    if backend == "sqlite":
        with engine.begin() as conn:
            rows = conn.execute(text("PRAGMA table_info(users)")).fetchall()
            col_names = {r[1] for r in rows}
            if "mfa_secret" not in col_names:
                conn.execute(text("ALTER TABLE users ADD COLUMN mfa_secret TEXT"))
            if "mfa_enabled" not in col_names:
                conn.execute(text("ALTER TABLE users ADD COLUMN mfa_enabled INTEGER NOT NULL DEFAULT 0"))
    else:
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_secret VARCHAR(500)"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_enabled BOOLEAN DEFAULT FALSE"
                    )
                )
        except Exception:
            # users table may not exist until full schema is applied
            pass


def _initialize_sqlite_travel_control_tables(connection) -> None:
    """Minimal ticketing schema for /control/validate when using SQLite fallback."""
    ddl = [
        """
        CREATE TABLE IF NOT EXISTS stations (
            station_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            city TEXT NOT NULL,
            code TEXT NOT NULL UNIQUE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS railway_operators (
            operator_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT NOT NULL UNIQUE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS routes (
            route_id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator_id INTEGER NOT NULL,
            route_name TEXT NOT NULL,
            origin_station_id INTEGER NOT NULL,
            destination_station_id INTEGER NOT NULL,
            FOREIGN KEY (operator_id) REFERENCES railway_operators(operator_id),
            FOREIGN KEY (origin_station_id) REFERENCES stations(station_id),
            FOREIGN KEY (destination_station_id) REFERENCES stations(station_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS trains (
            train_id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator_id INTEGER NOT NULL,
            route_id INTEGER NOT NULL,
            train_number TEXT NOT NULL,
            train_type TEXT NOT NULL DEFAULT 'regional',
            capacity INTEGER NOT NULL DEFAULT 200,
            is_active INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (operator_id) REFERENCES railway_operators(operator_id),
            FOREIGN KEY (route_id) REFERENCES routes(route_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            train_id INTEGER NOT NULL,
            departure_station_id INTEGER NOT NULL,
            arrival_station_id INTEGER NOT NULL,
            travel_date TEXT NOT NULL,
            travel_time TEXT,
            seat_number TEXT,
            ticket_type TEXT NOT NULL DEFAULT 'single',
            ticket_status TEXT NOT NULL DEFAULT 'active',
            price REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (train_id) REFERENCES trains(train_id),
            FOREIGN KEY (departure_station_id) REFERENCES stations(station_id),
            FOREIGN KEY (arrival_station_id) REFERENCES stations(station_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS subscriptions (
            subscription_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subscription_type TEXT NOT NULL DEFAULT 'monthly',
            operator_id INTEGER,
            route_id INTEGER,
            valid_from TEXT NOT NULL,
            valid_until TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            price REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS travel_entitlements (
            entitlement_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            ticket_id INTEGER,
            subscription_id INTEGER,
            user_benefit_id INTEGER,
            valid_from TEXT NOT NULL,
            valid_until TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (ticket_id) REFERENCES tickets(ticket_id),
            FOREIGN KEY (subscription_id) REFERENCES subscriptions(subscription_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS qr_tokens (
            qr_token_id INTEGER PRIMARY KEY AUTOINCREMENT,
            entitlement_id INTEGER NOT NULL,
            token_value TEXT NOT NULL UNIQUE,
            token_hash TEXT NOT NULL,
            issued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            used_at TEXT,
            FOREIGN KEY (entitlement_id) REFERENCES travel_entitlements(entitlement_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS validations (
            validation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            qr_token_id INTEGER NOT NULL,
            conductor_id INTEGER NOT NULL,
            validation_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            validation_result TEXT NOT NULL,
            location_station_id INTEGER,
            device_id TEXT,
            notes TEXT,
            FOREIGN KEY (qr_token_id) REFERENCES qr_tokens(qr_token_id),
            FOREIGN KEY (conductor_id) REFERENCES users(user_id)
        )
        """,
    ]
    for sql in ddl:
        try:
            connection.exec_driver_sql(sql)
        except Exception:
            pass


def _seed_sqlite_demo_travel_data(connection) -> None:
    """One demo ticket + QR token for user.demo@railwaydemo.com (SQLite only)."""
    row = connection.execute(
        text("SELECT user_id FROM users WHERE email = :email"),
        {"email": "user.demo@railwaydemo.com"},
    ).first()
    if not row:
        return
    demo_uid = row[0]

    connection.execute(
        text(
            """
            INSERT OR IGNORE INTO stations (station_id, name, city, code)
            VALUES (1, 'Bucuresti Nord', 'Bucuresti', 'BN'),
                   (2, 'Cluj Napoca', 'Cluj-Napoca', 'CJ')
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT OR IGNORE INTO railway_operators (operator_id, name, code)
            VALUES (1, 'CFR Calatori', 'CFR')
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT OR IGNORE INTO routes (route_id, operator_id, route_name, origin_station_id, destination_station_id)
            VALUES (1, 1, 'Bucuresti - Cluj', 1, 2)
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT OR IGNORE INTO trains (train_id, operator_id, route_id, train_number, train_type, capacity, is_active)
            VALUES (1, 1, 1, 'IR1741', 'intercity', 300, 1)
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT OR IGNORE INTO tickets (ticket_id, user_id, train_id, departure_station_id, arrival_station_id,
                travel_date, seat_number, ticket_type, ticket_status, price)
            VALUES (1, :uid, 1, 1, 2, '2099-12-31', '12A', 'single', 'active', 89.5)
            """
        ),
        {"uid": demo_uid},
    )
    connection.execute(
        text(
            """
            INSERT OR IGNORE INTO travel_entitlements (
                entitlement_id, user_id, source_type, ticket_id, subscription_id, user_benefit_id,
                valid_from, valid_until, status
            )
            VALUES (1, :uid, 'ticket', 1, NULL, NULL, '2020-01-01', '2099-12-31', 'active')
            """
        ),
        {"uid": demo_uid},
    )
    connection.execute(text("DELETE FROM qr_tokens WHERE token_value = 'DEMO_TRAVEL_QR'"))
    connection.execute(
        text(
            """
            INSERT INTO qr_tokens (entitlement_id, token_value, token_hash, expires_at, status)
            VALUES (1, 'DEMO_TRAVEL_QR', 'demo_hash', '2099-12-31T23:59:59', 'active')
            """
        )
    )


_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_SQLITE_FILE = _REPO_ROOT / "railway_demo.db"

DATABASE_URL = settings.DATABASE_URL
DATABASE_BACKEND = "postgresql"

if (DATABASE_URL or "").strip().lower().startswith("sqlite"):
    DATABASE_BACKEND = "sqlite"
    engine = _create_engine(DATABASE_URL)
    _attach_sqlite_pragmas(engine)
    _initialize_sqlite_demo_data_with_retry(engine)
else:
    try:
        engine = _create_engine(DATABASE_URL)
        with engine.connect():
            pass
    except Exception:
        DATABASE_URL = f"sqlite:///{_DEFAULT_SQLITE_FILE.as_posix()}"
        DATABASE_BACKEND = "sqlite"
        engine = _create_engine(DATABASE_URL)
        _attach_sqlite_pragmas(engine)
        _initialize_sqlite_demo_data_with_retry(engine)

_ensure_source_document_columns(engine, DATABASE_BACKEND)
_ensure_user_profile_columns(engine, DATABASE_BACKEND)
_ensure_user_mfa_columns(engine, DATABASE_BACKEND)
_ensure_card_presentation_columns(engine, DATABASE_BACKEND)

if DATABASE_BACKEND == "sqlite":
    with engine.begin() as _conn:
        # universities
        _conn.exec_driver_sql("""
            CREATE TABLE IF NOT EXISTS universities (
                university_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                short_name TEXT NOT NULL UNIQUE,
                city TEXT NOT NULL,
                email_domain TEXT,
                contact_email TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        _conn.execute(text("""
            INSERT OR IGNORE INTO universities (university_id, name, short_name, city)
            VALUES (1,'Universitatea Politehnica București (UPB)','UPB','București'),
                   (2,'Academia de Studii Economice','ASE','București'),
                   (3,'Universitatea din București','UNIBUC','București')
        """))
        try:
            _conn.exec_driver_sql("ALTER TABLE users ADD COLUMN university_id INTEGER")
        except Exception:
            pass
        # Seed agent UPB dacă nu există
        _DEMO_HASH = "$2b$12$HijeaYT9.i7NHMV/w9m4eez/yAa6hzJprroikrkomRWEbSnp7pIgO"
        for _email, _fname, _lname, _hash, _phone, _univ_id in [
            ('agent.upb@railwaydemo.com',   'Agent','UPB',    _DEMO_HASH, '+40720000004', 1),
            ('agent.ase@railwaydemo.com',   'Agent','ASE',    _DEMO_HASH, '+40720000005', 2),
            ('agent.unibuc@railwaydemo.com','Agent','UNIBUC', _DEMO_HASH, '+40720000006', 3),
        ]:
            _conn.execute(text("""
                INSERT OR IGNORE INTO users
                    (first_name, last_name, email, password_hash, phone, date_of_birth, role, is_active, university_id)
                VALUES (:fn, :ln, :email, :ph, :phone, '1985-01-01', 'university_agent', 1, :uid)
            """), {"fn": _fname, "ln": _lname, "email": _email, "ph": _hash, "phone": _phone, "uid": _univ_id})
            _conn.execute(text(
                "UPDATE users SET university_id = :uid WHERE email = :email AND university_id IS NULL"
            ), {"uid": _univ_id, "email": _email})

# Migrare: setează valid_until la 30 septembrie 2026 pentru credențialele existente
# care au valid_until > 2026-09-30 (setat anterior ca +365 zile arbitrar)
if DATABASE_BACKEND == "sqlite":
    with engine.begin() as _conn:
        _conn.exec_driver_sql(
            "UPDATE user_credentials SET valid_until = '2026-09-30 23:59:59' "
            "WHERE valid_until > '2026-09-30 23:59:59' AND status = 'active'"
        )
        _conn.exec_driver_sql(
            "UPDATE digital_cards SET valid_until = '2026-09-30 23:59:59' "
            "WHERE valid_until > '2026-09-30 23:59:59' AND status = 'active'"
        )

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# Base class for models
Base = declarative_base()

