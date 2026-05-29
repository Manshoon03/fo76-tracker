import sqlite3
import os
db_path = os.getenv('FO76_DB_PATH', '/home/manny/fo76-tracker/fo76.db')
print('Using DB:', db_path)
conn = sqlite3.connect(db_path)
stmts = [
    "ALTER TABLE fish_log ADD COLUMN caught_time TEXT DEFAULT ''",
    "ALTER TABLE fish_log ADD COLUMN logged_at TEXT DEFAULT ''",
    "ALTER TABLE fish_species ADD COLUMN catch_count INTEGER DEFAULT 0",
    "CREATE TABLE IF NOT EXISTS fish_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, character_id INTEGER DEFAULT 1, started_at TEXT NOT NULL, ended_at TEXT, notes TEXT DEFAULT '', created_at TEXT DEFAULT '')",
]
for sql in stmts:
    try:
        conn.execute(sql)
        conn.commit()
        print('OK:', sql[:60])
    except Exception as e:
        print('SKIP:', e)
conn.close()
print('Done.')
