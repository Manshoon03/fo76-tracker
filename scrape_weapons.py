"""
Fallout 76 Weapon + Mod Database Scraper
=========================================
Scrapes all FO76 weapon pages from the Fallout Wiki and populates
wiki_weapons + wiki_weapon_mods tables in fo76.db.

  python scrape_weapons.py            # scrape everything (skips existing)
  python scrape_weapons.py --reset    # wipe and re-scrape from scratch
  python scrape_weapons.py "Salt and Pepper Shaker"   # single weapon test
"""

import re
import sys
import time
import sqlite3
import requests
from pathlib import Path
from bs4 import BeautifulSoup

DB_PATH  = Path(__file__).parent / "fo76.db"
API_BASE = "https://fallout.wiki/api.php"
HEADERS  = {"User-Agent": "FO76Tracker/1.0 (weapon/mod scraper, personal project)"}

# Subcategory → weapon type label (verified against fallout.wiki)
WEAPON_CATEGORIES = [
    ("Category:Fallout 76 heavy guns",          "Heavy"),
    ("Category:Fallout 76 explosive heavy guns", "Explosive Heavy"),
    ("Category:Fallout 76 Flamers",             "Flamer"),
    ("Category:Fallout 76 rifles",              "Rifle"),
    ("Category:Fallout 76 pistols",             "Pistol"),
    ("Category:Fallout 76 shotguns",            "Shotgun"),
    ("Category:Fallout 76 SMGs",                "SMG"),
    ("Category:Fallout 76 bows",                "Bow"),
    ("Category:Fallout 76 laser rifles",        "Energy Rifle"),
    ("Category:Fallout 76 laser pistols",       "Energy Pistol"),
    ("Category:Fallout 76 plasma rifles",       "Plasma Rifle"),
    ("Category:Fallout 76 plasma pistols",      "Plasma Pistol"),
    ("Category:Fallout 76 melee weapons",       "Melee"),
    ("Category:Fallout 76 thrown weapons",      "Thrown"),
    ("Category:Fallout 76 miscellaneous weapons","Misc"),
]


# ── DB setup ──────────────────────────────────────────────────────────────────

def init_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS wiki_weapons (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT UNIQUE NOT NULL,
            weapon_type TEXT DEFAULT '',
            damage_type TEXT DEFAULT 'Ballistic',
            damage      INTEGER DEFAULT 0,
            fire_rate   INTEGER DEFAULT 0,
            range       INTEGER DEFAULT 0,
            accuracy    INTEGER DEFAULT 0,
            weight      REAL    DEFAULT 0,
            ammo_type   TEXT DEFAULT '',
            wiki_url    TEXT DEFAULT '',
            scraped_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS wiki_weapon_mods (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            weapon_id   INTEGER NOT NULL,
            slot        TEXT DEFAULT '',
            mod_name    TEXT NOT NULL,
            description TEXT DEFAULT '',
            is_default  INTEGER DEFAULT 0,
            FOREIGN KEY(weapon_id) REFERENCES wiki_weapons(id)
        );
        CREATE INDEX IF NOT EXISTS idx_wmods_weapon ON wiki_weapon_mods(weapon_id);
    """)
    conn.commit()


# ── Wiki API helpers ──────────────────────────────────────────────────────────

def get_category_members(category):
    pages = []
    params = {
        "action":  "query",
        "list":    "categorymembers",
        "cmtitle": category,
        "cmtype":  "page",
        "cmlimit": "500",
        "format":  "json",
    }
    while True:
        r = requests.get(API_BASE, params=params, headers=HEADERS, timeout=15)
        data = r.json()
        for m in data.get("query", {}).get("categorymembers", []):
            pages.append(m["title"])
        cont = data.get("continue", {}).get("cmcontinue")
        if not cont:
            break
        params["cmcontinue"] = cont
        time.sleep(0.3)
    return pages


def fetch_page_html(title):
    params = {
        "action": "parse",
        "page":   title,
        "prop":   "text",
        "format": "json",
    }
    r = requests.get(API_BASE, params=params, headers=HEADERS, timeout=25)
    data = r.json()
    return data.get("parse", {}).get("text", {}).get("*", "")


# ── Parsers ───────────────────────────────────────────────────────────────────

def parse_infobox(soup):
    """Pull base stats out of the weapon infobox table."""
    stats = {}
    infobox = (
        soup.find("table", class_=lambda c: c and ("va-table" in c or "infobox" in c))
        or soup.find("aside")
    )
    if not infobox:
        return stats

    for row in infobox.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        label = cells[0].get_text(" ", strip=True).lower()
        value = cells[-1].get_text(" ", strip=True)
        if not label or not value:
            continue

        if "damage" in label and "type" not in label and "resist" not in label:
            m = re.search(r"\d+", value)
            if m:
                stats["damage"] = int(m.group())
        elif re.search(r"fire.?rate", label):
            m = re.search(r"\d+", value)
            if m:
                stats["fire_rate"] = int(m.group())
        elif label.strip() == "range":
            m = re.search(r"\d+", value)
            if m:
                stats["range"] = int(m.group())
        elif label.strip() == "accuracy":
            m = re.search(r"\d+", value)
            if m:
                stats["accuracy"] = int(m.group())
        elif label.strip() == "weight":
            m = re.search(r"[\d.]+", value)
            if m:
                stats["weight"] = float(m.group())
        elif "ammo" in label:
            stats["ammo_type"] = value.strip()
        elif "damage type" in label:
            stats["damage_type"] = value.strip()

    return stats


def parse_mods(soup):
    """
    Extract weapon mods.  Handles two wiki layouts:
      1. Modern tabber:  <div class="tabber"> → <article class="tabber__panel" title="Slot">
      2. Legacy table:   table immediately after a Modifications heading, slot in first column
    Returns list of {slot, mod_name, description, is_default}.
    """
    mods = []

    # ── Locate the Weapon Modifications heading ───────────────────────
    mod_heading = None
    for tag in soup.find_all(["h2", "h3", "h4"]):
        if "modification" in tag.get_text(strip=True).lower():
            mod_heading = tag
            break

    if not mod_heading:
        return mods

    # ── Try modern tabber layout first ───────────────────────────────
    tabber = mod_heading.find_next_sibling("div", class_="tabber")
    if tabber:
        panels = tabber.find_all("article", class_="tabber__panel")
        for panel in panels:
            slot = panel.get("title", "General").strip()
            table = panel.find("table")
            if not table:
                continue

            rows = table.find_all("tr")
            # Find the header row to locate "Mod" and "Effects" columns
            header_row = None
            mod_col = 0
            eff_col = 3  # default fallback
            for row in rows:
                ths = row.find_all("th")
                texts = [th.get_text(strip=True).lower() for th in ths]
                if "mod" in texts:
                    header_row = row
                    all_cells = row.find_all(["th", "td"])
                    for i, c in enumerate(all_cells):
                        t = c.get_text(strip=True).lower()
                        if t == "mod":
                            mod_col = i
                        if "effect" in t:
                            eff_col = i
                    break

            for row in rows:
                cells = row.find_all(["th", "td"])
                if not cells or row == header_row:
                    continue
                # Skip colspan header rows (e.g. the big "Barrel" title row)
                if cells[0].get("colspan"):
                    continue
                # Skip hidden/empty rows
                style = cells[0].get("style", "")
                if "display:none" in style.replace(" ", ""):
                    continue

                mod_name = cells[mod_col].get_text(strip=True) if mod_col < len(cells) else ""
                effects  = cells[eff_col].get_text(strip=True) if eff_col < len(cells) else ""

                # Skip table header-like values
                if not mod_name or mod_name.lower() in (
                    "mod", "modification", "name", "effect", "description"
                ):
                    continue

                # Build stat-change description from icon title attributes
                stat_notes = []
                for cell in cells[eff_col + 1:]:
                    val = cell.get_text(strip=True)
                    if val and val not in ("—", "-", ""):
                        # Get the stat name from icon title if present
                        icon = cell.find(attrs={"title": True})
                        stat_name = icon["title"] if icon else "stat"
                        stat_notes.append(f"{stat_name} {val}")

                description = effects
                if stat_notes:
                    description = (effects + "  " if effects else "") + " | ".join(stat_notes)

                mods.append({
                    "slot":        slot,
                    "mod_name":    mod_name,
                    "description": description.strip(),
                    "is_default":  1 if "standard" in mod_name.lower() or "default" in mod_name.lower() else 0,
                })
        return mods

    # ── Fallback: legacy table layout ────────────────────────────────
    heading_tag  = mod_heading.name
    current_slot = "General"

    for sibling in mod_heading.find_next_siblings():
        if sibling.name in ("h2", "h3", "h4") and sibling.name <= heading_tag:
            break
        if sibling.name != "table":
            continue

        rows = sibling.find_all("tr")
        header_cells = rows[0].find_all(["th", "td"]) if rows else []
        headers = [c.get_text(strip=True).lower() for c in header_cells]
        has_slot_col = bool(headers) and any(
            kw in headers[0] for kw in ("slot", "type", "modification", "mod")
        )

        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            if not cells:
                continue
            if cells[0].get("colspan"):
                continue

            if has_slot_col or cells[0].get("rowspan"):
                slot_text = cells[0].get_text(strip=True)
                if slot_text:
                    current_slot = slot_text
                remaining = cells[1:]
            else:
                remaining = cells

            mod_name    = remaining[0].get_text(strip=True) if remaining else ""
            description = remaining[1].get_text(strip=True) if len(remaining) > 1 else ""

            if not mod_name or mod_name.lower() in (
                "modification", "mod", "name", "effect", "description", "crafting"
            ):
                continue

            mods.append({
                "slot":        current_slot,
                "mod_name":    mod_name,
                "description": description,
                "is_default":  1 if "standard" in mod_name.lower() or "default" in mod_name.lower() else 0,
            })
        break

    return mods


# ── Core scrape function ──────────────────────────────────────────────────────

def scrape_weapon(title, weapon_type, conn, force=False):
    """
    Scrape one weapon page and upsert into the DB.
    Returns (saved: bool, mods_count: int).
    """
    existing = conn.execute(
        "SELECT id FROM wiki_weapons WHERE name=?", (title,)
    ).fetchone()

    if existing and not force:
        return False, 0

    html = fetch_page_html(title)
    if not html:
        return False, 0

    soup  = BeautifulSoup(html, "lxml")
    stats = parse_infobox(soup)
    mods  = parse_mods(soup)
    url   = f"https://fallout.wiki/wiki/{title.replace(' ', '_')}"

    if existing:
        conn.execute("DELETE FROM wiki_weapon_mods WHERE weapon_id=?", (existing[0],))
        conn.execute("""
            UPDATE wiki_weapons SET
                weapon_type=?, damage_type=?, damage=?, fire_rate=?, range=?,
                accuracy=?, weight=?, ammo_type=?, wiki_url=?, scraped_at=datetime('now')
            WHERE id=?
        """, (
            weapon_type,
            stats.get("damage_type", "Ballistic"),
            stats.get("damage",    0),
            stats.get("fire_rate", 0),
            stats.get("range",     0),
            stats.get("accuracy",  0),
            stats.get("weight",    0.0),
            stats.get("ammo_type", ""),
            url,
            existing[0],
        ))
        weapon_id = existing[0]
    else:
        cur = conn.execute("""
            INSERT INTO wiki_weapons
                (name, weapon_type, damage_type, damage, fire_rate, range,
                 accuracy, weight, ammo_type, wiki_url)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            title,
            weapon_type,
            stats.get("damage_type", "Ballistic"),
            stats.get("damage",    0),
            stats.get("fire_rate", 0),
            stats.get("range",     0),
            stats.get("accuracy",  0),
            stats.get("weight",    0.0),
            stats.get("ammo_type", ""),
            url,
        ))
        weapon_id = cur.lastrowid

    for m in mods:
        conn.execute(
            "INSERT INTO wiki_weapon_mods (weapon_id, slot, mod_name, description, is_default) "
            "VALUES (?,?,?,?,?)",
            (weapon_id, m["slot"], m["mod_name"], m["description"], m["is_default"])
        )

    conn.commit()
    return True, len(mods)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    args    = sys.argv[1:]
    reset   = "--reset" in args
    singles = [a for a in args if not a.startswith("--")]

    conn = sqlite3.connect(DB_PATH)
    init_tables(conn)

    if reset:
        conn.execute("DELETE FROM wiki_weapon_mods")
        conn.execute("DELETE FROM wiki_weapons")
        conn.commit()
        print("Tables cleared — full re-scrape starting.")

    # ── Single-weapon test mode ────────────────────────────────────────
    if singles:
        for name in singles:
            print(f"\nScraping: {name}")
            saved, n_mods = scrape_weapon(name, "Unknown", conn, force=True)
            if saved:
                print(f"  Saved. Mods found: {n_mods}")
                rows = conn.execute(
                    "SELECT slot, mod_name, description FROM wiki_weapon_mods "
                    "WHERE weapon_id=(SELECT id FROM wiki_weapons WHERE name=?) "
                    "ORDER BY slot, id", (name,)
                ).fetchall()
                cur_slot = None
                for slot, mod, desc in rows:
                    if slot != cur_slot:
                        print(f"\n  [{slot}]")
                        cur_slot = slot
                    print(f"    {mod:35s}  {desc[:80]}")
            else:
                print("  Not saved (page not found or already exists — use --reset to force)")
        conn.close()
        return

    # ── Full scrape by category ────────────────────────────────────────
    total_saved  = 0
    total_skip   = 0
    total_failed = 0

    for category, wtype in WEAPON_CATEGORIES:
        print(f"\n{'='*55}")
        print(f"  {wtype}  ({category})")
        print(f"{'='*55}")

        pages = get_category_members(category)
        print(f"  {len(pages)} pages in category.\n")

        for title in pages:
            try:
                saved, n_mods = scrape_weapon(title, wtype, conn)
                if saved:
                    total_saved += 1
                    print(f"  OK   {title}  ({n_mods} mods)")
                else:
                    total_skip += 1
            except Exception as e:
                print(f"  FAIL {title} - {e}")
                total_failed += 1
            time.sleep(0.4)

    conn.close()

    print(f"\n{'='*55}")
    print(f"  Done.")
    print(f"  Saved : {total_saved}")
    print(f"  Skipped (already in DB): {total_skip}")
    print(f"  Failed: {total_failed}")
    print(f"  DB: {DB_PATH}")
    print(f"{'='*55}")


if __name__ == "__main__":
    main()
