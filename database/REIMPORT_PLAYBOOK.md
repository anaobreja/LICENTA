# Playbook: reimport date CFR fără pierderea coordonatelor GPS

## Context

Tabela `stations` conține date din **trei surse independente**:

| Sursă | Coloane populate | Script | Re-rulabil? |
|---|---|---|---|
| 1. XML CFR (data.gov.ro) | `name`, `code`, `city`, `country`, `is_active` | `import_cfr.py` | da, sigur cu `--reset` |
| 2. OpenStreetMap (Overpass API) | `latitude`, `longitude` | `geocode_stations.py` | da, idempotent |
| 3. Dataset universități (hardcoded) | `is_university_hub`, `student_count`, `universities_count`, `notes` | `04_university_stations.sql` | da, idempotent |

**Regula de aur:** scripturile NU se suprascriu reciproc. Fiecare actualizează strict coloanele care îi aparțin.

---

## ⚠️ Scenarii care DISTRUG datele

### 🔴 `docker compose down -v`
Șterge volumul Postgres. Pierzi **TOT**: useri, stații, coordonate GPS, abonamente, etc. Nu folosi decât dacă vrei reset total.

### 🟡 `psql ... < database/schema.sql`
`schema.sql` are `DROP TABLE IF EXISTS stations CASCADE` la început. Recrează schema goală. Pierzi coordonatele GPS și metadatele universitare.

### 🟢 `python database/import_cfr.py --reset` ← **SIGUR**
NU șterge `stations` (FK-urile sunt RESTRICT). Doar reinserează/actualizează `name` la stațiile existente. Coordonatele GPS și flag-urile universitare rămân intacte. Sanity check-ul afișează câte stații cu GPS rămân, ca să detectezi imediat o regresie.

---

## ✅ Workflow sigur pentru reimport CFR (anual sau la nevoie)

```cmd
cd D:\LICENTA

# 1. Import trenuri/rute noi (păstrează GPS + hub universitar)
python database/import_cfr.py --reset

# 2. Geocodează STAȚIILE NOI (cele apărute în XML-ul nou)
#    Skip dacă numărul de stații nu s-a schimbat
python database/geocode_stations.py

# 3. Re-rulează SQL-ul cu universități
#    (în caz că s-au adăugat stații noi în centre universitare)
docker exec -i railway_db psql -U railway -d railway_db < database/04_university_stations.sql

# 4. Verifică rezultatul
docker exec railway_db psql -U railway -d railway_db -c "SELECT COUNT(*) AS total, COUNT(latitude) AS cu_gps, ROUND(COUNT(latitude)*100.0/COUNT(*), 1) AS procent FROM stations;"
```

**Așteptat după rulare corectă:**
```
 total | cu_gps | procent 
-------+--------+---------
  1818 |   1459 |    80.3
```

---

## 🔧 Workflow recovery (dacă ai pierdut GPS-urile)

Asta s-a întâmplat o dată — cauza probabilă: cineva a rulat `down -v` sau a re-aplicat `schema.sql`. Recovery în 2 pași:

```cmd
cd D:\LICENTA

# 1. Restaurează coordonatele GPS (durează 30-90s)
python database/geocode_stations.py

# 2. Restaurează flag-urile universitare
docker exec -i railway_db psql -U railway -d railway_db < database/04_university_stations.sql

# 3. Verifică
docker exec railway_db psql -U railway -d railway_db -c "SELECT COUNT(latitude) FROM stations;"
```

**Notă:** `geocode_stations.py` e idempotent — rulează doar pentru stațiile cu `latitude IS NULL`. Dacă toate stațiile au deja GPS, scriptul nu face nimic.

---

## 📊 Statistici așteptate (baseline 2026-06-11)

| Metrică | Valoare |
|---|---|
| Stații totale | 1818 |
| Stații cu GPS | ~1459 (80%) |
| Stații fără GPS | ~360 (halte mici, puncte de mișcare — nu există în OSM) |
| Hub-uri universitare | 19 |
| Studenți acoperiți | ~576.000 |
| Operatori feroviari | 7 |
| Rute | 2103 |
| Trenuri | 2103 |
| Opriri (route_stops) | 46.501 |

Dacă vezi cifre semnificativ mai mici după un reimport → ceva nu a mers. Recitește acest playbook.

---

## 🛡️ Fix-ul defensiv din `import_cfr.py` (aplicat 2026-06-10)

### Modificare 1: sanity check la `--reset`

```python
if reset:
    # ...truncate trenuri/rute/etc...
    # Sanity check post-reset: confirma ca stations au ramas cu coordonate
    cur.execute(
        "SELECT COUNT(*) AS total, COUNT(latitude) AS cu_gps FROM stations WHERE code LIKE 'CFR-%'"
    )
    row = cur.fetchone()
    if row and row[0] > 0:
        print(f"  Stations pastrate: {row[0]} total, {row[1]} cu coordonate GPS")
```

Output așteptat la rulare:
```
Reset: stergem datele de transport existente (pastram users/universities/issuers)...
  Stations pastrate: 1818 total, 1459 cu coordonate GPS
Reset done.
```

Dacă vezi `1818 total, 0 cu coordonate GPS` → știi imediat că trebuie să rerulezi geocoderul.

### Modificare 2: `ON CONFLICT` documentat explicit

```python
INSERT INTO stations (name, code, city, country, is_active)
VALUES (%s, %s, %s, 'Romania', TRUE)
ON CONFLICT (code) DO UPDATE
  SET name = EXCLUDED.name
  -- coordonatele GPS si metadatele universitate raman neatinse
RETURNING station_id
```

Comentariul previne ca cineva care recitește codul peste 6 luni să „optimizeze" prin adăugarea de `latitude=EXCLUDED.latitude` (care ar fi NULL la fiecare reimport).

---

## 📁 Fișiere implicate

| Fișier | Rol |
|---|---|
| `database/import_cfr.py` | Import trenuri + rute din XML CFR |
| `database/geocode_stations.py` | Geocoding stații cu Overpass API |
| `database/04_university_stations.sql` | Flag-uri pentru centre universitare |
| `database/schema.sql` | Schema completă a BD (⚠️ folosește doar la setup inițial) |
| `database/external/*.xml` | XML-uri descărcate de pe data.gov.ro |

---

## 🔗 Surse de date

- **Mers tren**: https://data.gov.ro (căutare „mers tren", licență CC-BY 4.0)
- **OpenStreetMap**: https://overpass-api.de/api/interpreter (gratuit, fără autentificare)
- **Centre universitare**: hardcoded în `04_university_stations.sql` (revizuit anual)
