# Platformă Digitală de Identitate — Lucrare de Licență

Sistem de gestionare a **identității digitale** pentru studenți, cu verificare prin agenți universitari, card digital QR și audit complet.

---

## Diagrame

| Diagramă | Fișier |
|----------|--------|
| Use Case | [docs/use-case.md](docs/use-case.md) |
| Arhitectură | [docs/architecture.md](docs/architecture.md) |
| Model de date (ER) | [docs/er-diagram.md](docs/er-diagram.md) |
| Diagrame de secvență | [docs/sequence.md](docs/sequence.md) |

---

## Stadiu implementare

### Implementat complet

- Autentificare JWT + MFA (TOTP) optțional
- Înregistrare utilizatori cu roluri: `passenger`, `university_agent`, `train_verifier`, `issuer_verifier`
- Scanare automată CI prin OCR (easyocr, MRZ parsing TD2 — format CI românesc)
- Depunere cerere de verificare identitate (CI + legitimație student)
- Dashboard agent universitar cu statistici și grafice (Recharts): distribuție pe an, activitate 30 zile
- Filtrare cereri după an de studiu (Licență 1-4, Master 1-2)
- Aprobare / Respingere cereri cu motiv, emitere automată credențiale
- Card digital QR cu countdown vizual (120 secunde, auto-regenerare)
- Verificare card digital cu ecran VERDE/ROȘU (agent tren)
- Progress stepper pe dashboard pasager (4 pași)
- Notificări in-app cu badge în navbar
- Export date personale (GDPR)
- Baza de date: 12 tabele, normalizată 3NF (SQLite dev / PostgreSQL prod)
- Containerizare Docker + Docker Compose (varianta PostgreSQL)

### Work in progress / Limitări cunoscute

- Integrarea cu baze de date universitare reale (momentan simulată prin tabelul `university_students`)
- Verificarea offline a cardului digital (fără internet)
- Prezentare selectivă a credențialelor (student alege ce claims să dezvăluie)
- Dashboard de fraudă / anomalii (token reutilizat, respingeri repetate)
- Teste automate (unit + integration)

---

---

## Cerințe minime

- **Python 3.10+** instalat cu opțiunea „Add to PATH" bifată
- Windows 10/11

Nu este nevoie de Node.js, PostgreSQL sau Docker pentru rularea de bază.

---

## Pornire rapidă (recomandat)

### Varianta 1 — dublu-click

Dublu-click pe fișierul **`start.bat`** din folderul proiectului.

### Varianta 2 — terminal PowerShell

    cd D:\LICENTA
    python run.py

La **prima rulare** scriptul:
1. Creează automat mediul virtual `.venv`
2. Instalează toate dependențele Python (~2-3 minute)
3. Inițializează baza de date SQLite cu date demo
4. Pornește aplicația

Aplicația devine disponibilă la: **http://127.0.0.1:8765**

> La prima utilizare a funcției **Scanează CI**, se descarcă modelele easyocr (~800MB). Ulterior funcționează offline.

---

## Conturi demo (parola pentru toate: `demo`)

| Rol | Email | Acces |
|-----|-------|-------|
| Pasager (demo) | `user.demo@railwaydemo.com` | Dashboard, Documente, Card Digital |
| Agent universitar UPB | `agent.upb@railwaydemo.com` | Dashboard agent, cereri UPB |
| Agent universitar ASE | `agent.ase@railwaydemo.com` | Dashboard agent, cereri ASE |
| Agent universitar UNIBUC | `agent.unibuc@railwaydemo.com` | Dashboard agent, cereri UNIBUC |
| Agent tren (verificare card) | `agent.train@railwaydemo.com` | Verificare card digital |
| Issuer verifier (admin) | `agent.issuer@railwaydemo.com` | Aprobare documente |
| Pasager (date reale demo) | `alexandra.popescu@email.com` | Pasager cu date demo |

---

## Flux demo recomandat pentru prezentare

1. **Login** ca `user.demo@railwaydemo.com` → Dashboard (stepper identitate)
2. **Documente** → Scanează CI → completează legitimație → trimite
3. **Login** ca `agent.upb@railwaydemo.com` → Dashboard agent → aprobă cererea
4. **Login** din nou ca pasager → Dashboard (stepper avansat la „Card activ")
5. **Card Digital** → generează QR cu countdown
6. **Login** ca `agent.train@railwaydemo.com` → Verificare card → ecran verde VALID

---

## Structura proiectului

    LICENTA/
    ├── run.py                  — Script de pornire (un singur fișier)
    ├── start.bat               — Dublu-click pentru pornire pe Windows
    ├── proxy_server.py         — Server web + proxy API
    ├── requirements-run.txt    — Dependențe Python minime
    ├── railway_demo.db         — Baza de date SQLite (creată automat)
    │
    ├── backend/
    │   └── app/
    │       ├── main.py         — FastAPI entry point
    │       ├── core/           — Configurare, securitate, baza de date
    │       └── routers/        — Endpoint-uri API (auth, users, identity)
    │
    ├── frontend/
    │   ├── dist/               — Build static (servit de proxy_server.py)
    │   └── src/                — Cod sursă React (modificare necesită rebuild)
    │
    └── database/
        ├── schema.sql          — Schema PostgreSQL (18 tabele)
        └── queries.sql         — 50+ interogări reprezentative

---

## Baza de date

**SQLite** (implicit, zero configurare) — fișier `railway_demo.db` creat automat.

**PostgreSQL** (opțional) — setează în `.env`:

    DATABASE_URL=postgresql://user:pass@localhost:5432/railway_db

Apoi aplică schema: `psql -d railway_db -f database/schema.sql`

Vizualizare baza de date: **[DB Browser for SQLite](https://sqlitebrowser.org/dl/)** (gratuit)

---

## Modificare frontend (necesită Node.js)

    cd frontend
    npm install
    npm run build

---

## Documentație API (Swagger)

Cu aplicația pornită: **http://127.0.0.1:8000/docs**

---

## Tehnologii utilizate

| Componentă | Tehnologie |
|-----------|-----------|
| Backend | FastAPI + Python 3.10+ |
| Bază de date | SQLite (demo) / PostgreSQL (producție) |
| ORM | SQLAlchemy |
| Autentificare | JWT + TOTP MFA |
| OCR documente | easyocr (MRZ parsing) |
| Frontend | React 18 + Vite + Tailwind CSS |
| Grafice | Recharts |
| QR codes | qrcode + html5-qrcode |
