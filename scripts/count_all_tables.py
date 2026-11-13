"""Count rows across all models in the database."""
import os
import sys
from dotenv import load_dotenv
import psycopg2

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

from app import create_app
from app.extensions import db
import app.models

app = create_app()

with app.app_context():
    tables = sorted(db.metadata.tables.keys())
    print(f"Counting rows across all {len(tables)} tables:\n")
    conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
    cur = conn.cursor()
    
    counts = {}
    for t in tables:
        cur.execute(f'SELECT count(*) FROM "{t}";')
        cnt = cur.fetchone()[0]
        counts[t] = cnt
        print(f"  {t:<35}: {cnt:>5} rows")
        
    cur.close()
    conn.close()

# Also verify Super Admin
with app.app_context():
    from app.models.identity import User, Role, UserRole
    from sqlalchemy import select
    admin = db.session.scalar(select(User).filter_by(email=os.environ.get('ADMIN_EMAIL', '').strip().lower()))
    if admin:
        roles = [ur.role.name for ur in admin.user_roles]
        print("\nSUPER ADMIN VERIFICATION:")
        print(f"  - Admin User Email: {admin.email}")
        print(f"  - Admin Roles: {roles}")
        print(f"  - Password Hash Present: {bool(admin.password_hash)}")
    else:
        print("\nSUPER ADMIN NOT FOUND!")

