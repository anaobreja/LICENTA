# Diagrame de Secvență — Fluxuri principale

## 1. Flux: Înregistrare și autentificare cu MFA

```mermaid
sequenceDiagram
    actor P as Pasager
    participant FE as Frontend React
    participant API as FastAPI
    participant DB as SQLite

    P->>FE: Completează formular înregistrare
    FE->>API: POST /auth/register {email, password}
    API->>API: hash_password(bcrypt, cost=12)
    API->>DB: INSERT INTO users (...)
    DB-->>API: user_id
    API-->>FE: {message: "Account created"}

    P->>FE: Completează formular login
    FE->>API: POST /auth/login {email, password}
    API->>DB: SELECT users WHERE email=?
    DB-->>API: user row
    API->>API: verify_password(bcrypt)
    alt MFA activat
        API-->>FE: HTTP 403 MFA_REQUIRED
        P->>FE: Introduce codul TOTP (6 cifre)
        FE->>API: POST /auth/login {email, password, totp_code}
        API->>API: verify_totp_code(secret, code)
    end
    API->>API: create_access_token(JWT, 15min)
    API-->>FE: {access_token, user}
    FE->>FE: localStorage.setItem(token)
```

---

## 2. Flux: Depunere documente cu OCR

```mermaid
sequenceDiagram
    actor P as Pasager
    participant FE as Frontend React
    participant API as FastAPI
    participant OCR as easyocr
    participant DB as SQLite

    P->>FE: Apasă "Scanează CI"
    FE->>FE: Deschide camera / file picker
    P->>FE: Fotografiază CI-ul
    FE->>API: POST /documents/extract-id {photo}
    API->>OCR: reader.readtext(img_bytes)
    OCR-->>API: Lista texte detectate
    API->>API: _parse_mrz(texts) — caută zona MRZ
    alt MRZ detectat
        API-->>FE: {success: true, data: {surname, given_names, document_number, date_of_birth, sex}}
        FE->>FE: Pre-completează câmpurile formularului
    else MRZ nedetectat
        API-->>FE: {success: false, message: "Zona MRZ nu a fost detectată"}
        P->>FE: Completează manual câmpurile
    end

    P->>FE: Selectează universitatea și anul de studiu
    P->>FE: Încarcă poza legitimației de student
    P->>FE: Apasă "Trimite pentru validare"
    FE->>API: POST /documents/validation-request {ci_data, legitimation_photo, university, year}
    API->>API: _save_uploaded_document_photo()
    API->>DB: DELETE old pending docs (dacă există)
    API->>DB: INSERT INTO source_documents (...)
    DB-->>API: document_id
    API-->>FE: {message: "Cererea a fost trimisă"}
    FE->>FE: Toast succes + refresh state
```

---

## 3. Flux: Verificare și aprobare de către agentul universitar

```mermaid
sequenceDiagram
    actor AU as Agent Universitar
    participant FE as Frontend React
    participant API as FastAPI
    participant DB as SQLite

    AU->>FE: Login cu rol university_agent
    FE->>API: POST /auth/login
    API-->>FE: {access_token, role: "university_agent"}
    FE->>FE: Redirect → /agent

    AU->>FE: Accesează Dashboard Agent
    FE->>API: GET /university/stats
    API->>DB: COUNT pending/approved/rejected WHERE university_name = agent.university
    DB-->>API: Statistici
    API-->>FE: {totals, year_distribution, activity}
    FE->>FE: Renderează grafice (Pie + Bar chart)

    FE->>API: GET /issuer/documents/pending
    API->>DB: SELECT source_documents WHERE university_name = agent.university AND status='pending'
    DB-->>API: Lista cereri
    API-->>FE: Lista cereri cu date CI

    AU->>FE: Apasă "📷 Vezi poza"
    FE->>API: GET /documents/{id}/photo
    API-->>FE: FileResponse (imagine)
    FE->>FE: Afișează poza în modal

    AU->>FE: Apasă "✔ Aprobă"
    FE->>API: POST /issuer/documents/{id}/approve
    API->>DB: UPDATE source_documents SET status='approved'
    API->>DB: INSERT INTO user_credentials (student_verified, valid 1 an)
    API->>DB: INSERT OR IGNORE INTO digital_cards
    API->>DB: INSERT INTO notifications (user_id, "Cerere aprobată")
    DB-->>API: OK
    API-->>FE: {status: "approved"}
    FE->>FE: Toast "Document aprobat"
```

---

## 4. Flux: Generare și verificare card digital

```mermaid
sequenceDiagram
    actor P as Pasager
    actor AT as Agent Tren
    participant FE_P as Frontend (Pasager)
    participant FE_A as Frontend (Agent)
    participant API as FastAPI
    participant DB as SQLite

    P->>FE_P: Accesează /present (Card Digital)
    FE_P->>API: GET /card/me
    API->>DB: SELECT digital_cards WHERE user_id=?
    DB-->>API: Card info + claims
    API-->>FE_P: {card, claims}
    FE_P->>FE_P: Afișează cardul vizual (gradient)

    P->>FE_P: Apasă "Generează token dinamic"
    FE_P->>API: POST /card/present {ttl_seconds: 120}
    API->>API: secrets.token_urlsafe(24) — token aleator
    API->>DB: INSERT INTO card_presentations (token_value, expires_at)
    API->>API: _build_qr_data_url(token) — generare QR PNG
    API-->>FE_P: {token_value, qr_data_url, expires_at}
    FE_P->>FE_P: Afișează QR + countdown 120s
    FE_P->>FE_P: Auto-regenerare la expirare

    AT->>FE_A: Accesează /verify
    AT->>FE_A: Scanează QR din camera
    FE_A->>API: POST /card/verify {token: "card_..."}
    API->>DB: SELECT card_presentations WHERE token_value=?
    DB-->>API: Presentation + card + holder
    API->>API: Verifică: expirare, status card, validity
    alt Token valid
        API->>DB: INSERT INTO card_verifications (result='valid')
        API->>DB: INSERT INTO notifications (pasager, "Cont verificat")
        API-->>FE_A: {result: "valid", holder, claims}
        FE_A->>FE_A: Ecran VERDE fullscreen 2 secunde
    else Token invalid / expirat
        API-->>FE_A: {result: "invalid", notes}
        FE_A->>FE_A: Ecran ROȘU fullscreen 2 secunde
    end
    FE_A->>FE_A: Afișează detalii holder + claims
```

---

## 5. Flux: Export date GDPR

```mermaid
sequenceDiagram
    actor P as Pasager
    participant FE as Frontend
    participant API as FastAPI
    participant DB as SQLite

    P->>FE: Accesează Settings → Export date
    FE->>API: GET /users/me/export
    API->>DB: SELECT user profile, credentials, notifications, documents
    DB-->>API: Toate datele utilizatorului
    API-->>FE: JSON complet cu toate datele
    FE->>FE: Browser descarcă fișierul JSON
```
