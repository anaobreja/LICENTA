import psycopg
conn = psycopg.connect(host="localhost", port=5432, dbname="railway_db", user="railway", password="railway_dev")
cur = conn.cursor()
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
print([r[0] for r in cur.fetchall()])

# Verifica coloanele tabelului tickets
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='tickets' ORDER BY ordinal_position")
print("tickets cols:", [r[0] for r in cur.fetchall()])
conn.close()
