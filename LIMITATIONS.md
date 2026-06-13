# Limitări cunoscute ale aplicației

Document scris la sfârșitul auditului autonom. Listează **ce NU face aplicația**, ca să nu fii surprins la prezentare.

---

## 1. Funcționalitate

### 1.1 Călătorii multi-leg (cu schimbări)
**STATUS**: NU implementat.

Aplicația suportă **doar bilete directe** (1 tren, 1 origin → 1 destination). Dacă nu există tren direct A → C, userul **nu poate** cumpăra automat itinerariu A → B → C.

**Workaround**: cumpără 2 bilete separate (A → B și B → C) manual.

**Cost estimat dezvoltare**: 2-3 ore (algoritm Dijkstra pe `route_stops` cu time windows).

### 1.2 Notificare push / email
**STATUS**: Doar in-app.

Notificările (bilet cumpărat, anulat, etc.) apar **doar** în `/notifications` pe interfața web. NU se trimit pe email, NU SMS, NU push.

### 1.3 Plată reală
**STATUS**: Mock.

Cumpărarea unui bilet sau abonament nu integrează un payment gateway. Tranzacția e doar marcată în DB. Nu sunt incluse Stripe/PayU/etc.

### 1.4 Anularea unui bilet din grup multi-pax
**STATUS**: Per-ticket, NU per-grup.

Dacă cumperi 3 bilete într-un singur call (multi-pasager), anularea **unuia** lasă celelalte 2 active. Nu există concept de "trip group cancel".

**Justificare business**: pasagerii pot avea schimbări de plan individuale.

### 1.5 Reschedule cu schimbare de traseu
**STATUS**: NU implementat.

Reprogramarea funcționează **doar** pe același traseu (aceleași stații origin/destination). Pentru altă rută → anulează + cumpără bilet nou.

---

## 2. Securitate

### 2.1 Rate limiting
**STATUS**: ABSENT.

`/auth/login` și `/auth/register` **nu** au rate limit. Un atacator poate face brute force pe parole.

**Workaround pentru demo**: parolele sunt complexe + bcrypt e slow → 1 încercare/secundă maxim.

**Recomandare prod**: `slowapi` + Redis.

### 2.2 Password policy
**STATUS**: Minim 6 chars (sub OWASP).

Backend acceptă orice parolă ≥6 caractere. Recomandare OWASP: 8+ + complexitate.

### 2.3 JWT logout
**STATUS**: NU implementat (by design pentru JWT stateless).

JWT-urile emise rămân valide până la `exp` (60 min). Nu există blacklist server-side. Userul își poate șterge token-ul din browser, dar dacă a fost furat de cineva, e valid 60min.

### 2.4 Email validation
**STATUS**: Slabă.

Backend acceptă `"@".in.email` ca validare. NU validează RFC 5322 complet. Acceptă `a@b` ca valid.

### 2.5 Privilege check pe endpointuri map
**STATUS**: Doar auth check, NU role check.

Orice user logat poate accesa `/map/stations`, `/map/connections`, etc. Nu există filtru pe rol (passenger vs admin).

**Justificare**: harta e info publică, nu sensibilă.

---

## 3. Date / OCR

### 3.1 MRZ scan
**STATUS**: Bazat pe euristici, fără validare cifră de control.

`extract_id_data` parsează MRZ-ul după pattern recognition. NU calculează cifra de control oficială ICAO 9303. Un scan parțial corect poate trece.

### 3.2 Format `ci_date_of_birth`
**STATUS**: Suportă 4 formate, NU toate.

Suport: `YYYY-MM-DD`, `DD.MM.YYYY`, `DD/MM/YYYY`, `YYMMDD` (MRZ).

NU suportă: text liber ("25 mai 2003"), formate cu locale, timestamps.

Format necunoscut → approve trece dar `users.date_of_birth` rămâne NULL.

---

## 4. Performanță

### 4.1 Test suite full timing
**TIMP**: ~2 minute pe 381 teste.

DB se recreează prima dată. Cleanup între teste face TRUNCATE pe tabele tranzitorii. Acceptabil pentru CI.

### 4.2 N+1 queries
**STATUS**: Audit pozitiv — niciun N+1 detectat.

Testele de performance confirmă:
- `/tickets/my` cu 10 bilete = <25 queries
- `/trains/{id}/seats` cu 60 locuri = <15 queries

### 4.3 Cache
**STATUS**: Absent.

Niciun endpoint nu folosește cache (Redis, memcached). Fiecare cerere lovește DB-ul. Pentru demo OK, pentru prod nu.

---

## 5. Compatibilitate

### 5.1 Browser
**TESTAT**: Chrome / Firefox / Brave (testat de utilizator).

NU testat: Safari, Edge mobile, IE.

### 5.2 Mobile responsive
**STATUS**: Tailwind responsive folosit, dar NU testat pe device real.

### 5.3 PWA / Offline
**STATUS**: Există `offline_presentation` flow, dar NU service worker, NU manifest pentru install.

---

## 6. Test stability

### 6.1 Test izolare
~10 teste din 381 sunt **flaky** în suita completă (~3% rate).

**Cauză**: state leakage între teste prin `KEEP_TABLES` care păstrează `users`, `stations`, etc.

**Workaround**: rulează individual sau cu `--forked` (proces separat per test).

### 6.2 Order-dependence
Unele teste presupun ordine seq (ex: testele DOB sync creează users + agents care interferează cu testele de pricing).

---

## 7. Internationalizare

### 7.1 Limbi
**SUPORTAT**: doar română.

UI-ul are texte hardcodate în română. Nu există i18n framework (react-i18next, etc).

### 7.2 Diacritice
**STATUS**: Suportat consistent.

Toate operațiunile pe nume (universități, stații) folosesc `unaccent()` în DB pentru match diacritic-insensitive.

---

## Recapitulare prioritizare

| Prioritate | Item | Cost dezvoltare |
|---|---|---|
| HIGH | Rate limiting login | 1h |
| MEDIUM | Trip planner multi-leg | 2-3h |
| MEDIUM | Plată reală (Stripe sandbox) | 4-6h |
| LOW | Push notifications | 2h |
| LOW | PWA install | 1h |
| LOW | i18n EN | 3h |

Toate sunt **post-licență**.
