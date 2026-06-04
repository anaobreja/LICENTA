from datetime import datetime, timedelta, timezone, date
import secrets
import base64
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
import qrcode
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.uploads import save_uploaded_image
from app.core.security import decode_token
from app.core.roles import (
    ROLE_PASSENGER,
    ROLE_TRAIN_VERIFIER,
    ROLE_UNIVERSITY_AGENT,
    has_role,
    normalize_role,
)

router = APIRouter(tags=["identity"])


def _academic_year_end() -> datetime:
    """Returnează 30 septembrie al sfârșitului anului universitar curent.
    An universitar: 1 oct → 30 sep.
    Dacă suntem în oct-dec, noul an a început → end = sep următor.
    """
    today = date.today()
    year = today.year + 1 if today.month >= 10 else today.year
    return datetime(year, 9, 30, 23, 59, 59, tzinfo=timezone.utc)


def _renewal_open() -> bool:
    """Reînnoirea e deschisă din 1 august până la expirarea credențialelor."""
    today = date.today()
    year_end = _academic_year_end().year
    # Fereastra: 1 august → 30 septembrie al anului de expirare
    return today >= date(year_end, 8, 1)

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads" / "documents"
PROFILE_UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads" / "profiles"

# ---------------------------------------------------------------------------
# OCR / MRZ helpers
# ---------------------------------------------------------------------------

_ocr_reader = None


def _get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        try:
            import easyocr  # noqa: PLC0415
            _ocr_reader = easyocr.Reader(["ro", "en"], gpu=False, verbose=False)
        except ImportError:
            raise HTTPException(
                status_code=503,
                detail="easyocr nu este instalat. Ruleaza: pip install easyocr",
            )
    return _ocr_reader


def _parse_mrz(texts: list[str]) -> dict | None:
    """
    Extrage date din zona MRZ a CI-ului romanesc.

    Suporta:
    - TD2 (2 linii x 36 caractere) — formatul CI romanesc actual
    - TD1 (3 linii x 30 caractere) — format mai vechi / alte tari

    Strategia principala: cauta tipare MRZ cu regex in textul concatenat
    al tuturor detectiilor OCR (robust la fragmentare easyocr).
    """
    import re  # noqa: PLC0415

    # Curata fiecare text de caractere non-MRZ si concateneaza totul
    all_mrz = "".join(re.sub(r"[^A-Z0-9<]", "", t.upper()) for t in texts)

    # ----------------------------------------------------------------
    # Strategie 1: TD2 cu regex pe textul concatenat
    # Linia 1 (CI roman): I[D<]ROU + nume (<<) + padding <
    # Linia 2: numar_doc + check + ROU + YYMMDD + check + M/F + YYMMDD + check + ...
    # ----------------------------------------------------------------
    name_m = re.search(r'I[D<]ROU([A-Z<]{15,35})', all_mrz)
    data_m = re.search(
        r'([A-Z]{1,3}\d{4,8}[<\d])(\d)ROU(\d{6})(\d)(M|F)(\d{6})(\d)',
        all_mrz,
    )

    if name_m and data_m:
        name_raw = name_m.group(1).rstrip("<")
        parts = name_raw.split("<<")
        surname = parts[0].replace("<", " ").strip().title()
        given_names = parts[1].replace("<", " ").strip().title() if len(parts) > 1 else ""

        doc_number_raw = data_m.group(1).replace("<", "").strip()
        dob_str = data_m.group(3)
        sex_char = data_m.group(5)

        try:
            yy, mm, dd = int(dob_str[:2]), int(dob_str[2:4]), int(dob_str[4:6])
            year = 2000 + yy if yy < 30 else 1900 + yy
            date_of_birth = f"{year:04d}-{mm:02d}-{dd:02d}"
        except ValueError:
            date_of_birth = None

        return {
            "surname": surname,
            "given_names": given_names,
            "date_of_birth": date_of_birth,
            "sex": "M" if sex_char == "M" else "F",
            "document_number": doc_number_raw,
        }

    # ----------------------------------------------------------------
    # Strategie 2: linii individuale lungi (TD2 sau TD1)
    # ----------------------------------------------------------------
    mrz_lines: list[str] = []
    for raw in texts:
        clean = re.sub(r"[^A-Z0-9<]", "", raw.upper())
        if 28 <= len(clean) <= 42:          # TD1≈30, TD2≈36
            mrz_lines.append(clean)

    # TD2: 2 linii
    for i in range(len(mrz_lines) - 1):
        l1, l2 = mrz_lines[i], mrz_lines[i + 1]

        # Linia 1 incepe cu I?ROU si contine <<
        if not re.match(r'I.{0,2}ROU', l1) or "<<" not in l1:
            continue
        # Linia 2 contine ROU si M sau F
        if "ROU" not in l2 or not re.search(r'(M|F)', l2):
            continue

        name_raw = l1[5:].rstrip("<")
        parts = name_raw.split("<<")
        surname = parts[0].replace("<", " ").strip().title()
        given_names = parts[1].replace("<", " ").strip().title() if len(parts) > 1 else ""

        doc_number = l2[:9].replace("<", "").strip()

        rou_idx = l2.find("ROU")
        dob_str = l2[rou_idx + 3: rou_idx + 9] if rou_idx != -1 else ""
        try:
            yy, mm, dd = int(dob_str[:2]), int(dob_str[2:4]), int(dob_str[4:6])
            year = 2000 + yy if yy < 30 else 1900 + yy
            date_of_birth = f"{year:04d}-{mm:02d}-{dd:02d}"
        except (ValueError, IndexError):
            date_of_birth = None

        sex_idx = rou_idx + 10 if rou_idx != -1 else -1
        sex_char = l2[sex_idx] if 0 <= sex_idx < len(l2) else ""
        sex = "M" if sex_char == "M" else ("F" if sex_char == "F" else "")

        return {
            "surname": surname,
            "given_names": given_names,
            "date_of_birth": date_of_birth,
            "sex": sex,
            "document_number": doc_number,
        }

    # TD1: 3 linii
    for i in range(len(mrz_lines) - 2):
        l1, l2, l3 = mrz_lines[i], mrz_lines[i + 1], mrz_lines[i + 2]
        if "<<" not in l3:
            continue
        if not re.match(r"\d{6}", l2[:6]):
            continue

        name_raw = l3.rstrip("<")
        parts = name_raw.split("<<")
        surname = parts[0].replace("<", " ").strip().title()
        given_names = parts[1].replace("<", " ").strip().title() if len(parts) > 1 else ""

        dob_str = l2[:6]
        try:
            yy, mm, dd = int(dob_str[:2]), int(dob_str[2:4]), int(dob_str[4:6])
            year = 2000 + yy if yy < 30 else 1900 + yy
            date_of_birth = f"{year:04d}-{mm:02d}-{dd:02d}"
        except ValueError:
            date_of_birth = None

        td1_doc_number = l1[5:14].replace("<", "").strip()
        td1_sex = "M" if (len(l2) > 7 and l2[7] == "M") else "F"
        return {
            "surname": surname,
            "given_names": given_names,
            "date_of_birth": date_of_birth,
            "sex": td1_sex,
            "document_number": td1_doc_number,
        }

    return None
MAX_PHOTO_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


class DocumentCreateRequest(BaseModel):
    document_type: str = Field(min_length=2, max_length=50)
    document_number_masked: str = Field(min_length=4, max_length=64)


class ReviewRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=1000)


class CardPresentationCreateRequest(BaseModel):
    ttl_seconds: int = Field(default=180, ge=30, le=600)


class VerifyCardPresentationRequest(BaseModel):
    token: str = Field(min_length=10, max_length=255)


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


def _current_user(authorization: str | None, db: Session):
    token = _extract_bearer_token(authorization)
    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub", "0"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    row = db.execute(
        text(
            """
            SELECT user_id, first_name, last_name, email, role, is_active
            FROM users
            WHERE user_id = :user_id
            """
        ),
        {"user_id": user_id},
    ).mappings().first()

    if not row or not row["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user = dict(row)
    user["role"] = normalize_role(user["role"])
    return user


def _require_role(user: dict, expected_role: str):
    if not has_role(user.get("role"), expected_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{expected_role} access required",
        )


# DDL is loaded from database/schema.sql at PostgreSQL container startup.
# No runtime CREATE TABLE — the schema is the single source of truth.


def _ensure_default_issuer(db: Session) -> int:
    row = db.execute(
        text(
            """
            SELECT id FROM issuers
            WHERE name = 'Railway Digital Identity Authority'
            LIMIT 1
            """
        )
    ).mappings().first()

    if row:
        return row["id"]

    created = db.execute(
        text(
            """
            INSERT INTO issuers (name, issuer_type, is_active)
            VALUES ('Railway Digital Identity Authority', 'transport', true)
            RETURNING id
            """
        )
    ).mappings().first()
    db.commit()
    return created["id"]


def _issue_card_if_missing(db: Session, user_id: int):
    existing = db.execute(
        text("SELECT id FROM digital_cards WHERE user_id = :user_id"),
        {"user_id": user_id},
    ).mappings().first()

    if existing:
        return

    issuer_id = _ensure_default_issuer(db)
    card_identifier = f"RDC-{secrets.token_hex(6).upper()}"

    db.execute(
        text(
            """
            INSERT INTO digital_cards (user_id, issuer_id, card_identifier, status, valid_until)
            VALUES (:user_id, :issuer_id, :card_identifier, 'active', :valid_until)
            """
        ),
        {
            "user_id": user_id,
            "issuer_id": issuer_id,
            "card_identifier": card_identifier,
            "valid_until": _academic_year_end(),
        },
    )
    db.commit()


def _credential_type_from_document(document_type: str) -> str:
    document_type = (document_type or "").lower()
    if document_type == "identity_card":
        return "identity_verified"
    if document_type in ("student_id", "student_card"):
        return "student_verified"
    if document_type in ("school_id", "elev_card"):
        return "elev_verified"
    return "identity_verified"


def _normalize_user_credentials_state(db: Session, user_id: int):
    # Expire credentials that passed their validity date.
    db.execute(
        text(
            """
            UPDATE user_credentials
            SET status = 'expired'
            WHERE user_id = :user_id
              AND status = 'active'
              AND valid_until < CURRENT_TIMESTAMP
            """
        ),
        {"user_id": user_id},
    )

    # Keep only the latest active credential per credential_type for this user.
    db.execute(
        text(
            """
            WITH ranked AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY credential_type
                           ORDER BY issued_at DESC, id DESC
                       ) AS rn
                FROM user_credentials
                WHERE user_id = :user_id
                  AND status = 'active'
                  AND valid_until >= CURRENT_TIMESTAMP
            )
            UPDATE user_credentials
            SET status = 'expired'
            WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
            """
        ),
        {"user_id": user_id},
    )


def _save_uploaded_document_photo(photo: UploadFile) -> str:
    return save_uploaded_image(photo, UPLOAD_DIR, prefix="doc")


def _save_uploaded_profile_photo(photo: UploadFile) -> str:
    return save_uploaded_image(photo, PROFILE_UPLOAD_DIR, prefix="profile")


def _upload_has_file(photo: UploadFile | None) -> bool:
    return bool(photo and photo.filename)


def _build_qr_data_url(token_value: str) -> str:
    qr = qrcode.QRCode(border=2, box_size=8)
    qr.add_data(token_value)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    try:
        img.save(buffer, format="PNG")
    except TypeError:
        # qrcode can return PyPNGImage, whose save() does not accept format.
        img.save(buffer)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _as_naive_datetime(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            return parsed.replace(tzinfo=None)
        except ValueError:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return value


def _insert_source_document(
    db: Session,
    user_id: int,
    document_type: str,
    document_number_masked: str,
    document_image_path: str | None,
    document_image_path_verso: str | None = None,
    university_name: str | None = None,
    year_of_study: int | None = None,
    ci_number: str | None = None,
    ci_name: str | None = None,
    ci_date_of_birth: str | None = None,
    ci_sex: str | None = None,
    ci_address: str | None = None,
):
    row = db.execute(
        text(
            """
            INSERT INTO source_documents
                (user_id, document_type, document_number_masked, document_image_path,
                 document_image_path_verso, status, university_name, year_of_study,
                 ci_number, ci_name, ci_date_of_birth, ci_sex, ci_address)
            VALUES
                (:user_id, :document_type, :document_number_masked, :document_image_path,
                 :document_image_path_verso, 'pending', :university_name, :year_of_study,
                 :ci_number, :ci_name, :ci_date_of_birth, :ci_sex, :ci_address)
            RETURNING id, user_id, document_type, document_number_masked, document_image_path,
                      document_image_path_verso, status, uploaded_at, university_name, year_of_study,
                      ci_number, ci_name, ci_date_of_birth, ci_sex, ci_address
            """
        ),
        {
            "user_id": user_id,
            "document_type": document_type,
            "document_number_masked": document_number_masked,
            "document_image_path": document_image_path,
            "document_image_path_verso": document_image_path_verso,
            "university_name": university_name or None,
            "year_of_study": year_of_study or None,
            "ci_number": ci_number or None,
            "ci_name": ci_name or None,
            "ci_date_of_birth": ci_date_of_birth or None,
            "ci_sex": ci_sex or None,
            "ci_address": ci_address or None,
        },
    ).mappings().first()
    return dict(row)


def _user_has_pending_documents(db: Session, user_id: int) -> bool:
    row = db.execute(
        text(
            """
            SELECT 1
            FROM source_documents
            WHERE user_id = :user_id AND status = 'pending'
            LIMIT 1
            """
        ),
        {"user_id": user_id},
    ).mappings().first()
    return row is not None


def _calculate_age(dob_str: str) -> int | None:
    try:
        from datetime import date
        dob = date.fromisoformat(dob_str.strip())
        today = date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except Exception:
        return None


def _user_has_active_credentials(db: Session, user_id: int) -> bool:
    credential_row = db.execute(
        text(
            """
            SELECT 1
            FROM user_credentials
            WHERE user_id = :user_id AND status = 'active'
            LIMIT 1
            """
        ),
        {"user_id": user_id},
    ).mappings().first()

    if credential_row:
        return True

    card_row = db.execute(
        text(
            """
            SELECT 1
            FROM digital_cards
            WHERE user_id = :user_id AND status = 'active'
            LIMIT 1
            """
        ),
        {"user_id": user_id},
    ).mappings().first()
    return card_row is not None


def _document_type_label(document_type: str) -> str:
    labels = {
        "identity_card": "carte de identitate",
        "student_card": "legitimatie student",
        "elev_card": "carnet de elev",
    }
    return labels.get(document_type, document_type)


def _create_notification(
    db: Session,
    user_id: int,
    category: str,
    title: str,
    message: str,
):
    db.execute(
        text(
            """
            INSERT INTO notifications (user_id, category, title, message)
            VALUES (:user_id, :category, :title, :message)
            """
        ),
        {
            "user_id": user_id,
            "category": category,
            "title": title,
            "message": message,
        },
    )


@router.post("/documents/extract-id")
def extract_id_data(
    photo: UploadFile = File(...),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Primeste o poza a cartii de identitate, ruleaza OCR si incearca sa
    extraga datele din zona MRZ (cele 3 randuri de jos).
    Prima apelare descarca modelele easyocr (~800MB) o singura data.
    """
    _current_user(authorization, db)

    if photo.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Format imagine invalid (acceptat: JPG, PNG, WEBP)")

    img_bytes = photo.file.read()
    if not img_bytes:
        raise HTTPException(status_code=400, detail="Fisierul este gol")

    try:
        reader = _get_ocr_reader()
        results = reader.readtext(img_bytes, detail=0, paragraph=False)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Eroare OCR: {exc}") from exc

    mrz = _parse_mrz(results)

    if mrz:
        return {
            "success": True,
            "method": "mrz",
            "data": mrz,
            "raw_texts": results,
        }

    # MRZ nu a fost gasit — returnam textele brute ca sa afisam utilizatorului
    return {
        "success": False,
        "method": "ocr_raw",
        "data": {},
        "raw_texts": results,
        "message": "Zona MRZ nu a fost detectata. Verifica ca imaginea sa includa toata fata CI-ului.",
    }


@router.post("/documents")
def create_document(
    payload: DocumentCreateRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    current = _current_user(authorization, db)
    _require_role(current, ROLE_PASSENGER)

    if _user_has_active_credentials(db, current["user_id"]):
        raise HTTPException(
            status_code=400,
            detail="Ai credentiale active. Nu poti depune o noua cerere.",
        )

    row = db.execute(
        text(
            """
            INSERT INTO source_documents (user_id, document_type, document_number_masked, document_image_path, status)
            VALUES (:user_id, :document_type, :document_number_masked, NULL, 'pending')
            RETURNING id, user_id, document_type, document_number_masked, document_image_path, status, uploaded_at
            """
        ),
        {
            "user_id": current["user_id"],
            "document_type": payload.document_type,
            "document_number_masked": payload.document_number_masked,
        },
    ).mappings().first()

    db.commit()
    return dict(row)


@router.post("/documents/upload")
def create_document_with_photo(
    document_type: str = Form(...),
    document_number_masked: str = Form(...),
    photo: UploadFile = File(...),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    current = _current_user(authorization, db)
    _require_role(current, ROLE_PASSENGER)

    if _user_has_active_credentials(db, current["user_id"]):
        raise HTTPException(
            status_code=400,
            detail="Ai credentiale active. Nu poti depune o noua cerere.",
        )

    image_path = _save_uploaded_document_photo(photo)

    row = db.execute(
        text(
            """
            INSERT INTO source_documents (user_id, document_type, document_number_masked, document_image_path, status)
            VALUES (:user_id, :document_type, :document_number_masked, :document_image_path, 'pending')
            RETURNING id, user_id, document_type, document_number_masked, document_image_path, status, uploaded_at
            """
        ),
        {
            "user_id": current["user_id"],
            "document_type": document_type,
            "document_number_masked": document_number_masked,
            "document_image_path": image_path,
        },
    ).mappings().first()

    db.commit()
    return {
        **dict(row),
        "has_photo": bool(row["document_image_path"]),
    }


@router.post("/documents/validation-request")
def submit_identity_validation_request(
    legitimation_type: str = Form(...),
    legitimation_number_masked: str = Form(...),
    legitimation_photo_front: UploadFile | None = File(default=None),
    legitimation_photo_verso: UploadFile | None = File(default=None),
    profile_photo: UploadFile | None = File(default=None),
    university_name: str = Form(default=""),
    year_of_study: str = Form(default="0"),
    ci_number: str = Form(default=""),
    ci_name: str = Form(default=""),
    ci_date_of_birth: str = Form(default=""),
    ci_sex: str = Form(default=""),
    ci_address: str = Form(default=""),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    current = _current_user(authorization, db)
    _require_role(current, ROLE_PASSENGER)

    legitimation_type = (legitimation_type or "").strip().lower()
    if legitimation_type not in {"student_card"}:
        raise HTTPException(
            status_code=400,
            detail="Tipul de legitimație acceptat este student_card.",
        )

    if ci_date_of_birth and ci_date_of_birth.strip():
        age = _calculate_age(ci_date_of_birth.strip())
        if age is not None and age >= 30:
            raise HTTPException(
                status_code=400,
                detail=f"Nu poți beneficia de reducerea studențească — vârsta ({age} ani) depășește limita de 30 de ani prevăzută de CFR.",
            )

    # Cerere pending existentă (modificare)
    pending_docs = db.execute(
        text(
            """
            SELECT id, document_image_path, document_image_path_verso
            FROM source_documents
            WHERE user_id = :user_id AND status = 'pending'
            ORDER BY uploaded_at DESC
            """
        ),
        {"user_id": current["user_id"]},
    ).mappings().all()

    is_modification = len(pending_docs) > 0
    existing_front: str | None = pending_docs[0].get("document_image_path") if pending_docs else None
    existing_verso: str | None = pending_docs[0].get("document_image_path_verso") if pending_docs else None

    # Document aprobat anterior → reînnoire anuală
    approved_doc = db.execute(
        text(
            """
            SELECT id, ci_number, ci_name, ci_date_of_birth, ci_sex, ci_address
            FROM source_documents
            WHERE user_id = :user_id AND status = 'approved'
            ORDER BY uploaded_at DESC
            LIMIT 1
            """
        ),
        {"user_id": current["user_id"]},
    ).mappings().first()

    is_renewal = approved_doc is not None

    # Prima cerere: blocare dacă are deja credențiale active
    if not is_renewal and not is_modification and _user_has_active_credentials(db, current["user_id"]):
        raise HTTPException(
            status_code=400,
            detail="Ai credentiale active. Nu poti depune o noua cerere initiala.",
        )

    # Reînnoire: verifică fereastra de timp (disponibilă din 1 august)
    if is_renewal and not is_modification:
        has_active = _user_has_active_credentials(db, current["user_id"])
        if has_active and not _renewal_open():
            year_end = _academic_year_end().year
            raise HTTPException(
                status_code=400,
                detail=f"Reînnoirea va fi disponibilă începând cu 1 august {year_end}.",
            )

    # La reînnoire: preia automat datele CI din cererea aprobată anterior
    if is_renewal and approved_doc:
        ci_number = ci_number or approved_doc.get("ci_number") or ""
        ci_name = ci_name or approved_doc.get("ci_name") or ""
        ci_date_of_birth = ci_date_of_birth or approved_doc.get("ci_date_of_birth") or ""
        ci_sex = ci_sex or approved_doc.get("ci_sex") or ""
        ci_address = ci_address or approved_doc.get("ci_address") or ""

    # Poză de profil
    user_profile_row = db.execute(
        text("SELECT profile_photo_path FROM users WHERE user_id = :uid"),
        {"uid": current["user_id"]},
    ).mappings().first()
    has_profile = bool(user_profile_row and user_profile_row.get("profile_photo_path"))

    if _upload_has_file(profile_photo):
        new_profile_path = _save_uploaded_profile_photo(profile_photo)
        db.execute(
            text(
                """
                UPDATE users
                SET profile_photo_path = :path, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = :user_id
                """
            ),
            {"path": new_profile_path, "user_id": current["user_id"]},
        )
        has_profile = True
    elif not has_profile and not is_renewal and not is_modification:
        raise HTTPException(
            status_code=400,
            detail="Incarca fotografia de profil (obligatorie la prima cerere).",
        )

    if _upload_has_file(legitimation_photo_front):
        legitimation_front_path = _save_uploaded_document_photo(legitimation_photo_front)
    else:
        legitimation_front_path = existing_front

    if _upload_has_file(legitimation_photo_verso):
        legitimation_verso_path = _save_uploaded_document_photo(legitimation_photo_verso)
    else:
        legitimation_verso_path = existing_verso

    if not legitimation_front_path or not legitimation_verso_path:
        raise HTTPException(
            status_code=400,
            detail="Incarca ambele poze ale legitimatiei: fata si verso (verso = semnatura).",
        )

    if pending_docs:
        for doc_row in pending_docs:
            db.execute(
                text("DELETE FROM source_documents WHERE id = :document_id"),
                {"document_id": doc_row["id"]},
            )

    try:
        _safe_year = int(year_of_study)
        if not (1 <= _safe_year <= 6):
            _safe_year = None
    except (ValueError, TypeError):
        _safe_year = None

    legitimation_doc = _insert_source_document(
        db=db,
        user_id=current["user_id"],
        document_type=legitimation_type,
        document_number_masked=legitimation_number_masked,
        document_image_path=legitimation_front_path,
        document_image_path_verso=legitimation_verso_path,
        university_name=university_name.strip() or None,
        year_of_study=_safe_year,
        ci_number=ci_number.strip() or None,
        ci_name=ci_name.strip() or None,
        ci_date_of_birth=ci_date_of_birth.strip() or None,
        ci_sex=ci_sex.strip() or None,
        ci_address=ci_address.strip() or None,
    )

    db.commit()

    return {
        "message": (
            "Cererea de validare a fost modificata si retrimisa catre issuer"
            if is_modification
            else "Cererea de validare a fost trimisa catre issuer"
        ),
        "is_modification": is_modification,
        "documents": [
            {
                **legitimation_doc,
                "has_photo": bool(legitimation_doc.get("document_image_path")),
                "has_photo_verso": bool(legitimation_doc.get("document_image_path_verso")),
            },
        ],
    }


@router.get("/documents/{document_id}/photo")
def get_document_photo(
    document_id: int,
    side: str = "front",
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    current = _current_user(authorization, db)

    row = db.execute(
        text(
            """
            SELECT sd.id, sd.user_id, sd.document_image_path, sd.document_image_path_verso,
                   u.university_name AS owner_university
            FROM source_documents sd
            JOIN users u ON u.user_id = sd.user_id
            WHERE sd.id = :document_id
            """
        ),
        {"document_id": document_id},
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    # AUTHORIZATION FIX: only owner and same-university agents can access
    agent_university = current.get("university_name")
    can_access = (
        current["user_id"] == row["user_id"]  # Owner can access own documents
        or (has_role(current.get("role"), ROLE_UNIVERSITY_AGENT) and 
            agent_university == row["owner_university"])  # Agent only from same university
    )
    if not can_access:
        raise HTTPException(status_code=403, detail="Access denied")

    side_norm = (side or "front").strip().lower()
    if side_norm == "verso":
        image_path = row.get("document_image_path_verso")
    else:
        image_path = row.get("document_image_path")

    if not image_path:
        raise HTTPException(status_code=404, detail="No photo uploaded for this side")

    file_path = Path(image_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Photo file not found")

    return FileResponse(path=file_path)


@router.get("/documents/me")
def list_my_documents(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    current = _current_user(authorization, db)
    _require_role(current, ROLE_PASSENGER)

    rows = db.execute(
        text(
            """
            SELECT id, document_type, document_number_masked, document_image_path,
                   document_image_path_verso, status, uploaded_at, university_name, year_of_study,
                   ci_number, ci_name, ci_date_of_birth, ci_sex, ci_address
            FROM source_documents
            WHERE user_id = :user_id
            ORDER BY uploaded_at DESC
            """
        ),
        {"user_id": current["user_id"]},
    ).mappings().all()

    return [
        {
            **dict(r),
            "has_photo": bool(r["document_image_path"]),
            "has_photo_verso": bool(r.get("document_image_path_verso")),
        }
        for r in rows
    ]


@router.get("/credentials/me")
def list_my_credentials(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    current = _current_user(authorization, db)
    _require_role(current, ROLE_PASSENGER)

    _normalize_user_credentials_state(db, current["user_id"])
    db.commit()

    rows = db.execute(
        text(
            """
            SELECT id, credential_type, claim_value, status, issued_at, valid_until
            FROM user_credentials
            WHERE user_id = :user_id
            ORDER BY issued_at DESC
            """
        ),
        {"user_id": current["user_id"]},
    ).mappings().all()

    return [dict(r) for r in rows]


@router.get("/notifications/me")
def list_my_notifications(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    current = _current_user(authorization, db)
    _require_role(current, ROLE_PASSENGER)

    rows = db.execute(
        text(
            """
            SELECT id, category, title, message, is_read, created_at
            FROM notifications
            WHERE user_id = :user_id
            ORDER BY created_at DESC
            """
        ),
        {"user_id": current["user_id"]},
    ).mappings().all()

    return [dict(r) for r in rows]


@router.patch("/notifications/me/{notification_id}/read")
def mark_my_notification_read(
    notification_id: int,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    current = _current_user(authorization, db)
    _require_role(current, ROLE_PASSENGER)

    read_val = True
    exists = db.execute(
        text(
            """
            SELECT id FROM notifications
            WHERE id = :notification_id AND user_id = :user_id
            """
        ),
        {"notification_id": notification_id, "user_id": current["user_id"]},
    ).first()

    if not exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    db.execute(
        text(
            """
            UPDATE notifications
            SET is_read = :read_val
            WHERE id = :notification_id AND user_id = :user_id
            """
        ),
        {
            "read_val": read_val,
            "notification_id": notification_id,
            "user_id": current["user_id"],
        },
    )

    db.commit()
    return {"id": notification_id, "is_read": True}


@router.get("/card/me")
def get_my_card(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    current = _current_user(authorization, db)
    _require_role(current, ROLE_PASSENGER)

    card = db.execute(
        text(
            """
            SELECT dc.id, dc.card_identifier, dc.status, dc.issued_at, dc.valid_until,
                   i.name AS issuer_name
            FROM digital_cards dc
            JOIN issuers i ON i.id = dc.issuer_id
            WHERE dc.user_id = :user_id
            LIMIT 1
            """
        ),
        {"user_id": current["user_id"]},
    ).mappings().first()

    if not card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No digital card issued yet. Wait for issuer approval.",
        )

    claims = db.execute(
        text(
            """
            SELECT credential_type, claim_value, valid_until
            FROM user_credentials
            WHERE user_id = :user_id AND status = 'active' AND valid_until >= CURRENT_TIMESTAMP
            ORDER BY credential_type
            """
        ),
        {"user_id": current["user_id"]},
    ).mappings().all()

    return {
        "card": {
            "id": card["id"],
            "card_identifier": card["card_identifier"],
            "status": card["status"],
            "issued_at": card["issued_at"],
            "valid_until": card["valid_until"],
            "issuer_name": card["issuer_name"],
            "holder_name": f"{current['first_name']} {current['last_name']}",
        },
        "claims": [dict(c) for c in claims],
    }


@router.post("/card/present")
def present_card(
    payload: CardPresentationCreateRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    current = _current_user(authorization, db)
    _require_role(current, ROLE_PASSENGER)

    card = db.execute(
        text(
            """
            SELECT id, status, valid_until
            FROM digital_cards
            WHERE user_id = :user_id
            LIMIT 1
            """
        ),
        {"user_id": current["user_id"]},
    ).mappings().first()

    if not card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No digital card found. Wait for issuer approval.",
        )

    if card["status"] != "active":
        raise HTTPException(status_code=400, detail="Card is not active")

    if datetime.now(timezone.utc).replace(tzinfo=None) > _as_naive_datetime(card["valid_until"]):
        raise HTTPException(status_code=400, detail="Card expired")

    token = f"card_{secrets.token_urlsafe(24)}"
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=payload.ttl_seconds)

    row = db.execute(
        text(
            """
            INSERT INTO card_presentations (card_id, token_value, expires_at, status)
            VALUES (:card_id, :token_value, :expires_at, 'active')
            RETURNING id, token_value, issued_at, expires_at, status
            """
        ),
        {
            "card_id": card["id"],
            "token_value": token,
            "expires_at": expires_at,
        },
    ).mappings().first()

    db.commit()
    response = dict(row)
    response["qr_data_url"] = _build_qr_data_url(response["token_value"])
    return response


@router.get("/issuer/documents/pending")
def issuer_pending_documents(
    year_of_study: int | None = None,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    current = _current_user(authorization, db)

    is_agent = has_role(current.get("role"), ROLE_UNIVERSITY_AGENT)
    is_issuer = has_role(current.get("role"), ROLE_UNIVERSITY_AGENT)
    if not is_agent and not is_issuer:
        raise HTTPException(status_code=403, detail="Acces interzis")

    # university_agent vede doar cererile universității sale
    agent_university_id: int | None = None
    if is_agent:
        row = db.execute(
            text("SELECT university_id FROM users WHERE user_id = :uid"),
            {"uid": current["user_id"]},
        ).first()
        agent_university_id = row[0] if row else None

    query = """
        SELECT d.id, d.user_id, u.first_name, u.last_name, u.email,
               d.document_type, d.document_number_masked, d.document_image_path,
               d.document_image_path_verso, d.uploaded_at, d.university_name, d.year_of_study,
               d.ci_number, d.ci_name, d.ci_date_of_birth, d.ci_sex, d.ci_address,
               u.profile_photo_path
        FROM source_documents d
        JOIN users u ON u.user_id = d.user_id
        WHERE d.status = 'pending'
    """
    params: dict = {}
    if agent_university_id:
        query += " AND d.university_name = (SELECT name FROM universities WHERE university_id = :univ_id)"
        params["univ_id"] = agent_university_id
    if year_of_study is not None:
        query += " AND d.year_of_study = :year_of_study"
        params["year_of_study"] = year_of_study

    query += " ORDER BY d.year_of_study ASC NULLS LAST, d.uploaded_at ASC"

    rows = db.execute(text(query), params).mappings().all()

    return [
        {
            **dict(r),
            "has_photo": bool(r["document_image_path"]),
            "has_photo_verso": bool(r.get("document_image_path_verso")),
            "has_profile_photo": bool(r.get("profile_photo_path")),
        }
        for r in rows
    ]


@router.get("/university/stats")
def university_stats(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    current = _current_user(authorization, db)

    is_agent = has_role(current.get("role"), ROLE_UNIVERSITY_AGENT)
    is_issuer = has_role(current.get("role"), ROLE_UNIVERSITY_AGENT)
    if not is_agent and not is_issuer:
        raise HTTPException(status_code=403, detail="Acces interzis")

    # Filtru universitate pentru agenti
    univ_filter = ""
    params: dict = {}
    if is_agent:
        row = db.execute(
            text("SELECT university_id, name FROM universities WHERE university_id = (SELECT university_id FROM users WHERE user_id = :uid)"),
            {"uid": current["user_id"]},
        ).first()
        if row:
            univ_filter = " AND d.university_name = :univ_name"
            params["univ_name"] = row[1]

    # Totale per status
    totals = db.execute(text(f"""
        SELECT
            COUNT(CASE WHEN d.status='pending' THEN 1 END)  AS pending,
            COUNT(CASE WHEN d.status='approved' THEN 1 END) AS approved,
            COUNT(CASE WHEN d.status='rejected' THEN 1 END) AS rejected
        FROM source_documents d
        WHERE 1=1 {univ_filter}
    """), params).mappings().first()

    # Distributie pe an de studiu
    year_rows = db.execute(text(f"""
        SELECT d.year_of_study, COUNT(*) AS total
        FROM source_documents d
        WHERE d.year_of_study IS NOT NULL {univ_filter}
        GROUP BY d.year_of_study
        ORDER BY d.year_of_study
    """), params).mappings().all()

    year_labels = {1:"Licență 1",2:"Licență 2",3:"Licență 3",4:"Licență 4",5:"Master 1",6:"Master 2"}
    year_dist = [
        {"name": year_labels.get(r["year_of_study"], f"Anul {r['year_of_study']}"), "value": r["total"]}
        for r in year_rows
    ]

    # Activitate ultimele 30 zile (aprobate + respinse pe zi)
    activity_rows = db.execute(text(f"""
        SELECT
            DATE(d.uploaded_at) AS day,
            COUNT(CASE WHEN d.status='approved' THEN 1 END) AS approved,
            COUNT(CASE WHEN d.status='rejected' THEN 1 END) AS rejected,
            COUNT(CASE WHEN d.status='pending'  THEN 1 END) AS pending
        FROM source_documents d
        WHERE d.uploaded_at >= DATE('now', '-30 days') {univ_filter}
        GROUP BY DATE(d.uploaded_at)
        ORDER BY day ASC
    """), params).mappings().all()

    activity = [dict(r) for r in activity_rows]

    return {
        "totals": dict(totals) if totals else {"pending": 0, "approved": 0, "rejected": 0},
        "year_distribution": year_dist,
        "activity": activity,
    }


@router.get("/issuer/documents/{document_id}")
def issuer_document_details(
    document_id: int,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    current = _current_user(authorization, db)
    _require_role(current, ROLE_UNIVERSITY_AGENT)

    row = db.execute(
        text(
            """
            SELECT d.id, d.user_id, u.first_name, u.last_name, u.email,
                   d.document_type, d.document_number_masked, d.document_image_path, d.status, d.uploaded_at
            FROM source_documents d
            JOIN users u ON u.user_id = d.user_id
            WHERE d.id = :document_id
            """
        ),
        {"document_id": document_id},
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        **dict(row),
        "has_photo": bool(row["document_image_path"]),
    }


@router.post("/issuer/documents/{document_id}/approve")
def issuer_approve_document(
    document_id: int,
    payload: ReviewRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    reviewer = _current_user(authorization, db)
    if not has_role(reviewer.get("role"), ROLE_UNIVERSITY_AGENT):
        raise HTTPException(status_code=403, detail="Acces interzis")

    doc = db.execute(
        text("SELECT id, user_id, document_type, status, university_name FROM source_documents WHERE id = :id"),
        {"id": document_id},
    ).mappings().first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc["status"] != "pending":
        raise HTTPException(status_code=400, detail="Document is not pending")

    # Cross-university check: agent can only approve documents from their own university
    agent_univ_row = db.execute(
        text("SELECT name FROM universities WHERE university_id = (SELECT university_id FROM users WHERE user_id = :uid)"),
        {"uid": reviewer["user_id"]},
    ).first()
    if agent_univ_row:
        agent_univ_name = agent_univ_row[0]
        if doc.get("university_name") != agent_univ_name:
            raise HTTPException(status_code=403, detail="Nu poți aproba documente de la altă universitate")

    credential_type = _credential_type_from_document(doc["document_type"])
    active_same_type = db.execute(
        text(
            """
            SELECT id
            FROM user_credentials
            WHERE user_id = :user_id
              AND credential_type = :credential_type
              AND status = 'active'
              AND valid_until >= CURRENT_TIMESTAMP
            LIMIT 1
            """
        ),
        {
            "user_id": doc["user_id"],
            "credential_type": credential_type,
        },
    ).first()

    if active_same_type:
        raise HTTPException(
            status_code=400,
            detail="Exista deja un document aprobat activ pentru acest tip. Poate fi aprobat altul doar dupa expirare.",
        )

    db.execute(
        text("UPDATE source_documents SET status = 'approved' WHERE id = :id"),
        {"id": document_id},
    )

    db.execute(
        text(
            """
            INSERT INTO document_reviews (document_id, reviewer_id, decision, notes)
            VALUES (:document_id, :reviewer_id, 'approved', :notes)
            """
        ),
        {
            "document_id": document_id,
            "reviewer_id": reviewer["user_id"],
            "notes": payload.notes,
        },
    )

    # Expire only prior credentials of the same type (CI + student/elev can coexist).
    db.execute(
        text(
            """
            UPDATE user_credentials
            SET status = 'expired'
            WHERE user_id = :user_id
              AND status = 'active'
              AND credential_type = :credential_type
            """
        ),
        {
            "user_id": doc["user_id"],
            "credential_type": credential_type,
        },
    )

    # Resolve issuer_id: agentii universitari au users.issuer_id setat catre universitatea lor;
    # fallback la "Railway Digital Identity Authority" daca lipseste.
    issuer_row = db.execute(
        text("SELECT issuer_id FROM users WHERE user_id = :uid"),
        {"uid": reviewer["user_id"]},
    ).first()
    credential_issuer_id = (
        issuer_row[0] if issuer_row and issuer_row[0] is not None
        else _ensure_default_issuer(db)
    )

    db.execute(
        text(
            """
            INSERT INTO user_credentials (user_id, credential_type, claim_value, issuer_id, status, valid_until)
            VALUES (:user_id, :credential_type, 'true', :issuer_id, 'active', :valid_until)
            """
        ),
        {
            "user_id": doc["user_id"],
            "credential_type": credential_type,
            "issuer_id": credential_issuer_id,
            "valid_until": _academic_year_end(),
        },
    )

    _issue_card_if_missing(db, doc["user_id"])

    doc_label = _document_type_label(doc["document_type"])
    approval_message = f"Cererea ta pentru {doc_label} a fost aprobata."
    _create_notification(
        db,
        user_id=doc["user_id"],
        category="cereri",
        title="Cerere aprobata",
        message=approval_message,
    )

    db.commit()

    return {"status": "approved", "document_id": document_id, "credential_type": credential_type}


@router.post("/issuer/documents/{document_id}/reject")
def issuer_reject_document(
    document_id: int,
    payload: ReviewRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    reviewer = _current_user(authorization, db)
    if not has_role(reviewer.get("role"), ROLE_UNIVERSITY_AGENT):
        raise HTTPException(status_code=403, detail="Acces interzis")

    doc = db.execute(
        text("SELECT id, user_id, document_type, status, university_name FROM source_documents WHERE id = :id"),
        {"id": document_id},
    ).mappings().first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc["status"] != "pending":
        raise HTTPException(status_code=400, detail="Document is not pending")

    # Cross-university check
    agent_univ_row = db.execute(
        text("SELECT name FROM universities WHERE university_id = (SELECT university_id FROM users WHERE user_id = :uid)"),
        {"uid": reviewer["user_id"]},
    ).first()
    if agent_univ_row:
        agent_univ_name = agent_univ_row[0]
        if doc.get("university_name") != agent_univ_name:
            raise HTTPException(status_code=403, detail="Nu poți respinge documente de la altă universitate")

    db.execute(
        text("UPDATE source_documents SET status = 'rejected' WHERE id = :id"),
        {"id": document_id},
    )

    db.execute(
        text(
            """
            INSERT INTO document_reviews (document_id, reviewer_id, decision, notes)
            VALUES (:document_id, :reviewer_id, 'rejected', :notes)
            """
        ),
        {
            "document_id": document_id,
            "reviewer_id": reviewer["user_id"],
            "notes": payload.notes,
        },
    )

    doc_label = _document_type_label(doc["document_type"])
    note_text = (payload.notes or "").strip()
    rejection_message = (
        f"Cererea ta pentru {doc_label} a fost respinsa."
        if not note_text
        else f"Cererea ta pentru {doc_label} a fost respinsa. Motiv: {note_text}"
    )
    _create_notification(
        db,
        user_id=doc["user_id"],
        category="cereri",
        title="Cerere respinsa",
        message=rejection_message,
    )

    db.commit()
    return {"status": "rejected", "document_id": document_id}


@router.get("/issuer/credentials")
def issuer_credentials(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    reviewer = _current_user(authorization, db)
    _require_role(reviewer, ROLE_UNIVERSITY_AGENT)

    rows = db.execute(
        text(
            """
            SELECT c.id, c.user_id, u.first_name, u.last_name, c.credential_type,
                   c.status, c.issued_at, c.valid_until
            FROM user_credentials c
            JOIN users u ON u.user_id = c.user_id
            ORDER BY c.issued_at DESC
            """
        )
    ).mappings().all()

    return [dict(r) for r in rows]


@router.post("/issuer/credentials/{credential_id}/revoke")
def issuer_revoke_credential(
    credential_id: int,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    reviewer = _current_user(authorization, db)
    _require_role(reviewer, ROLE_UNIVERSITY_AGENT)

    row = db.execute(
        text(
            """
            UPDATE user_credentials
            SET status = 'revoked'
            WHERE id = :id
            RETURNING id, user_id, credential_type, status
            """
        ),
        {"id": credential_id},
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Credential not found")

    db.commit()
    return dict(row)


@router.post("/train/verify")
def train_verify(
    payload: VerifyCardPresentationRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    verifier = _current_user(authorization, db)
    _require_role(verifier, ROLE_TRAIN_VERIFIER)

    pres = db.execute(
        text(
            """
            SELECT cp.id, cp.card_id, cp.token_value, cp.issued_at, cp.expires_at, cp.status,
                   cp.used_at,
                   dc.user_id, dc.card_identifier, dc.valid_until, dc.status AS card_status,
                   i.name AS issuer_name
            FROM card_presentations cp
            JOIN digital_cards dc ON dc.id = cp.card_id
            JOIN issuers i ON i.id = dc.issuer_id
            WHERE cp.token_value = :token_value
            """
        ),
        {"token_value": payload.token},
    ).mappings().first()

    if not pres:
        raise HTTPException(status_code=404, detail="Card presentation not found")

    result = "valid"
    notes = "Card presentation accepted"

    # SINGLE-USE QR TOKEN (SECURITY FIX: prevent replay)
    if pres["used_at"] is not None:
        result = "invalid"
        notes = "Token already used (replay detected)"
    # Only allow 'active' status - 'used' tokens are rejected
    elif pres["status"] != "active":
        result = "invalid"
        notes = f"Presentation status is {pres['status']}"
    elif datetime.now(timezone.utc).replace(tzinfo=None) > _as_naive_datetime(pres["expires_at"]):
        result = "invalid"
        notes = "Presentation expired"
    elif pres["card_status"] != "active":
        result = "invalid"
        notes = "Card is not active"
    elif datetime.now(timezone.utc).replace(tzinfo=None) > _as_naive_datetime(pres["valid_until"]):
        result = "invalid"
        notes = "Card expired"

    db.execute(
        text(
            """
            INSERT INTO card_verifications (card_presentation_id, verifier_user_id, result, notes)
            VALUES (:card_presentation_id, :verifier_user_id, :result, :notes)
            """
        ),
        {
            "card_presentation_id": pres["id"],
            "verifier_user_id": verifier["user_id"],
            "result": result,
            "notes": notes,
        },
    )

    # SINGLE-USE: Mark token as used only on first successful validation
    if result == "valid":
        db.execute(
            text(
                """
                UPDATE card_presentations
                SET status = 'used', used_at = CURRENT_TIMESTAMP
                WHERE id = :pres_id
                """
            ),
            {"pres_id": pres["id"]},
        )

    holder = db.execute(
        text(
            """
            SELECT u.user_id, u.first_name, u.last_name,
                   sd.ci_date_of_birth, sd.ci_address
            FROM users u
            LEFT JOIN source_documents sd
                ON sd.user_id = u.user_id AND sd.status = 'approved'
            WHERE u.user_id = :user_id
            LIMIT 1
            """
        ),
        {"user_id": pres["user_id"]},
    ).mappings().first()

    claims = db.execute(
        text(
            """
            SELECT credential_type, claim_value, valid_until
            FROM user_credentials
            WHERE user_id = :user_id AND status = 'active' AND valid_until >= CURRENT_TIMESTAMP
            ORDER BY credential_type
            """
        ),
        {"user_id": pres["user_id"]},
    ).mappings().all()

    verification_title = "Cont verificat de agent"
    verification_message = (
        "Contul tau a fost verificat de un agent de calatorie."
        if result == "valid"
        else f"Verificarea facuta de agentul de calatorie nu a fost valida. Motiv: {notes}"
    )

    _create_notification(
        db,
        user_id=pres["user_id"],
        category="verificari",
        title=verification_title,
        message=verification_message,
    )

    doc_row = db.execute(
        text(
            """
            SELECT id, document_image_path, document_image_path_verso
            FROM source_documents
            WHERE user_id = :user_id AND document_type = 'student_card'
              AND document_image_path IS NOT NULL
            ORDER BY uploaded_at DESC
            LIMIT 1
            """
        ),
        {"user_id": pres["user_id"]},
    ).mappings().first()

    identity_document_id = doc_row["id"] if doc_row else None
    profile_row = db.execute(
        text("SELECT profile_photo_path FROM users WHERE user_id = :user_id"),
        {"user_id": pres["user_id"]},
    ).mappings().first()
    has_profile_photo = bool(profile_row and profile_row.get("profile_photo_path"))

    db.commit()

    return {
        "result": result,
        "notes": notes,
        "card": {
            "card_identifier": pres["card_identifier"],
            "issuer_name": pres["issuer_name"],
            "valid_until": pres["valid_until"],
        },
        "holder": {
            "user_id": holder["user_id"],
            "first_name": holder["first_name"],
            "last_name": holder["last_name"],
            "date_of_birth": holder.get("ci_date_of_birth"),
            "address": holder.get("ci_address"),
            "has_profile_photo": has_profile_photo,
        },
        "claims": [dict(c) for c in claims],
        "identity_document_id": identity_document_id,
    }


@router.get("/train/verifications/history")
def train_history(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    verifier = _current_user(authorization, db)
    _require_role(verifier, ROLE_TRAIN_VERIFIER)

    rows = db.execute(
        text(
            """
            SELECT cv.id, cv.verification_time, cv.result, cv.notes,
                   cp.token_value, dc.card_identifier
            FROM card_verifications cv
            JOIN card_presentations cp ON cp.id = cv.card_presentation_id
            JOIN digital_cards dc ON dc.id = cp.card_id
            WHERE cv.verifier_user_id = :verifier_user_id
            ORDER BY cv.verification_time DESC
            LIMIT 50
            """
        ),
        {"verifier_user_id": verifier["user_id"]},
    ).mappings().all()

    return [dict(r) for r in rows]


@router.post("/card/verify")
def verify_card_alias(
    payload: VerifyCardPresentationRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    return train_verify(payload=payload, authorization=authorization, db=db)


@router.post("/presentations/generate")
def generate_presentation_alias(
    payload: CardPresentationCreateRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    return present_card(payload=payload, authorization=authorization, db=db)


@router.post("/presentations/verify")
def verify_presentation_alias(
    payload: VerifyCardPresentationRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    return train_verify(payload=payload, authorization=authorization, db=db)
