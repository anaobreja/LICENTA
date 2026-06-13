import psycopg

sql = open("database/07_ticket_legs_migration.sql", encoding="utf-8").read()
conn = psycopg.connect(host="localhost", port=5432, dbname="railway_db", user="railway", password="railway_dev")
conn.execute(sql)
conn.commit()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name='ticket_legs'")
print("ticket_legs exists:", cur.fetchone()[0] == 1)
conn.close()
print("Migrare 07 OK")
