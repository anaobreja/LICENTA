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

- Autentificare JWT + MFA (TOTP) opțional
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
- Baza de date: 18 tabele, normalizată 3NF (PostgreSQL)
- Containerizare Docker + Docker Compose (varianta PostgreSQL)
- **Verificare offline a cardului digital prin semnături Ed25519** (controlorul poate valida QR-ul fără semnal — vezi secțiunea dedicată mai jos)
- **Test automate**: 150 teste backend (pytest) + 19 teste frontend (Node + Web Crypto API), toate trec

### Work in progress / Limitări cunoscute

- **Aplicație web mobilă / deploy în cloud** - urmează ca platforma să fie publicată pe un serviciu cloud (Render / Railway.app), accesibilă de pe orice dispozitiv fără rulare locală; momentan aplicația rulează local și poate fi accesată de pe telefon în aceeași rețea (vezi secțiunea de mai jos)
- Prezentare selectivă a credențialelor (student alege ce claims să dezvăluie)
- Dashboard de fraudă / anomalii (token reutilizat, respingeri repetate)

---

## Verificare offline cu semnături Ed25519

Aplicația implementează **verificarea offline** a cardului digital — un caz de utilizare real pe trenurile CFR: controlorul intră într-un tunel sau zonă cu semnal slab (Predeal, Valea Prahovei, dealuri din Apuseni) și trebuie să valideze totuși biletul. Soluția standard în PKI: semnături digitale asimetrice.

### Cum funcționează

```
┌─────────────────┐                            ┌──────────────────────┐
│     SERVER      │   GET /verification-key    │  APLICAȚIE CONTROLOR │
│                 │ ─────────────────────────► │                      │
│  cheie PRIVATĂ  │   (o singură dată/24h)     │  cheie PUBLICĂ       │
│  (semnează)     │ ◄───────────────────────── │  (verifică local)    │
└─────────────────┘                            └──────────────────────┘
        │                                                 ▲
        │                                                 │
        │     POST /card/present                          │
        │ ◄─────── student cere token ──────              │
        │                                                 │
        │     răspuns: { offline_token: "..." }           │
        │ ─────► offline_token = base64(payload).base64(signature)
        │                                                 │
        │                                                 │
        ▼                                                 │
   ┌────────────┐    QR scanat de telefon controlor   ────┘
   │ STUDENT    │ ─────────────────────────────────────►  VERIFICĂ local cu cheia publică
   │ telefon    │                                         (FĂRĂ INTERNET)
   └────────────┘
```

### Componente implementate

| Componentă | Locație | Rol |
|---|---|---|
| Modul criptografic | `backend/app/core/signing.py` | Generare/încărcare cheie Ed25519, semnare payload, verificare server-side |
| Endpoint distribuție cheie publică | `GET /verification-key` (router `crypto_keys.py`) | Returnează cheia publică în PEM + raw base64 |
| Emitere token semnat | Extensie la `POST /card/present` | Răspunsul include `offline_token` cu semnătura + `kid` |
| Verificare client-side | `frontend/src/services/api.js` (`verifyOfflineToken`) | Web Crypto API: importKey raw + verify Ed25519 |
| UI controlor | `frontend/src/pages/VerifyPresentation.jsx` | Toggle "Mod offline" cu indicator vizual și refresh manual al cheii |
| Cache cheie | `localStorage` (TTL 24h, `getVerificationKey`) | Evită refetch la fiecare scanare; refresh forțat dacă `kid` s-a schimbat |

### Garanții de securitate

| Atac | Apărare |
|---|---|
| **Tampering** (modificare payload) | Semnătura Ed25519 e calculată pe payload-ul exact. Orice modificare a unui byte invalidează semnătura. |
| **Spoofing** (token emis de altcineva) | Doar serverul are cheia privată. Tokenuri semnate cu altă cheie eșuează la verificare. |
| **Forge signature** (semnătură falsă) | Ed25519 = securitate echivalentă cu 128 biți; imposibil de spart cu hardware actual. |
| **Replay** (refolosire token expirat) | Câmpul `exp` în payload e validat la verificare. TTL implicit: 3 minute. |
| **Replay în fereastra de validitate** | LIMITARE: în mod offline nu putem detecta că tokenul a fost deja folosit. Atac mitigat de TTL scurt + verificare online ulterioară când există semnal. |

### Format token

```
<base64url(canonical_json_payload)>.<base64url(signature_64_bytes)>
```

Payload semnat (JSON canonical, sort_keys + separatori compacți):

```json
{
  "sub": 42,                      // user_id (identificator stabil)
  "pid": 1234,                    // presentation_id (sync ulterioară)
  "card": 7,                      // card_id
  "holder": "Demo User",          // nume complet (afișat pe ecran controlor)
  "claims": ["student_verified"], // credențiale active relevante
  "issuer": "UPB",                // universitatea emitentă (scurt)
  "iat": "2026-06-05T17:30:00Z",  // emitere
  "exp": "2026-06-05T17:33:00Z",  // expirare (validat la verify)
  "kid": "4a26bbbdd9c41066"       // key id (pentru rotire)
}
```

### Dimensiuni

* **Cheie publică Ed25519**: 32 bytes raw (44 chars base64) — descărcată o dată
* **Semnătură Ed25519**: 64 bytes
* **Token complet**: ~280 caractere — încape lejer într-un QR de versiunea 14
* **Verificare**: O(1), sub 1 ms pe orice telefon din ultimii 5 ani

### Persistența cheii

* Cheia privată: `backend/keys/signing_ed25519.pem` (PKCS#8 PEM, **niciodată committed**, în `.gitignore`)
* Auto-generare la primul startup dacă lipsește (cu warning explicit în log)
* În producție ar fi pre-provisionată via secrets manager (Render env vars, AWS KMS, etc.)

### Demo

1. Login `agent.train@railwaydemo.com` / `demo2026`
2. Mergi la **Verificare card digital**
3. Activează toggle-ul **"Offline"** (sus-dreapta)
4. Pune telefonul în **mod avion**
5. Scanează QR-ul de pe telefonul unui student → **ECRAN VERDE**, fără semnal

### Teste

Suite-ul este organizat pe niveluri de testare. Toate testele de mai jos
trec curent (fara skipped, fara warnings critice).

```bash
# === BACKEND (150 teste pytest, organizate in 4 categorii) ===

# Tot suite-ul backend:
cd backend && pytest tests/ -v

# Doar testele unit (rapide, fara DB integration grea):
cd backend && pytest tests/unit -v

# Doar testele de integrare API + DB:
cd backend && pytest tests/integration -v

# Doar end-to-end (flow complet student -> agent -> conductor):
cd backend && pytest tests/e2e -v

# Subset focalizat pe componenta criptografica (cele mai relevante pentru
# capitolul de securitate al lucrarii):
cd backend && pytest tests/unit/test_signing.py tests/unit/test_crypto_keys.py tests/integration/test_offline_presentation.py -v

# Load testing (separat - necesita backend pornit):
cd backend && locust -f tests/performance/locustfile.py --host http://127.0.0.1:8000


# === FRONTEND (19 teste pe verificarea offline a tokenurilor) ===

cd frontend && npm test
# Echivalent:
cd frontend && node tests/test_offline_verify.mjs
```

**De ce aceasta acoperire este suficienta pentru lucrare:**

- `tests/unit/test_signing.py` + `tests/unit/test_crypto_keys.py` testeaza
  pe partea de server: semnare Ed25519 determinista, expirare, tampering,
  serializare canonical JSON, persistenta cheilor.
- `tests/integration/test_offline_presentation.py` testeaza flow-ul real
  prin API: student genereaza token semnat -> backend ofera cheia publica
  -> verificare independenta cu `cryptography`.
- `frontend/tests/test_offline_verify.mjs` (19 teste) inchide bucla pe
  partea de client: dovedeste ca `verifyOfflineToken` din browser produce
  aceleasi rezultate ca `signing.py` din backend, inclusiv pe edge case-uri
  de base64url (padding 0/1/2 chars, caractere unicode, semnaturi
  modificate, chei substituite, expirare).

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
3. Inițializează baza de date PostgreSQL cu date demo
4. Pornește aplicația

Aplicația devine disponibilă la: **http://127.0.0.1:8765**

**Porturi folosite:**

| Port | Serviciu | Folosit pentru |
|------|----------|----------------|
| `8765` | Proxy frontend + API | Acces principal la aplicație |
| `8000` | FastAPI direct (uvicorn) | API docs (`/docs`), debug |
| `5432` | PostgreSQL (docker) | Doar la rularea testelor backend |
| `8089` | Locust web UI | Doar la rularea load tests |

> La prima utilizare a funcției **Scanează CI**, se descarcă modelele easyocr (~800MB). Ulterior funcționează offline.

---

## Conturi demo (parola pentru toate: `demo2026`)

| Rol | Email | Acces |
|-----|-------|-------|
| Pasager (demo) | `user.demo@railwaydemo.com` | Dashboard, Documente, Card Digital |
| Agent universitar UPB | `agent.upb@railwaydemo.com` | Dashboard agent, cereri UPB |
| Agent universitar ASE | `agent.ase@railwaydemo.com` | Dashboard agent, cereri ASE |
| Agent universitar UNIBUC | `agent.unibuc@railwaydemo.com` | Dashboard agent, cereri UNIBUC |
| Agent tren (verificare card) | `agent.train@railwaydemo.com` | Verificare card digital |
| Pasager (date reale demo) | `alexandra.popescu@email.com` | Pasager cu date demo |

---

## Flux demo recomandat pentru prezentare

### Partea 1 — Înregistrare și depunere documente (utilizator nou)

1. **Înregistrare** cont nou (`/register`) cu email și parolă
2. **Login** cu noul cont → Dashboard (stepper la pasul 1 — „Cont creat")
3. **Documente** → apasă „Scanează CI" → fotografiezi CI-ul → datele se completează automat din MRZ (nume, serie, dată naștere, sex)
4. Completează legitimația de student, selectează universitatea și anul → **Trimite cererea**
5. Dashboard → stepper avansat la pasul 2 — „Documente depuse / În așteptare" (badge portocaliu pulsând)
6. **Login** ca `agent.upb@railwaydemo.com / demo` → Dashboard agent → cererea apare cu datele CI și poza legitimației → **Aprobă**

### Partea 2 — Card digital activ (utilizator demo cu credențiale gata)

7. **Login** ca `user.demo@railwaydemo.com / demo` → Dashboard (stepper la pasul 4 — „Card activ", credențiale active)
8. **Card Digital** → apasă „Generează token dinamic" → apare QR cu countdown 120 secunde
9. Tap pe QR → se deschide fullscreen (ideal pe telefon, prezentat agentului)
10. **Login** ca `agent.train@railwaydemo.com / demo` → Verificare card → scanează QR → ecran **VERDE VALID** + claims pasager

---

## Structura proiectului

    LICENTA/
    ├── run.py                  — Script de pornire (un singur fișier)
    ├── start.bat               — Dublu-click pentru pornire pe Windows
    ├── proxy_server.py         — Server web + proxy API
    ├── requirements-run.txt    — Dependențe Python minime
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
    ├── docs/                   — Diagrame (use case, arhitectură, ER, secvență)
    │
    └── database/
        ├── schema.sql          — Schema PostgreSQL (18 tabele)
        └── queries.sql         — 50+ interogări reprezentative

---

## Baza de date

**PostgreSQL 16** (pornit prin `docker-compose up -d db`) — schema încărcată automat din `database/schema.sql`.

**PostgreSQL** (opțional) — setează în `.env`:

    DATABASE_URL=postgresql://user:pass@localhost:5432/railway_db

Apoi aplică schema: `psql -d railway_db -f database/schema.sql`

Vizualizare baza de date: **[DBeaver](https://dbeaver.io/)** sau **[pgAdmin](https://www.pgadmin.org/)** (gratuit, conexiune `postgresql://railway:railway_dev@localhost:5432/railway_db`)

---

## Modificare frontend (necesită Node.js)

    cd frontend
    npm install
    npm run build

---

## Acces de pe telefon și scanare QR

### Accesare de pe telefon (aceeași rețea WiFi)

1. Află IP-ul laptopului în CMD: `ipconfig` → caută „IPv4 Address" la adaptorul WiFi
2. Asigură-te că aplicația rulează (`python run.py` sau `start.bat`)
3. Pe telefon, deschide browser-ul și accesează: `http://<IP-laptop>:8765`

Exemplu: dacă IP-ul e `172.20.10.13` → `http://172.20.10.13:8765`

### Scanare QR card digital

Fluxul complet pe două dispozitive:

1. **Pasager (telefon)** → login `pasager.demo@railwaydemo.com` / `demo2026` → Card Digital → apasă „Generează token dinamic" → apare QR cu countdown 120 secunde
2. **Agent tren (laptop sau alt telefon)** → login cu `agent.train@railwaydemo.com / demo` → Verificare card → pornește camera → scanează QR-ul pasagerului
3. Apare ecran **VERDE (VALID)** sau **ROȘU (INVALID)** timp de 2 secunde, apoi detaliile cardului

> Dacă camera nu funcționează la scanare, se poate introduce manual token-ul din câmpul text de sub QR.

### Acces public temporar (fără WiFi comun)

Folosind **ngrok** (gratuit), poți expune aplicația pe internet:

    ngrok http 8765

Se generează un URL de tipul `https://abc123.ngrok.io` — funcționează de pe orice rețea, cât timp laptopul rulează.

---

## Documentație API (Swagger)

Cu aplicația pornită: **http://127.0.0.1:8000/docs**

---

## Tehnologii utilizate

| Componentă | Tehnologie |
|-----------|-----------|
| Backend | FastAPI + Python 3.10+ |
| Bază de date | PostgreSQL 16 (Docker) |
| ORM | SQLAlchemy |
| Autentificare | JWT + TOTP MFA |
| OCR documente | easyocr (MRZ parsing) |
| Frontend | React 18 + Vite + Tailwind CSS |
| Grafice | Recharts |
| QR codes | qrcode + html5-qrcode |
