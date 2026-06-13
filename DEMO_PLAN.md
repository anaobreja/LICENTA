# Plan de demo licență — Railway Digital Identity Platform

**Status la 2026-06-09:** 25/25 endpoint-uri cheie funcționale. 2 probleme reale descoperite și corectate în această sesiune (vezi secțiunea „Probleme găsite & rezolvate").

---

## 0. Pregătire înainte de demo

### 0.1 Pornire stack
```bat
cd D:\LICENTA
python run.py
```
Așteaptă mesajele:
- `[db] Postgres ready`
- `[uvicorn] Started server process` (port 8000)
- `[web] UI disponibilă pe http://127.0.0.1:8765`

Browserul se deschide automat. Dacă nu, vizitează `http://127.0.0.1:8765`.

### 0.2 Verificare rapidă (sanity check)
```bat
curl http://127.0.0.1:8000/health
```
Răspuns așteptat: `{"status":"healthy", ..., "database":"postgresql"}`

### 0.3 Conturi demo (parolă pentru toate: `demo2026`)

| Email | Rol | Ce demonstrează |
|---|---|---|
| `user.demo@railwaydemo.com` | passenger (student UPB) | Toate fluxurile pasager + reducere student |
| `agent.upb@railwaydemo.com` | university_agent | Aprobare cereri credențiale |
| `agent.train@railwaydemo.com` | conductor | Validare bilet prin QR + verificare card |
| `admin@railway.gov.ro` | admin | Audit & administrare |
| `alexandra.popescu@email.com` | passenger | Pasager fără reduceri (date reale demo) |

### 0.4 Două device-uri pentru efect maxim
Pentru demo „wow" folosește **laptop + telefon** sau **2 browsere** (incognito pentru fiecare):
- Device A: pasager (cumpără bilet, prezintă QR)
- Device B: conductor (validează QR)

---

## 1. Scenarii demo (în ordine recomandată)

### Scenariu 1 — Tur rapid harta (2 min) 🗺️

**Login:** `user.demo` → meniu `Hartă`

**De arătat:**
- 30 de stații afișate (toate cele cu GPS)
- Toggle „Doar centre universitare" → rămân 18 hub-uri
- Click pe **Iași** (verde = plecare) → click pe **București Nord** (roșu = sosire)
- Apare automat în sidebar „Ruta optimă":
  - **0 schimbări** (direct)
  - **5h 28m**
  - Tren IC 11762
  - **Polyline verde** desenat **pe șine reale** prin toate stațiile intermediare (NU linie dreaptă)
- Buton „Cumpără bilet pentru această rută" → preia datele în BuyTicket

**Punct de evidențiat:**
> „Sistemul rulează *trip_planner* cu Dijkstra peste graful CFR. Linia urmărește traseul real al trenului, nu coordonate aproximate. Pentru rute fără tren direct, găsește automat itinerariul optim cu schimbări de tren."

### Scenariu 2 — Reducerea student pe ruta personală (3 min) 🎓

**Pasul 1:** `user.demo` are deja `home_station=Iași` și `university=UPB` în profil. Verifică în `Profil`.

**Pasul 2:** Mergi la `Cumpără bilet` (sau folosește prefill din Scenariul 1).
- Plecare: Iași, Sosire: București Nord
- Selectează tren (IC 11762)
- **Detalii tarif:**
  - Banner verde: „🎓 Ruta ta personală. Reducerea de student se aplică."
  - Preț întreg: **135 RON**
  - Reducere -90%: **-121.50 RON**
  - **Preț final: 13.50 RON**

**Pasul 3 (twist pentru juriu):** Schimbă destinația la **Cluj-Napoca** (rută OFF-personal).
- Banner devine portocaliu: „⚠ Tarif întreg. Ruta nu corespunde traseului tău personal."
- Preț: tarif integral, fără reducere.

**Punct de evidențiat:**
> „Reducerea se aplică conform OUG 11/2024 DOAR pe ruta declarată (home ↔ universitate), inclusiv pe **segmentele intermediare** (Iași→Bacău) și pe **leg-urile rutelor cu schimbare** (ex: Făurei→Buzău→București). Asta e o subtilitate legală pe care alte sisteme nu o respectă."

### Scenariu 3 — Cumpărare bilet + QR live (3 min) 🎫

**Device A — `user.demo`:**
1. Continuă din Scenariul 2 (Iași→București, 13.50 RON cu reducere).
2. Selectează un loc din `SeatMap` (loc 14B, vagon 1).
3. Confirmă cumpărarea → redirect la `Biletele mele`.
4. Cardul biletului nou pulsează verde (highlight).
5. Click „Afișează QR pentru control" → modal cu QR + countdown 120 secunde.

**Device B — `agent.train`:**
6. Login conductor → `Verificare bilet`.
7. Pornește camera (sau click „Upload imagine QR").
8. Scanează QR-ul de pe device A.
9. **Ecran VERDE „VALID"** + nume pasager + locul rezervat.

**Punct de evidențiat:**
> „QR-ul este verificabil OFFLINE — conține semnătura Ed25519 a issuer-ului CFR. Conductorul poate valida bilete și fără internet, fiindcă cheia publică e cached în PWA. La 120s, QR-ul expiră — îl regenerăm cu un nou token cu jitter contra screenshot-urilor."

### Scenariu 4 — Multi-pax cu reducere doar pentru titular (2 min) 👥

**Pasager:** `user.demo` → `Cumpără bilet`
- Iași → București
- **+2 pasageri:** Mama (Maria Popescu), Tata (Ion Popescu)
- Selectează 3 locuri vecine.

**Detalii preț:**
- Bilet 1 (titularul Demo User, student UPB): **13.50 RON** (cu -90%)
- Bilet 2 (Maria Popescu): **135 RON** (tarif întreg)
- Bilet 3 (Ion Popescu): **135 RON** (tarif întreg)
- **Total: 283.50 RON** pentru 3 bilete

În `Biletele mele`, fiecare bilet are propriul pasager afișat: `Pasager: Maria Popescu — locul V1-15B (cumpărat de tine)`.

**Punct de evidențiat:**
> „Reducerea de student este nominală conform legii — se aplică DOAR pe biletul cumpărătorului. Sistemul creează N bilete separate cu N nume diferite, ca să poată fi controlate individual la conductor."

### Scenariu 5 — Călătorie cu schimbare (JourneyCard) (3 min) 🔄

**Setup:** cumpără 2 bilete în secvență rapidă (la max 2 min între ele):
- Bilet 1: Făurei → Buzău (R 9102) — dimineața
- Bilet 2: Buzău → București Nord (IR 1768) — după aproape 1h

În `Biletele mele`, cele 2 bilete apar **grupate într-un singur card** „Călătorie cu schimbare":
```
Călătorie cu schimbare (2 trenuri, 1 schimbare)          [Activ]
Făurei 07:00 → București Nord Gr.A 10:15

Data călătorie: 2026-06-15
Pasager: Demo User
- - - - - - - - - - - - - - - - - - - - - - - -
Tren 1/2: R 9102 (regio)
  Făurei 07:00 → Buzău 08:00
  Locul: V1-12A
  Preț: 18.00 RON
  [QR] [Reprogramare] [Anulare]

↓ Schimbare în Buzău — aștepți 30 min

Tren 2/2: IR 1768 (intercity)
  Buzău 08:30 → București Nord 10:15
  Locul: V2-08B
  Preț: 45.00 RON
- - - - - - - - - - - - - - - - - - - - - - - -
Total plătit: 63.00 RON
```

**Punct de evidențiat:**
> „Sistemul detectează automat că două bilete cumpărate în același flow formează o călătorie cu schimbare și le grupează vizual. Algoritmul are protecție anti-cycle (nu te poți întoarce într-o stație vizitată) și un prag strâns de 2 min între cumpărări — fără false-positive pe bilete cumpărate separat."

### Scenariu 6 — Abonament lunar pe ruta studentului (2 min) 💳

**Pasager `user.demo`:**
1. Mergi la `Abonamente` → „Cumpără abonament nou".
2. Type: **lunar**, Ruta: **Iași → București** (preluată automat din ruta personală).
3. Calcul preț: cu reducerea de student aplicată.
4. Confirmă plata → abonament activ pentru 30 zile.

**Acum** mergi la `Cumpără bilet`:
- Aceeași rută Iași → București.
- Detalii tarif arată: **„Abonament lunar acoperă această rută. Bilet 0.00 RON."**
- Confirmă cumpărare → bilet gratuit emis.

În `Biletele mele`, bilet nou cu:
- Preț plătit: **0.00 RON**
- Mențiune: *„(gratuit pe baza abonamentului)"*

**Bonus:** încearcă o rută parțială (Iași → Bacău). Abonamentul tot se aplică (P2 fix).

**Punct de evidențiat:**
> „Abonamentul acoperă inclusiv **segmente parțiale** ale rutei și leg-urile rutelor cu schimbare. E logic, dar foarte multe sisteme reale NU implementează asta și forțează utilizatorul să plătească ambele bilete."

### Scenariu 7 — Cerere & aprobare credențial student (5 min) 📄

**Partea 1 — Pasager (`alexandra.popescu` sau cont nou):**
1. `Documente` → „Încarcă document" → poză CI + poză legitimație student.
2. Sistem rulează OCR (EasyOCR) → extrage CNP, nume, număr matricol, universitate.
3. Utilizatorul confirmă datele extrase.
4. Click „Trimite spre validare la UPB".

**Partea 2 — Agent (`agent.upb`):**
5. Login → `Cereri pending` → vede cererea cu pozele și datele OCR.
6. Verifică datele (de exemplu nr. matricol contra tabelei `university_students`).
7. Apasă **Aprobă**.
8. Backend semnează credențialul cu cheia Ed25519 a UPB → emis.

**Partea 3 — Pasager (revenit):**
9. `Card Digital` → vede credențialul activ.
10. Acum poate cumpăra bilete cu reducere de student.

**Punct de evidențiat:**
> „Aceasta e arhitectură de tip Self-Sovereign Identity (SSI) — fiecare universitate e un issuer cu propria pereche de chei Ed25519, semnează credențiale Verifiable Credentials W3C-compatible, iar pasagerul stochează credențialul în wallet-ul propriu. La control, prezintă o Verifiable Presentation care expune doar claim-urile necesare (selective disclosure)."

### Scenariu 8 — Anulare cu refund pro-rata (2 min) ↩️

**Pasager:** alege un bilet cumpărat acum 2 zile, departures peste 5 zile.
- Click „Anulare" → modal cu informația refund:
  - „Anulare > 48h înainte de plecare → refund 80%"
  - „Pierderi de procesare: 10%"
  - „Vei primi: X RON"
- Confirmă → status devine `cancelled`, banca primește refund.

În card apare „Refund acordat: X RON".

**Punct de evidențiat:**
> „Politica de refund e configurabilă în `ticket_business.compute_refund()` — momentan implementează regulile CFR Călători (80% > 48h, 50% > 24h, 0% < 24h)."

---

## 2. Demonstrație opțională (dacă mai e timp)

### MFA cu TOTP (Google Authenticator)
`Setări` → MFA Setup → scanează QR cu app autentificator → confirmă cod. Apoi log-out / log-in → cere TOTP.

### Export GDPR
`Setări` → „Export datele mele" → primește ZIP cu toate înregistrările tale (bilete, credențiale, audit log).

### Verificare offline a QR-ului
Conductor: oprește WiFi → scanează QR → tot validează (folosește cheia publică cached).

---

## 3. Probleme găsite & rezolvate în această sesiune

| # | Problemă | Severitate | Status |
|---|---|---|---|
| 1 | `map.py` accidentally golit de un patch script cu bug (`open('w')` după ValueError) | 🔴 Catastrofală | ✅ Reconstruit complet; toate 15 teste map trec |
| 2 | `trip_planner._make_leg` calcula `duration_min = arrival - departure` fără să țină cont de trenurile peste noapte → durate **negative** (-1047 min pentru Iași→Buc cu plecare 22:45) | 🔴 Logic | ✅ Adăugat `if duration < 0: duration += 1440` |
| 3 | `total_duration_min` pentru rute cu transfer folosea `leg_last.arrival_min - leg_first.departure_min` → ignora trecerile peste noapte la oricare din leg-uri (Iași→Buc cu transfer afișa **14 min** în loc de ~7h) | 🔴 Logic | ✅ Refăcut ca `sum(leg.duration_min) + sum(wait_transfer)` |
| 4 | Endpoint `/map/route-geometry` lipsea în backend rulant până la restart | 🟡 Operațional | ✅ Backend repornit |

### Probleme cunoscute (NU blocante pentru demo)

| # | Problemă | Severitate | Workaround |
|---|---|---|---|
| 5 | Toate `user1*@gmail.com` (utilizatori creați manual prin Register) au date inconsistente (același nume duplicat) | 🟢 Cosmetic | Folosește doar conturile cu sufix `@railwaydemo.com` în demo |
| 6 | P4 (cumpărare combinată multi-leg dintr-un click) — utilizatorul tot trebuie să cumpere câte un bilet per leg | 🟡 UX | Demonstrează că JourneyCard le grupează automat după cumpărare (Scenariu 5) |
| 7 | `train-simulate` (poziție live a trenurilor pe hartă) — deprecated; pozițiile erau aproximative | 🟢 By design | Pentru un sistem real ar trebui GTFS-Realtime (out of scope licență) |

---

## 4. Sumar metrici pentru juriu

| Metrică | Valoare |
|---|---|
| Stații cu GPS în DB | **30** (în versiunea demo; importatorul CFR poate aduce 1818) |
| Centre universitare hub | **18** |
| Operatori feroviari | **CFR Călători** + variante demo |
| Utilizatori demo populați | **20+** (multiple roluri) |
| Endpoint-uri REST | **~50** (vezi `INVENTORY.md`) |
| Pagini frontend | **17** (vezi `INVENTORY.md`) |
| Linii de cod backend | ~10.000 (Python/FastAPI) |
| Linii de cod frontend | ~8.500 (React/Tailwind) |
| Teste automate | **140+** (unit, integrare, contract, perf smoke) |
| Endpoint-uri verificate manual | **25/25 OK** (acest smoke test) |

---

## 5. Întrebări probabile de la juriu & răspunsuri

**Q: De ce SSI / Verifiable Credentials?**
A: Pasagerul nu mai depinde de un server central pentru a-și demonstra identitatea. Universitatea semnează un credențial, iar pasagerul îl prezintă conductorului care îl validează cu cheia publică universitară — totul offline. E aliniat cu eIDAS 2.0 / EU Digital Identity Wallet.

**Q: Cum protejați împotriva clonării QR?**
A: QR-ul nu conține biletul în sine, ci un token semnat cu expirare 120s + jitter. Plus selective disclosure pe Verifiable Presentation — conductorul vede DOAR claim-urile relevante (nume, loc, valid), nu CNP/adresă.

**Q: De ce nu folosiți blockchain?**
A: Pentru emitenții autorizați (CFR, universități) PKI tradițional cu chei Ed25519 e suficient și nu introduce overhead. Blockchain ar fi util DOAR dacă ai nevoie de revocare descentralizată sau public ledger — nu e cazul aici.

**Q: Câți utilizatori concurenți poate susține?**
A: Smoke test perf (`backend/tests/performance/`) măsoară ~200 RPS pe endpoint-uri citire pe un laptop normal. Pentru producție ar trebui caching Redis (vezi `LIMITATIONS.md` punct 2.3).

**Q: Cum gestionați aglomerația pentru locuri?**
A: `ticket_seats` cu `UNIQUE(seat_id, travel_date)` la nivel DB + Lock pesimist pe rândul vagonului în `seats/hold`. Două cumpărări simultane pe același loc → una primește `409 Conflict`.

**Q: Ce se întâmplă dacă serverul moare în mijlocul cumpărării?**
A: Toate operațiile sunt în tranzacție DB. Dacă uvicorn crash între `seat_hold` și `ticket_insert`, hold-ul expiră în 15 min și locul redevine liber. Vezi `test_seat_concurrency.py`.

---

## 6. Pași post-demo (de fix-uit pentru versiunea finală)

1. **Grafica `MyTickets` pentru bilete single** — utilizatorul a indicat că vrea ceva mai compact (poate format tabel cu expand pe click).
2. **Cumpărare combinată multi-leg (P4)** — un buton „Cumpără tot itinerariul" pe sugestiile rutei cu schimbare.
3. **Validare end-to-end pentru fluxul abonament+segment** (logica e verificată unit-test, dar lipsește un test E2E care simulează cumpărare abonament → cumpărare segment).
4. **Importul CFR full** (1818 stații + ~3500 trenuri) — momentan se sare peste când rulezi local cu `RUN_SKIP_IMPORT_CFR=1`. Înainte de demo, rulează importul complet ca să arăți acoperirea reală.

---

**Document generat automat după smoke test live: 25/25 OK la 2026-06-09 17:51.**
