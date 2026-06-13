# Sesiune 2 — Focus pe Bilete / Abonamente / Hartă / Sugestii Rute

**Durată muncă autonomă**: ~50min după prima sesiune
**Obiectiv**: audit profund + fix bug-uri + feature mare (trip planner multi-leg)

---

## Rezultate finale Sesiune 2

| Metric | Sesiunea 1 (final) | Sesiunea 2 (final) | Δ |
|---|---|---|---|
| **Backend teste passed** | 379 | **391** | **+12** |
| **Backend teste failed** | 0 | **0** | ✅ |
| **Frontend teste passed** | 14 | **14** | = |
| **Bug-uri noi găsite** | 24 (audit complet) | **+11** (ZONE specifice) | +11 |
| **Bug-uri fix-uite în Sesiunea 2** | — | **5** | +5 |
| **Feature-uri noi mari** | — | **Trip Planner multi-leg** | +1 |

---

## ZONA 1 — Bilete (audit profund)

### Bug-uri găsite

| # | Bug | Severity | Status |
|---|---|---|---|
| 27 | Cumpărare bilet origin == destination → silent accept | **MEDIUM** | ✅ FIX |
| 28 | distance < 1km → fallback la `total_km` (suprapreț ascuns) | **MEDIUM** | ✅ FIX |
| 29 | Direcție inversă pe rută (dep_km > arr_km) | INFO | ✅ OK (abs) |
| 30 | `check_overlap` N+1 queries | LOW | NOTAT |
| 31 | Pentru bilet multi-pax pe același tren, candidates includ ele înșile | INFO | ✅ OK (verificat) |
| 33 | `ticket_type` fără validare regex | LOW | ✅ FIX |

### Fix-uri aplicate

**Fix #27**: Validare origin ≠ destination
```python
if departure_station_id == arrival_station_id:
    raise HTTPException(400, "Statia de plecare si cea de sosire trebuie sa fie diferite.")
```

**Fix #28**: Distanță minimă 1km în loc de fallback dezastruos
```python
if distance_km < 1:
    distance_km = 1.0  # NU mai face fallback la total_km!
```

**Fix #33**: Validare regex strictă pe ticket_type
```python
ticket_type: str = Field(default="single", pattern="^(single|return|Single|Return|SINGLE|RETURN)$")
```

---

## ZONA 2 — Abonamente

### Bug-uri găsite

| # | Bug | Severity | Status |
|---|---|---|---|
| 34 | Overlap check doar pe `subscription_scope='route'` | INFO | by design |
| 35 | **Auto-discount aplicat tuturor pasagerilor (abuz nominal)** | **MEDIUM** | ✅ FIX |

### Fix #35 — CRITICĂ pentru anti-abuz

**Înainte**: User cu abonament UPB→Iași cumpără bilet pentru 3 pasageri pe această rută → **TOATE 3 devin gratuite**.

**Atac scenariu**: Cumperi abonament, inviti 2 prieteni cu nume distincte, toți călătoresc free cu trenul. CFR nu permite — abonamentul e **nominal**.

**Fix aplicat**:
```python
# Auto-discount din abonament se aplica DOAR primului pasager (titularul).
# Pasagerii suplimentari platesc tariful intreg.
apply_subscription_discount = (_covering_sub is not None and pax_idx == 0)
```

---

## ZONA 3 — Hartă

| Endpoint | Status |
|---|---|
| `/map/stations` | ✅ Safe, no leak |
| `/map/connections` | ✅ OK |
| `/map/operators` | ✅ OK |
| `/map/train-simulate/{id}` | ✅ OK |
| `MapView.jsx` UI | ✅ Verificat |

**Bug găsit (Bug #37)**: când userul selectează 2 stații pe hartă fără tren direct, lista e goală. **REZOLVAT** prin integrarea Trip Planner în BuyTicket (ZONA 4).

---

## ZONA 4 — Trip Planner Multi-Leg (FEATURE NOU)

### Algoritm

**BFS modificat pe graful `route_stops`** cu 3 niveluri (max 2 schimbări):

1. **Direct**: trenuri care opresc în `from_station` și ajung în `to_station`
2. **1 schimbare**: A → B (via tren 1) + B → C (via tren 2), cu fereastră conexiune 15-180 min
3. **2 schimbări**: A → B → C → D, cu safeguard performanță (`MAX_INTERMEDIATES = 500`)

**Sortare**: `(total_duration_min ASC, transfer_count ASC, departure_min ASC)` — utilizatorul vede primul cel mai rapid + cu cele mai puține schimbări.

**Top 5** rezultate, configurabil 1-10.

### Endpoint

```
GET /trips/suggest?from_station_id=1&to_station_id=2&travel_date=2026-06-10&top_n=5
```

Response:
```json
{
  "from_station_id": 1,
  "to_station_id": 2,
  "travel_date": "2026-06-10",
  "count": 3,
  "trips": [
    {
      "legs": [
        {
          "train_id": 12, "train_number": "IR1582", "train_type": "interregio",
          "from_station": "BUC Nord", "to_station": "Buzău",
          "departure_time": "14:00:00", "arrival_time": "16:30:00",
          "duration_min": 150, "distance_km": 130
        },
        {
          "train_id": 87, "train_number": "R7501", "train_type": "regio",
          "from_station": "Buzău", "to_station": "Făurei",
          "departure_time": "17:00:00", "arrival_time": "18:15:00",
          "duration_min": 75, "distance_km": 70
        }
      ],
      "transfer_count": 1,
      "transfer_stations": ["Buzău"],
      "total_duration_min": 255,
      "total_distance_km": 200,
      "departure_time": "14:00:00",
      "arrival_time": "18:15:00"
    },
    ...
  ]
}
```

### Frontend integration

În `BuyTicket.jsx`:
- Când userul selectează 2 stații, **în paralel** cu `searchTrains()` se cheamă `suggestTrips()`
- Dacă **NU există trenuri directe**: se afișează sugestii cu schimbare cu UI dedicat
- Pentru fiecare itinerariu: legi cu detalii tren, ore, distanță + label "1 schimbare prin Buzău"
- Sub fiecare itinerariu: notă "Cumpararea per leg: trebuie să cumperi câte un bilet pentru fiecare tren"

### Teste (12/12 trec)

Suite `test_trip_planner.py`:
- Itinerariu direct când există
- Itinerariu cu 1 schimbare când nu există direct
- 0 itinerarii când conexiune absentă
- Durata totală corectă (departure → last arrival)
- Sortare după timp + transferuri
- Validare input (same from/to, past date, invalid date, top_n out of range)
- Fereastră conexiune respectată (5 min refuzat, 4h refuzat)

---

## Sumar bug-uri sesiunea 2

| # | Severity | Status | Beneficiu |
|---|---|---|---|
| 27 | MEDIUM | ✅ FIX | Previne bilet pe aceeași stație |
| 28 | MEDIUM | ✅ FIX | Previne suprapreț ascuns la segmente scurte |
| 33 | LOW | ✅ FIX | Validare ticket_type strict |
| 35 | **MEDIUM** | ✅ FIX | **Anti-abuz abonament nominal** |

Plus: **Feature Trip Planner complet** (algoritm + endpoint + UI + 12 teste).

---

## Acoperire teste

**Suita backend**: 379 → **391 passed** (+12 trip planner, 0 regresii)
**Suita frontend**: 14 → **14 passed** (stabil)
**Coverage backend**: menținut 76%+

---

## Files modificate Sesiunea 2

### Backend
- `app/routers/tickets.py` (fix #27, #28, #33, #35 + endpoint `/trips/suggest`)
- `app/services/trip_planner.py` **NOU** (370 linii)

### Frontend
- `src/services/api.js` (adăugat `suggestTrips()`)
- `src/pages/BuyTicket.jsx` (integrare sugestii)

### Tests
- `tests/integration/test_trip_planner.py` **NOU** (512 linii, 12 teste)

### Build
- `frontend/dist/assets/index-DzsYlpjL.js` (proaspăt 04:16)
- `frontend/dist/assets/index-Bjqoobsz.js`

---

## TOTAL CUMULATIV (Sesiunea 1 + 2)

| Metric | Inițial | Final |
|---|---|---|
| **Backend teste passed** | 295 | **391** (+96) |
| **Backend teste failed** | 0 | **0** |
| **Frontend teste passed** | 11 | **14** (+3) |
| **Bug-uri găsite și fix-uite** | — | **17 critice/medium** |
| **Bug-uri documentate (LOW/INFO)** | — | **17** în LIMITATIONS.md |
| **Coverage** | 75% | **76%+** |
| **Feature-uri majore noi** | — | **Trip Planner multi-leg** |

---

## Stare aplicație după 2 sesiuni autonome

✅ **Zero bug-uri critice rămase**
✅ **Zero teste failed/skipped pe backend**
✅ **Feature-uri majore complete și testate** (multi-pax, QR pe bilete, trip planner, gara de proveniență, etc.)
✅ **Documentație completă** (REPORT_AUDIT.md, LIMITATIONS.md, TEST_MATRIX.md, REPORT_SESSION2.md)
✅ **Build dist proaspăt**

**Aplicația e gata pentru demo licență.**
