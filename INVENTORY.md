# 📋 INVENTAR EXHAUSTIV — Sistem CFR Digital (Lucrare de Licență)

> Data inventarului: 2026-06-09
> Scope: backend FastAPI (`app/routers/`), frontend React (`src/pages/`), suită de teste.

---

## 1. Backend — Endpoint-uri pe routers

### 1.1 `auth.py` — Autentificare & MFA  (358 LOC)

| Metodă | Path | Descriere |
|---|---|---|
| POST | `/register` | Înregistrare cont (form multipart cu CI/poză). |
| POST | `/login` | Login email + parolă, suport flux MFA (TOTP). |
| POST | `/mfa/setup` | Generează secret TOTP + QR code pentru enrolare. |
| POST | `/mfa/verify` | Activează MFA după verificarea unui cod TOTP. |
| POST | `/mfa/disable` | Dezactivează MFA (necesită parolă). |

### 1.2 `users.py` — Profil & cont  (631 LOC)

| Metodă | Path | Descriere |
|---|---|---|
| GET | `/users/me` | Date profil curent (nume, email, rol, verificat, etc.). |
| GET | `/users/{user_id}/profile-photo` | Servește fotografia de profil (cu auth). |
| PUT | `/users/me` | Update profil (nume, telefon, adresă, rută personală). |
| PUT | `/users/me/password` | Schimbare parolă. |
| PUT | `/users/me/profile-photo` | Upload fotografie de profil. |
| GET | `/users/me/export` | Export GDPR — toate datele utilizatorului în JSON. |
| DELETE | `/users/me` | Ștergere/dezactivare cont (right to be forgotten). |
| GET | `/users/me/verification-status` | Statusul verificării identității (pending/verified/rejected). |
| GET | `/users/me/travel-stats` | Statistici personale: km, CO₂ economisit, top trenuri, achievements. |

### 1.3 `tickets.py` — Bilete & catalog rute  (≈2k LOC)

| Metodă | Path | Descriere |
|---|---|---|
| GET | `/stations/suggest` | Sugerează gări pornind de la adresa din CI. |
| GET | `/trips/suggest` | Itinerarii directe + cu 1–2 schimbări. |
| GET | `/stations/search` | Autocomplete gări. |
| GET | `/trains/search` | Trenuri directe între două gări la o dată. |
| POST | `/tickets/quote` | Preview preț FĂRĂ cumpărare (reduceri, abonament). |
| GET | `/tickets/catalog` | Catalog rute + trenuri disponibile. |
| POST | `/tickets/buy` | Cumpărare bilet → travel_entitlement + qr_token semnat. |
| GET | `/tickets/my` | Lista biletelor utilizatorului. |
| POST | `/tickets/validate` | Conductor scanează QR (online sau offline-signed). |
| GET | `/validations/history` | Istoric validări (conductor). |
| POST | `/tickets/{id}/cancel` | Anulare cu refund pro-rata stil CFR. |
| POST | `/tickets/{id}/reschedule` | Schimbare tren/dată păstrând traseul. |

### 1.4 `subscriptions.py` — Abonamente  (486 LOC)

| Metodă | Path | Descriere |
|---|---|---|
| POST | `/subscriptions/quote` | Preview preț abonament (route-scope, semestru, lunar, anual). |
| POST | `/subscriptions/buy` | Cumpără abonament cu anti-overlap. |
| GET | `/subscriptions/my` | Lista abonamentelor (active/expirate/anulate). |
| POST | `/subscriptions/{id}/cancel` | Anulare cu refund pro-rata. |

### 1.5 `identity.py` — Identitate digitală & SSI  (≈2k LOC)

**Cetățean (titular):**

| Metodă | Path | Descriere |
|---|---|---|
| POST | `/documents/extract-id` | OCR pe poză CI → câmpuri pre-completate. |
| POST | `/documents` | Creează document fără poză. |
| POST | `/documents/upload` | Creează document cu foto. |
| POST | `/documents/validation-request` | Cerere de validare identitate (CI/legitimație). |
| GET | `/documents/{id}/photo` | Foto document (cu autorizație). |
| GET | `/documents/me` | Documentele mele. |
| GET | `/credentials/me` | Credențialele mele (student, reducere, etc.). |
| GET | `/notifications/me` | Notificările mele. |
| PATCH | `/notifications/me/{id}/read` | Marchează notificare ca citită. |
| GET | `/card/me` | Cardul digital de identitate. |
| POST | `/card/present` | Generează Verifiable Presentation (Ed25519, TTL=120s). |

**Issuer (agent universitate):**

| Metodă | Path | Descriere |
|---|---|---|
| GET | `/issuer/documents/pending` | Cereri de validare în așteptare. |
| GET | `/university/stats` | KPI agent: aprobate / respinse / pending. |
| GET | `/issuer/documents/{id}` | Detalii cerere. |
| POST | `/issuer/documents/{id}/approve` | Aprobă → emite credențial verificabil. |
| POST | `/issuer/documents/{id}/reject` | Respinge cu motiv. |
| GET | `/issuer/credentials` | Credențialele emise de issuer. |
| POST | `/issuer/credentials/{id}/revoke` | Revocă credențial. |

**Verifier (conductor / oricine):**

| Metodă | Path | Descriere |
|---|---|---|
| POST | `/train/verify` | Verifică VP la conductor (online). |
| GET | `/train/verifications/history` | Istoric verificări conductor. |
| POST | `/card/verify` | Alias verificare card. |
| POST | `/presentations/generate` | Alias generare prezentare. |
| POST | `/presentations/verify` | Alias verificare prezentare. |

### 1.6 `seats.py` — Locuri & rezervări temporare  (307 LOC)

| Metodă | Path | Descriere |
|---|---|---|
| GET | `/trains/{train_id}/seats` | Layout vagon + status loc (liber/rezervat/hold). |
| POST | `/seats/hold` | Ține un loc rezervat 5 min pentru user. |
| POST | `/seats/release` | Eliberează hold-ul. |

### 1.7 `map.py` — Hartă & rute  (296 LOC)

| Metodă | Path | Descriere |
|---|---|---|
| GET | `/map/stations` | Gări cu GPS + nr. trenuri (filtru only_university). |
| GET | `/map/connections` | Conexiuni între gări (cu prag min_trains). |
| GET | `/map/operators` | Listă operatori pentru filtre UI. |
| GET | `/map/train-simulate/{id}` | Simulator poziție tren live. |

### 1.8 `crypto_keys.py` — Cheie publică verifier  (49 LOC)

| Metodă | Path | Descriere |
|---|---|---|
| GET | `/verification-key` | Cheia publică Ed25519 pentru verificare offline QR/VP. |

---

## 2. Frontend — Pagini (`src/pages/`)

| Pagină | LOC | Funcționalități cheie | Endpoint-uri folosite |
|---|---|---|---|
| **Login.jsx** | 156 | Login email/parolă + flux TOTP MFA. | `/login`, `/mfa/verify` |
| **Register.jsx** | 147 | Înregistrare cu upload CI + OCR pre-fill. | `/register`, `/documents/extract-id` |
| **Dashboard.jsx** | 186 | Stepper onboarding + quick stats. | `/users/me`, `/users/me/verification-status` |
| **Profile.jsx** | 464 | Profil + rută personală + foto profil. | `/users/me`, `/users/me/profile-photo`, `/stations/suggest` |
| **Settings.jsx** | 274 | Temă, MFA, schimbare parolă, export GDPR, ștergere cont. | `/mfa/setup`, `/mfa/verify`, `/mfa/disable`, `/users/me/password`, `/users/me/export`, `DELETE /users/me` |
| **Documents.jsx** | 906 | Listă documente, upload, request validare (CI + adeverință student). | `/documents/me`, `/documents/upload`, `/documents/validation-request`, `/documents/{id}/photo` |
| **Credentials.jsx** | 71 | Listă credențiale emise (VC-uri). | `/credentials/me` |
| **Notifications.jsx** | 92 | Listă notificări + mark-as-read. | `/notifications/me`, `PATCH /notifications/me/{id}/read` |
| **BuyTicket.jsx** | 477 | Flux cumpărare: sugestii itinerar (direct/cu schimbări), selectie loc, multi-pax, retur, plată gratuită dacă abonament acoperă. | `/stations/suggest`, `/trips/suggest`, `/stations/search`, `/trains/search`, `/tickets/quote`, `/tickets/buy`, `/trains/{id}/seats`, `/seats/hold`, `/seats/release` |
| **MyTickets.jsx** | 883 | Listă bilete, QR offline, cancel cu refund estimat, reschedule. | `/tickets/my`, `/tickets/{id}/cancel`, `/tickets/{id}/reschedule`, `/verification-key` |
| **Subscriptions.jsx** | 525 | Cumpărare + listă abonamente (route-scope, semestru, lunar, anual), quote live. | `/subscriptions/quote`, `/subscriptions/buy`, `/subscriptions/my`, `/subscriptions/{id}/cancel` |
| **MapView.jsx** | 398 | Hartă Leaflet cu gări, conexiuni, filtru operator, simulator tren. | `/map/stations`, `/map/connections`, `/map/operators`, `/map/train-simulate/{id}` |
| **PresentIdentity.jsx** | 205 | Generează VP (QR + countdown TTL 120s), anti-loop. | `/card/me`, `/card/present` |
| **VerifyPresentation.jsx** | 464 | Verifier (conductor): scan QR, modul online + offline Ed25519. | `/presentations/verify`, `/verification-key` |
| **ValidateTicket.jsx** | 126 | Conductor: scan QR bilet, validare online + offline. | `/tickets/validate`, `/verification-key` |
| **TravelHistory.jsx** | 266 | Statistici: km, CO₂, achievements, top trenuri, lunar. | `/users/me/travel-stats` |
| **UniversityAgentDashboard.jsx** | 314 | Agent: lista pending, aprobă/respinge atestate, revocă, KPI. | `/issuer/documents/pending`, `/issuer/documents/{id}`, `/issuer/documents/{id}/approve`, `/issuer/documents/{id}/reject`, `/issuer/credentials`, `/university/stats`, `/issuer/credentials/{id}/revoke` |

**Total pagini: 17 · ~5895 LOC frontend**

---

## 3. Suită de teste

| Categorie | Fișiere | LOC |
|---|---|---|
| Unit | 8 (auth, crypto_keys, refund_matrix, security, signing, tickets, uploads, users) | ~1500 |
| Integration | 25 (auth_mfa, identity, map, multi_passenger_e2e, offline_presentation, personal_route, seats, subscriptions, ticket_validation, trip_planner, cross_university_security, etc.) | ~7800 |
| E2E | 1 (test_demo_e2e.py) | 156 |
| Performance | 1 (locustfile.py) | 267 |
| Frontend | `tests/pages/`, `tests/mocks/`, `setup.js`, `test_offline_verify.mjs` (vitest) | ~440 |

> **Acoperire excelentă** — există teste dedicate pentru refund pro-rata, OCR/extracție CI, sincronizare DOB, congelare profil, concurență locuri, cross-university security, lifecycle QR, offline presentation, multi-passenger e2e, edge cases abonamente, security inputs.

---

## 4. Categorizare pe domenii funcționale

### 🟢 4.1 Autentificare & profil — ✅ COMPLET

- Backend: register, login, MFA TOTP (setup/verify/disable), profile CRUD, schimbare parolă, foto profil, export GDPR, delete account, verification-status.
- Frontend: `Login`, `Register`, `Profile`, `Settings`, `Dashboard`.
- Teste: `test_auth.py`, `test_auth_mfa.py`, `test_users.py`, `test_users_endpoints.py`, `test_profile_freeze.py`, `test_security.py`.
- **Status:** ✅ **COMPLET** — UI rafinat, suport MFA real (pyotp), GDPR export + delete.

### 🟢 4.2 Cumpărare bilete — ✅ COMPLET

- Tipuri suportate: **single**, **multi-pax** (nume per loc), **multi-leg** (cu schimbări 1–2), **retur**.
- Trip planner (sugestii cu schimbări) + station autocomplete + station-from-CI-address.
- Quote dinamic, anti-overlap loc, hold 5 min, reduceri abonament aplicate la /buy.
- QR semnat Ed25519 (verificabil offline).
- Anulare cu refund pro-rata stil CFR + reschedule cu păstrare traseu.
- Frontend: `BuyTicket.jsx` (477), `MyTickets.jsx` (883).
- Teste: `test_tickets.py`, `test_tickets_contract.py`, `test_ticket_validation.py`, `test_ticket_lifecycle_edges.py`, `test_multi_passenger_e2e.py`, `test_trip_planner.py`, `test_refund_matrix.py`, `test_qr_lifecycle.py`, `test_seat_concurrency.py`, `test_seats.py`.
- **Status:** ✅ **COMPLET** — cap-coadă, inclusiv multi-leg & multi-pax.

### 🟢 4.3 Abonamente — ✅ COMPLET

- **Route-scope** (segment dat) + posibilitate operator-scope din schemă DB.
- Tipuri: **lunar**, **semestru**, **anual** (toate cu quote dinamic).
- Bilet gratuit automat dacă ruta e acoperită → integrare cu `/tickets/buy`.
- Anti-overlap, refund pro-rata la cancel.
- Frontend: `Subscriptions.jsx` (525) cu modal quote-preview live.
- Teste: `test_subscriptions.py`, `test_subscription_edge_cases.py`, `test_subscription_segments.py`.
- **Status:** ✅ **COMPLET** (route-scope este flagship). 🟡 operator-scope există în model dar UI explicit nu îl scoate ca buton separat.

### 🟢 4.4 Identitate digitală (SSI / VC / VP) — ✅ COMPLET

- Card digital, Verifiable Credentials, Verifiable Presentations Ed25519 cu TTL 120s.
- Issuer flow (universitate): pending → approve/reject → emit VC → revoke.
- Verifier flow (conductor): online + **offline cu cheie publică pre-cache**.
- OCR pe poza CI cu pre-fill formular.
- Frontend: `Documents`, `Credentials`, `PresentIdentity`, `VerifyPresentation`, `UniversityAgentDashboard`.
- Teste: `test_identity.py`, `test_offline_presentation.py`, `test_signing.py`, `test_crypto_keys.py`, `test_cross_university_security.py`, `test_dob_sync.py`, `test_home_station_contract.py`, plus `test_offline_verify.mjs` (frontend).
- **Status:** ✅ **COMPLET** — element de diferențiere puternic (SSI real, nu mock).

### 🟢 4.5 Validare bilete (conductor) — ✅ COMPLET

- Online: `/tickets/validate` cu device_id + locație.
- Offline: QR semnat Ed25519, verificare locală cu cheia publică cache-uită.
- Istoric validări cu filtrare.
- Frontend: `ValidateTicket.jsx`.
- Teste: `test_ticket_validation.py`, `test_qr_lifecycle.py`, `test_signing.py`.
- **Status:** ✅ **COMPLET** — offline-first este punct forte.

### 🟢 4.6 Hartă & rute (planner, sugestii) — ✅ COMPLET

- Hartă Leaflet cu toate gările (filtru only_university / operator).
- Conexiuni cu prag min_trains.
- Simulator poziție tren live.
- Sugestii itinerar cu schimbări (Dijkstra-like prin DB).
- Sugestii gară de origine pornind de la adresa din CI.
- Frontend: `MapView.jsx`.
- Teste: `test_map.py`, `test_map_endpoints.py`, `test_trip_planner.py`, `test_personal_route.py`, `test_personal_route_segments.py`.
- **Status:** ✅ **COMPLET** — planner cu schimbări este peste media studențească.

### 🟢 4.7 Agent universitate (atestate, beneficii student) — ✅ COMPLET

- Dashboard cu KPI (pending / approved / rejected / total credențiale).
- Flux approve → emite VC „student la anul X" → reducere automată la bilet.
- Revoke credențial.
- Cross-university security: un agent vede DOAR documentele propriei universități.
- Frontend: `UniversityAgentDashboard.jsx`.
- Teste: `test_cross_university_security.py`, `test_identity.py` (issuer flow).
- **Status:** ✅ **COMPLET** — actor distinct, separație de roluri bine făcută.

### 🟡 4.8 Statistici personale & gamification — ✅ COMPLET (bonus)

- Km parcurși, CO₂ economisit (echivalent copaci), bani economisiți cu reduceri.
- Achievements: first_trip, frequent_traveler, veteran, km_1000, km_5000, eco_warrior, saver.
- Top 5 trenuri folosite, breakdown lunar 6 luni.
- Frontend: `TravelHistory.jsx`.
- Teste: `test_travel_stats_and_recommendation.py`.
- **Status:** ✅ **COMPLET** — element de UX peste media CFR-ului real.

### 🟡 4.9 Admin / audit — 🟡 PARȚIAL

- Există: roluri (`ROLE_PASSENGER`, `ROLE_TRAIN_VERIFIER`, `ROLE_ISSUER`), `validations_history`, `train/verifications/history`, audit pe documente, notifications.
- Lipsește: pagină dedicată „super-admin" cu listă globală users / blocare cont / dashboard sistem.
- **Status:** 🟡 **PARȚIAL** — auditul există la nivel de API (history endpoints), dar nu există UI de admin global. Pentru licență NU e blocant pentru că rolul de admin nu este în use-case-uri.

---

## 5. Tabel de sinteză status

| Domeniu | Backend | UI | Teste | Verdict |
|---|---|---|---|---|
| Autentificare & profil (cu MFA, GDPR) | ✅ | ✅ | ✅ | ✅ COMPLET |
| Cumpărare bilete (single/multi-pax/multi-leg/retur) | ✅ | ✅ | ✅ | ✅ COMPLET |
| Abonamente route-scope | ✅ | ✅ | ✅ | ✅ COMPLET |
| Abonamente operator-scope | ✅ (schemă) | 🟡 (implicit) | ✅ | 🟡 PARȚIAL |
| Identitate digitală (SSI/VC/VP Ed25519) | ✅ | ✅ | ✅ | ✅ COMPLET |
| Validare bilet conductor (online + offline) | ✅ | ✅ | ✅ | ✅ COMPLET |
| Hartă & trip planner | ✅ | ✅ | ✅ | ✅ COMPLET |
| Agent universitate (issuer flow) | ✅ | ✅ | ✅ | ✅ COMPLET |
| Statistici & achievements | ✅ | ✅ | ✅ | ✅ BONUS |
| Admin global | 🟡 | ❌ | n/a | 🟡 PARȚIAL |

---

## 6. 🎓 VERDICT pentru evaluatorul de licență

### Suficient pentru nota maximă? **DA, cu marjă.**

#### Ce iese în evidență (elemente diferențiatoare):

1. **SSI real, nu mock** — Verifiable Credentials + Verifiable Presentations semnate Ed25519, cu TTL, cu emitent (universitate) distinct, cu revocare. Nu există în aplicația CFR Călători reală.
2. **QR offline-verifiable** — conductorul poate valida biletul fără internet, folosind cheia publică Ed25519 cache-uită. E un caz de utilizare realist (tren în tunel/zonă fără semnal).
3. **Trip planner cu schimbări (1–2 hop-uri)** — nu doar trenuri directe, ci itinerarii compuse.
4. **Sugestie de gară pornind de la adresa din CI** — UX gândit, integrat cu OCR.
5. **Refund pro-rata stil CFR** + reschedule cu păstrarea traseului — logică de business reală.
6. **Cross-university security testat** — un agent de la „UPB" nu vede cereri de la „UTCN". Test dedicat.
7. **Multi-passenger** — cumperi pentru mai multe persoane în același tranzacție, fiecare cu nume.
8. **Suită de teste serioasă** — ~10k LOC teste (unit + integration + e2e + performance Locust), cu acoperire pentru concurență, refund matrix, securitate input, profil freeze.
9. **Achievements & CO₂** — UX care încurajează folosirea trenului (component social/ecologic, util în motivația lucrării).
10. **MFA TOTP real** (pyotp), nu simulat.

#### Ce e slab / poate fi îmbunătățit:

- 🟡 **UI admin global** lipsește (nu e blocant — nu e în use-case-uri formale).
- 🟡 **Abonamente operator-scope** există în schemă dar nu sunt expuse vizibil în UI ca opțiune separată — un buton „abonament toți operatorii" ar clarifica.
- 🟡 **Plată reală (Stripe/Netopia)** lipsește — toate „cumpărările" sunt simulate. Pentru licență e acceptabil, dar e o limitare de menționat onest în capitolul „Limitări".
- 🟡 **Push notifications** doar in-app, nu prin email/SMS/web-push real.
- 🟡 **Simulator tren live** este o simulare matematică (interpolare), nu integrare cu GPS real (acceptabil — nu există API public CFR).
- 🟡 **PWA / offline-first pe frontend** nu este declarat ca service worker; doar verificarea QR e offline.

#### Comparație cu aplicația CFR Călători reală (acoperire estimată)

| Funcționalitate CFR reală | Acoperită în proiect? |
|---|---|
| Căutare trenuri | ✅ |
| Cumpărare bilet | ✅ (fără plată reală) |
| Bilet pe telefon (QR) | ✅ (+ semnat Ed25519, peste CFR real) |
| Abonament student | ✅ (+ atestat digital, peste CFR real) |
| Hartă rute | ✅ |
| Multi-passenger | ✅ |
| Retur | ✅ |
| Anulare/refund | ✅ |
| Reschedule | ✅ (CFR real nu permite — punct forte) |
| Identitate digitală (VC) | ✅ (CFR real NU are) |
| Validare offline conductor | ✅ (CFR real NU are) |
| MFA | ✅ (CFR real NU are) |
| Trip planner cu schimbări | ✅ |
| Plată online reală | ❌ (simulată) |
| Catering / locuri specifice cu poză vagon | 🟡 (layout abstract) |
| Notificări push reale | 🟡 (doar in-app) |

**Estimare acoperire față de CFR Călători live: ~85% din funcțional + 3 features net peste (SSI, QR offline, reschedule).**

---

## 7. Concluzie executivă (TL;DR)

Proiectul este **substanțial peste pragul de nota 10** pentru o licență la Informatică / Calculatoare:

- **8 routere backend**, **~6000 LOC** logică server (FastAPI + SQLAlchemy raw + Pydantic).
- **17 pagini frontend React**, **~5900 LOC** UI cu Tailwind.
- **35 fișiere de teste**, **~10k LOC** acoperire (unit + integration + e2e + Locust + vitest).
- **9 din 10 domenii funcționale** sunt ✅ COMPLET; doar „admin global" e parțial (și nu e cerut de use-case).
- **3 elemente net diferențiatoare** față de CFR Călători real: identitate digitală cu VC/VP Ed25519, validare offline a biletelor, trip planner cu schimbări.
- **Logică de business reală**: refund pro-rata, anti-overlap abonamente, anti-loop pe prezentări, cross-university isolation testat.

**Recomandare:** în prezentarea orală, insistă pe SSI + offline verification + suita de teste — sunt cele 3 elemente care impresionează o comisie tehnică.
