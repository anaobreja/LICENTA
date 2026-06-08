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

    UC31 -.->|include| UC30
    UC33 -.->|include| UC32
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
