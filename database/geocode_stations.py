"""
Geocodificare stații CFR din OpenStreetMap via Overpass API.

Strategia:
1. Descarcă TOATE nodurile railway=station/halt/stop din bbox România cu un singur query Overpass
2. Construieste un index de nume -> (lat, lon)
3. Potriveste fiecare stație din DB (fara GPS) cu un nod OSM prin comparatie de nume
4. Actualizează DB-ul cu GPS găsite

Rulare: python database/geocode_stations.py
"""
import sys, re, unicodedata, time, json
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from urllib.error import URLError

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

import psycopg

DB_URL = "postgresql://railway:railway_dev@localhost:5432/railway_db"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

def normalize(s: str) -> str:
    """Normalizare pentru potrivire: lowercase, fara diacritice, fara sufixe."""
    if not s:
        return ""
    # NFKD decompose -> drop combining marks (diacritics)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    # Elimina sufixe comune CFR care nu apar in OSM
    for suffix in [" hm.", " h.", " ram.", " gr.a", " gr.b", " gr.c", " nord gr.a",
                   " triaj", " vest", " est", " sud", " calatori", " nord", " mag.",
                   " p.mac.", " p. mac."]:
        if s.endswith(suffix):
            s = s[:-len(suffix)].strip()
    # Elimina spatii multiple
    s = re.sub(r"\s+", " ", s)
    return s

def fetch_osm_stations() -> list[dict]:
    """Descarca toate statiile feroviare din Romania via Overpass."""
    query = """
[out:json][timeout:90];
(
  node["railway"~"station|halt|stop"]["name"](44.0,20.0,48.5,30.0);
  way["railway"~"station|halt"]["name"](44.0,20.0,48.5,30.0);
);
out center;
"""
    print("Descarcă stații din Overpass API...")
    req = Request(
        OVERPASS_URL,
        data=urlencode({"data": query}).encode(),
        method="POST",
    )
    req.add_header("User-Agent", "CFR-Thesis-Geocoder/1.0")
    try:
        with urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
        elements = data.get("elements", [])
        print(f"  {len(elements)} elemente OSM descărcate")
        return elements
    except URLError as e:
        print(f"  Eroare Overpass: {e}")
        return []

def build_osm_index(elements: list[dict]) -> dict[str, tuple[float, float]]:
    """Construieste index norm_name -> (lat, lon) din elementele OSM."""
    index: dict[str, list[tuple[float, float]]] = {}
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("name:ro", "")
        if not name:
            continue
        # Coordonate (node are lat/lon direct, way are in 'center')
        if el["type"] == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:
            center = el.get("center", {})
            lat, lon = center.get("lat"), center.get("lon")
        if lat is None or lon is None:
            continue
        key = normalize(name)
        if key:
            index.setdefault(key, []).append((lat, lon))
    # Pentru fiecare cheie pastreaza cel mai frecvent (sau primul) punct
    return {k: v[0] for k, v in index.items()}

def best_match(norm_name: str, osm_index: dict) -> tuple[float, float] | None:
    """Cauta cea mai buna potrivire pentru un nume de statie."""
    # Match exact
    if norm_name in osm_index:
        return osm_index[norm_name]
    # Match partial - primul cuvant semnificativ
    words = norm_name.split()
    if len(words) >= 2:
        # incearca fara ultimul cuvant (ex. "buzau ram" -> "buzau")
        shorter = " ".join(words[:-1])
        if shorter in osm_index:
            return osm_index[shorter]
    return None

def main():
    conn = psycopg.connect(DB_URL)
    cur = conn.cursor()

    # Incarca statiile fara GPS
    cur.execute("""
        SELECT station_id, name, code
        FROM stations
        WHERE latitude IS NULL OR longitude IS NULL
        ORDER BY name
    """)
    stations = cur.fetchall()
    print(f"\n{len(stations)} stații fără GPS în DB")

    # Descarca OSM
    elements = fetch_osm_stations()
    if not elements:
        # Fallback: Nominatim pentru fiecare statie (mai lent)
        print("Overpass esuat - încearcă din nou sau rulează mai târziu")
        conn.close()
        return

    osm_index = build_osm_index(elements)
    print(f"  {len(osm_index)} stații unice în indexul OSM")

    updated = 0
    not_found = []

    for station_id, name, code in stations:
        norm = normalize(name)
        coords = best_match(norm, osm_index)
        if coords:
            lat, lon = coords
            cur.execute(
                "UPDATE stations SET latitude=%s, longitude=%s WHERE station_id=%s",
                (round(lat, 6), round(lon, 6), station_id)
            )
            updated += 1
        else:
            not_found.append(name)

    conn.commit()
    print(f"\n✓ GPS actualizat pentru {updated} stații")
    print(f"✗ Negăsite: {len(not_found)}")
    if not_found[:20]:
        print("  Exemple negăsite:", not_found[:20])

    # Verificare finala
    cur.execute("SELECT COUNT(*) FROM stations WHERE latitude IS NOT NULL")
    total_with_gps = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM stations")
    total = cur.fetchone()[0]
    print(f"\nTotal după geocodare: {total_with_gps}/{total} stații cu GPS")

    conn.close()

if __name__ == "__main__":
    main()
