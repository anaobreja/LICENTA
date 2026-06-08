# Diagrame de Secvență — Fluxuri principale

## 1. Flux: Înregistrare și autentificare cu MFA

```mermaid
sequenceDiagram
    actor P as Pasager
    participant FE as Frontend React
    participant API as FastAPI
    participant DB as PostgreSQL

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
    participant DB as PostgreSQL

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
    participant DB as PostgreSQL

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
    participant DB as PostgreSQL

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
    participant DB as PostgreSQL

    P->>FE: Accesează Settings → Export date
    FE->>API: GET /users/me/export
    API->>DB: SELECT user profile, credentials, notifications, documents
    DB-->>API: Toate datele utilizatorului
    API-->>FE: JSON complet cu toate datele
    FE->>FE: Browser descarcă fișierul JSON
```


---

## 6. Flux: Cumpărare bilet de tren

```mermaid
sequenceDiagram
    actor P as Pasager
    participant FE as Frontend
    participant API as FastAPI
    participant DB as PostgreSQL

    P->>FE: Accesează /buy-ticket
    FE->>API: GET /map/stations
    API->>DB: SELECT stations
    DB-->>API: lista stații
    API-->>FE: stations array
    P->>FE: Selectează stație plecare + sosire + dată + tip bilet
    FE->>API: POST /tickets/quote {from_station, to_station, ticket_type}
    API->>DB: SELECT route + train + tariff_brackets (calcul preț pe km)
    DB-->>API: preț + reduceri aplicabile (student_verified -> -50%)
    API-->>FE: {base_price, discounts, final_price}
    P->>FE: Confirmă cumpărarea
    FE->>API: POST /tickets/buy {train_id, from, to, payment_method}
    API->>API: Verifică credențialele user-ului (student_verified pentru reducere)
    API->>DB: INSERT INTO tickets (user_id, train_id, status='active', price)
    API->>DB: INSERT INTO qr_tokens (ticket_id, token, expires_at)
    API->>DB: INSERT INTO notifications (user_id, "Bilet cumpărat #X")
    DB-->>API: ticket_id
    API-->>FE: {ticket_id, qr_token, qr_data_url}
    FE->>FE: Afișează QR-ul biletului + buton "Vezi în MyTickets"
```

---

## 7. Flux: Validare bilet în tren (de către conductor)

```mermaid
sequenceDiagram
    actor PA as Pasager
    actor CO as Conductor
    participant FEP as Frontend Pasager
    participant FEC as Frontend Conductor
    participant API as FastAPI
    participant DB as PostgreSQL

    PA->>FEP: Deschide MyTickets și afișează QR-ul biletului
    CO->>FEC: Accesează /validate-ticket și pornește scanner-ul
    CO->>FEC: Scanează QR-ul de pe telefonul pasagerului
    FEC->>API: POST /tickets/validate {token}
    API->>DB: SELECT qr_tokens WHERE token=? JOIN tickets JOIN trains JOIN users
    DB-->>API: ticket + train info + user info
    API->>API: Verifică: expires_at, status='active', tren corect, dată călătorie corectă
    alt Bilet valid
        API->>DB: INSERT INTO validations (ticket_id, conductor_id, result='valid', train_id)
        API->>DB: UPDATE tickets SET status='used' (one-way) sau păstrează 'active' (subscription)
        API->>DB: INSERT INTO notifications (pasager, "Bilet validat în trenul X")
        API-->>FEC: {result='valid', holder, train_info, journey}
        FEC->>FEC: Ecran VERDE + detalii călătorie (origine -> destinație, tren, oră)
    else Bilet invalid/expirat/folosit
        API->>DB: INSERT INTO validations (result='invalid', notes)
        API-->>FEC: {result='invalid', reason}
        FEC->>FEC: Ecran ROȘU + motiv
    end
```

---

## 8. Flux: Verificare offline a cardului digital (Ed25519 fără internet)

> **NOTĂ:** Acest flux ilustrează cum sistemul funcționează FĂRĂ conexiune la internet pentru conductor.

```mermaid
sequenceDiagram
    actor PA as Pasager
    actor CO as Conductor
    participant FEP as Frontend Pasager
    participant FEC as Frontend Conductor
    participant API as FastAPI (NU e accesată offline!)

    Note over FEC,API: PRECONDIȚIE — La pornire (cu internet)
    FEC->>API: GET /verification-key (o singură dată, mod online)
    API-->>FEC: {pem, raw_base64, kid, algorithm: "Ed25519"}
    FEC->>FEC: Salvează în localStorage (cache permanent până la rotație cheie)

    Note over PA,FEP: OFFLINE — Pasager generează token semnat
    PA->>FEP: Generează token QR (funcționează offline dacă a fost emis recent)
    FEP->>FEP: Afișează QR cu token base64url(payload).base64url(ed25519_signature)

    Note over CO,FEC: OFFLINE — Conductor scanează QR
    CO->>FEC: Activează toggle "Offline mode" + scanează QR
    FEC->>FEC: getVerificationKey() — citește din localStorage (FĂRĂ fetch)
    FEC->>FEC: crypto.subtle.importKey(raw, Ed25519)
    FEC->>FEC: crypto.subtle.verify(signature, payload)
    alt Semnătură validă + exp în viitor
        FEC->>FEC: Decode payload, verifică exp, iat, claims
        FEC->>FEC: Ecran VERDE + claims (FĂRĂ call la backend!)
    else Semnătură invalidă / expirat
        FEC->>FEC: Ecran ROȘU + motiv (tampering / expirare)
    end

    Note over FEC,API: Niciun call la backend in pasii 2-3 — telefonul conductorului poate fi in mod avion
    Note over FEC,API: Cheia publica se descarca o singura data, iar rotatia se face prin push notification si invalidare cache
    Note over FEC,API: Spre deosebire de modul online, aici NU se inregistreaza nimic in card_verifications — audit se face doar la sincronizare ulterioara
```
