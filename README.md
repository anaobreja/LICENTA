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
- Baza de date: 25 tabele organizate în 4 module logice (identitate, transport feroviar, bilete, audit), normalizată 3NF (PostgreSQL)
- Containerizare Docker + Docker Compose (varianta PostgreSQL)
- **Verificare offline a cardului digital prin semnături Ed25519** (controlorul poate valida QR-ul fără semnal — vezi secțiunea dedicată mai jos)
- **Sistem complet de bilete cu logică CFR realistă**: selecție loc real-time (hold 5 min), anti-overlap pe intervale orare, anulare cu refund pe trepte (100% / 50% / 0%), reprogramare pe același traseu — vezi secțiunea dedicată mai jos
- **Imutabilitate date personale după validare**: câmpurile CNP, nume, data nașterii și stația de domiciliu devin frozen până la expirarea verificării (1 octombrie, începutul anului universitar următor). Previne identity laundering.
- **Abonamente CFR cu scope pe ruta** (`monthly`/`annual`): cumparare cu reducere 90% pentru studenti pe ruta home <-> universitate (OUG 11/2024), anti-overlap pe ruta, anulare cu refund pro-rata. Biletele pe ruta acoperita devin automat gratuite (price=0, marcate cu `uses_subscription_id`). Notificare 7 zile inainte de expirare. Vezi sectiunea dedicata mai jos.
- **Harta feroviara interactiva cu trasee reale CFR**: vizualizare ruta pe OpenStreetMap + OpenRailwayMap, polilinia urmeaza sina prin toate statiile intermediare cu GPS, markerele afiseaza DOAR opririle comerciale reale ale trenului (filtrate prin `is_commercial_stop` din XML CFR/Ferotrafic). Operatorul fiecarui tren (CFR Calatori, Ferotrafic, Regio Calatori, Astra Trans Carpatic, etc.) e afisat explicit langa numarul trenului — utilizatorul vede clar diferentele intre operatori (ex: IC 553 CFR opreste la Ploiesti Sud, IC 11762 Ferotrafic NU opreste, conform XML oficial). Vezi sectiunea "Harta feroviara" mai jos.
- **Pipeline de geocoding GPS multi-pass cu trasabilitate completa**: cele 1818 statii CFR au fost geocodate automat (99.5% acoperire) prin OpenStreetMap (Overpass + Nominatim) + interpolare iterativa din vecinii pe rute, cu blacklist persistent pentru outlieri. ZERO coordonate hardcodate. Sursa fiecarei coordonate (`gps_source`) e trasabila in DB cu tier-uri A-F (manual / OSM-exact / OSM-bbox / interpolare / Nominatim / legacy). Vezi sectiunea "Calitatea datelor GPS" mai jos.
- **Test automate**: **533 teste totale**, toate trec:
  - **489 teste backend** (pytest) — 36 fișiere organizate în 3 categorii:
    - `tests/unit/` (9 fișiere, ~135 teste) — logică pură: auth, crypto/signing Ed25519, MRZ parsing, refund matrix, security primitives, tickets, uploads, users
    - `tests/integration/` (26 fișiere, ~353 teste) — API + DB end-to-end: auth_mfa, cross_university_security, identity, journey_quote, map_route_geometry, multi_passenger, offline_presentation, performance_smoke, personal_route, profile_freeze, qr_lifecycle, seat_concurrency, security_inputs, subscriptions, ticket_validation, trip_planner, etc.
    - `tests/e2e/` (1 fișier, 1 test) — flow complet student → agent → conductor
  - **25 teste frontend Vitest** (`frontend/tests/pages/`) — UI pages cu MSW mocks: BuyTicket, Documents, MyTickets
  - **19 teste frontend Node + Web Crypto API** (`frontend/tests/test_offline_verify.mjs`) — verifică că `verifyOfflineToken()` din browser produce aceleași rezultate ca `signing.py` din backend (paritate cross-platform Ed25519, edge case-uri base64url padding, tampering, expirare)

### Work in progress / Limitări cunoscute

- **Aplicație web mobilă / deploy în cloud** - urmează ca platforma să fie publicată pe un serviciu cloud (Render / Railway.app), accesibilă de pe orice dispozitiv fără rulare locală; momentan aplicația rulează local și poate fi accesată de pe telefon în aceeași rețea (vezi secțiunea de mai jos)
- Prezentare selectivă a credențialelor (student alege ce claims să dezvăluie)
- Dashboard de fraudă / anomalii (token reutilizat, respingeri repetate)
- **9 stații (din 1818) rămân fără GPS** — toate sunt ramificații tehnice fără reprezentare în OpenStreetMap (ex: `Ram. Pav. C.F.R.`, `Ramificația C.S.G.`) sau gări din Bulgaria fără nume normalizate (Vidin, Kapitanovci). Doar 3 sunt comerciale, restul sunt puncte tehnice de trecere care nu apar oricum în UI (filtrate prin `is_commercial_stop`). Soluția: integrare cu o sursă oficială pentru poziții fizice de cale ferată (de ex. CFR Infrastructură).

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
# === BACKEND (489 teste pytest, organizate in 3 categorii) ===

# Tot suite-ul backend:
cd backend
python -m pytest tests/ -v

# Doar testele unit (~135 teste, rapide, fara DB):
python -m pytest tests/unit -v

# Doar testele de integrare API + DB (~353 teste):
python -m pytest tests/integration -v

# Doar end-to-end (1 test, flow complet student -> agent -> conductor):
python -m pytest tests/e2e -v

# Subset focalizat pe componenta criptografica (cele mai relevante pentru
# capitolul de securitate al lucrarii):
python -m pytest tests/unit/test_signing.py tests/unit/test_crypto_keys.py tests/integration/test_offline_presentation.py -v

# Cu raport de code coverage (genereaza htmlcov/index.html):
python -m pytest tests/ --cov=app --cov-report=html --cov-report=term

# Load testing (separat - necesita backend pornit):
locust -f tests/performance/locustfile.py --host http://127.0.0.1:8000


# === FRONTEND (44 teste totale, in doua sisteme) ===

cd frontend

# 25 teste Vitest pentru pagini UI cu MSW mocks (BuyTicket, Documents, MyTickets):
npm test

# 19 teste pe verificarea offline Ed25519 (Node + Web Crypto API,
# fara dependinte externe -- dovedesc paritatea cross-platform browser <-> Python):
node tests/test_offline_verify.mjs
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

## Sistem de bilete avansat

Pe lângă identitatea digitală, platforma include un modul complet de
vânzare bilete cu logică de business realistă (inspirat de regulamentul
CFR Călători).

### Funcționalități

| Capacitate | Detalii |
|---|---|
| **Anti-overlap** | Sistemul refuză cumpărarea unui bilet dacă utilizatorul are deja un bilet activ pe un interval orar suprapus (HTTP 409 cu detalii despre conflict). |
| **Selecție de loc real-time** | Hartă interactivă a vagoanelor cu locuri marcate liber / rezervat / vândut. Click pe loc → hold de 5 minute. Polling la 5s pentru actualizare live. |
| **Vagoane variabile per tip tren** | Regio = 3 vagoane (180 locuri), InterRegio = 5 (300), InterCity = 7 (420). Vagonul 1 = clasa 1, restul clasa 2. Layout 2+2 (A·B │ C·D). |
| **Anulare cu refund pe trepte CFR** | >24h înainte de plecare → 100% refund. 1m–24h → 50%. După plecare → 0%. Locurile redevin instant disponibile pentru alți useri. |
| **Reprogramare pe același traseu** | Permisă doar pe trenuri cu aceleași stații de plecare/sosire. Diferența de preț nu se restituie (conform CFR). Lanț de bilete legate prin `rescheduled_from/to_ticket_id`. |

### Arhitectură (4 tabele noi)

```
train_cars         — vagoanele unui tren (numar, capacitate, clasa)
seats              — locurile individuale dintr-un vagon (label '14B', is_window, etc.)
seat_reservations  — hold-uri temporare 5 minute pe (seat, travel_date)
ticket_seats       — locuri vândute, legate de un ticket activ
```

Plus coloane noi pe `tickets`: `cancelled_at`, `cancel_refund_amount`,
`rescheduled_from_ticket_id`, `rescheduled_to_ticket_id`.

### Endpoint-uri noi

| Metodă | Path | Descriere |
|---|---|---|
| `GET` | `/trains/{id}/seats?travel_date=YYYY-MM-DD` | Layout-ul trenului + status per loc (free / held / sold / mine_*) |
| `POST` | `/seats/hold` | Rezervă temporar un loc (5 minute) |
| `POST` | `/seats/release` | Eliberează un hold (idempotent) |
| `POST` | `/tickets/{id}/cancel` | Anulare + refund automat conform trepte CFR |
| `POST` | `/tickets/{id}/reschedule` | Reprogramare pe alt tren cu același traseu |

### Demo "wow" la aparăre

Sistemul permite un demo live impresionant pe **două device-uri**:

1. **Laptop:** login `user.demo` → BuyTicket → selectezi tren IR → vezi harta cu toate locurile libere.
2. **Click pe loc 14B în Vagon 2** → devine galben (rezervat pentru tine).
3. **Telefon:** login `pasager.demo` → același tren → **vezi locul 14B deja gri (indisponibil)**.
4. **Laptop:** confirmi cumpărarea → 14B devine roșu (vândut).
5. **Laptop:** apesi "Anulează" → în 2 secunde, pe telefon locul 14B revine la verde.

### Teste (18 noi, toate trec)

Backend: `tests/integration/test_seats.py`. Acoperă 5 categorii:

- **Anti-overlap** (4 teste): suprapunere exactă, parțială, date diferite, useri diferiți
- **Refund tiers** (3 teste): >24h, 1–24h, după plecare
- **Cancel** (4 teste): full refund, nu de 2 ori, doar own ticket, recumpărare după cancel
- **Seat hold flow** (5 teste): layout, hold, release, conflict cu alt user, buy cu locuri
- **Reschedule** (2 teste): același traseu OK, traseu diferit → 409

---

## Abonamente CFR (Subscriptions)

Sistemul implementeaza abonamente cu scope pe **ruta** (origin <-> destination),
inspirat de produsele CFR Calatori (lunar / anual) si de prevederile **OUG 11/2024**
pentru reducerea de student.

### Reguli de business

| Capacitate | Detalii |
|---|---|
| **Tipuri** | `monthly` (30 zile) sau `annual` (365 zile, multiplier x10 = "2 luni gratis") |
| **Scope** | Pe ruta specifica (acopera direct trenuri intre `from_station_id` <-> `to_station_id`, in ambele directii) |
| **Pret** | Formula: `(distance_km * 0.5 + 50) * multiplier_type`. Reducere **90% DOAR pe ruta home <-> universitate** pentru studentii cu credential `student_verified` activ. Pe alte rute = pret intreg, indiferent ca esti student. |
| **Anti-overlap** | Un singur abonament `active` per (user, ruta) — directiile contează in pereche, nu se pot suprapune Buc->Cluj cu Cluj->Buc |
| **Integrare bilete** | Bilet cumparat pe ruta acoperita -> **price=0 automat**, `uses_subscription_id` setat in DB. Funcționează la /tickets/buy fara cod aditional. |
| **Anulare** | Refund pro-rata: `full_not_started` daca abonamentul nu a inceput, `partial_pro_rata` (zile neutilizate × 0.5 penalty CFR) daca < 50% folosit, `0%` dupa. |
| **Lazy expire** | La fiecare `GET /subscriptions/my`, abonamentele cu `valid_until < azi` sunt marcate automat `expired` (fara cron). |
| **Notificare 7 zile** | La GET /my, daca exista abonament activ cu `valid_until` in <=7 zile, sistemul insereaza automat o notificare "expira curand". |

### Arhitectura DB

Migrarea `07_subscriptions_route_scope.sql` adauga pe `subscriptions`:

```
from_station_id    INT FK -> stations    -- statia de plecare a rutei
to_station_id      INT FK -> stations    -- statia de sosire
subscription_scope VARCHAR(20)           -- 'network' | 'route' (default 'route')
route_distance_km  NUMERIC(8,2)          -- cache pentru calcul rapid pret
```

Plus pe `tickets`:
```
uses_subscription_id INT FK -> subscriptions  -- marcheaza bilet cumparat via abonament
```

Constraint critic:
```sql
CHECK (subscription_scope != 'route'
       OR (from_station_id IS NOT NULL
           AND to_station_id IS NOT NULL
           AND from_station_id != to_station_id))
```

### Endpoint-uri noi

| Metoda | Path | Descriere |
|---|---|---|
| `POST` | `/subscriptions/quote` | Preview pret cu reducere conditionata (fara DB write) |
| `POST` | `/subscriptions/buy` | Cumparare cu anti-overlap |
| `GET` | `/subscriptions/my` | Lista mea (sortat active > expired > cancelled). Trigger lazy expire + notificare 7 zile. |
| `POST` | `/subscriptions/{id}/cancel` | Anulare cu refund pro-rata CFR |

### Scenariu demo "wow"

1. **Login** `pasager.demo`. Mergi la **Abonamente** -> "Cumpara abonament nou".
2. Selecteaza statiile de plecare/sosire. Daca esti student verificat si selectezi home <-> univ, **reducerea 50% apare in preview live**. Pe alte rute, pret intreg.
3. Confirma cumpararea -> abonament activ, valabil 30 zile.
4. Mergi la **Bilete** -> selecteaza acelasi traseu + aceeasi data.
5. **Banner verde**: "Acoperit de abonament. Biletul va fi GRATUIT (0 RON)".
6. Confirma -> bilet emis cu `price=0`, `uses_subscription_id=N`. QR token genereaza normal -> poate fi validat in tren ca orice bilet normal.

### Teste (20 noi, toate trec)

Backend: `tests/integration/test_subscriptions.py`. 6 categorii:

- **Formula pret** (4 unit tests): monthly/annual cu/fara reducere
- **Refund pro-rata** (3 unit tests): full_not_started, partial, more_than_half
- **Quote endpoint** (3): fara reducere, cu reducere home<->univ, fara reducere pe alta ruta
- **Buy + anti-overlap** (4): creeaza activ, overlap same direction, overlap reverse, multiple rute OK
- **Cancel** (3): refund OK, alt user 403, double cancel 409
- **Lazy expire** (1): valid_until trecut -> status='expired' la GET
- **Integrare bilete** (2): bilet pe ruta acoperita = 0 RON, pe alta = pret normal

---

---

## Harta feroviara interactiva

Aplicatia include o **harta a retelei feroviare CFR** cu vizualizare interactiva a traseelor pentru orice pereche origine-destinatie din cele 1818 statii.

### Datele utilizate

Datele sunt importate din **XML-urile oficiale** publicate pe [data.gov.ro](https://data.gov.ro/) de catre cei 7 operatori feroviari romani:

| Operator | XML | Trenuri |
|----------|-----|---------|
| SNTFC CFR Călători S.A. | `cfr_sntfc.xml` | 1256 |
| Regio Călători S.R.L. | `regio.xml` | 273 |
| Transferoviar Călători S.R.L. | `tfc.xml` | 303 |
| Interregional Călători S.R.L. | `interregional.xml` | 216 |
| Astra Trans Carpatic S.R.L. | `astra.xml` | 21 |
| Softrans S.R.L. | `softrans.xml` | 16 |
| Ferotrafic TFI S.R.L. | `ferotrafic.xml` | 18 |

Total: **2103 trenuri active**, **46.501 opriri**, **1818 statii** (importate prin `database/import_cfr.py`).

### Distinctia intre statii de oprire si statii de trecere

Atributul XML `TipOprire` per segment specifica daca trenul **opreste comercial** la o statie (`C` = oprire cu (de)imbarcare calatori, `StationareSecunde > 0`) sau **doar trece** prin ea (`N` = trecere tehnica, fara oprire). Sistemul mapeaza acest atribut in coloana `route_stops.is_commercial_stop` din DB.

**Endpoint-ul `GET /map/route-geometry` returneaza doua liste separate:**

- `stops` — DOAR opririle reale (comerciale + capete de leg) → afisate ca **markere violet pe harta**
- `geometry_points` — TOATE statiile cu GPS pe ruta (inclusiv tehnice de trecere) → folosite pentru **polilinia colorata** care urmeaza sina reala

Astfel polilinia urmeaza traseul real al caii ferate (de ex. Bucuresti → Buzau trece prin Mizil, Ploiesti, Inotesti), dar markerele violet apar **doar acolo unde trenul opreste cu adevarat** — diferit per operator!

**Exemplu concret**: pe ruta Bucuresti Nord ↔ Buzau exista 15 trenuri IC zilnice:

| Operator | Trenuri IC | Oprire la Ploiesti Sud? |
|----------|-----------|:----------------------:|
| **CFR Calatori** | 551, 553, 561, 564, 571 etc. | ✅ Toate opresc (120s stationare) |
| **Ferotrafic** | 11751, 11752, 11761, 11762 etc. | ❌ Niciuna nu opreste (strategie tren rapid) |

Operatorul fiecarui tren e afisat explicit langa numarul lui in UI-ul hartii pentru transparenta sursei.

### Calitatea datelor GPS

Cele 1818 statii CFR nu au coordonate in XML — au fost geocodate automat prin pipeline-ul `database/geocode_stations_v2.py`, in **7 pasuri**:

| Pas | Strategie | Stații recuperate |
|-----|-----------|:-----------------:|
| PASS 0 | Detect outlieri (salt > 60km vs km CFR) → blacklist | — (validare) |
| PASS 1 | Descarca OSM via Overpass API (railway=station/halt/stop in RO) | 4903 noduri |
| PASS 2 | Match exact dupa nume normalizat (NFKD + fix diacritice ț/ş) | 220 |
| PASS 3 | Match cu bbox contextual (intre vecinii cu GPS cunoscut) | 162 |
| PASS 4 | Fallback Nominatim (rate-limited 1 req/s) | 44 |
| PASS 4.5 | Interpolare iterativa din vecinii imediati pe rute | 112 |
| PASS 5 | Override manual (DEZACTIVAT — vezi nota mai jos) | 0 |

**Acoperire finala: 99.5% (1809/1818 statii)**, **0 outlieri** (verificat prin `gps_dist > 1.5 × cfr_dist + 20km`).

#### Decizie de design: ZERO coordonate hardcodate

Versiunile timpurii ale pipeline-ului foloseau ~29 override-uri manuale (statii cu GPS scris in cod, ex: Aeroport Otopeni T1, statii litoral). **Au fost eliminate complet** dintr-un considerent de onestitate stiintifica:

1. Hardcodarea ascunde gap-urile reale ale datelor sursei
2. O statie cu GPS hardcodat ar arata in DB la fel de "valida" ca una geocodata din OSM, desi sursa e diferita → compromite trasabilitatea pentru lucrarea academica
3. Mai bine 9 statii **raportate cinstit fara GPS** decat 0 statii cu GPS ghicit

Pipeline-ul actual recupereaza 26/29 statii automat (OSM exact + bbox + Nominatim + interpolare); cele 3 ramase comerciale (Berești, Balintești, Vidin Patnicheska) sunt **blacklisted explicit** ca outlieri detectati de algoritm.

#### Trasabilitate prin `gps_source`

Tabelul `stations` are coloana `gps_source` care pastreaza **provenienta exacta** a coordonatelor. Distribuția curentă (vizibilă în view-ul `v_stations_gps_summary`):

| Tier | Sursa | Statii |
|:----:|------|------:|
| A | manual (hardcodat) | **0** ⭐ |
| B | OSM exact / shorter / firstword | 47 |
| C | OSM cu validare bbox de ruta | 151 |
| D | interpolare iterativa din vecini | 110 |
| E | Nominatim fallback | 44 |
| F | geocodare initiala (pre-v2) | 1435 |
| - | blacklisted (outlieri detectati) | 3 |
| X | fara GPS (ramificatii tehnice) | 9 |

Documentatia completa a pipeline-ului si view-urile SQL de monitorizare: vezi `database/09_gps_quality_view.sql`.

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
        ├── schema.sql          — Schema PostgreSQL (25 tabele, 4 module)
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

Pentru a expune aplicația pe internet — util pentru demo de pe telefon fără să fie în aceeași rețea WiFi, sau pentru a permite cuiva să testeze de la distanță — există două opțiuni:

#### Opțiunea 1 — VS Code Dev Tunnels (recomandat)

**Cel mai simplu pentru workflow-ul de development**, fără cont separat, fără install — direct din VS Code:

1. Deschide aplicația și pornește frontend-ul (`npm run dev` în terminal, sau backend-ul prin `python run.py`)
2. În VS Code, deschide panoul **Ports** (Ctrl+\\` apoi click pe tab-ul **PORTS**, sau Command Palette → `Ports: Focus on Ports View`)
3. Click pe **Add Port** și introdu portul aplicației (ex: `5173` pentru Vite, `8765` pentru proxy_server.py)
4. Pe rândul portului adăugat, schimbă **Visibility** din `Private` în **`Public`** (click dreapta → `Port Visibility` → `Public`)
5. Copiază URL-ul din coloana **Forwarded Address** — va fi de forma:

       https://c9q8rq05-5173.euw.devtunnels.ms/

6. Deschide URL-ul de pe orice dispozitiv (telefon, alt laptop, altă rețea) — **funcționează imediat cu HTTPS valid**, fără să accepți certificate

**Avantaje față de ngrok**:
- Nu necesită cont sau autentificare separată (folosește contul GitHub/Microsoft din VS Code)
- HTTPS cu certificat valid din prima (camera de pe telefon merge fără warnings)
- URL stabil cât timp tunelul rămâne activ
- Tunelul se închide automat când închizi VS Code → nu rămâne deschis accidental

**Important**: dacă pornești și backend-ul separat, expune și portul `8000` cu vizibilitate Public, altfel apelurile API vor eșua.

#### Opțiunea 2 — ngrok (alternativă)

Dacă preferi un tool dedicat sau nu folosești VS Code:

    ngrok http 8765

Se generează un URL de tipul `https://abc123.ngrok-free.app` — funcționează similar, dar necesită cont ngrok gratuit pentru sesiuni mai lungi de 2 ore.

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
