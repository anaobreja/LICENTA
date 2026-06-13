import psycopg, sys
sys.stdout.reconfigure(encoding='utf-8')
conn = psycopg.connect(host='localhost', port=5432, dbname='railway_db', user='railway', password='railway_dev')
cur = conn.cursor()

cur.execute(r"""
SELECT COUNT(*) FROM stations s
WHERE s.latitude IS NOT NULL
AND (
    s.is_university_hub = TRUE
    OR s.name ~* '(Gr\.?|hm\.?|Sat h\.|h\.)(\s*)$'
    OR s.name ~* '(Nord|Sud|Est|Vest|C[aă]l[aă]tori)(\s*)$'
    OR s.name ~* 'Triaj|Depou|Tehnic|Aeroport|Macaz|Pasaj|Rampa|R\. \d'
    OR (SELECT COUNT(*) FROM route_stops rs_cnt WHERE rs_cnt.station_id = s.station_id) >= 100
)
""")
print('Statii pe harta:', cur.fetchone()[0])

cur.execute(r"""
SELECT name FROM stations s
WHERE s.latitude IS NOT NULL
AND s.name ILIKE '%Huedin%'
AND (
    s.is_university_hub = TRUE
    OR s.name ~* '(Gr\.?|hm\.?|Sat h\.|h\.)(\s*)$'
    OR s.name ~* '(Nord|Sud|Est|Vest|C[aă]l[aă]tori)(\s*)$'
    OR s.name ~* 'Triaj|Depou|Tehnic|Aeroport|Macaz|Pasaj|Rampa|R\. \d'
    OR (SELECT COUNT(*) FROM route_stops rs_cnt WHERE rs_cnt.station_id = s.station_id) >= 100
)
""")
h = cur.fetchall()
print('Huedin prezent:', len(h) > 0)

# Check Galati, Brasov, Cluj
cur.execute(r"""
SELECT s.name FROM stations s
WHERE s.latitude IS NOT NULL
AND (unaccent(s.name) ILIKE 'Galati%' OR unaccent(s.name) ILIKE 'Brasov%' OR s.name ILIKE 'Cluj%')
AND (
    s.is_university_hub = TRUE
    OR s.name ~* '(Gr\.?|hm\.?|Sat h\.|h\.)(\s*)$'
    OR s.name ~* '(Nord|Sud|Est|Vest|C[aă]l[aă]tori)(\s*)$'
    OR s.name ~* 'Triaj|Depou|Tehnic|Aeroport|Macaz|Pasaj|Rampa|R\. \d'
    OR (SELECT COUNT(*) FROM route_stops rs_cnt WHERE rs_cnt.station_id = s.station_id) >= 100
)
ORDER BY name
""")
print('Galati/Brasov/Cluj pe harta:', [r[0] for r in cur.fetchall()])

# R. Aeroport T1
cur.execute(r"""
SELECT name FROM stations s
WHERE s.latitude IS NOT NULL
AND s.name ILIKE '%Aeroport%'
AND (
    s.name ~* 'Triaj|Depou|Tehnic|Aeroport|Macaz|Pasaj|Rampa|R\. \d'
)
LIMIT 5
""")
print('Aeroport:', [r[0] for r in cur.fetchall()])

conn.close()
