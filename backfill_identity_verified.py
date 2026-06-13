import psycopg, sys
sys.stdout.reconfigure(encoding='utf-8')
conn = psycopg.connect(host='localhost', port=5432, dbname='railway_db', user='railway', password='railway_dev')
cur = conn.cursor()

# Issuer default
cur.execute("SELECT id, name FROM issuers ORDER BY id LIMIT 3")
print("Issuers:", cur.fetchall())

# Useri cu student_card aprobat dar fara identity_verified activ
cur.execute("""
SELECT DISTINCT sd.user_id, u.email
FROM source_documents sd
JOIN users u ON u.user_id = sd.user_id
WHERE sd.document_type IN ('student_card', 'student_id')
  AND sd.status = 'approved'
  AND NOT EXISTS (
      SELECT 1 FROM user_credentials uc
      WHERE uc.user_id = sd.user_id
        AND uc.credential_type = 'identity_verified'
        AND uc.status = 'active'
        AND uc.valid_until > NOW()
  )
""")
users = cur.fetchall()
print(f"\nUseri care primesc backfill: {len(users)}")
for u in users:
    print(f"  user_id={u[0]} email={u[1]}")

# Issuer: primul din lista
cur.execute("SELECT id FROM issuers ORDER BY id LIMIT 1")
issuer_id = cur.fetchone()[0]
valid_until = '2026-10-01'

for uid, email in users:
    cur.execute("""
        INSERT INTO user_credentials (user_id, credential_type, claim_value, issuer_id, status, valid_until)
        VALUES (%s, 'identity_verified', 'true', %s, 'active', %s)
    """, (uid, issuer_id, valid_until))

conn.commit()
print(f"\n{len(users)} credentiale identity_verified create.")
conn.close()
