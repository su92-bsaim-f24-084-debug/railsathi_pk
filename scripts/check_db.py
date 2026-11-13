"""Database connectivity and isolation check script."""
import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()
db_url = os.environ.get('DATABASE_URL')
test_url = os.environ.get('TEST_DATABASE_URL')

print("Testing DATABASE_URL...")
conn_main = psycopg2.connect(db_url)
cur_m = conn_main.cursor()
cur_m.execute("SELECT version(), current_database();")
ver_m, db_m = cur_m.fetchone()
print(f"DATABASE_URL: connected to {db_m} | {ver_m[:45]}...")

print("\nTesting TEST_DATABASE_URL...")
conn_test = psycopg2.connect(test_url)
cur_t = conn_test.cursor()
cur_t.execute("SELECT version(), current_database();")
ver_t, db_t = cur_t.fetchone()
print(f"TEST_DATABASE_URL: connected to {db_t} | {ver_t[:45]}...")

# Isolation test: create a marker table on TEST and verify it is NOT in MAIN
cur_t.execute("CREATE TABLE IF NOT EXISTS _test_branch_isolation_check (id int);")
conn_test.commit()

cur_m.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = '_test_branch_isolation_check');")
exists_on_main = cur_m.fetchone()[0]

cur_t.execute("DROP TABLE IF EXISTS _test_branch_isolation_check;")
conn_test.commit()

cur_t.close()
conn_test.close()
cur_m.close()
conn_main.close()

print(f"\nMarker table on TEST exists on MAIN: {exists_on_main}")
assert not exists_on_main, "ERROR: DATABASE_URL and TEST_DATABASE_URL point to the same database!"
print("VERIFICATION SUCCESS: DATABASE_URL and TEST_DATABASE_URL point to two distinct, isolated databases.")

