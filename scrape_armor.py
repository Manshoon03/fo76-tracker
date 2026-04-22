"""
Fallout 76 Armor + Power Armor Mod Scraper
==========================================
Scrapes armor sets and power armor from the Fallout Wiki into
wiki_armor and wiki_armor_mods tables in fo76.db.

  python scrape_armor.py            # scrape all (skip existing)
  python scrape_armor.py --reset    # wipe and re-scrape
  python scrape_armor.py "T-65"     # single armor test
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
HEADERS  = {"User-Agent": "FO76Tracker/1.0 (armor scraper, personal project)"}

ARMOR_CATEGORIES = [
    ("Category:Fallout 76 Armor",       "Armor"),
    ("Category:Fallout 76 power armor", "Power Armor"),
    ("Category:Fallout 76 Apparel",     "Clothing"),
]


def init_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS wiki_armor (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT UNIQUE NOT NULL,
            armor_type  TEXT DEFAULT 'Armor',
            dr          INTEGER DEFAULT 0,
            er          INTEGER DEFAULT 0,
            rr          INTEGER DEFAULT 0,
            weight      REAL DEFAULT 0,
            wiki_url    TEXT DEFAULT '',
            scraped_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS wiki_armor_mods (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            armor_id    INTEGER NOT NULL,
            slot        TEXT DEFAULT '',
            mod_name    TEXT NOT NULL,
            description TEXT DEFAULT '',
            is_default  INTEGER DEFAULT 0,
            FOREIGN KEY(armor_id) REFERENCES wiki_armor(id)
        );
        CREATE INDEX IF NOT EXISTS idx_amods_armor ON wiki_armor_mods(armor_id);
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
    params = {"action": "parse", "page": title, "prop": "text", "format": "json"}
    r = requests.get(API_BASE, params=params, headers=HEADERS, timeout=20)
    return r.json().get("parse", {}).get("text", {}).get("*", "")


def parse_infobox_stats(soup):
    """
    Armor wiki pages use a portable infobox (aside) rather than va-table.
    Stats like DR vary by tier; we just record what we can find.
    """
    stats = {}

    # Try portable infobox (aside) first
    for aside in soup.find_all("aside"):
        for item in aside.find_all("div", class_=lambda c: c and "pi-item" in c and "pi-data" in c):
            label_p = item.find("p")
            value_div = item.find("div", class_=lambda c: c and "pi-data-value" in c)
            if not label_p or not value_div:
                continue
            lbl = label_p.get_text(strip=True).lower()
            val = value_div.get_text(strip=True)
            if "damage resist" in lbl and "energy" not in lbl and "radiation" not in lbl:
                m = re.search(r"\d+", val)
                if m: stats["dr"] = int(m.group())
            elif "energy resist" in lbl:
                m = re.search(r"\d+", val)
                if m: stats["er"] = int(m.group())
            elif "radiation resist" in lbl:
                m = re.search(r"\d+", val)
                if m: stats["rr"] = int(m.group())
            elif lbl == "weight":
                m = re.search(r"[\d.]+", val)
                if m: stats["weight"] = float(m.group())

    # Fallback: va-table
    if not stats:
        infobox = soup.find("table", class_=lambda c: c and ("va-table" in c or "infobox" in c))
        if infobox:
            for row in infobox.find_all("tr"):
                cells = row.find_all(["th", "td"])
                if len(cells) < 2:
                    continue
                label = cells[0].get_text(" ", strip=True).lower()
                value = cells[-1].get_text(" ", strip=True)
                if re.search(r"damage resist", label) and "energy" not in label and "radiation" not in label:
                    m = re.search(r"\d+", value)
                    if m: stats["dr"] = int(m.group())
                elif "energy resist" in label:
                    m = re.search(r"\d+", value)
                    if m: stats["er"] = int(m.group())
                elif "radiation resist" in label:
                    m = re.search(r"\d+", value)
                    if m: stats["rr"] = int(m.group())
                elif label.strip() == "weight":
                    m = re.search(r"[\d.]+", value)
                    if m: stats["weight"] = float(m.group())

    return stats


def _parse_mod_table(table, slot, table_type):
    """
    Parse one mod table. Returns list of mod dicts.
    table_type: 'material' or 'misc' (detected from the section header row)
    """
    mods = []
    rows = table.find_all("tr")

    # Find column header row
    name_col, eff_col = 0, 1
    for i, row in enumerate(rows):
        cells = row.find_all(["th", "td"])
        texts = [c.get_text(strip=True).lower() for c in cells]
        if "name" in texts:
            for j, t in enumerate(texts):
                if t == "name":
                    name_col = j
                elif t in ("effect", "description", "resistance"):
                    eff_col = j
            break

    # Parse data rows
    for row in rows:
        cells = row.find_all(["th", "td"])
        if not cells:
            continue
        # Skip section header rows (colspan spanning full width)
        if cells[0].get("colspan") and len(cells) == 1:
            continue
        # Skip header rows
        first_text = cells[0].get_text(strip=True).lower()
        if first_text in ("name", "material", "miscellaneous", "paint", "appearance",
                          "image", "mod", "modification", ""):
            continue
        # Skip rows that are entirely empty/dashes
        if all(re.fullmatch(r"[\s\u2014\u2013\-]*", c.get_text(strip=True)) for c in cells):
            continue

        mod_name = cells[name_col].get_text(strip=True) if name_col < len(cells) else ""
        effect   = cells[eff_col].get_text(strip=True)  if eff_col  < len(cells) else ""
        # Skip pure-numeric rows (tier sub-rows like "40", "30", "20")
        if not mod_name or re.fullmatch(r"\d+", mod_name):
            continue

        mods.append({
            "slot":       f"{slot} ({table_type})" if table_type != "general" else slot,
            "mod_name":   mod_name,
            "description": effect,
            "is_default": 1 if "standard" in mod_name.lower() or "no misc" in mod_name.lower() else 0,
        })

    return mods


def parse_mods(soup):
    """
    Armor wiki pages: Modifications heading → h3 per slot (Arms/Chest/Legs/Helmet) →
    tables with section labels 'Material' and 'Miscellaneous'.
    Also handles weapon-style tabber panels as fallback.
    """
    mods = []

    # Find the top-level Modifications heading (h2 or h3)
    mod_heading = None
    for tag in soup.find_all(["h2", "h3", "h4"]):
        txt = tag.get_text(strip=True).lower()
        if txt.startswith("modification"):
            mod_heading = tag
            break
    if not mod_heading:
        return mods

    # Weapon-style: direct tabber after the heading
    tabber = mod_heading.find_next_sibling("div", class_="tabber")
    if tabber:
        for panel in tabber.find_all("article", class_="tabber__panel"):
            slot  = panel.get("title", "General").strip()
            table = panel.find("table")
            if not table:
                continue
            rows     = table.find_all("tr")
            mod_col, eff_col = 0, 3
            for row in rows:
                ths   = row.find_all("th")
                texts = [th.get_text(strip=True).lower() for th in ths]
                if "mod" in texts or "name" in texts:
                    all_c = row.find_all(["th", "td"])
                    for i, c in enumerate(all_c):
                        t = c.get_text(strip=True).lower()
                        if t in ("mod", "name"):   mod_col = i
                        if "effect" in t:          eff_col = i
                    break
            for row in rows:
                cells = row.find_all(["th", "td"])
                if not cells or cells[0].get("colspan"):
                    continue
                mod_name = cells[mod_col].get_text(strip=True) if mod_col < len(cells) else ""
                effects  = cells[eff_col].get_text(strip=True) if eff_col < len(cells) else ""
                if not mod_name or mod_name.lower() in ("mod", "modification", "name", "effect"):
                    continue
                mods.append({"slot": slot, "mod_name": mod_name, "description": effects,
                             "is_default": 1 if "standard" in mod_name.lower() else 0})
        return mods

    # Armor-style: h3 per slot, tables within each slot section
    SKIP_SLOTS = {"appearance", "variant", "legendary effects", "locations", "notes", "bugs", "gallery"}
    current_slot = None

    for sib in mod_heading.find_next_siblings():
        if sib.name == "h2":
            break
        if sib.name in ("h3", "h4"):
            slot_txt = sib.get_text(strip=True).lower().replace("[edit]", "").strip()
            if slot_txt in SKIP_SLOTS:
                current_slot = None
            else:
                current_slot = sib.get_text(strip=True).replace("[edit]", "").strip()
            continue

        if sib.name == "table" and current_slot:
            # Detect table type from its first section-header row (colspan row)
            table_type = "general"
            rows = sib.find_all("tr")
            for row in rows:
                cells = row.find_all(["th", "td"])
                if len(cells) == 1 and cells[0].get("colspan"):
                    lbl = cells[0].get_text(strip=True).lower()
                    if "material" in lbl:
                        table_type = "material"
                    elif "misc" in lbl:
                        table_type = "misc"
                    break
            mods.extend(_parse_mod_table(sib, current_slot, table_type))

    return mods


def scrape_armor(title, armor_type, conn, force=False):
    existing = conn.execute("SELECT id FROM wiki_armor WHERE name=?", (title,)).fetchone()
    if existing and not force:
        return False, 0

    html = fetch_page_html(title)
    if not html:
        return False, 0

    soup  = BeautifulSoup(html, "lxml")
    stats = parse_infobox_stats(soup)
    mods  = parse_mods(soup)
    url   = f"https://fallout.wiki/wiki/{title.replace(' ', '_')}"

    if existing:
        conn.execute("DELETE FROM wiki_armor_mods WHERE armor_id=?", (existing[0],))
        conn.execute("""UPDATE wiki_armor SET armor_type=?, dr=?, er=?, rr=?, weight=?,
                        wiki_url=?, scraped_at=datetime('now') WHERE id=?""",
                     (armor_type, stats.get("dr",0), stats.get("er",0),
                      stats.get("rr",0), stats.get("weight",0.0), url, existing[0]))
        armor_id = existing[0]
    else:
        cur = conn.execute(
            "INSERT INTO wiki_armor (name, armor_type, dr, er, rr, weight, wiki_url) VALUES (?,?,?,?,?,?,?)",
            (title, armor_type, stats.get("dr",0), stats.get("er",0),
             stats.get("rr",0), stats.get("weight",0.0), url)
        )
        armor_id = cur.lastrowid

    for m in mods:
        conn.execute(
            "INSERT INTO wiki_armor_mods (armor_id, slot, mod_name, description, is_default) VALUES (?,?,?,?,?)",
            (armor_id, m["slot"], m["mod_name"], m["description"], m["is_default"])
        )
    conn.commit()
    return True, len(mods)


def main():
    args    = sys.argv[1:]
    reset   = "--reset" in args
    singles = [a for a in args if not a.startswith("--")]

    conn = sqlite3.connect(DB_PATH)
    init_tables(conn)

    if reset:
        conn.execute("DELETE FROM wiki_armor_mods")
        conn.execute("DELETE FROM wiki_armor")
        conn.commit()
        print("Tables cleared.")

    if singles:
        for name in singles:
            print(f"\nScraping: {name}")
            saved, n = scrape_armor(name, "Armor", conn, force=True)
            if saved:
                rows = conn.execute(
                    "SELECT slot, mod_name, description FROM wiki_armor_mods "
                    "WHERE armor_id=(SELECT id FROM wiki_armor WHERE name=?) ORDER BY slot, id", (name,)
                ).fetchall()
                a = conn.execute("SELECT dr, er, rr, weight FROM wiki_armor WHERE name=?", (name,)).fetchone()
                print(f"  DR:{a[0]} ER:{a[1]} RR:{a[2]} Wt:{a[3]}  Mods:{len(rows)}")
                cur_slot = None
                for slot, mod, desc in rows:
                    if slot != cur_slot:
                        print(f"\n  [{slot}]")
                        cur_slot = slot
                    print(f"    {mod:35s}  {desc[:80]}")
            else:
                print("  Not saved.")
        conn.close()
        return

    total_saved = total_skip = total_failed = 0
    for category, atype in ARMOR_CATEGORIES:
        print(f"\n{'='*55}\n  {atype}  ({category})\n{'='*55}")
        pages = get_category_members(category)
        print(f"  {len(pages)} pages.\n")
        for title in pages:
            try:
                saved, n = scrape_armor(title, atype, conn)
                if saved:
                    total_saved += 1
                    print(f"  OK   {title}  ({n} mods)")
                else:
                    total_skip += 1
            except Exception as e:
                print(f"  FAIL {title} — {e}")
                total_failed += 1
            time.sleep(0.4)

    conn.close()
    print(f"\n{'='*55}")
    print(f"  Done. Saved:{total_saved}  Skipped:{total_skip}  Failed:{total_failed}")
    print(f"{'='*55}")


if __name__ == "__main__":
    main()
