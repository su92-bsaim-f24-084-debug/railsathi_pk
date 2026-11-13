"""Query table counts and index definitions from PostgreSQL pg_indexes."""
import os
import sys
from dotenv import load_dotenv
import psycopg2

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
cur = conn.cursor()

# 1. Total table count in public schema
cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")
table_count = cur.fetchone()[0]
print("=" * 80)
print(f"TOTAL TABLES IN public SCHEMA: {table_count} (Expect 51: 50 domain tables + alembic_version)")
print("=" * 80)

# Check alembic_version exists
cur.execute("SELECT version_num FROM alembic_version;")
alembic_rev = cur.fetchone()[0]
print(f"Current Alembic revision in database: {alembic_rev}\n")

# 2. Index definitions for stations, users, bookings from pg_indexes
target_tables = ['stations', 'users', 'bookings']
print("=" * 80)
print("INDEX DEFINITIONS FROM pg_indexes (stations, users, bookings)")
print("=" * 80)

for tbl in target_tables:
    cur.execute("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public' AND tablename = %s
        ORDER BY indexname;
    """, (tbl,))
    rows = cur.fetchall()
    print(f"\nTABLE: {tbl} ({len(rows)} indexes)")
    print("-" * 50)
    for idx_name, idx_def in rows:
        print(f"  * {idx_name}:")
        print(f"    {idx_def}")

cur.close()
conn.close()

