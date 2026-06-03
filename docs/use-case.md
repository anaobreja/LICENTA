# Diagrame Use Case

## Actori

| Actor | Descriere |
|-------|-----------|
| **Pasager (Student)** | Utilizatorul care depune documente și folosește cardul digital |
| **Agent Universitar** | Verifică și aprobă/respinge cererile studenților universității sale și emite credențiale |
| **Agent Tren** | Scanează cardul digital al pasagerului în tren |

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

    UC20 -.->|extend| UC21
    UC22 -.->|include| UC23
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
