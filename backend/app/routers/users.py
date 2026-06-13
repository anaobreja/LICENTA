from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import decode_token, hash_password, verify_password
from app.core.uploads import save_uploaded_image
from app.core.roles import (
    ROLE_TRAIN_VERIFIER,
    ROLE_UNIVERSITY_AGENT,
    has_role,
    normalize_role,
)
from app.core.identity_status import (
    check_frozen_field_changes,
    get_verification_status,
    FROZEN_FIELDS_WHEN_VERIFIED,
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
    # Statia de domiciliu declarata de pasager pentru ruta personala.
    # Trimite 0 sau null ca sa stergi setarea.
    home_station_id: Optional[int] = Field(default=None, ge=0)


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
            SELECT
                u.user_id, u.first_name, u.last_name, u.email, u.phone,
                u.date_of_birth, u.role, u.is_active,
                u.mfa_enabled, u.university_name, u.profile_photo_path,
                u.home_station_id,
                hs.name AS home_station_name,
                hs.city AS home_station_city,
                hs.code AS home_station_code,
                un.main_station_id  AS university_station_id,
                us.name AS university_station_name,
                un.short_name       AS university_short_name
            FROM users u
            LEFT JOIN stations     hs ON hs.station_id    = u.home_station_id
            LEFT JOIN universities un ON un.university_id = u.university_id
            LEFT JOIN stations     us ON us.station_id    = un.main_station_id
            WHERE u.user_id = :user_id
            """
        ),
        {"user_id": user_id},
    ).mappings().first()

    if not row or not _is_account_active(row.get("is_active")):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    home_station = None
    if row.get("home_station_id"):
        home_station = {
            "station_id": row["home_station_id"],
            "name": row.get("home_station_name"),
            "city": row.get("home_station_city"),
            "code": row.get("home_station_code"),
        }

    university_station = None
    if row.get("university_station_id"):
        university_station = {
            "station_id": row["university_station_id"],
            "name": row.get("university_station_name"),
        }

    return {
        "user_id": row["user_id"],
        "first_name": row["first_name"],
        "last_name": row["last_name"],
        "email": row["email"],
        "phone": row.get("phone"),
        "date_of_birth": row.get("date_of_birth"),
        "university_name": row.get("university_name"),
        "university_short_name": row.get("university_short_name"),
        "has_profile_photo": bool(row.get("profile_photo_path")),
        "role": normalize_role(row["role"]),
        "mfa_enabled": _mfa_enabled_value(row.get("mfa_enabled")),
        # Ruta personala — folosita la cumpararea de bilete cu reducere
        "home_station": home_station,
        "university_station": university_station,
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

    # Securitate: campurile FROZEN nu pot fi modificate cat timp userul
    # are credential identity_verified activ (datele validate sunt protejate
    # pana la sfarsitul anului universitar curent).
    payload_dict = payload.model_dump(exclude_unset=True)
    if payload_dict:
        # Aducem starea curenta a userului pentru comparare cu payload
        current_row = db.execute(
            text("""
                SELECT cnp, first_name, last_name, date_of_birth, home_station_id
                FROM users WHERE user_id = :uid
            """),
            {"uid": user_id},
        ).mappings().first()

        if current_row:
            frozen_changes = check_frozen_field_changes(
                db, user_id, current_row, payload_dict
            )
            if frozen_changes:
                status_info = get_verification_status(db, user_id)
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "frozen_field_modification_blocked",
                        "message": (
                            f"Nu puteti modifica campurile {frozen_changes} "
                            f"cat timp identitatea este verificata. "
                            f"Verificarea expira pe {status_info['expires_at']} "
                            f"(sfarsitul anului universitar curent). "
                            f"Dupa expirare puteti modifica datele si va trebui "
                            f"sa refaceti procesul de verificare."
                        ),
                        "frozen_fields_attempted": frozen_changes,
                        "expires_at": status_info["expires_at"],
                        "days_until_expiry": status_info["days_until_expiry"],
                    },
                )

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
        # Acceptam 3 formate: YYYY-MM-DD (ISO), YYYY-MM-DDTHH:MM:SS (ISO timestamp)
        # si dd.mm.YYYY (legacy romanesc). Normalizam toate la string YYYY-MM-DD.
        from datetime import date, datetime
        raw = payload.date_of_birth.strip()
        try:
            if "T" in raw:
                parsed_str = datetime.fromisoformat(raw).date().isoformat()
            elif "." in raw:
                # Format legacy dd.mm.YYYY -> normalizez la ISO
                parsed_str = datetime.strptime(raw, "%d.%m.%Y").date().isoformat()
            else:
                date.fromisoformat(raw)  # validare
                parsed_str = raw
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"date_of_birth format invalid: {raw!r}. Use YYYY-MM-DD or dd.mm.YYYY.",
            )
        updates["date_of_birth"] = parsed_str
    if payload.home_station_id is not None:
        # 0 sau null = sterge selectia
        if payload.home_station_id == 0:
            updates["home_station_id"] = None
        else:
            exists = db.execute(
                text("SELECT 1 FROM stations WHERE station_id = :sid AND is_active = TRUE"),
                {"sid": payload.home_station_id},
            ).first()
            if not exists:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Statia cu id {payload.home_station_id} nu exista sau este inactiva",
                )
            updates["home_station_id"] = payload.home_station_id

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

    inactive = False
    db.execute(
        text("UPDATE users SET is_active = :inactive, updated_at = CURRENT_TIMESTAMP WHERE user_id = :user_id"),
        {"inactive": inactive, "user_id": user_id},
    )
    db.commit()

    return {"message": "Account deactivated", "user_id": user_id}


# ============================================================================
# === VERIFICATION STATUS ===
# ----------------------------------------------------------------------------
# Endpoint dedicat pentru frontend ca sa stie ce campuri sunt frozen si pana
# cand. Folosit in Profile.jsx pentru a afisa banner + a dezactiva inputurile.
# ============================================================================


@router.get("/me/verification-status")
def my_verification_status(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Returneaza statusul de verificare al utilizatorului curent:
      - is_verified: True daca exista credential identity_verified activ
      - verified_at, expires_at: datele cheie
      - days_until_expiry: cate zile mai sunt pana la expirare
      - frozen_fields: lista campurilor protejate (cand verified)
      - academic_year: e.g. "2025-2026"
      - message: text pentru afisare in UI
    """
    user_id = _current_user_id(authorization, db)
    return get_verification_status(db, user_id)


@router.get("/me/travel-stats")
def my_travel_stats(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Statistici personalizate de calatorie pentru dashboard.

    IMPORTANT: o "calatorie efectiva" inseamna ca biletul a fost VALIDAT
    de conductor (ticket_status = 'used'), NU doar cumparat. Asta reflecta
    distanta REAL parcursa cu trenul, nu intentii.

      - total_trips: nr bilete cumparate (active + used + cancelled)
      - completed_trips: nr calatorii efectiv validate (only 'used')
      - upcoming_trips: bilete active cu travel_date >= azi (informativ)
      - total_km, total_spent_ron, total_saved_ron: pentru calatoriile validate
      - co2_saved_kg + trees_equivalent: pentru calatoriile validate
      - top_trains, monthly, achievements: bazate pe calatorii validate
    """
    user_id = _current_user_id(authorization, db)

    tickets = db.execute(
        text("""
            SELECT
                t.ticket_id, t.train_id, t.travel_date, t.price,
                t.discount_applied, t.ticket_status, t.purchase_time,
                tr.train_number, tr.train_type,
                r.total_distance_km
            FROM tickets t
            LEFT JOIN trains tr ON tr.train_id = t.train_id
            LEFT JOIN routes r ON r.route_id = tr.route_id
            WHERE t.user_id = :uid
              AND t.ticket_status != 'rescheduled'
            ORDER BY t.travel_date DESC
        """),
        {"uid": user_id},
    ).mappings().all()

    if not tickets:
        return {
            "total_trips": 0, "completed_trips": 0, "upcoming_trips": 0,
            "total_km": 0, "total_spent_ron": 0, "total_saved_ron": 0,
            "co2_saved_kg": 0, "trees_equivalent": 0,
            "top_trains": [], "monthly": [], "achievements": [],
        }

    # Calatorii efective: doar bilete cu ticket_status='used' (validate de
    # conductor in tren). 'active' = cumparat dar nu validat inca, 'cancelled'
    # = anulat. NU contam decat ce s-a intamplat real.
    completed = [t for t in tickets if t["ticket_status"] == "used"]
    # Bilete active in viitor (afisare informativa, neinclusa in stats)
    from datetime import date as _date_today
    _today = _date_today.today()
    upcoming = [
        t for t in tickets
        if t["ticket_status"] == "active" and t["travel_date"] and t["travel_date"] >= _today
    ]
    total_km = 0.0
    total_spent = 0.0
    total_saved = 0.0

    from collections import Counter
    train_counts: dict = {}
    monthly_counter: Counter = Counter()

    for t in completed:
        km = float(t["total_distance_km"] or 0)
        total_km += km

        price = float(t["price"] or 0)
        total_spent += price

        discount_pct = float(t["discount_applied"] or 0)
        if discount_pct > 0:
            if discount_pct >= 100:
                total_saved += 50.0  # estimare tarif intreg pt bilete gratuite abonament
            else:
                full_price = price / (1 - discount_pct / 100)
                total_saved += (full_price - price)

        tn = t["train_number"] or f"Tren {t['train_id']}"
        if tn not in train_counts:
            train_counts[tn] = {
                "train_number": tn,
                "train_type": t["train_type"] or "regio",
                "count": 0,
            }
        train_counts[tn]["count"] += 1

        if t["travel_date"]:
            key = t["travel_date"].strftime("%Y-%m")
            monthly_counter[key] += 1

    top_trains = sorted(train_counts.values(), key=lambda x: x["count"], reverse=True)[:5]

    from datetime import date as _date
    today = _date.today()
    monthly_list = []
    for i in range(5, -1, -1):
        y = today.year
        m = today.month - i
        while m <= 0:
            m += 12
            y -= 1
        key = f"{y:04d}-{m:02d}"
        monthly_list.append({
            "month": key,
            "label": _month_label_ro(m, y),
            "count": monthly_counter.get(key, 0),
        })

    # CO2 vs masina (120g/km/pasager)
    co2_kg = round(total_km * 0.12, 1)
    trees = round(co2_kg / 21, 1) if co2_kg > 0 else 0

    achievements = []
    if len(completed) >= 1:
        achievements.append({"code": "first_trip", "label": "Prima calatorie",
                             "description": "Ai facut prima ta calatorie cu trenul!", "icon": "trophy"})
    if len(completed) >= 10:
        achievements.append({"code": "frequent_traveler", "label": "Calator frecvent",
                             "description": "10+ calatorii efectuate", "icon": "star"})
    if len(completed) >= 50:
        achievements.append({"code": "veteran", "label": "Veteran feroviar",
                             "description": "50+ calatorii efectuate", "icon": "medal"})
    if total_km >= 1000:
        achievements.append({"code": "km_1000", "label": "1000km parcursi",
                             "description": f"Ai parcurs {int(total_km)}km cu trenul", "icon": "road"})
    if total_km >= 5000:
        achievements.append({"code": "km_5000", "label": "Globe-trotter",
                             "description": "5000km+ parcursi", "icon": "globe"})
    if co2_kg >= 100:
        achievements.append({"code": "eco_warrior", "label": "Eco-warrior",
                             "description": f"{co2_kg}kg CO2 economisit", "icon": "leaf"})
    if total_saved >= 500:
        achievements.append({"code": "saver", "label": "Economist",
                             "description": f"Ai economisit {int(total_saved)} RON cu reducerile",
                             "icon": "wallet"})

    # total_trips = bilete platite care nu au fost anulate/refundate
    # (active + used + expired). Exclude cancelled/refunded = user-ul a renuntat,
    # nu ar trebui sa conteze ca "bilet cumparat".
    meaningful = [t for t in tickets if t["ticket_status"] not in ("cancelled", "refunded")]

    return {
        "total_trips": len(meaningful),
        "completed_trips": len(completed),
        "upcoming_trips": len(upcoming),
        "total_km": round(total_km, 1),
        "total_spent_ron": round(total_spent, 2),
        "total_saved_ron": round(total_saved, 2),
        "co2_saved_kg": co2_kg,
        "trees_equivalent": trees,
        "top_trains": top_trains,
        "monthly": monthly_list,
        "achievements": achievements,
    }


_MONTH_RO = ["", "Ian", "Feb", "Mar", "Apr", "Mai", "Iun",
             "Iul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _month_label_ro(month: int, year: int) -> str:
    return f"{_MONTH_RO[month]} {year}"

