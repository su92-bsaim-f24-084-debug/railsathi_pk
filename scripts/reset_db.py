"""Database schema reset helper script with strict safety guards.

Refuses to execute unless:
1. Environment variable CONFIRM_RESET is explicitly set to 'yes'.
2. The target database is NOT a production database (rejects if FLASK_ENV=production or RENDER is set).
"""
import os
import sys
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Safety Check 1: Explicit confirmation variable required
if os.environ.get("CONFIRM_RESET") != "yes":
    print("ABORTED: Refusing to reset database without explicit confirmation.")
    print("To proceed on a non-production development database, run:")
    print("  CONFIRM_RESET=yes python scripts/reset_db.py")
    sys.exit(1)

# Safety Check 2: Strictly prohibit running against production
flask_env = os.environ.get("FLASK_ENV", "").lower()
is_render = bool(os.environ.get("RENDER"))
db_url = os.environ.get("DATABASE_URL", "")

if flask_env == "production" or is_render or "prod" in db_url.lower():
    print("FATAL: reset_db.py cannot be run against a production database environment!")
    sys.exit(1)

print("Connecting to development database to reset public schema...")
conn = psycopg2.connect(db_url)
conn.autocommit = True
cur = conn.cursor()
cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
cur.close()
conn.close()
print("Cleaned public schema on development database successfully.")

