import sqlite3
import os
import shutil
import glob
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fo76.db')

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    # Performance pragmas — WAL mode allows reads while writing,
    # larger cache reduces disk hits, NORMAL sync is safe and faster
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA cache_size=-8000")   # ~8 MB cache
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS characters (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            platform   TEXT DEFAULT 'PC',
            char_type  TEXT DEFAULT 'Playable',
            level      INTEGER DEFAULT 1,
            notes      TEXT DEFAULT '',
            created_at TEXT DEFAULT (date('now'))
        );
        CREATE TABLE IF NOT EXISTS perk_cards (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            special      TEXT NOT NULL DEFAULT 'S',
            current_rank INTEGER DEFAULT 1,
            max_rank     INTEGER DEFAULT 3,
            copies_owned INTEGER DEFAULT 1,
            effect       TEXT DEFAULT '',
            used_in      TEXT DEFAULT '',
            can_scrap    TEXT DEFAULT 'No',
            notes        TEXT DEFAULT '',
            created_at   TEXT DEFAULT (date('now'))
        );
        CREATE TABLE IF NOT EXISTS builds (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            playstyle  TEXT DEFAULT '',
            s INTEGER DEFAULT 1, p INTEGER DEFAULT 1, e INTEGER DEFAULT 1,
            c INTEGER DEFAULT 1, i INTEGER DEFAULT 1, a INTEGER DEFAULT 1,
            l INTEGER DEFAULT 1,
            key_cards  TEXT DEFAULT '',
            notes      TEXT DEFAULT '',
            created_at TEXT DEFAULT (date('now'))
        );
        CREATE TABLE IF NOT EXISTS weapons (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            wtype         TEXT DEFAULT '',
            damage_type   TEXT DEFAULT 'Ballistic',
            star1         TEXT DEFAULT '',
            star2         TEXT DEFAULT '',
            star3         TEXT DEFAULT '',
            mods          TEXT DEFAULT '',
            condition_pct INTEGER DEFAULT 100,
            weight        REAL DEFAULT 0,
            value         INTEGER DEFAULT 0,
            status        TEXT DEFAULT 'Keep',
            notes         TEXT DEFAULT '',
            created_at    TEXT DEFAULT (date('now'))
        );
        CREATE TABLE IF NOT EXISTS armor (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            slot       TEXT DEFAULT '',
            material   TEXT DEFAULT '',
            star1      TEXT DEFAULT '',
            star2      TEXT DEFAULT '',
            star3      TEXT DEFAULT '',
            mods       TEXT DEFAULT '',
            dr INTEGER DEFAULT 0,
            er INTEGER DEFAULT 0,
            rr INTEGER DEFAULT 0,
            weight     REAL DEFAULT 0,
            status     TEXT DEFAULT 'Keep',
            notes      TEXT DEFAULT '',
            created_at TEXT DEFAULT (date('now'))
        );
        CREATE TABLE IF NOT EXISTS mods (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            applies_to TEXT DEFAULT '',
            effect     TEXT DEFAULT '',
            qty        INTEGER DEFAULT 1,
            value_each INTEGER DEFAULT 0,
            status     TEXT DEFAULT 'Keep',
            notes      TEXT DEFAULT '',
            created_at TEXT DEFAULT (date('now'))
        );
        CREATE TABLE IF NOT EXISTS vendor_stock (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT NOT NULL,
            category         TEXT DEFAULT '',
            description      TEXT DEFAULT '',
            qty              INTEGER DEFAULT 1,
            my_price         INTEGER DEFAULT 0,
            avg_market_price INTEGER DEFAULT 0,
            date_listed      TEXT DEFAULT (date('now')),
            notes            TEXT DEFAULT '',
            created_at       TEXT DEFAULT (date('now'))
        );
        CREATE TABLE IF NOT EXISTS price_research (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name   TEXT NOT NULL,
            category    TEXT DEFAULT '',
            description TEXT DEFAULT '',
            price_seen  INTEGER DEFAULT 0,
            source      TEXT DEFAULT '',
            date_seen   TEXT DEFAULT (date('now')),
            notes       TEXT DEFAULT '',
            created_at  TEXT DEFAULT (date('now'))
        );
        CREATE TABLE IF NOT EXISTS plans (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            category      TEXT DEFAULT '',
            unlocks       TEXT DEFAULT '',
            learned       INTEGER DEFAULT 0,
            qty_unlearned INTEGER DEFAULT 0,
            sell_price    INTEGER DEFAULT 0,
            status        TEXT DEFAULT 'Keep',
            notes         TEXT DEFAULT '',
            created_at    TEXT DEFAULT (date('now'))
        );
        CREATE TABLE IF NOT EXISTS inventory (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            category    TEXT DEFAULT '',
            sub_type    TEXT DEFAULT '',
            qty         INTEGER DEFAULT 1,
            weight_each REAL DEFAULT 0,
            value_each  INTEGER DEFAULT 0,
            status      TEXT DEFAULT 'Keep',
            notes       TEXT DEFAULT '',
            created_at  TEXT DEFAULT (date('now'))
        );
        CREATE TABLE IF NOT EXISTS challenges (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            ctype        TEXT DEFAULT 'Daily',
            category     TEXT DEFAULT '',
            description  TEXT DEFAULT '',
            progress     INTEGER DEFAULT 0,
            target       INTEGER DEFAULT 1,
            completed    INTEGER DEFAULT 0,
            reward       TEXT DEFAULT '',
            notes        TEXT DEFAULT '',
            completed_at TEXT DEFAULT '',
            created_at   TEXT DEFAULT (date('now'))
        );
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS notices (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT NOT NULL,
            body       TEXT DEFAULT '',
            level      TEXT DEFAULT 'info',
            expires_at TEXT DEFAULT '',
            created_at TEXT DEFAULT (date('now'))
        );
        CREATE TABLE IF NOT EXISTS nuke_codes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            silo       TEXT NOT NULL,
            code       TEXT DEFAULT '',
            week_of    TEXT DEFAULT '',
            notes      TEXT DEFAULT '',
            updated_at TEXT DEFAULT (date('now'))
        );
        CREATE TABLE IF NOT EXISTS feeds (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            url        TEXT NOT NULL UNIQUE,
            enabled    INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (date('now'))
        );
        CREATE TABLE IF NOT EXISTS power_armor (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            pa_set        TEXT DEFAULT '',
            slot          TEXT DEFAULT '',
            star1         TEXT DEFAULT '',
            star2         TEXT DEFAULT '',
            star3         TEXT DEFAULT '',
            mods          TEXT DEFAULT '',
            condition_pct INTEGER DEFAULT 100,
            weight        REAL DEFAULT 0,
            value         INTEGER DEFAULT 0,
            status        TEXT DEFAULT 'Keep',
            notes         TEXT DEFAULT '',
            created_at    TEXT DEFAULT (date('now'))
        );
        CREATE TABLE IF NOT EXISTS mutations (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT NOT NULL,
            effects_positive TEXT DEFAULT '',
            effects_negative TEXT DEFAULT '',
            active           INTEGER DEFAULT 1,
            build_id         INTEGER DEFAULT 0,
            notes            TEXT DEFAULT '',
            created_at       TEXT DEFAULT (date('now'))
        );
        CREATE TABLE IF NOT EXISTS season_score_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            log_date     TEXT DEFAULT (date('now')),
            score_earned INTEGER DEFAULT 0,
            notes        TEXT DEFAULT '',
            created_at   TEXT DEFAULT (date('now'))
        );
        CREATE TABLE IF NOT EXISTS wishlist (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name   TEXT NOT NULL,
            category    TEXT DEFAULT '',
            max_price   INTEGER DEFAULT 0,
            priority    TEXT DEFAULT 'Normal',
            description TEXT DEFAULT '',
            found       INTEGER DEFAULT 0,
            notes       TEXT DEFAULT '',
            created_at  TEXT DEFAULT (date('now'))
        );
        CREATE TABLE IF NOT EXISTS caps_ledger (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            txn_type    TEXT NOT NULL DEFAULT 'income',
            amount      INTEGER NOT NULL DEFAULT 0,
            category    TEXT DEFAULT '',
            description TEXT DEFAULT '',
            txn_date    TEXT DEFAULT (date('now')),
            notes       TEXT DEFAULT '',
            created_at  TEXT DEFAULT (date('now'))
        );
        CREATE TABLE IF NOT EXISTS play_sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time TEXT NOT NULL,
            end_time   TEXT DEFAULT '',
            duration_s INTEGER DEFAULT 0,
            notes      TEXT DEFAULT '',
            created_at TEXT DEFAULT (date('now'))
        );
    """)
    conn.commit()
    # Legendary mods / bobblehead tables
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS legendary_craftable (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT NOT NULL,
            star_level       INTEGER DEFAULT 1,
            have_materials   INTEGER DEFAULT 0,
            need_materials   INTEGER DEFAULT 0,
            requires_to_craft TEXT DEFAULT '',
            updated_at       TEXT DEFAULT (date('now'))
        );
        CREATE TABLE IF NOT EXISTS legendary_mods_inventory (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            star_level INTEGER DEFAULT 1,
            qty        INTEGER DEFAULT 0,
            notes      TEXT DEFAULT '',
            updated_at TEXT DEFAULT (date('now'))
        );
        CREATE TABLE IF NOT EXISTS bobbleheads (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL UNIQUE,
            qty        INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT (date('now'))
        );
    """)
    conn.commit()
    # Safe column migrations for existing databases
    for stmt in [
        "ALTER TABLE challenges ADD COLUMN score_reward INTEGER DEFAULT 0",
        "ALTER TABLE challenges ADD COLUMN atoms_reward INTEGER DEFAULT 0",
        "ALTER TABLE mods ADD COLUMN mod_type TEXT DEFAULT 'Normal'",
        "ALTER TABLE inventory ADD COLUMN source_table TEXT DEFAULT ''",
        "ALTER TABLE inventory ADD COLUMN source_id INTEGER DEFAULT 0",
        "ALTER TABLE challenges ADD COLUMN times_completed INTEGER DEFAULT 0",
        "ALTER TABLE challenges ADD COLUMN missed_count INTEGER DEFAULT 0",
        "ALTER TABLE challenges ADD COLUMN repeatable INTEGER DEFAULT 0",
        "ALTER TABLE inventory ADD COLUMN fo1st_stored INTEGER DEFAULT 0",
        "ALTER TABLE challenges ADD COLUMN active INTEGER DEFAULT 1",
        "ALTER TABLE weapons ADD COLUMN star4 TEXT DEFAULT ''",
        "ALTER TABLE armor ADD COLUMN star4 TEXT DEFAULT ''",
        "ALTER TABLE power_armor ADD COLUMN star4 TEXT DEFAULT ''",
        "ALTER TABLE vendor_stock ADD COLUMN character_id INTEGER DEFAULT 1",
        "ALTER TABLE weapons ADD COLUMN character_id INTEGER DEFAULT 1",
        "ALTER TABLE armor ADD COLUMN character_id INTEGER DEFAULT 1",
        "ALTER TABLE power_armor ADD COLUMN character_id INTEGER DEFAULT 1",
        "ALTER TABLE mods ADD COLUMN character_id INTEGER DEFAULT 1",
        "ALTER TABLE inventory ADD COLUMN character_id INTEGER DEFAULT 1",
        "ALTER TABLE caps_sessions ADD COLUMN character_id INTEGER DEFAULT 1",
        "ALTER TABLE caps_ledger ADD COLUMN character_id INTEGER DEFAULT 1",
        "ALTER TABLE builds ADD COLUMN character_id INTEGER DEFAULT 1",
        "ALTER TABLE mutations ADD COLUMN character_id INTEGER DEFAULT 1",
        "ALTER TABLE challenges ADD COLUMN character_id INTEGER DEFAULT 1",
        "ALTER TABLE daily_tasks ADD COLUMN character_id INTEGER DEFAULT 1",
        "ALTER TABLE ammo ADD COLUMN character_id INTEGER DEFAULT 1",
        "ALTER TABLE plans ADD COLUMN character_id INTEGER DEFAULT 1",
        "ALTER TABLE legend_runs ADD COLUMN character_id INTEGER DEFAULT 1",
        "ALTER TABLE perk_cards ADD COLUMN character_id INTEGER DEFAULT 1",
        "ALTER TABLE season_score_log ADD COLUMN character_id INTEGER DEFAULT 1",
        "ALTER TABLE fish_log ADD COLUMN character_id INTEGER DEFAULT 1",
        "ALTER TABLE session_journal ADD COLUMN character_id INTEGER DEFAULT 1",
        "ALTER TABLE builds ADD COLUMN perk_cards_json TEXT DEFAULT ''",
        "ALTER TABLE builds ADD COLUMN legendary_perks_json TEXT DEFAULT ''",
        "ALTER TABLE armor ADD COLUMN build_id INTEGER DEFAULT 0",
        "ALTER TABLE weapons ADD COLUMN build_id INTEGER DEFAULT 0",
        """CREATE TABLE IF NOT EXISTS caps_sessions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            session_date TEXT DEFAULT (date('now')),
            start_caps   INTEGER NOT NULL DEFAULT 0,
            end_caps     INTEGER NOT NULL DEFAULT 0,
            note         TEXT DEFAULT '',
            created_at   TEXT DEFAULT (date('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS price_alerts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name    TEXT NOT NULL,
            target_price INTEGER NOT NULL DEFAULT 0,
            active       INTEGER DEFAULT 1,
            created_at   TEXT DEFAULT (date('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS ammo (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ammo_type     TEXT NOT NULL,
            qty           INTEGER DEFAULT 0,
            low_threshold INTEGER DEFAULT 0,
            notes         TEXT DEFAULT '',
            updated_at    TEXT DEFAULT (date('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS daily_tasks (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            freq       TEXT DEFAULT 'daily',
            sort_order INTEGER DEFAULT 0,
            active     INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (date('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS daily_completions (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id        INTEGER NOT NULL,
            completed_date TEXT NOT NULL,
            completed_at   TEXT DEFAULT (datetime('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS legend_runs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            boss_name  TEXT NOT NULL,
            last_run   TEXT DEFAULT '',
            run_count  INTEGER DEFAULT 0,
            notes      TEXT DEFAULT '',
            updated_at TEXT DEFAULT (date('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS server_hops (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            hop_date   TEXT DEFAULT (date('now')),
            notes      TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS atom_shop (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            category   TEXT DEFAULT '',
            cost_atoms INTEGER DEFAULT 0,
            status     TEXT DEFAULT 'Want',
            available  INTEGER DEFAULT 0,
            notes      TEXT DEFAULT '',
            created_at TEXT DEFAULT (date('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS trade_partners (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ign         TEXT NOT NULL,
            platform    TEXT DEFAULT 'PC',
            rating      TEXT DEFAULT 'Good',
            trade_count INTEGER DEFAULT 0,
            notes       TEXT DEFAULT '',
            last_trade  TEXT DEFAULT '',
            created_at  TEXT DEFAULT (date('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS trade_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            partner_id INTEGER NOT NULL,
            trade_date TEXT DEFAULT (date('now')),
            gave       TEXT DEFAULT '',
            received   TEXT DEFAULT '',
            caps_delta INTEGER DEFAULT 0,
            notes      TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS vendor_route_stops (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            stop_name    TEXT NOT NULL,
            location     TEXT DEFAULT '',
            notes        TEXT DEFAULT '',
            last_checked TEXT DEFAULT '',
            sort_order   INTEGER DEFAULT 0
        )""",
        """CREATE TABLE IF NOT EXISTS fish_species (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            rarity      TEXT DEFAULT 'Generic',
            biome       TEXT DEFAULT '',
            notes       TEXT DEFAULT '',
            caught      INTEGER DEFAULT 0,
            first_caught TEXT DEFAULT ''
        )""",
        """CREATE TABLE IF NOT EXISTS fish_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            fish_name  TEXT NOT NULL,
            rarity     TEXT DEFAULT '',
            biome      TEXT DEFAULT '',
            location   TEXT DEFAULT '',
            bait_used  TEXT DEFAULT '',
            weather    TEXT DEFAULT '',
            notes      TEXT DEFAULT '',
            caught_at  TEXT DEFAULT (date('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS world_finds (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            item_type   TEXT NOT NULL DEFAULT 'Bobblehead',
            item_name   TEXT NOT NULL,
            location    TEXT DEFAULT '',
            region      TEXT DEFAULT '',
            server_type TEXT DEFAULT 'Public',
            notes       TEXT DEFAULT '',
            found_date  TEXT DEFAULT (date('now')),
            created_at  TEXT DEFAULT (date('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS world_find_screenshots (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            find_id    INTEGER NOT NULL,
            filename   TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS spawn_notes (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            enemy_type    TEXT NOT NULL,
            location_name TEXT DEFAULT '',
            region        TEXT DEFAULT '',
            landmark      TEXT DEFAULT '',
            reliability   TEXT DEFAULT 'Usually',
            enemy_count   TEXT DEFAULT '',
            has_legendary TEXT DEFAULT 'Sometimes',
            server_type   TEXT DEFAULT 'Public',
            notes         TEXT DEFAULT '',
            date_added    TEXT DEFAULT (date('now')),
            created_at    TEXT DEFAULT (datetime('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS spawn_note_screenshots (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            spawn_note_id INTEGER NOT NULL,
            filename      TEXT NOT NULL,
            created_at    TEXT DEFAULT (datetime('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS session_journal (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            date         TEXT DEFAULT (date('now')),
            server_vibe  TEXT DEFAULT 'Good',
            server_type  TEXT DEFAULT 'Public',
            nuke_status  TEXT DEFAULT 'None',
            caps_made    INTEGER DEFAULT 0,
            legendaries  INTEGER DEFAULT 0,
            events_done  INTEGER DEFAULT 0,
            highlight    TEXT DEFAULT '',
            notes        TEXT DEFAULT '',
            created_at   TEXT DEFAULT (datetime('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS session_journal_screenshots (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            journal_id INTEGER NOT NULL,
            filename   TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )""",
    ]:
        try:
            conn.execute(stmt)
            conn.commit()
        except Exception:
            pass  # Column already exists
    # Remove Mothman Lair (limited-time event) and replace with Ultracite Titan
    for stmt in [
        "DELETE FROM daily_tasks WHERE name = 'Mothman Lair'",
        "DELETE FROM legend_runs  WHERE boss_name = 'Mothman Lair'",
        "INSERT INTO daily_tasks (name, freq, sort_order) SELECT 'Ultracite Titan','weekly',6 WHERE NOT EXISTS (SELECT 1 FROM daily_tasks WHERE name='Ultracite Titan')",
        "INSERT INTO legend_runs (boss_name) SELECT 'Ultracite Titan' WHERE NOT EXISTS (SELECT 1 FROM legend_runs WHERE boss_name='Ultracite Titan')",
    ]:
        try:
            conn.execute(stmt)
            conn.commit()
        except Exception:
            pass

    # Seed default daily tasks (only if table is empty)
    if conn.execute("SELECT COUNT(*) FROM daily_tasks").fetchone()[0] == 0:
        defaults = [
            ('Daily Challenges',    'daily',  1),
            ('Daily Ops',           'daily',  2),
            ('SCORE Daily Event',   'daily',  3),
            ('Claim Treasury Notes','daily',  4),
            ('Check Vendor Sales',  'daily',  5),
            ('Weekly Challenges',   'weekly', 1),
            ('Launch Nuke',         'weekly', 2),
            ('Earle Williams',      'weekly', 3),
            ('Colossal Problem',    'weekly', 4),
            ('Scorchbeast Queen',   'weekly', 5),
            ('Ultracite Titan',     'weekly', 6),
        ]
        conn.executemany(
            "INSERT INTO daily_tasks (name, freq, sort_order) VALUES (?,?,?)", defaults
        )
        conn.commit()

    # Seed default legend run bosses (only if table is empty)
    if conn.execute("SELECT COUNT(*) FROM legend_runs").fetchone()[0] == 0:
        bosses = [
            'Scorchbeast Queen',
            'Earle Williams',
            'Wendigo Colossus',
            'Ultracite Titan',
            'Daily Ops',
        ]
        conn.executemany("INSERT INTO legend_runs (boss_name) VALUES (?)", [(b,) for b in bosses])
        conn.commit()

    # Seed fish species (only if table is empty)
    if conn.execute("SELECT COUNT(*) FROM fish_species").fetchone()[0] == 0:
        fish = [
            # Generic — catchable everywhere
            ('Brook Silverside',         'Generic',       'All Regions'),
            ('Chain Pickerel',           'Generic',       'All Regions'),
            ('Redbelly',                 'Generic',       'All Regions'),
            ('Ridge Trout',              'Generic',       'All Regions'),
            ('Smoky Salmon',             'Generic',       'All Regions'),
            ('Sunscream',                'Generic',       'All Regions'),
            ('Walleye',                  'Generic',       'All Regions'),
            ('Yellow Bullhead',          'Generic',       'All Regions'),
            # Common Sawgills — region-specific
            ('Alpine Sawgill',           'Common',        'Savage Divide'),
            ('Bog Sawgill',              'Common',        'Cranberry Bog'),
            ('Muddy Sawgill',            'Common',        'The Mire'),
            ('Noxious Sawgill',          'Common',        'Toxic Valley'),
            ('Rusted Sawgill',           'Common',        'Burning Springs'),
            ('Sooty Sawgill',            'Common',        'Ash Heap'),
            ('Static Sawgill',           'Common',        'Skyline Valley'),
            ('Timber Sawgill',           'Common',        'The Forest'),
            # Uncommon — region-specific, improved/superb bait
            ('Ashen Ambusher',           'Uncommon',      'Ash Heap'),
            ('Deathjaw',                 'Uncommon',      'Ash Heap'),
            ('Blisterfish',              'Uncommon',      'Cranberry Bog'),
            ('Bog Lurker',               'Uncommon',      'Cranberry Bog'),
            ('Bloodwhisker',             'Uncommon',      'The Forest'),
            ('Kanawha Piranha',          'Uncommon',      'The Forest'),
            ('Bluefin Zapper',           'Uncommon',      'Skyline Valley'),
            ('Brahfin',                  'Uncommon',      'Burning Springs'),
            ('Gulpy',                    'Uncommon',      'The Mire'),
            ('Spikesnapper',             'Uncommon',      'The Mire'),
            ('Potbelly Kelt',            'Uncommon',      'Toxic Valley'),
            ('Purple Radpole',           'Uncommon',      'Toxic Valley'),
            # Glowing — nuke zone / rad storm required
            ('Glowing Ambusher',         'Glowing',       'Ash Heap'),
            ('Glowing Bog Lurker',       'Glowing',       'Cranberry Bog'),
            ('Glowing Brahfin',          'Glowing',       'Burning Springs'),
            ('Glowing Gulpy',            'Glowing',       'The Mire'),
            ('Glowing Kanawha Piranha',  'Glowing',       'The Forest'),
            ('Glowing Potbelly Kelt',    'Glowing',       'Toxic Valley'),
            ('Glowing Spinefish',        'Glowing',       'Any Nuke Zone'),
            ('Glowing Stormswimmer',     'Glowing',       'Any Nuke Zone'),
            # Local Legends — specific locations only
            ('Hocking Hill Hellion',     'Local Legend',  'Ash Cave / Burning Springs'),
            ('Organ Grinder',            'Local Legend',  'Organ Cave / The Forest'),
            ('Ryl-Tkannoth Maw-Begotten','Local Legend',  'Big Maw / The Mire'),
            ('Wavy Willard',             'Local Legend',  "Wavy Willard's / Toxic Valley"),
            # Axolotls — rainy weather, one type per month
            ('Banded Axolotl',           'Axolotl',       'Varies (Monthly)'),
            ('Charcoal Axolotl',         'Axolotl',       'Varies (Monthly)'),
            ('Clay Axolotl',             'Axolotl',       'Varies (Monthly)'),
            ('Dotted Axolotl',           'Axolotl',       'Varies (Monthly)'),
            ('Pink Axolotl',             'Axolotl',       'Varies (Monthly)'),
            ('Purple Axolotl',           'Axolotl',       'Varies (Monthly)'),
            ('Scaled Axolotl',           'Axolotl',       'Varies (Monthly)'),
            ('Shadow Axolotl',           'Axolotl',       'Varies (Monthly)'),
            ('Speckled Axolotl',         'Axolotl',       'Varies (Monthly)'),
            ('Spotted Axolotl',          'Axolotl',       'Varies (Monthly)'),
            ('Stone Axolotl',            'Axolotl',       'Varies (Monthly)'),
            ('Striped Axolotl',          'Axolotl',       'Varies (Monthly)'),
        ]
        conn.executemany(
            "INSERT INTO fish_species (name, rarity, biome) VALUES (?,?,?)", fish
        )
        conn.commit()

    # Seed default character (PC Main) if no characters exist yet
    if conn.execute("SELECT COUNT(*) FROM characters").fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO characters (id, name, platform, char_type, level) VALUES (1, 'PC Main', 'PC', 'Playable', 1)"
        )
        conn.commit()

    conn.close()

def query(sql, params=()):
    conn = get_db()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows

def insert(sql, params=()):
    conn = get_db()
    cur = conn.execute(sql, params)
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid

def execute(sql, params=()):
    conn = get_db()
    conn.execute(sql, params)
    conn.commit()
    conn.close()

def get_one(sql, params=()):
    conn = get_db()
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return row

def dashboard_stats(character_id=1):
    conn = get_db()
    cid = int(character_id)
    # Single query for all counts + action alerts (character-scoped)
    row = conn.execute("""
        SELECT
            (SELECT COUNT(*) FROM perk_cards  WHERE character_id=:c)                          AS perk_cards,
            (SELECT COUNT(*) FROM builds      WHERE character_id=:c)                          AS builds,
            (SELECT COUNT(*) FROM weapons     WHERE character_id=:c)                          AS weapons,
            (SELECT COUNT(*) FROM armor       WHERE character_id=:c)                          AS armor,
            (SELECT COUNT(*) FROM mods        WHERE character_id=:c)                          AS mods,
            (SELECT COUNT(*) FROM vendor_stock WHERE character_id=:c)                         AS vendor_items,
            (SELECT COUNT(*) FROM price_research)                                             AS price_records,
            (SELECT COUNT(*) FROM plans       WHERE character_id=:c)                          AS plans,
            (SELECT COUNT(*) FROM inventory   WHERE character_id=:c)                          AS inventory,
            (SELECT COUNT(*) FROM perk_cards  WHERE character_id=:c AND can_scrap='Yes')      AS scrappable,
            (SELECT COUNT(*) FROM weapons     WHERE character_id=:c AND status='Sell')        AS sell_weapons,
            (SELECT COUNT(*) FROM armor       WHERE character_id=:c AND status='Sell')        AS sell_armor,
            (SELECT COUNT(*) FROM mods        WHERE character_id=:c AND status='Sell')        AS sell_mods,
            (SELECT COUNT(*) FROM plans       WHERE character_id=:c AND qty_unlearned > 0)    AS dupe_plans,
            (SELECT COALESCE(SUM(my_price*qty),0) FROM vendor_stock WHERE character_id=:c)   AS vendor_total,
            (SELECT COUNT(*) FROM wishlist WHERE found=0)                                     AS wishlist_active,
            (SELECT COUNT(*) FROM (SELECT name FROM weapons WHERE character_id=:c GROUP BY name HAVING COUNT(*)>1)) AS dupe_weapons
    """, {'c': cid}).fetchone()

    s = {
        'Perk Cards':    row['perk_cards'],
        'Builds':        row['builds'],
        'Weapons':       row['weapons'],
        'Armor':         row['armor'],
        'Mods':          row['mods'],
        'Vendor Items':  row['vendor_items'],
        'Price Records': row['price_records'],
        'Plans':         row['plans'],
        'Inventory':     row['inventory'],
        'scrappable':    row['scrappable'],
        'sell_weapons':  row['sell_weapons'],
        'sell_armor':    row['sell_armor'],
        'sell_mods':     row['sell_mods'],
        'dupe_plans':     row['dupe_plans'],
        'vendor_total':   row['vendor_total'],
        'wishlist_active': row['wishlist_active'],
        'dupe_weapons':   row['dupe_weapons'],
    }

    s['price_avgs'] = conn.execute("""
        SELECT item_name, COUNT(*) as cnt,
               MIN(price_seen) as min_p, MAX(price_seen) as max_p,
               ROUND(AVG(price_seen)) as avg_p
        FROM price_research GROUP BY item_name ORDER BY cnt DESC LIMIT 10
    """).fetchall()

    s['recent_prices'] = conn.execute("""
        SELECT item_name, price_seen, source, date_seen
        FROM price_research ORDER BY created_at DESC LIMIT 6
    """).fetchall()

    wt = conn.execute("""
        SELECT
            COALESCE((SELECT SUM(weight) FROM weapons     WHERE character_id=:c), 0)           AS weapon_wt,
            COALESCE((SELECT SUM(weight) FROM armor       WHERE character_id=:c), 0)           AS armor_wt,
            COALESCE((SELECT SUM(weight) FROM power_armor WHERE character_id=:c), 0)           AS pa_wt,
            COALESCE((SELECT SUM(qty * weight_each) FROM inventory
                       WHERE character_id=:c
                         AND source_table NOT IN ('weapons','armor','power_armor')
                         AND fo1st_stored = 0), 0) AS other_wt
    """, {'c': cid}).fetchone()
    s['stash_weight'] = {
        'weapons': round(float(wt['weapon_wt']), 1),
        'armor':   round(float(wt['armor_wt']),   1),
        'pa':      round(float(wt['pa_wt']),       1),
        'other':   round(float(wt['other_wt']),   1),
        'total':   round(float(wt['weapon_wt']) + float(wt['armor_wt']) + float(wt['pa_wt']) + float(wt['other_wt']), 1),
    }
    _cap_row = conn.execute("SELECT value FROM settings WHERE key='stash_cap'").fetchone()
    s['stash_cap'] = int((_cap_row[0] if _cap_row else None) or 1200)

    _cur_caps = conn.execute(
        "SELECT end_caps FROM caps_sessions WHERE character_id=? ORDER BY session_date DESC, id DESC LIMIT 1",
        (cid,)
    ).fetchone()
    s['current_caps'] = int(_cur_caps['end_caps']) if _cur_caps else 0

    _goal_name   = conn.execute("SELECT value FROM settings WHERE key='caps_goal_name'").fetchone()
    _goal_amount = conn.execute("SELECT value FROM settings WHERE key='caps_goal_amount'").fetchone()
    _goal_amt    = int(_goal_amount['value']) if _goal_amount and _goal_amount['value'] else 0
    _goal_pct    = min(100, round(s['current_caps'] / _goal_amt * 100)) if _goal_amt else 0
    s['caps_goal'] = {
        'name':   _goal_name['value'] if _goal_name else '',
        'amount': _goal_amt,
        'pct':    _goal_pct,
    }

    s['price_hits'] = conn.execute("""
        SELECT pa.item_name, pa.target_price, MIN(pr.price_seen) AS best_seen
        FROM price_alerts pa
        JOIN price_research pr ON pr.item_name = pa.item_name
        WHERE pa.active=1 AND pr.price_seen <= pa.target_price
          AND pr.date_seen >= date('now', '-7 days')
        GROUP BY pa.item_name
        ORDER BY pa.item_name
    """).fetchall()

    # Ammo low-stock alerts
    s['low_ammo'] = conn.execute(
        "SELECT ammo_type, qty, low_threshold FROM ammo "
        "WHERE character_id=? AND low_threshold > 0 AND qty < low_threshold ORDER BY ammo_type",
        (cid,)
    ).fetchall()

    # Daily tasks pending today
    today_str = datetime.now().strftime('%Y-%m-%d')
    this_monday = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime('%Y-%m-%d')
    s['daily_pending'] = conn.execute("""
        SELECT COUNT(*) FROM daily_tasks dt
        WHERE dt.active=1 AND dt.freq='daily'
          AND dt.id NOT IN (
              SELECT task_id FROM daily_completions WHERE completed_date=?
          )
    """, (today_str,)).fetchone()[0]
    s['weekly_pending'] = conn.execute("""
        SELECT COUNT(*) FROM daily_tasks dt
        WHERE dt.active=1 AND dt.freq='weekly'
          AND dt.id NOT IN (
              SELECT task_id FROM daily_completions WHERE completed_date >= ?
          )
    """, (this_monday,)).fetchone()[0]

    # Session summary — what happened today
    s['today_caps_delta'] = conn.execute(
        "SELECT COALESCE(SUM(end_caps - start_caps), 0) FROM caps_sessions WHERE character_id=? AND session_date=?",
        (cid, today_str)
    ).fetchone()[0]
    s['today_weapons'] = conn.execute(
        "SELECT COUNT(*) FROM weapons WHERE character_id=? AND created_at=?", (cid, today_str)
    ).fetchone()[0]
    s['today_prices'] = conn.execute(
        "SELECT COUNT(*) FROM price_research WHERE created_at = ?", (today_str,)
    ).fetchone()[0]
    s['today_challenges'] = conn.execute(
        "SELECT COUNT(*) FROM challenges WHERE character_id=? AND completed=1 AND date(completed_at)=?",
        (cid, today_str)
    ).fetchone()[0]
    conn.close()
    return s


def get_setting(key, default=''):
    row = get_one("SELECT value FROM settings WHERE key=?", (key,))
    return row['value'] if row else default

def set_setting(key, value):
    execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))


def ensure_nuke_silos():
    conn = get_db()
    for silo in ('Alpha', 'Bravo', 'Charlie'):
        exists = conn.execute("SELECT COUNT(*) FROM nuke_codes WHERE silo=?", (silo,)).fetchone()[0]
        if not exists:
            conn.execute("INSERT INTO nuke_codes (silo, code, week_of, notes) VALUES (?,?,?,?)",
                         (silo, '', '', ''))
    conn.commit()
    conn.close()

def search_all(q):
    like = f'%{q}%'
    results = []
    conn = get_db()
    searches = [
        ('perk_cards',    'Perk Card',    '/perk-cards', ['name', 'effect', 'notes']),
        ('builds',        'Build',        '/builds',     ['name', 'playstyle', 'key_cards']),
        ('weapons',       'Weapon',       '/weapons',    ['name', 'star1', 'star2', 'star3', 'notes']),
        ('armor',         'Armor',        '/armor',      ['name', 'star1', 'material', 'notes']),
        ('mods',          'Mod',          '/mods',       ['name', 'effect', 'applies_to']),
        ('vendor_stock',  'Vendor Item',  '/vendor',     ['name', 'description']),
        ('price_research','Price Record', '/prices',     ['item_name', 'description']),
        ('plans',         'Plan',         '/plans',      ['name', 'unlocks']),
        ('inventory',     'Inventory',    '/inventory',  ['name', 'sub_type', 'notes']),
    ]
    for table, label, url, cols in searches:
        where = ' OR '.join(f'{c} LIKE ?' for c in cols)
        rows = conn.execute(
            f'SELECT id, {cols[0]} as display FROM {table} WHERE {where}',
            [like] * len(cols)
        ).fetchall()
        for row in rows:
            results.append({'type': label, 'name': row['display'], 'url': url, 'id': row['id']})
    conn.close()
    return results

def auto_backup(keep=7):
    backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    if not os.path.isfile(DB_PATH):
        return
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    dest = os.path.join(backup_dir, f'fo76_backup_{timestamp}.db')
    shutil.copy2(DB_PATH, dest)
    # Keep only the most recent `keep` backups
    backups = sorted(glob.glob(os.path.join(backup_dir, 'fo76_backup_*.db')))
    for old in backups[:-keep]:
        os.remove(old)
