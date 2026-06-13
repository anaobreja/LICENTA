# Security Assessment Report
## Railway Digital Identity Platform - Backend Security Analysis

**Assessment Date:** May 14, 2026  
**Platform:** Railway Digital Identity Platform  
**Backend Stack:** FastAPI, SQLAlchemy, JWT, TOTP MFA, PostgreSQL 16  

---

## Executive Summary

The backend demonstrates **moderate security implementation** with solid foundational practices (bcrypt hashing, JWT, MFA support, parameterized queries) but contains several **critical and high-severity vulnerabilities** that must be addressed before production deployment. The primary concerns are:

1. **CRITICAL:** Hardcoded SECRET_KEY and default DEBUG mode enabled
2. **CRITICAL:** CORS allows all origins in DEBUG mode
3. **HIGH:** Demo account password bypass mechanism
4. **HIGH:** No rate limiting or DDoS protection
5. **HIGH:** Missing security headers (HSTS, X-Frame-Options, CSP)
6. **MEDIUM:** Plain-text MFA secrets stored in database
7. **MEDIUM:** Insufficient input validation/sanitization
8. **MEDIUM:** No HTTPS enforcement in CORS configuration

---

## 1. Authentication & Authorization

### Strengths

#### Password Hashing (STRONG)
- **File:** [backend/app/core/security.py](backend/app/core/security.py#L18-L25)
- **Implementation:** BCrypt with 12 rounds
```python
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12
)
```
- **Assessment:** Excellent - bcrypt with 12 rounds is industry-standard for password hashing
- **Compliance:** OWASP, NIST recommendations ✓

#### JWT Token Management
- **File:** [backend/app/core/security.py](backend/app/core/security.py#L35-L60)
- **Implementation:** PyJWT library with HS256 algorithm
- **Expiration Settings:**
  - Access tokens: 15 minutes (appropriate)
  - Refresh tokens: 7 days (acceptable)
- **Assessment:** Good token design with reasonable expiration

#### MFA/TOTP Implementation
- **File:** [backend/app/core/security.py](backend/app/core/security.py#L90-L120)
- **Implementation:** pyotp library for TOTP generation and verification
- **Features:**
  - 6-digit codes with time window tolerance (±1 window)
  - QR code generation for authenticator apps
  - Proper verification with time-window consideration
- **Assessment:** Good MFA implementation

#### Bearer Token Authentication
- **File:** [backend/app/routers/auth.py](backend/app/routers/auth.py#L48-L55)
- **Implementation:** Standard Bearer token extraction
- **Assessment:** Proper token validation in all endpoints

---

### Vulnerabilities

#### 1. CRITICAL: Hardcoded DEFAULT SECRET_KEY
**Severity:** CRITICAL   
**File:** [backend/app/core/config.py](backend/app/core/config.py#L18)

```python
SECRET_KEY: str = "your-secret-key-change-in-production"
```

**Issues:**
- Hardcoded placeholder secret in production code
- If `.env` file is missing, this default is used for JWT signing
- All deployed instances would share the same secret key
- Anyone with code access can forge JWT tokens

**Impact:** Complete authentication bypass, token forgery, account takeover

**Recommendation:**
```python
# MUST be from environment variable with no default
SECRET_KEY: str = os.environ["SECRET_KEY"]  # Raise error if missing
```

Use environment variables and fail fast:
```bash
# .env (example - generate with: python -c "import secrets; print(secrets.token_urlsafe(32))")
SECRET_KEY=jF8xK2mN9pL0q_vwX3yZ1aB2cD4eF5gH6iJ7kL8mN9oP
```

---

#### 2. CRITICAL: Demo Login Password Bypass
**Severity:** CRITICAL   
**File:** [backend/app/routers/auth.py](backend/app/routers/auth.py#L68-L70)

```python
def _is_demo_login_allowed(password_hash: str, provided_password: str) -> bool:
    return "demo_hash" in (password_hash or "") and provided_password == "demo"
```

**Issues:**
- Demo account (`user.demo@railwaydemo.com`) can be logged in with plain password "demo"
- This bypass is checked even if bcrypt verification fails
- Allows unauthenticated access to demo account in any environment
- Demo accounts contain full test data with QR tokens, card presentations, etc.

**Evidence in Database:**
- [backend/app/core/database.py](backend/app/core/database.py#L165) - Demo user created with marker hash
- Demo user has access to digital cards, QR tokens, and verification endpoints

**Impact:** Unauthorized access to test/demo data, potential disclosure of system functionality

**Recommendations:**
1. Remove demo login bypass from production code
2. Use separate demo/testing environment if needed
3. If demo accounts must exist, use regular bcrypt hashes
4. Do not mark demo passwords specially - use actual accounts with known passwords documented in private wiki

```python
# REMOVE this function entirely for production
# OR use in testing environment only behind feature flag
if settings.ENVIRONMENT != "production":
    # demo login allowed only in dev/test
```

---

#### 3. HIGH: No Token Refresh Mechanism
**Severity:** HIGH   
**Files:** [backend/app/routers/auth.py](backend/app/routers/auth.py), [backend/app/core/security.py](backend/app/core/security.py)

**Issues:**
- Refresh tokens are generated but no `/auth/refresh` endpoint exists
- Access tokens expire in 15 minutes but can't be renewed
- Users must re-login after token expiration
- No refresh token validation or rotation

**Impact:** Poor user experience, users can't maintain sessions

**Recommendation:** Implement refresh token endpoint:
```python
@router.post("/refresh")
def refresh_access_token(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db)
):
    token = _extract_bearer_token(authorization)
    try:
        payload = decode_token(token)
        if payload.get("type") != "refresh":
            raise ValueError("Not a refresh token")
        
        user_id = int(payload.get("sub"))
        user = db.execute(
            text("SELECT role, is_active FROM users WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).first()
        
        if not user or not user[1]:  # not active
            raise HTTPException(status_code=401, detail="Invalid user")
        
        new_access_token = create_access_token(
            data={"sub": str(user_id), "role": normalize_role(user[0])}
        )
        return {"access_token": new_access_token, "token_type": "bearer"}
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
```

---

#### 4. MEDIUM: MFA Secret Stored in Plain Text
**Severity:** MEDIUM   
**File:** [backend/app/routers/auth.py](backend/app/routers/auth.py#L230-L235)

```python
db.execute(
    text("UPDATE users SET mfa_secret = :secret, mfa_enabled = :mfa_off WHERE user_id = :user_id"),
    {"secret": secret, "mfa_off": mfa_off, "user_id": user_id},
)
```

**Issues:**
- TOTP secrets stored unencrypted in database
- Database breaches expose MFA secrets
- Secrets are 32-character base32 strings - valuable target for attackers

**Impact:** MFA bypass if database is compromised

**Recommendation:** Encrypt TOTP secrets at rest:
```python
from cryptography.fernet import Fernet

class Settings(BaseSettings):
    ENCRYPTION_KEY: str  # 32-byte key encoded as base64
    
    @property
    def cipher(self):
        return Fernet(self.ENCRYPTION_KEY.encode())

# When storing
encrypted_secret = settings.cipher.encrypt(secret.encode()).decode()
db.execute(text("UPDATE users SET mfa_secret = :secret WHERE user_id = :user_id"),
           {"secret": encrypted_secret, "user_id": user_id})

# When verifying
stored_encrypted = db.execute(...).scalar()
decrypted_secret = settings.cipher.decrypt(stored_encrypted.encode()).decode()
verify_totp_code(decrypted_secret, provided_code)
```

---

## 2. Database Security

### Strengths

#### Parameterized Queries
- **Usage:** Consistent use of SQLAlchemy `text()` with parameters
- **Examples:**
  - [auth.py:82-85](backend/app/routers/auth.py#L82-L85)
  - [identity.py](backend/app/routers/identity.py) - All queries use parameters
  - [users.py](backend/app/routers/users.py) - Proper parameterization

**Assessment:** SQL injection prevention is properly implemented ✓

#### Connection Security
- **File:** [backend/app/core/database.py](backend/app/core/database.py#L48-L63)
- **Features:**
  - Connection pooling with proper timeout configuration
  - PostgreSQL connection pooling (pool_size=10, pool_pre_ping, pool_recycle=3600)
  - SQLAlchemy pre-ping for connection health

---

###  Vulnerabilities

#### 1. HIGH: Sensitive Data in Database Without Encryption
**Severity:** HIGH  
**Files:** [backend/app/core/database.py](backend/app/core/database.py#L120-L145)

**Unencrypted fields in users table:**
- `email` - PII
- `phone` - PII
- `date_of_birth` - PII
- `mfa_secret` - Authentication factor
- `password_hash` - Hashed (okay) but high-value target

**Unencrypted in digital_cards:**
- `card_identifier` - Credential identifier
- `valid_until` - Sensitive metadata

**Unencrypted in card_presentations:**
- `token_value` - Critical: Presentation tokens (should be hashed)

**Impact:** Data breach exposes personal information and credentials

**Recommendation:**
```python
# Encrypt PII fields
from sqlalchemy import String, TypeDecorator
from cryptography.fernet import Fernet

class EncryptedString(TypeDecorator):
    impl = String
    cache_ok = True
    
    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        return settings.cipher.encrypt(value.encode()).decode()
    
    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return settings.cipher.decrypt(value.encode()).decode()

# Use in models
email: EncryptedString = Column(String(255))
phone: EncryptedString = Column(String(30))
date_of_birth: EncryptedString = Column(String(32))
```

---

#### 2. MEDIUM: Card Presentation Tokens Stored Plaintext
**Severity:** MEDIUM   
**File:** [backend/app/core/database.py](backend/app/core/database.py#L150-L160)

```sql
CREATE TABLE IF NOT EXISTS card_presentations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL,
    token_value TEXT NOT NULL UNIQUE,  --  PLAINTEXT
    issued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    used_at TEXT
)
```

**Issues:**
- Card presentation tokens are used to prove identity
- Stored in plaintext in database
- Could allow token enumeration if database accessed
- `token_value` should be hashed (already has hash_qr_token function in [security.py](backend/app/core/security.py#L132-L134))

**Current Implementation:**
```python
def hash_qr_token(token: str) -> str:
    """Hash QR token for storage (don't store plaintext)"""
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()
```

But it's not being used! The token is stored plaintext.

**Impact:** Token compromise leads to identity presentation forgery

**Recommendation:**
```python
# In identity.py when creating presentations
plain_token = generate_qr_token()
token_hash = hash_qr_token(plain_token)

db.execute(
    text("""
        INSERT INTO card_presentations (card_id, token_value, expires_at)
        VALUES (:card_id, :token_hash, :expires_at)
    """),
    {"card_id": card_id, "token_hash": token_hash, "expires_at": expires_at}
)

# Return plaintext to user
return {"token": plain_token, "expires_at": expires_at}

# When verifying
provided_token = request.token
provided_hash = hash_qr_token(provided_token)
db_record = db.execute(
    text("SELECT * FROM card_presentations WHERE token_value = :hash"),
    {"hash": provided_hash}
).first()
```

---

#### 3. MEDIUM: No Database Encryption at Rest
**Severity:** MEDIUM 🟡  

**Issues:**
- PostgreSQL stores data unencrypted by default at the filesystem level
- PostgreSQL instance may not have encryption enabled
- File [railway_demo.db](railway_demo.db) in repository root is unencrypted

**Impact:** Disk-level access exposes entire database

**Recommendation:**
- For PostgreSQL: Use Transparent Data Encryption (TDE) or filesystem-level encryption (LUKS / BitLocker)
- For PostgreSQL: Enable pgcrypto extension
- For production: Use encrypted storage volumes/drives

```bash
# PostgreSQL TDE (via pg_tde extension or hosted solution)
pip install sqlcipher3
DATABASE_URL=sqlcipher:///database.db?key=your-password
```

---

## 3. API Security

### Vulnerabilities

#### 1. CRITICAL: CORS Allows All Origins in DEBUG Mode
**Severity:** CRITICAL  
**File:** [backend/app/main.py](backend/app/main.py#L32-L44)

```python
if settings.DEBUG:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  #  DANGEROUS
        allow_credentials=True,  #  Allows cookies/auth
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

**Issues:**
- `DEBUG=True` by default in [config.py](backend/app/core/config.py#L28)
- `allow_origins=["*"]` with `allow_credentials=True` is dangerous
- This allows any website to make authenticated requests
- CSRF attacks possible
- Cross-site request forgery (CSRF) vulnerability

**Attack Scenario:**
1. Attacker hosts malicious site
2. Victim logs into platform
3. Victim visits attacker's site
4. Attacker's site makes API calls using victim's credentials
5. Attacker can change password, modify profile, create QR tokens, etc.

**Impact:** CSRF, credential theft, unauthorized actions

**Recommendations:**
```python
# .env should contain explicit CORS origins
CORS_ORIGINS=["https://example.com", "https://admin.example.com"]

# In main.py
if settings.DEBUG:
    allowed_origins = [
        "http://localhost:5173",    # Vite dev server
        "http://localhost:3000",     # Alt dev port
        "http://127.0.0.1:8765",    # Local proxy
    ]
else:
    allowed_origins = settings.CORS_ORIGINS  # From .env

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,  # Only if using cookies for auth
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # Explicit
    allow_headers=["Authorization", "Content-Type"],  # Explicit
    max_age=3600,
)
```

**CRITICAL:** Never use `["*"]` with `allow_credentials=True` - browsers will reject this.

---

#### 2. HIGH: No Rate Limiting
**Severity:** HIGH   

**Issues:**
- No rate limiting on authentication endpoints
- Brute force attacks possible on `/auth/login`
- No DDoS protection
- QR token validation endpoint has no rate limits
- TOTP code verification has no attempt limits

**Impact:** Brute force attacks, credential stuffing, DDoS

**Recommendation:** Implement rate limiting with slowapi:
```bash
pip install slowapi
```

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# In auth router
@router.post("/login")
@limiter.limit("5/minute")  # 5 attempts per minute
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ...

@router.post("/mfa/verify")
@limiter.limit("10/minute")  # Allow more for legitimate users entering codes
def mfa_verify(payload: MFAEnableRequest, ...):
    ...

@router.post("/auth/register")
@limiter.limit("3/hour")  # Prevent registration spam
def register(payload: RegisterRequest, ...):
    ...
```

Add to dependencies:
```
slowapi==0.1.9
```

---

#### 3. HIGH: Missing Security Headers
**Severity:** HIGH   
**File:** [backend/app/main.py](backend/app/main.py)

**Missing Headers:**
- `Strict-Transport-Security` (HSTS) - Force HTTPS
- `X-Content-Type-Options` - Prevent MIME sniffing
- `X-Frame-Options` - Prevent clickjacking
- `X-XSS-Protection` - Browser XSS protection
- `Content-Security-Policy` - Script injection prevention
- `Referrer-Policy` - Control referrer information

**Recommendation:** Add security headers middleware:
```python
from fastapi.middleware import Middleware
from fastapi.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'"
        return response

app.add_middleware(SecurityHeadersMiddleware)
```

Or simpler with fastapi-middleware:
```bash
pip install fastapi-middleware-security-headers
```

---

#### 4. MEDIUM: No HTTPS Enforcement in CORS Config
**Severity:** MEDIUM   
**File:** [backend/app/core/config.py](backend/app/core/config.py#L23-L30)

```python
CORS_ORIGINS: list = [
    "http://localhost:5173",      
    "http://localhost:3000",       
    "http://127.0.0.1:8765",      
    "http://localhost:8765",
    "http://127.0.0.1:5000",
    "http://localhost:5000",
]
```

**Issues:**
- Dev origins using HTTP is fine
- Production origins should be HTTPS-only
- No distinction between development and production

**Recommendation:**
```python
if settings.DEBUG:
    CORS_ORIGINS = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:8765",
        "http://127.0.0.1:5000",
    ]
else:
    CORS_ORIGINS = [
        "https://platform.railwaydemo.com",
        "https://admin.railwaydemo.com",
    ]
```

---

#### 5. MEDIUM: No Input Validation for Query Parameters
**Severity:** MEDIUM   
**File:** Various router files

**Issues:**
- No validation of pagination parameters (limit, offset)
- No validation of filter parameters
- Could cause DoS by requesting huge datasets

**Recommendation:** Add validation to query parameters:
```python
from pydantic import BaseModel, Field

class PaginationParams(BaseModel):
    skip: int = Field(default=0, ge=0, le=100000)
    limit: int = Field(default=50, ge=1, le=1000)

@router.get("/items")
def list_items(params: PaginationParams = Depends(), db: Session = Depends(get_db)):
    ...
```

---

## 4. Sensitive Data Handling

### Strengths

#### QR Code Generation
- **File:** [backend/app/core/security.py](backend/app/core/security.py#L106-L120)
- **Implementation:** QR codes generated as base64 data URIs
- **Assessment:** Safe - not persisted on server, only sent to client

#### QR Token Generation
- **File:** [backend/app/core/security.py](backend/app/core/security.py#L123-L126)
- **Implementation:** Uses `secrets.token_urlsafe(32)` - cryptographically secure
- **Assessment:** Good randomness ✓

---

###  Vulnerabilities

#### 1. HIGH: QR Tokens Returned Plaintext
**Severity:** HIGH   
**Impact:** Token logged in server logs, browser history, network proxies

**Recommendation:**
```python
# Return token only once, in response header (not body)
response.headers["X-QR-Token"] = plain_token
return {"message": "Token generated. Check X-QR-Token header"}

# Or use one-time retrieval URL
token_id = db.execute(
    text("INSERT INTO qr_tokens (token_hash, expires_at) VALUES (:h, :e) RETURNING id"),
    {"h": hash_qr_token(plain_token), "e": expires_at}
).scalar()
return {"token_url": f"/api/qr-tokens/{token_id}?secret={plain_token}"}
```

---

#### 2. MEDIUM: Card Presentation Tokens in Response
**Severity:** MEDIUM   
**File:** [backend/app/routers/identity.py](backend/app/routers/identity.py)

**Issue:** Card presentation tokens returned in API responses could be:
- Logged in application logs
- Captured in browser history
- Intercepted by proxies or MITM
- Stored in browser cache

**Recommendation:**
- Return token only in secure httpOnly cookie (if applicable)
- Or use POST request that immediately redirects to download QR
- Include token expiration warning in response

---

#### 3. MEDIUM: User Data Export Contains Sensitive Information
**Severity:** MEDIUM   
**File:** [backend/app/routers/users.py](backend/app/routers/users.py#L174-L220)

```python
@router.get("/me/export")
def export_me(authorization: str | None = Header(default=None), ...):
    # Returns all user data including credentials, documents
    # Could be exported and stored unencrypted
```

**Recommendation:**
- Warn user before export
- Encrypt export file
- Log all data exports
- Limit export frequency (e.g., once per day)

```python
@router.get("/me/export")
@limiter.limit("1/day")  # Once per day
def export_me(...):
    # Generate encrypted ZIP
    import zipfile
    from cryptography.fernet import Fernet
    
    cipher = Fernet(settings.ENCRYPTION_KEY.encode())
    export_json = json.dumps(export_data)
    encrypted = cipher.encrypt(export_json.encode())
    
    # Return as download with warning
    return FileResponse(
        path,
        headers={
            "Content-Disposition": f"attachment; filename=export-{user_id}-{date.today()}.zip",
            "Warning": "This export contains sensitive personal data. Keep it secure."
        }
    )
```

---

## 4.1 Identity Data Immutability (NEW)

### Strengths

#### Frozen Fields After Verification (STRONG)

Once a user's identity is validated by a university agent, the following
fields become immutable until the credential expires (start of the next
academic year, October 1st):

- `cnp` (national ID number)
- `first_name`, `last_name`
- `birth_date`
- `home_station_id` (derived from validated home address)

**Implementation:** `app/core/identity_status.py` provides
`is_identity_verified()` and `check_frozen_field_changes()`. The router
`update_me` in `users.py` raises HTTP 403 with detailed error if a
verified user attempts to modify any frozen field. The endpoint
`GET /users/me/verification-status` exposes expiry information to the
frontend so the UI can disable inputs and show a banner.

**Threat mitigated:** Identity laundering. Without this rule, an
attacker who compromised a verified account could change CNP/name to
match a stolen identity, effectively transferring the verified status
to fraudulent data. Even with the digital card revoked, the underlying
profile would carry undeserved trust signals.

**Business rule rationale:** Verification is anchored to physical
documents inspected by an agent. Allowing field changes between
verifications breaks the cryptographic chain of trust between the
agent's approval and the credential's claim_value.

### Lifecycle

```
1. User registers     -> fields editable, no credentials
2. Uploads ID         -> source_documents row, status='pending'
3. Agent approves     -> 3 credentials created:
                         - identity_verified (locks fields)
                         - student_verified / elev_verified
                         - national_id
                         All valid_until = 1 oct next academic year
4. Fields are FROZEN until 1 october of current academic year
5. On 1 october       -> credentials auto-expire (lazy cleanup in
                         get_verification_status())
6. Fields editable    -> user must re-upload documents for re-validation
```

### Tested with 17 integration tests

See `tests/integration/test_profile_freeze.py`. Covers:

- Academic year boundary logic (3 edge cases at 30 sep / 1 oct / etc.)
- Unverified users can change everything (3 tests)
- Verified users blocked on each frozen field (5 tests, one per field)
- Expired credentials automatically unlock fields (1 test)
- No-op updates (same value) are not blocked (1 test)
- `/users/me/verification-status` returns correct payload (2 tests)

---

## 4.2 Vulnerabilitati descoperite si reparate prin testare automata

### Critical Fix: Privilege Escalation in Ticket Validation (FIXED)

**Severity:** CRITICAL
**Affected endpoint:** `POST /tickets/validate`
**Discovered:** prin extinderea suite-ului de teste integration (sesiunea de
coverage improvement, iunie 2026)
**Fixed in:** commit `feat(security)` din `feat/postgres-migration`

#### Descriere problema

Endpoint-ul `/tickets/validate` (folosit de conductori la bord pentru a valida
QR code-ul biletelor) **nu impunea verificarea rolului `train_verifier`**.
Verificarea autentificarii era prezenta (`_extract_current_user`), dar lipsea
filtrul de autorizare pe rol.

Asta inseamna ca **orice utilizator autentificat** (inclusiv un pasager
obisnuit) putea apela endpoint-ul si valida un QR token. Tipic atac:

```http
POST /tickets/validate HTTP/1.1
Authorization: Bearer <passenger_jwt>
Content-Type: application/json

{"token": "<qr_token_furat>"}
```

Raspuns observat **inainte de fix**: `200 OK, {"result": "valid"}` urmat de
marcarea token-ului ca `used` in `qr_tokens.used_at`.

#### Impact

1. **Bilet single-use poate fi "ars" de oricine** - un atacator care intercepteaza
   un QR token poate apela `/tickets/validate` si marca biletul ca folosit, chiar
   daca pasagerul real n-a apucat sa-l prezinte conductorului. Pasagerul real
   primeste **al doilea apel ca `already_used`** si NU mai poate calatori.

2. **Audit trail compromis** - validarile false sunt inregistrate in
   tabela `validations` cu `conductor_id = passenger_id`, ceea ce arata ca
   "pasagerul s-a validat singur" (caz fizic imposibil).

3. **Privilege escalation chain** - daca sistemul extinde validate cu actiuni
   privilegiate (de exemplu raportare statistica, blacklist), un atacator putea
   abuza acelasi endpoint.

#### Fix aplicat

```python
@router.post("/tickets/validate", response_model=ValidateTicketResponse)
def validate_ticket(
    payload: ValidateTicketRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    user = _extract_current_user(authorization, db)

    # SECURITY FIX: doar conductorii (train_verifier) si adminii pot valida
    # bilete. Inainte oricare user autentificat putea apela endpoint-ul.
    user_role = normalize_role(user.get("role"))
    if not has_role(user_role, ROLE_TRAIN_VERIFIER) and user_role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Doar conductorii sau adminii pot valida bilete.",
        )

    # ... rest of validation flow
```

#### Test de regresie strict

```python
def test_validate_passenger_role_rejected_403(self, client):
    """
    BUG #2 (REPARAT): pasagerii NU pot valida bilete.
    Inainte de fix: orice user autentificat era acceptat.
    Dupa fix: cere strict train_verifier sau admin -> 403 pentru passenger.
    """
    # ... seteaza un bilet valid, pasager incearca sa-l valideze
    r = client.post("/tickets/validate", json={"token": qr_token}, headers=h)
    assert r.status_code == 403, r.text
```

Test in `backend/tests/integration/test_ticket_validation.py::TestValidateTicket::test_validate_passenger_role_rejected_403`.

#### Lectie pentru rest of codebase

Auditat **toate endpoint-urile cu rol** (`_extract_current_user`) si confirmat
ca au verificarea de rol unde este necesar. Pattern recomandat pentru viitor:

```python
# In loc de:
user = _extract_current_user(...)
# imediat dupa, daca actiunea e privilegiata:
user_role = normalize_role(user.get("role"))
if not has_role(user_role, ROLE_REQUIRED):
    raise HTTPException(403, "Acces interzis.")
```

### False alarms investigate (NU au fost bug-uri)

In aceeasi sesiune am investigat 5 alte ipoteze de vulnerabilitati care s-au
dovedit a NU exista in cod (rezultat fals din teste cu path-uri/payload-uri
incorecte):

| Bug ipotetic | Status real | Verificare |
|---|---|---|
| `validate` accepta orice token (fallback ascuns) | NU exista | linia 798 verifica `if not row -> invalid` |
| `password change` nu verifica current_password | NU exista | linia 304 apeleaza `verify_password` |
| `password change` accepta parole scurte | NU exista | Pydantic `Field(min_length=6)` |
| `profile-photo` accepta orice content_type | NU exista | `save_uploaded_image` valideaza `ALLOWED_IMAGE_TYPES` |
| `export-data` arunca 500 KeyError | NU exista | bloc `try/except SQLAlchemyError` |

Toate au fost confirmate cu teste live + lectura cod.

---

## 5. Known Vulnerabilities & Gaps

### Critical Issues Summary

| # | Issue | Severity | File | Recommendation |
|---|-------|----------|------|-----------------|
| 1 | Hardcoded SECRET_KEY |  CRITICAL | [config.py](backend/app/core/config.py#L18) | Use environment variable with no default |
| 2 | Demo password bypass |  CRITICAL | [auth.py](backend/app/routers/auth.py#L68-L70) | Remove demo login function |
| 3 | CORS all origins + credentials |  CRITICAL | [main.py](backend/app/main.py#L32-L44) | Explicit origins list only |
| 4 | DEBUG mode enabled by default |  CRITICAL | [config.py](backend/app/core/config.py#L28) | Default to False, explicit enable in dev |

### High Issues

| # | Issue | Severity | File | Recommendation |
|---|-------|----------|------|-----------------|
| 5 | No rate limiting |  HIGH | All auth endpoints | Implement slowapi |
| 6 | Missing security headers |  HIGH | [main.py](backend/app/main.py) | Add middleware |
| 7 | No token refresh endpoint |  HIGH | [auth.py](backend/app/routers/auth.py) | Implement /refresh |
| 8 | QR tokens plaintext in responses |  HIGH | [identity.py](backend/app/routers/identity.py) | Return in headers or one-time URL |
| 9 | No database encryption |  HIGH | [database.py](backend/app/core/database.py) | Use sqlcipher or pgcrypto |
| 10 | Card tokens plaintext in DB |  HIGH | [identity.py](backend/app/routers/identity.py) | Hash tokens before storage |

### Medium Issues

| # | Issue | Severity | File | Recommendation |
|---|-------|----------|------|-----------------|
| 11 | MFA secrets plaintext |  MEDIUM | [auth.py](backend/app/routers/auth.py#L230) | Encrypt with Fernet |
| 12 | PII not encrypted |  MEDIUM | [database.py](backend/app/core/database.py) | Encrypt email, phone, DOB |
| 13 | No input validation |  MEDIUM | Query parameters | Add Pydantic validators |
| 14 | No HTTPS in CORS |  MEDIUM | [config.py](backend/app/core/config.py#L23) | Enforce HTTPS in prod |
| 15 | Document uploads minimal validation |  MEDIUM | [identity.py](backend/app/routers/identity.py#L273-L290) | Add filename sanitization |

---

## Security Checklist for Production

### Before Deployment

- [ ] Change `SECRET_KEY` to long random value (32+ characters)
- [ ] Set `DEBUG=False` in production `.env`
- [ ] Remove demo login bypass function
- [ ] Implement explicit CORS origins list (HTTPS only)
- [ ] Add rate limiting to all auth endpoints
- [ ] Implement `/auth/refresh` endpoint
- [ ] Add security headers middleware
- [ ] Encrypt database at rest (sqlcipher or pgcrypto)
- [ ] Hash card presentation tokens before storage
- [ ] Encrypt TOTP secrets with Fernet
- [ ] Encrypt PII fields (email, phone, date_of_birth)
- [ ] Add HTTPS enforcement (redirect HTTP to HTTPS)
- [ ] Enable HSTS header (min 1 year)
- [ ] Add input validation to all endpoints
- [ ] Implement audit logging for sensitive operations
- [ ] Set up error logging without sensitive data exposure
- [ ] Enable PostgreSQL query logging (`log_statement = 'mod'`)
- [ ] Test CORS configuration thoroughly
- [ ] Review and restrict admin endpoints
- [ ] Add database connection encryption (SSL/TLS)

### Monitoring & Maintenance

- [ ] Monitor failed authentication attempts
- [ ] Alert on suspicious IP/geo activity
- [ ] Regular security audits (monthly)
- [ ] Dependency updates (security patches)
- [ ] Log rotation and retention
- [ ] Database backup encryption
- [ ] Security header validation tests
- [ ] OWASP dependency check in CI/CD

---

## Implementation Priority

### Phase 1 (Critical - Deploy Before Any Users)
1. Fix SECRET_KEY management
2. Remove demo password bypass
3. Fix CORS configuration  
4. Enable rate limiting
5. Add security headers

**Estimated time:** 2-3 days

### Phase 2 (High - Deploy Before Public Release)
1. Implement token refresh
2. Hash QR tokens in database
3. Implement database encryption
4. Encrypt TOTP secrets
5. HTTPS enforcement

**Estimated time:** 5-7 days

### Phase 3 (Medium - Deploy Within 30 Days)
1. Encrypt PII fields
2. Input validation improvements
3. Audit logging
4. Error handling review
5. Security testing

**Estimated time:** 5-7 days

---

## Testing Recommendations

### Security Testing Tools
```bash
# OWASP Dependency Check
pip install safety
safety check --json > safety-report.json

# SQL Injection testing
pytest tests/security/test_sql_injection.py

# CORS testing
pytest tests/security/test_cors.py

# Rate limiting testing
pytest tests/security/test_rate_limiting.py

# Authentication testing
pytest tests/security/test_auth.py
```

### Example Security Tests
```python
# tests/security/test_cors.py
def test_cors_denies_unauthorized_origin():
    response = client.options(
        "/auth/login",
        headers={"Origin": "https://malicious.com"}
    )
    assert response.headers.get("Access-Control-Allow-Origin") != "https://malicious.com"

# tests/security/test_rate_limiting.py
def test_login_rate_limiting():
    for i in range(10):
        response = client.post("/auth/login", json={"email": "test@test.com", "password": "wrong"})
    assert response.status_code == 429  # Too Many Requests

# tests/security/test_secrets.py
def test_no_hardcoded_secrets():
    with open("backend/app/core/config.py") as f:
        content = f.read()
    assert "your-secret-key" not in content
    assert "demo" not in content
```

---

## References & Standards

- [OWASP Top 10 2021](https://owasp.org/www-project-top-ten/)
- [NIST Guidelines](https://pages.nist.gov/800-63-3/)
- [FastAPI Security](https://fastapi.tiangolo.com/advanced/security/)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [JWT Best Practices](https://tools.ietf.org/html/rfc8725)
- [Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html)

---

## Assessment Conclusion

The Railway Digital Identity Platform backend has **good foundational security practices** (bcrypt, JWT, parameterized queries) but requires **immediate fixes for critical vulnerabilities** before any production deployment. The primary concerns are configuration/deployment issues (hardcoded secrets, demo bypass, CORS) rather than fundamental architectural flaws.

**Risk Level: HIGH** 

With implementation of Phase 1 recommendations (2-3 days of work), the risk can be reduced to **MEDIUM**. Full Phase 2 & 3 implementation brings it to **LOW**.

---

**Prepared by:** GitHub Copilot Security Analysis  
**Date:** May 14, 2026  
**Recommendation:** DO NOT DEPLOY to production without Phase 1 fixes.
