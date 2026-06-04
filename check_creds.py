import sys
sys.path.insert(0, "backend")
from app.core.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

# What /credentials/me returns
rows = db.execute(text(
    "SELECT id, credential_type, status, valid_until "
    "FROM user_credentials uc "
    "WHERE user_id = (SELECT user_id FROM users WHERE email='user.demo@railwaydemo.com')"
)).mappings().all()
print("=== user_credentials rows ===")
for r in rows:
    print(dict(r))

# What _user_has_active_credentials returns
row = db.execute(text(
    "SELECT 1 FROM user_credentials "
    "WHERE user_id = (SELECT user_id FROM users WHERE email='user.demo@railwaydemo.com') "
    "AND status = 'active' LIMIT 1"
)).mappings().first()
print("\n=== _user_has_active_credentials ===", row is not None)

db.close()
