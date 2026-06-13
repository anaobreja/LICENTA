# Lucrare de licență — instrucțiuni de lucru

## Fișiere

| Fișier | Rol |
|---|---|
| `licenta.tex` | **Documentul principal LaTeX** — toate cele 7 capitole completate cu draft |
| `bibliography.bib` | Bibliografie BibTeX cu 20 surse (standarde RFC, W3C, GDPR, OUG, articole) |
| `LICENTA_TEMPLATE_BACKUP.txt` | Backup-ul template-ului original UPB (gol) |
| `LICENTA.txt` | Versiunea inițială a template-ului (păstrată ca referință) |

## Ce a fost completat

### Câmpuri de identitate (în preambul, înlocuiește cu datele tale reale)
- `\ProjectTitleRO` — *„Platformă digitală de identitate și gestiune a drepturilor de călătorie în transportul feroviar"*
- `\ProjectTitleEN` — varianta în engleză
- `\Name` — **`[Numele Autorului]`** ← înlocuiește
- `\Advisor` — **`[Titulatură și nume coordonator]`** ← înlocuiește
- `\Year` — 2026

### Capitole scrise (draft complet, gata de editat)
- **Sinopsis (RO) + Abstract (EN)** — în jur de 200 cuvinte fiecare
- **Mulțumiri**
- **Cap 1 — Introducere** (Context, Problema, Obiective, Soluția propusă, Rezultate, Structura lucrării)
- **Cap 2 — Analiza cerințelor** (4 actori, 5 scenarii, 9 funcționalități, cadru legislativ OUG/GDPR/eIDAS)
- **Cap 3 — Studiu de piață** (CFR/SNCF/SBB/Trainline, VC/eIDAS/ROeID, comparație criptografică RSA/ECDSA/Ed25519)
- **Cap 4 — Soluția propusă** (arhitectură pe straturi, modelul de date, 3 fluxuri principale)
- **Cap 5 — Detalii implementare** (Ed25519, anti-replay, layout vagoane PL/pgSQL, refund CFR, anti-overlap, MRZ, profile freeze)
- **Cap 6 — Evaluare** (76% coverage, 395 teste, tabel comparație vs CFR Călători)
- **Cap 7 — Concluzii** (sinteza, limitări, 5 direcții de dezvoltare)
- **Bibliografie** (referință la `bibliography.bib`)
- **Anexe** (placeholder)

## Compilare în Overleaf (recomandat)

1. Intră în Overleaf, **New Project → Upload Project → ZIP**
2. Selectează fișierele:
   - `licenta.tex`
   - `bibliography.bib`
   - folderul `pics/` (trebuie să adaugi logo-urile UPB — `upb-logo.jpg` și `cs-logo.pdf`)
3. În Overleaf: **Recompile**
4. Compilatorul: `pdfLaTeX` (default OK), Latin: bibtex (cleanup automat)

## Compilare locală (Windows + MikTeX)

```cmd
cd D:\LICENTA
pdflatex licenta.tex
bibtex licenta
pdflatex licenta.tex
pdflatex licenta.tex
```

> Compilarea triplă e necesară pentru ca referințele bibliografice (`\cite`) și TOC-ul să fie actualizate corect.

## Ce trebuie să faci tu

### 1. Completează datele personale
În `licenta.tex`, găsește și înlocuiește:
- `[Numele Autorului]` → numele tău complet
- `[Titulatură și nume coordonator]` → ex: `Prof. dr. ing. Andrei Popescu`

### 2. Adaugă logo-urile UPB
Template-ul cere două imagini în folderul `pics/`:
- `pics/upb-logo.jpg`
- `pics/cs-logo.pdf`

Le poți descărca de pe site-ul UPB sau le cere de la coordonator/decanat.

### 3. Inserează citările `\cite{}` în text
Bibliografia are 20 de surse, dar **nu le-am citat încă în text** (ca să nu pun referințe forțate). Recomandare:
- În Cap 1 Context: `\cite{eidas2}`, `\cite{w3cVcDataModel}`, `\cite{allenSSI}`
- În Cap 3 (algoritmi cripto): `\cite{bernsteinEd25519}`, `\cite{rfc8032}`
- În Cap 3 (aplicații): `\cite{cfrcalatori}`, `\cite{sncfConnect}`, `\cite{sbbMobile}`
- În Cap 4 (DB): `\cite{postgresql}`, `\cite{sqlalchemy}`
- În Cap 5 (auth): `\cite{rfc7519}`, `\cite{rfc6238}`, `\cite{icao9303}`
- În Cap 6 (securitate): `\cite{owaspTop10}`, `\cite{owaspAsvs}`
- În Cap 2 (legal): `\cite{oug112024}`, `\cite{gdpr}`

### 4. Recitește și personalizează stilul
Draftul actual e **scris la persoana a III-a, ton tehnic neutru** — verifică dacă coordonatorul preferă persoana I („am implementat") sau a III-a („a fost implementat").

### 5. Adaugă diagramele

Capitolul 4 (Soluția propusă) **trebuie să conțină diagrame** ca să atingă criteriul „Bine". Sugestii:
- Diagramă bloc arhitectură (pornind de la `docs/architecture.md` — convertește mermaid în PNG)
- Diagramă entitate-relație (din `docs/er-diagram.md`)
- Diagramă de secvență pentru fluxul de verificare ofline (din `docs/sequence.md`)

Pune-le în `pics/` și include-le cu:
```latex
\begin{figure}[th]
\centering
\includegraphics[width=0.9\textwidth]{pics/architecture.png}
\caption{Arhitectura pe straturi a platformei}
\label{fig:architecture}
\end{figure}
```

### 6. Adaugă extrase de cod în Anexe
În Cap 5 am citat funcții (\texttt{generate\_train\_layout}, \texttt{calculate\_refund}, etc.) — ar fi bine să le incluzi efectiv în Anexa A:

```latex
\lstinputlisting[language=SQL, caption=Funcția PL/pgSQL pentru generarea layout-ului]{database/06_seats_migration.sql}
```

## Statistici draft actual

| Element | Cantitate |
|---|---|
| Capitole completate | 7 / 7 |
| Pagini estimate (după compilare) | 35-45 |
| Cuvinte | ~6.500 |
| Tabele | 6 |
| Surse bibliografice gata | 20 |
| Citări `\cite{}` inserate în text | 0 (TO DO) |
| Figuri | 0 (TO DO — diagrame din `docs/`) |

## Pași imediați recomandați

1. **Acum (5 min)**: înlocuiește `[Numele Autorului]` și `[Titulatură coordonator]` în `licenta.tex`
2. **Astăzi (30 min)**: încarcă tot în Overleaf, vezi dacă compilează, ajustează ce nu arată bine
3. **Mâine**: adaugă citările `\cite{}` în text și convertește diagramele mermaid din `docs/` în PNG
4. **Săptămâna asta**: recitește fiecare capitol și adaugă observațiile tale personale / nuanțele care lipsesc

Spune-mi dacă vrei să continuu cu:
- Inserarea citărilor `\cite{}` în textul existent (durează ~10 min)
- Conversia diagramelor mermaid din `docs/` în TikZ / PNG
- Scrierea anexei A cu extrase de cod efective
- Verificarea compilării locale (dacă ai MikTeX instalat)
