"""
Fallout 76 Perk Card Data Scraper
===================================
Scrapes full perk card data (SPECIAL, ranks, effects per rank) from the
Fallout Wiki and stores in wiki_perks + wiki_perk_ranks tables in fo76.db.

  python scrape_perk_data.py            # scrape all (skip existing)
  python scrape_perk_data.py --reset    # wipe and re-scrape
  python scrape_perk_data.py "Slugger"  # single card test
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
HEADERS  = {"User-Agent": "FO76Tracker/1.0 (perk data scraper, personal project)"}

SPECIAL_CATEGORIES = [
    ("Category:Fallout 76 Strength perks",     "S"),
    ("Category:Fallout 76 Perception perks",   "P"),
    ("Category:Fallout 76 Endurance perks",    "E"),
    ("Category:Fallout 76 Charisma perks",     "C"),
    ("Category:Fallout 76 Intelligence perks", "I"),
    ("Category:Fallout 76 Agility perks",      "A"),
    ("Category:Fallout 76 Luck perks",         "L"),
]

LEGENDARY_PERK_CATEGORY = "Category:Fallout 76 legendary perks"


def init_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS wiki_perks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT UNIQUE NOT NULL,
            special     TEXT DEFAULT '',
            is_legendary INTEGER DEFAULT 0,
            max_rank    INTEGER DEFAULT 1,
            description TEXT DEFAULT '',
            wiki_url    TEXT DEFAULT '',
            scraped_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS wiki_perk_ranks (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            perk_id   INTEGER NOT NULL,
            rank      INTEGER NOT NULL,
            effect    TEXT DEFAULT '',
            cost      INTEGER DEFAULT 1,
            FOREIGN KEY(perk_id) REFERENCES wiki_perks(id)
        );
        CREATE INDEX IF NOT EXISTS idx_prank_perk ON wiki_perk_ranks(perk_id);
    """)
    conn.commit()


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
    r = requests.get(API_BASE, params=params, headers=HEADERS, timeout=20)
    data = r.json()
    return data.get("parse", {}).get("text", {}).get("*", "")


def parse_perk_page(title, special, is_legendary):
    html = fetch_page_html(title)
    if not html:
        return None, []

    soup = BeautifulSoup(html, "lxml")

    # Find the infobox / rank table
    ranks = []
    max_rank = 1
    description = ""

    # Try to find a rank table — wiki perk pages have a table with Rank | Cost | Effect columns
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if not any("rank" in h for h in headers):
            continue

        # Determine column indices
        rank_col = next((i for i, h in enumerate(headers) if h == "rank"), 0)
        effect_col = next((i for i, h in enumerate(headers) if "effect" in h or "description" in h), -1)
        cost_col = next((i for i, h in enumerate(headers) if "cost" in h or "point" in h), -1)

        if effect_col == -1:
            continue

        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["th", "td"])
            if not cells or len(cells) < 2:
                continue
            try:
                rank_val = int(cells[rank_col].get_text(strip=True)) if rank_col < len(cells) else len(ranks) + 1
            except ValueError:
                continue

            effect = cells[effect_col].get_text(strip=True) if effect_col < len(cells) else ""
            try:
                cost = int(cells[cost_col].get_text(strip=True)) if cost_col != -1 and cost_col < len(cells) else rank_val
            except ValueError:
                cost = rank_val

            if effect:
                ranks.append({"rank": rank_val, "effect": effect, "cost": cost})
                max_rank = max(max_rank, rank_val)

        if ranks:
            break  # found a valid rank table

    # Fallback: look for rank info in the portable infobox
    if not ranks:
        for aside in soup.find_all("aside"):
            items = aside.find_all("div", class_=lambda c: c and "pi-item" in c)
            for item in items:
                label = item.find(class_=lambda c: c and "pi-data-label" in c)
                value = item.find(class_=lambda c: c and "pi-data-value" in c)
                if label and value:
                    lbl = label.get_text(strip=True).lower()
                    val = value.get_text(strip=True)
                    if "rank" in lbl or "effect" in lbl:
                        ranks.append({"rank": 1, "effect": val, "cost": 1})
                        max_rank = 1

    # Get description from first paragraph after infobox
    for p in soup.find_all("p"):
        txt = p.get_text(strip=True)
        if txt and len(txt) > 20:
            description = txt[:300]
            break

    perk_info = {
        "name":         title,
        "special":      special,
        "is_legendary": 1 if is_legendary else 0,
        "max_rank":     max_rank,
        "description":  description,
        "wiki_url":     f"https://fallout.wiki/wiki/{title.replace(' ', '_')}",
    }
    return perk_info, ranks


def scrape_perk(title, special, is_legendary, conn, force=False):
    existing = conn.execute("SELECT id FROM wiki_perks WHERE name=?", (title,)).fetchone()
    if existing and not force:
        return False, 0

    perk_info, ranks = parse_perk_page(title, special, is_legendary)
    if not perk_info:
        return False, 0

    if existing:
        conn.execute("DELETE FROM wiki_perk_ranks WHERE perk_id=?", (existing[0],))
        conn.execute("""UPDATE wiki_perks SET special=?, is_legendary=?, max_rank=?,
                        description=?, wiki_url=?, scraped_at=datetime('now') WHERE id=?""",
                     (special, 1 if is_legendary else 0, perk_info["max_rank"],
                      perk_info["description"], perk_info["wiki_url"], existing[0]))
        perk_id = existing[0]
    else:
        cur = conn.execute(
            "INSERT INTO wiki_perks (name, special, is_legendary, max_rank, description, wiki_url) VALUES (?,?,?,?,?,?)",
            (perk_info["name"], special, 1 if is_legendary else 0,
             perk_info["max_rank"], perk_info["description"], perk_info["wiki_url"])
        )
        perk_id = cur.lastrowid

    for r in ranks:
        conn.execute(
            "INSERT INTO wiki_perk_ranks (perk_id, rank, effect, cost) VALUES (?,?,?,?)",
            (perk_id, r["rank"], r["effect"], r["cost"])
        )

    conn.commit()
    return True, len(ranks)


def scrape_legendary_perks_overview(conn):
    """
    Parse the 'Legendary Perks' wiki page (not Fallout 76-specific URL).
    Table structure: 5-cell rows start a new perk (name has rowspan),
    3-cell rows continue with Rank | Description | FormID.
    Inserts into wiki_perks (is_legendary=1) and wiki_perk_ranks.
    Returns (saved_count, skipped_count).
    """
    html = fetch_page_html("Legendary Perks")
    if not html:
        print("  Could not fetch Legendary Perks page.")
        return 0, 0

    soup = BeautifulSoup(html, "lxml")
    saved = skipped = 0

    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if not any("rank" in h for h in headers):
            continue

        current_name = None
        perk_ranks   = []

        def flush():
            nonlocal current_name, perk_ranks, saved, skipped
            if not current_name or not perk_ranks:
                return
            existing = conn.execute("SELECT id FROM wiki_perks WHERE name=?", (current_name,)).fetchone()
            if existing:
                skipped += 1
                current_name = None
                perk_ranks   = []
                return
            max_rank = max(r["rank"] for r in perk_ranks)
            url = f"https://fallout.wiki/wiki/{current_name.replace(' ', '_')}"
            cur = conn.execute(
                "INSERT INTO wiki_perks (name, special, is_legendary, max_rank, description, wiki_url) VALUES (?,?,?,?,?,?)",
                (current_name, "Legendary", 1, max_rank, perk_ranks[0]["effect"][:300], url)
            )
            perk_id = cur.lastrowid
            for rk in perk_ranks:
                conn.execute(
                    "INSERT INTO wiki_perk_ranks (perk_id, rank, effect, cost) VALUES (?,?,?,?)",
                    (perk_id, rk["rank"], rk["effect"], rk["rank"])
                )
            conn.commit()
            print(f"  OK   {current_name}  ({len(perk_ranks)} ranks)")
            saved += 1
            current_name = None
            perk_ranks   = []

        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) == 5:
                # New perk: Name, Image, Rank, Description, FormID
                name_txt = cells[0].get_text(strip=True)
                if name_txt.lower() in ("name", "legendary perks", "legendary perks (ghoul-only)", ""):
                    continue
                flush()
                current_name = name_txt
                try:
                    rank = int(cells[2].get_text(strip=True))
                    effect = cells[3].get_text(strip=True)
                    perk_ranks.append({"rank": rank, "effect": effect})
                except ValueError:
                    pass
            elif len(cells) == 3 and current_name:
                # Continuation: Rank, Description, FormID
                try:
                    rank = int(cells[0].get_text(strip=True))
                    effect = cells[1].get_text(strip=True)
                    perk_ranks.append({"rank": rank, "effect": effect})
                except ValueError:
                    pass

        flush()  # flush last perk in table

    return saved, skipped


def main():
    args     = sys.argv[1:]
    reset    = "--reset" in args
    singles  = [a for a in args if not a.startswith("--")]

    conn = sqlite3.connect(DB_PATH)
    init_tables(conn)

    if reset:
        conn.execute("DELETE FROM wiki_perk_ranks")
        conn.execute("DELETE FROM wiki_perks")
        conn.commit()
        print("Tables cleared.")

    # ── Single perk test ────────────────────────────────────────────
    if singles:
        for name in singles:
            print(f"\nScraping: {name}")
            saved, n = scrape_perk(name, "?", False, conn, force=True)
            if saved:
                rows = conn.execute(
                    "SELECT rank, effect, cost FROM wiki_perk_ranks WHERE perk_id="
                    "(SELECT id FROM wiki_perks WHERE name=?) ORDER BY rank", (name,)
                ).fetchall()
                p = conn.execute("SELECT * FROM wiki_perks WHERE name=?", (name,)).fetchone()
                print(f"  SPECIAL: {p[2]}  Max Rank: {p[4]}  Ranks scraped: {len(rows)}")
                for rank, effect, cost in rows:
                    print(f"  Rank {rank} (cost {cost}): {effect[:100]}")
            else:
                print("  Not saved or not found.")
        conn.close()
        return

    # ── Full scrape ─────────────────────────────────────────────────
    total_saved = total_skip = total_failed = 0

    for category, special in SPECIAL_CATEGORIES:
        print(f"\n{'='*55}")
        print(f"  {special} — SPECIAL Perks  ({category})")
        print(f"{'='*55}")
        pages = get_category_members(category)
        print(f"  {len(pages)} pages.\n")
        for title in pages:
            try:
                saved, n = scrape_perk(title, special, False, conn)
                if saved:
                    total_saved += 1
                    print(f"  OK   {title}  ({n} ranks)")
                else:
                    total_skip += 1
            except Exception as e:
                print(f"  FAIL {title} — {e}")
                total_failed += 1
            time.sleep(0.4)

    # Legendary perks — parsed from the unified "Legendary Perks" wiki page
    # (no per-page category exists; all perks are in one table)
    print(f"\n{'='*55}")
    print(f"  Legendary Perks  (Legendary Perks overview page)")
    print(f"{'='*55}\n")
    leg_saved, leg_skip = scrape_legendary_perks_overview(conn)
    total_saved += leg_saved
    total_skip  += leg_skip

    conn.close()
    print(f"\n{'='*55}")
    print(f"  Done. Saved:{total_saved}  Skipped:{total_skip}  Failed:{total_failed}")
    print(f"{'='*55}")


if __name__ == "__main__":
    main()
