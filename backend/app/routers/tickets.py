"""
Ticketing and validations - PostgreSQL-based (separate from identity SQLite DB)
Routes: /tickets/* endpoints for buying, validating tickets
"""

from fastapi import APIRouter, HTTPException, Header, Depends, status
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from typing import Optional
from app.core.config import settings

router = APIRouter(prefix="/tickets", tags=["tickets"])

# PostgreSQL session for ticketing
TICKETING_DB_URL = settings.POSTGRES_TICKETING_URL or settings.DATABASE_URL.replace("sqlite", "postgresql")
try:
    ticketing_engine = create_engine(TICKETING_DB_URL, connect_args={"check_same_thread": False} if "sqlite" in TICKETING_DB_URL else {})
    TicketingSession = sessionmaker(bind=ticketing_engine)
except Exception as e:
    print(f"Warning: Could not connect to ticketing database: {e}. Ticketing endpoints will not be available.")
    TicketingSession = None


def get_ticketing_db():
    """Get ticketing database session"""
    if TicketingSession is None:
        raise HTTPException(status_code=503, detail="Ticketing service not available")
    db = TicketingSession()
    try:
        yield db
    finally:
        db.close()


class ValidateTicketRequest(BaseModel):
    """Request to validate a ticket QR"""
    token: str
    device_id: Optional[str] = None
    location_name: Optional[str] = None


class ValidateTicketResponse(BaseModel):
    """Response from ticket validation"""
    result: str  # "valid", "invalid", "expired", "already_used"
    message: str
    passenger_name: Optional[str] = None
    ticket_type: Optional[str] = None
    valid_until: Optional[str] = None


@router.post("/validate", response_model=ValidateTicketResponse)
def validate_ticket(
    payload: ValidateTicketRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_ticketing_db),
):
    """
    Validate a ticket/entitlement QR token.
    Conductor scans QR, system checks if valid and marks as used.
    """
    # Extract conductor info from JWT (simplified - uses Bearer token)
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization",
        )

    try:
        # Query QR token - single-use validation
        qr = db.execute(
            text(
                """
                SELECT qt.qr_token_id, qt.status, qt.expires_at, qt.used_at,
                       te.entitlement_id, te.user_id, te.source_type, te.valid_until,
                       u.first_name, u.last_name,
                       CASE 
                           WHEN te.source_type = 'ticket' THEN t.ticket_type
                           WHEN te.source_type = 'subscription' THEN s.subscription_type
                           WHEN te.source_type = 'benefit' THEN 'student_card'
                       END AS entitlement_type
                FROM qr_tokens qt
                JOIN travel_entitlements te ON te.entitlement_id = qt.entitlement_id
                JOIN users u ON u.user_id = te.user_id
                LEFT JOIN tickets t ON t.ticket_id = te.ticket_id
                LEFT JOIN subscriptions s ON s.subscription_id = te.subscription_id
                WHERE qt.token_value = :token_value
                """
            ),
            {"token_value": payload.token},
        ).mappings().first()

        if not qr:
            return ValidateTicketResponse(
                result="invalid",
                message="Token not found"
            )

        # Check if already used (single-use)
        if qr["used_at"] is not None:
            return ValidateTicketResponse(
                result="already_used",
                message="This ticket has already been used"
            )

        # Check status
        if qr["status"] != "active":
            return ValidateTicketResponse(
                result="invalid",
                message=f"Token status is {qr['status']}"
            )

        # Check expiration
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if qr["expires_at"] and now > qr["expires_at"]:
            return ValidateTicketResponse(
                result="expired",
                message="Token has expired"
            )

        if qr["valid_until"] and now > qr["valid_until"]:
            return ValidateTicketResponse(
                result="expired",
                message="Entitlement validity period expired"
            )

        # Mark as used (SINGLE-USE ENFORCEMENT)
        db.execute(
            text(
                """
                UPDATE qr_tokens
                SET status = 'used', used_at = CURRENT_TIMESTAMP
                WHERE qr_token_id = :qr_token_id
                """
            ),
            {"qr_token_id": qr["qr_token_id"]},
        )

        # Record validation in audit log
        db.execute(
            text(
                """
                INSERT INTO validations (qr_token_id, conductor_id, validation_result, device_id, notes)
                VALUES (:qr_token_id, :conductor_id, :result, :device_id, :notes)
                """
            ),
            {
                "qr_token_id": qr["qr_token_id"],
                "conductor_id": 0,  # Would be extracted from JWT in production
                "result": "valid",
                "device_id": payload.device_id,
                "notes": payload.location_name,
            },
        )

        db.commit()

        return ValidateTicketResponse(
            result="valid",
            message="Ticket validated successfully",
            passenger_name=f"{qr['first_name']} {qr['last_name']}",
            ticket_type=qr["entitlement_type"],
            valid_until=str(qr["valid_until"]) if qr["valid_until"] else None,
        )

    except Exception as e:
        db.rollback()
        return ValidateTicketResponse(
            result="invalid",
            message=f"Validation error: {str(e)}"
        )


@router.post("/buy")
def buy_ticket(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_ticketing_db),
):
    """
    Buy a ticket (demo endpoint - creates a ticket + QR token)
    Returns: ticket info + QR token
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        # Create demo ticket for current user
        ticket = db.execute(
            text(
                """
                INSERT INTO tickets (
                    user_id, train_id, departure_station_id, arrival_station_id,
                    travel_date, ticket_type, ticket_status, price
                )
                VALUES (1, 1, 1, 2, CURRENT_DATE + INTERVAL '7 days', 'single', 'active', 50.00)
                RETURNING ticket_id, travel_date, ticket_type
                """
            ),
        ).mappings().first()

        if not ticket:
            raise HTTPException(status_code=500, detail="Could not create ticket")

        # Create travel entitlement
        entitlement = db.execute(
            text(
                """
                INSERT INTO travel_entitlements (
                    user_id, source_type, ticket_id, valid_from, valid_until, status
                )
                VALUES (1, 'ticket', :ticket_id, CURRENT_DATE, CURRENT_DATE + INTERVAL '7 days', 'active')
                RETURNING entitlement_id
                """
            ),
            {"ticket_id": ticket["ticket_id"]},
        ).mappings().first()

        # Create QR token
        import secrets
        token_value = secrets.token_urlsafe(32)
        
        qr = db.execute(
            text(
                """
                INSERT INTO qr_tokens (
                    entitlement_id, token_value, token_hash, expires_at, status
                )
                VALUES (:ent_id, :token, :token_hash, CURRENT_TIMESTAMP + INTERVAL '7 days', 'active')
                RETURNING qr_token_id, token_value, expires_at
                """
            ),
            {
                "ent_id": entitlement["entitlement_id"],
                "token": token_value,
                "token_hash": token_value,  # Simplified - should hash in prod
            },
        ).mappings().first()

        db.commit()

        return {
            "ticket_id": ticket["ticket_id"],
            "type": ticket["ticket_type"],
            "travel_date": str(ticket["travel_date"]),
            "qr_token": qr["token_value"],
            "expires_at": str(qr["expires_at"]),
            "message": "Ticket created. Use the QR token to validate."
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
