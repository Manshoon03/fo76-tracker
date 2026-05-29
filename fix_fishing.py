import sqlite3
conn = sqlite3.connect('/home/manny/fo76-tracker/fo76.db')
stmts = [
    "ALTER TABLE fish_log ADD COLUMN caught_time TEXT DEFAULT ''",
    "ALTER TABLE fish_log ADD COLUMN logged_at TEXT DEFAULT (datetime('now'))",
    "ALTER TABLE fish_species ADD COLUMN catch_count INTEGER DEFAULT 0",
    "CREATE TABLE IF NOT EXISTS fish_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, character_id INTEGER DEFAULT 1, started_at TEXT NOT NULL, ended_at TEXT, notes TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now')))",
]
for sql in stmts:
    try:
        conn.execute(sql)
        print('OK:', sql[:60])
    except Exception as e:
        print('SKIP:', e)
conn.commit()
conn.close()
print('Done.')
