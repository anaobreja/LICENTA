# Diagrame Use Case

## Actori

| Actor | Descriere |
|-------|-----------|
| **Pasager (Student)** | Utilizatorul care depune documente și folosește cardul digital |
| **Agent Universitar** | Verifică și aprobă/respinge cererile studenților universității sale și emite credențiale |
| **Agent Tren** | Scanează cardul digital al pasagerului în tren |
| **Administrator** | Operator de sistem: gestionează utilizatori, vede audit logs, monitorizează statistici globale. |

---

## UC1 — Pasager (Student)

```mermaid
graph TD
    P((Pasager))

    P --> UC1[Înregistrare cont]
    P --> UC2[Autentificare cu email și parolă]
    P --> UC3[Configurare MFA - TOTP]
    P --> UC4[Scanare CI prin OCR - MRZ]
    P --> UC5[Depunere cerere verificare identitate]
    P --> UC6[Urmărire status cerere - stepper]
    P --> UC7[Vizualizare credențiale active]
    P --> UC8[Generare QR card digital - 120s]
    P --> UC9[Prezentare card digital agentului]
    P --> UC10[Export date personale - GDPR]

    UC4 -.->|include| UC5
    UC8 -.->|extend| UC7
```

---

## UC2 — Agent Universitar

```mermaid
graph TD
    AU((Agent\nUniversitar))

    AU --> UC11[Autentificare cu rol universitar]
    AU --> UC12[Vizualizare dashboard cu statistici și grafice]
    AU --> UC13[Vizualizare cereri universitate proprie]
    AU --> UC14[Filtrare cereri după an de studiu]
    AU --> UC15[Vizualizare date CI extrase prin OCR]
    AU --> UC16[Vizualizare poză legitimație student]
    AU --> UC17[Aprobare cerere și emitere credențial]
    AU --> UC18[Respingere cerere cu motiv]

    UC17 -.->|include| UC15
    UC17 -.->|include| UC16
    UC18 -.->|include| UC15
```

---

## UC3 — Agent Tren

```mermaid
graph TD
    AT((Agent\nTren))

    AT --> UC19[Autentificare cu rol tren]
    AT --> UC20[Scanare QR card digital din cameră]
    AT --> UC21[Introducere manuală token]
    AT --> UC22[Vizualizare rezultat VALID sau INVALID]
    AT --> UC23[Vizualizare claims pasager]
    AT --> UC36[Validare token offline cu cheie publică Ed25519]
    AT --> UC37[Vizualizare claims fără conexiune internet]

    UC20 -.->|extend| UC21
    UC22 -.->|include| UC23
    UC22 -.->|extend| UC36
```

---

## UC4 — Administrator

```mermaid
graph TD
    AD((Administrator))

    AD --> UC24[Vizualizare audit logs]
    AD --> UC25[Gestionare utilizatori - suspend / activate / șterge]
    AD --> UC26[Vizualizare statistici globale - cross-universitate]
    AD --> UC27[Configurare emitenți - issuers]
    AD --> UC28[Rotație cheie de semnare Ed25519]

    UC25 -.->|include| UC24
    UC28 -.->|include| UC27
```

---

## UC5 — Pasager (Modul Transport)

```mermaid
graph TD
    PT((Pasager\nTransport))

    PT --> UC29[Căutare stații și trenuri]
    PT --> UC30[Vizualizare hartă feroviară live]
    PT --> UC31[Cumpărare bilet - cu/fără card digital pentru reducere]
    PT --> UC32[Vizualizare bilete cumpărate]
    PT --> UC33[Validare bilet în tren - prin QR sau token]
    PT --> UC34[Vizualizare istoric călătorii]
    PT --> UC35[Calculare rută personală - universitate spre destinație]
    PT --> UC41[Selectare loc in vagon - hold 5 min real-time]
    PT --> UC42[Anulare bilet cu refund pe trepte CFR]
    PT --> UC43[Reprogramare bilet pe acelasi traseu, alt tren/data]
    UC44[Anti-overlap intervale orare] -.->|constraint| UC31
    UC44 -.->|constraint| UC43

    UC31 -.->|include| UC30
    UC33 -.->|include| UC32
    UC31 -.->|extend| UC41
    UC42 -.->|extend| UC32
    UC43 -.->|extend| UC32
```

---

## Descriere use case-uri principale

### UC5 — Depunere cerere verificare identitate
- **Actor principal:** Pasager
- **Precondiție:** Utilizator autentificat
- **Flux:** Scanează CI cu OCR → datele se completează automat → încarcă poza legitimației → selectează universitatea și anul → trimite cererea
- **Postcondiție:** Cerere în status `pending`, vizibilă agentului universitar

### UC17 — Aprobare cerere și emitere credențial
- **Actor principal:** Agent Universitar
- **Precondiție:** Există cereri `pending` pentru universitatea agentului
- **Flux:** Vizualizează datele CI + poza legitimației → verifică datele → aprobă
- **Postcondiție:** Se emite automat un `user_credential` de tip `student_verified`; pasagerul primește notificare și poate genera cardul digital

### UC20 — Scanare QR card digital
- **Actor principal:** Agent Tren
- **Precondiție:** Pasagerul a generat un QR activ (valabil 120 secunde)
- **Flux:** Agent scanează QR → sistemul validează token-ul → afișează ecran VERDE/ROȘU + claims
- **Postcondiție:** Validare înregistrată în `card_verifications`; pasagerul primește notificare

### UC25 — Gestionare utilizatori
- **Actor principal:** Administrator
- **Precondiție:** Administrator autentificat cu rol `admin`
- **Flux:** Vizualizează lista utilizatorilor → filtrează după status/rol → selectează un utilizator → execută acțiune (suspend / activate / șterge) → confirmă operația → sistemul scrie o intrare în audit log
- **Postcondiție:** Starea utilizatorului este actualizată; sesiunile active sunt invalidate la suspend/ștergere; acțiunea este trasabilă în `audit_logs`

### UC28 — Rotație cheie de semnare Ed25519
- **Actor principal:** Administrator
- **Precondiție:** Există o cheie Ed25519 activă pentru un issuer configurat
- **Flux:** Selectează issuer-ul → declanșează generarea unei noi perechi de chei Ed25519 → noua cheie publică este publicată în JWKS → cheia veche este marcată `rotated` (păstrată pentru verificarea tokenilor existenți până la expirare) → noile credențiale sunt semnate cu cheia nouă
- **Postcondiție:** Issuer-ul are o cheie activă nouă; cheia veche rămâne validă doar pentru verificare; evenimentul este înregistrat în audit logs

### UC31 — Cumpărare bilet
- **Actor principal:** Pasager
- **Precondiție:** Pasager autentificat; opțional are card digital activ pentru reducere studențească
- **Flux:** Caută stația de origine și destinație → vizualizează ruta pe harta feroviară live → selectează trenul și clasa → sistemul detectează automat dacă pasagerul are card digital activ și aplică reducerea → confirmă și plătește biletul
- **Postcondiție:** Biletul este emis și salvat în `tickets`; pasagerul primește un QR de validare; biletul apare în lista „Bilete cumpărate”

### UC33 — Validare bilet în tren
- **Actor principal:** Pasager
- **Precondiție:** Pasager are cel puțin un bilet activ pentru cursa curentă
- **Flux:** Deschide aplicația → accesează „Bilete cumpărate” → afișează QR-ul sau token-ul biletului → agentul tren scanează → sistemul verifică semnătura și valabilitatea biletului → afișează VALID/INVALID
- **Postcondiție:** Biletul este marcat ca `validated`; călătoria intră în istoric (UC34)

### UC36 — Validare token offline (Agent Tren)
- **Actor principal:** Agent Tren
- **Precondiție:** Aplicația agentului are cheia publică Ed25519 a issuer-ului cache-uită local (descărcată din JWKS la ultima conexiune online)
- **Flux:** Agent scanează QR-ul / introduce token-ul → aplicația verifică semnătura JWS local, în browser, folosind **Web Crypto API (algoritm Ed25519)** → validează `exp`, `nbf`, `iss` și `aud` fără apel la server → afișează rezultatul VALID/INVALID și claims-urile pasagerului
- **Postcondiție:** Validarea este efectuată complet offline; rezultatul și claims-urile sunt vizibile agentului; evenimentul de validare este pus într-o coadă locală și sincronizat în `card_verifications` la reconectare

### UC41 - Selectare loc in vagon (real-time)

**Actor:** Pasager

**Precondi?ii:** Pasagerul este �n procesul de cumparare a unui bilet ?i a selectat
un tren ?i o data.

**Flux:**
1. Sistemul afi?eaza harta vagoanelor trenului (Regio=3 vagoane, IR=5, IC=7,
   fiecare cu 60 locuri �n layout 2+2 cu culoar central).
2. Fiecare loc are status vizual: liber (alb), selec?ia ta (galben), v�ndut
   (ro?u), hold de alt user (portocaliu), deja cumparat de tine (albastru).
3. Pasagerul face click pe un loc liber.
4. Sistemul tine locul rezervat 5 minute (`seat_reservations` cu `expires_at`).
5. Pe alte device-uri (alti pasageri), locul apare ca portocaliu (indisponibil).
6. La click din nou pe locul propriu, hold-ul este eliberat (toggle).
7. La confirmarea cumpararii (UC31), hold-ul devine v�nzare (`ticket_seats`).
8. Daca nu confirma �n 5 minute, hold-ul expira automat ?i locul redevine liber.

**Postcondi?ii:** Locul este marcat ca v�ndut pentru data ?i trenul respective.
Schimbarile sunt vizibile live (polling 5s) pentru ceilal?i useri.

---

### UC42 - Anulare bilet cu refund pe trepte CFR

**Actor:** Pasager

**Precondi?ii:** Pasagerul are un bilet activ ne-utilizat (`ticket_status='active'`).

**Flux:**
1. Pasagerul deschide pagina "Biletele mele" ?i apasa "Anulare" pe un bilet activ.
2. Modal de confirmare afi?eaza refund-ul estimat conform regulamentului CFR:
   - **>24h** �nainte de plecare: 100% refund
   - **1m - 24h** �nainte de plecare: 50% refund
   - **0** sau dupa plecare: 0% refund (nu se acorda)
3. Pasagerul confirma.
4. Sistemul:
   - Marcheaza biletul `cancelled` + populeaza `cancel_refund_amount`
   - Elibereaza instantaneu locul (?terge `ticket_seats`) - alti pasageri pot
     cumpara acela?i loc imediat.
   - Invalideaza `travel_entitlements` ?i `qr_tokens` asociate
   - Creeaza notificare cu suma de refund
5. Raspuns: `{refund_amount, refund_tier, seats_released}`

**Postcondi?ii:** Biletul ramane vizibil �n istoric cu status "Anulat" ?i suma
refund. Locul este disponibil pentru reluarea v�nzarii.

---

### UC43 - Reprogramare bilet (acela?i traseu, alt tren / data)

**Actor:** Pasager

**Precondi?ii:** Bilet activ, trenul nu a plecat �nca, exista alte trenuri pe
acela?i traseu.

**Flux:**
1. Pasagerul apasa "Reprogramare" pe bilet.
2. Modal cu selector data + lista trenuri disponibile pe acela?i origin/destination.
3. Pasagerul alege noul tren + (op?ional) locuri noi prin SeatMap.
4. Sistemul valideaza:
   - Trenul nou este pe **acela?i traseu** (`origin_station_id` ?i
     `destination_station_id` identice) - altfel 409 `different_route`.
   - Noul interval orar nu se suprapune cu alte bilete active ale userului.
   - Trenul nu a plecat �nca.
5. Tranzac?ie atomica:
   - Elibereaza locurile vechi
   - Marcheaza biletul vechi `rescheduled` (cu link la cel nou)
   - Creeaza bilet nou clonat (acela?i pret, traseu, tip), legat invers
   - Muta `travel_entitlements` pe biletul nou
   - Notificare

**Postcondi?ii:** Lan? `rescheduled_from_ticket_id` <-> `rescheduled_to_ticket_id`
trasabil. **Diferen?a de pret nu se restituie** (regula CFR).

---

### UC44 - Constr�ngere anti-overlap (cross-cutting)

**Tip:** Constr�ngere de business aplicata la UC31 (cumparare) ?i UC43
(reprogramare).

**Regula:** Un user nu poate avea simultan doua bilete active �n intervale orare
suprapuse, indiferent de tren sau traseu.

**Algoritm:**
1. Calculeaza intervalul `[new_dep, new_arr]` pentru noul tren + data
   (din `route_stops` prima ?i ultima oprire pe ruta).
2. Selecteaza biletele active ale userului din `travel_date +/- 1 zi`
   (acopera ?i trenurile de noapte care trec peste miezul nop?ii).
3. Pentru fiecare bilet existent, calculeaza `[ex_dep, ex_arr]`.
4. Daca `new_dep < ex_arr AND ex_dep < new_arr` -> **conflict**.
5. Raspunde 409 cu detalii: trenul �n conflict, intervalul lui, ID-ul biletului.

**Justificare:** Pasagerul fizic nu poate fi �n doua trenuri �n acela?i timp.
Aceasta regula previne ?i fraudele de tip "rezervare multipla speculativa"
(blocare locuri �n trenuri diferite pentru a alege ulterior).

### UC45 - Imutabilitate date validate (Frozen Fields)

**Actor:** Pasager (orice user cu identitate validata).

**Tip:** Constrângere de business cross-cutting pe UC6 (Modificare profil).

**Precondi?ii:** Utilizatorul are credential `identity_verified` activ
(emis de un agent universitar, neexpirat).

**Regula:** Urmatoarele câmpuri NU pot fi modificate pâna la expirarea
credentialului:

- `cnp` (Cod Numeric Personal)
- `first_name`, `last_name`
- `birth_date`
- `home_station_id` (statia de domiciliu, derivata din adresa validata)

**Expirare:** Credentialul `identity_verified` are `valid_until = 1 oct
al anului universitar curent`. Logica:

- Daca verificarea s-a facut între 1 ian si 30 sep -> expira pe 1 oct anul curent.
- Daca verificarea s-a facut între 1 oct si 31 dec -> expira pe 1 oct anul urmator.

**Flux la modificare:**

1. Utilizatorul trimite `PATCH /users/me` cu un câmp FROZEN modificat.
2. Sistemul:
   - Verifica `is_identity_verified(user_id)` -> True.
   - Compara fiecare câmp FROZEN din payload cu valoarea curenta din DB.
   - Daca exista delta -> raspunde **HTTP 403** cu detalii:
     ```json
     {
       "error": "frozen_field_modification_blocked",
       "frozen_fields_attempted": ["cnp"],
       "expires_at": "2026-10-01",
       "days_until_expiry": 115,
       "message": "Nu puteti modifica câmpurile [\"cnp\"] cât timp
                   identitatea este verificata. Verificarea expira pe 2026-10-01."
     }
     ```
3. Frontend (Profile.jsx):
   - Apeleaza `GET /users/me/verification-status` la mount.
   - Daca `is_verified=true`, afișeaza banner sus cu data expirarii.
   - Marcheaza input-urile FROZEN cu icon 🔒 și atribut `disabled`.
   - Sectiunea "Ruta personala" devine read-only.

**Postcondi?ii:** Datele validate raman intacte. La 1 oct, credentialul
expira automat (lazy cleanup în `get_verification_status()`), iar
câmpurile redevin editabile. Utilizatorul trebuie sa reîncarce
documentele și sa fie re-aprobat de agent pentru a primi un nou card.

**Justificare:** Previne **identity laundering** — un atacator cu access
la cont nu poate transfera statusul "verificat" catre date frauduloase
(CNP/nume schimbat). Verificarea ramane ancorata în actele fizice
inspectate de agent.

**Acoperire de teste:** 17 teste integration în
`tests/integration/test_profile_freeze.py` (TestAcademicYearBoundary,
TestUnverifiedUserCanModifyEverything, TestVerifiedUserCannotModifyFrozenFields,
TestExpiredVerificationUnlocksFields, TestVerificationStatusEndpoint).

### UC46 - Cumparare abonament CFR cu scope pe ruta

**Actor:** Pasager (cu sau fara identitate verificata).

**Precondi?ii:**
- User autentificat
- Statiile de plecare si sosire exista
- User nu are deja un abonament `active` pe aceeasi ruta (in nicio directie)

**Flux principal:**

1. Pasagerul deschide **Abonamente** -> click "Cumpara abonament nou".
2. Selecteaza statia de plecare + statia de sosire (typeahead live cu `/stations/search`).
3. Selecteaza tip: `monthly` sau `annual`.
4. La fiecare schimbare, frontend-ul cere live un quote via `POST /subscriptions/quote`:
   - Backend calculeaza distanta din `routes.total_distance_km` (fallback: haversine din coordonate)
   - Aplica formula: `base = (distance * 0.5 + 50) * type_multiplier`
   - Verifica daca userul are credential `student_verified` activ
   - Verifica daca ruta selectata = `home_station ↔ university_station` (regula UC40/OUG 11/2024)
   - Daca DA: aplica reducere 90% (OUG 11/2024). Altfel: pret intreg.
   - Returneaza `{base_price, discount_amount, discount_pct, final_price, is_student_route, discount_reason}`
5. Pasagerul vede pretul + motivul reducerii (sau lipsa ei) si confirma.
6. `POST /subscriptions/buy`:
   - Re-verifica anti-overlap (`check_subscription_overlap`)
   - Insereaza abonament cu `subscription_scope='route'`, `status='active'`
   - Genereaza notificare confirmare
7. Pasagerul este redirectionat catre lista de abonamente, cu toast confirmare.

**Postcondi?ii:**
- Abonament `active` in DB cu `valid_from` = azi, `valid_until` = azi + 30 sau 365 zile
- Toate biletele cumparate pe ruta acoperita devin automat gratuite (vezi UC47)

**Erori posibile:**

- `400` - statia plecare == sosire / format invalid
- `400` - distanta indisponibila (statii fara coordonate)
- `409 subscription_overlap` - exista deja abonament activ pe ruta
- `401` - token absent/invalid

---

### UC47 - Bilet gratuit via abonament activ

**Actor:** Pasager cu abonament `active` pe ruta selectata.

**Tip:** Extindere a UC31 (Cumparare bilet) - se declanseaza automat la `/tickets/buy`.

**Flux:**

1. Pasagerul completeaza formularul de cumparare bilet ca de obicei (tren, statii, data, tip).
2. Frontend-ul detecteaza prin `getMySubscriptions()` daca exista abonament `active` care:
   - Are `subscription_scope='route'`
   - Acopera ruta selectata (in orice directie)
   - Are `valid_from <= travel_date <= valid_until`
3. Daca DA, **banner verde** in pagina BuyTicket:
   > "Acoperit de abonament. Biletul va fi GRATUIT (0 RON)."
4. La confirmare, `POST /tickets/buy`:
   - Backend apeleaza `find_active_subscription_for_route(user, from, to, date)` dupa anti-overlap check
   - Daca exista match -> dupa INSERT-ul ticketului, face UPDATE: `price=0, discount_applied=100, uses_subscription_id=N`
   - Restul flow-ului (entitlement, qr_token, seat confirmation) ramane neschimbat
5. Biletul rezultat este vizibil in **Biletele mele** cu pret 0 RON si poate fi validat in tren ca orice alt bilet.

**Postcondi?ii:**
- Bilet cu `price=0`, `uses_subscription_id` populat (audit trail)
- QR token valid pentru validare in tren
- Abonamentul ramane neschimbat (nu se decrementeaza nr de calatorii - sistem nelimitat in implementarea curenta)

**Reguli speciale:**

- **Anti-overlap normal se aplica**: chiar daca biletul e gratuit, daca userul are alt bilet activ in acelasi interval orar, primeste 409 (regula UC44).
- Daca abonamentul expira intre `travel_date` cumparare si data reala de calatorie, biletul ramane valid (era valid la momentul cumpararii).
- Anularea biletului cumparat via abonament nu da refund (pret=0) dar elibereaza locurile rezervate.

**Acoperire teste:**

- `test_ticket_on_covered_route_is_free` - confirma DB: price=0 + uses_subscription_id
- `test_ticket_on_uncovered_route_has_normal_price` - confirma ca abonamentul pe ruta A nu afecteaza biletul pe ruta B
