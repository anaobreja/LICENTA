# Diagrama Arhitectură

## Arhitectura generală

```mermaid
graph TB
    subgraph Client["Client (Browser / Mobile)"]
        FE["React 18 + Vite\nTailwind CSS + Recharts\nhtml5-qrcode"]
    end

    subgraph Server["Server (localhost)"]
        PS["Proxy Server\n:8765\nproxy_server.py"]
        API["FastAPI Backend\n:8000\nuvicorn"]
        OCR["easyocr\nMRZ Parser\n(lazy load)"]
    end

    subgraph Persistence["Persistență"]
        DB[(PostgreSQL 16\nrailway_db)]
        FS["Fișiere\nuploads/documents/"]
        PG[(PostgreSQL\nopțional)]
    end

    FE -->|"HTTP /api/*"| PS
    FE -->|"fișiere statice /dist"| PS
    PS -->|"proxy /api → :8000"| API
    API -->|"SQLAlchemy ORM"| DB
    API -->|"SQLAlchemy ORM"| PG
    API -->|"FileResponse"| FS
    API -->|"readtext(img)"| OCR
```

---

## Arhitectura detaliată — straturi

```mermaid
graph TD
    subgraph Frontend["Frontend — React"]
        Pages["Pages\nDashboard · Documents\nPresentIdentity · VerifyPresentation\nUniversityAgentDashboard · AdminDashboard"]
        Components["Components\nNavigation · ProtectedRoute · Toast"]
        Services["Services\napi.js — fetch wrapper"]
    end

    subgraph Backend["Backend — FastAPI"]
        Routers["Routers\n/auth · /users · /identity\n/university/stats"]
        Core["Core\nsecurity.py — JWT + TOTP + QR\ndatabase.py — SQLAlchemy + seed\nconfig.py — Settings\nroles.py — RBAC"]
    end

    subgraph Database["Baza de date — PostgreSQL 16"]
        UsersT["users · digital_identities\nauth_methods · universities"]
        DocsT["source_documents\ndocument_reviews"]
        CredT["user_credentials · issuers\ndigital_cards · card_presentations\ncard_verifications"]
        NotifT["notifications"]
    end

    Pages --> Services
    Components --> Services
    Services -->|"REST API"| Routers
    Routers --> Core
    Core --> Database
```

---

## Stack tehnologic

| Strat | Tehnologie | Versiune |
|-------|-----------|---------|
| Frontend | React | 18 |
| Build tool | Vite | 5.x |
| Stilizare | Tailwind CSS | 3.x |
| Grafice | Recharts | 2.x |
| Scanner QR | html5-qrcode | 2.x |
| Backend | FastAPI | 0.109 |
| Server ASGI | Uvicorn | 0.27 |
| ORM | SQLAlchemy | 2.x |
| Autentificare | JWT (PyJWT) + TOTP (pyotp) | — |
| OCR | easyocr | 1.7+ |
| QR generare | qrcode | 7.4 |
| Baza de date | PostgreSQL 16 | Docker container (`docker-compose up -d db`) |
| Baza de date (prod) | PostgreSQL | 15+ |
| Containerizare | Docker + Docker Compose | — |

---

## Fluxul unei cereri HTTP

```mermaid
sequenceDiagram
    participant B as Browser
    participant P as Proxy :8765
    participant A as FastAPI :8000
    participant D as PostgreSQL DB

    B->>P: GET /api/documents/me
    P->>A: GET /documents/me (forward)
    A->>A: Decodare JWT token
    A->>D: SELECT * FROM source_documents WHERE user_id=?
    D-->>A: Rows
    A-->>P: JSON response
    P-->>B: JSON response
```
