"""
Fallout 76 Mutations Scraper
=============================
Scrapes all mutations (positive effects, negative effects, serum info)
from the Fallout Wiki into the wiki_mutations table in fo76.db.

  python scrape_mutations.py            # scrape all (skip existing)
  python scrape_mutations.py --reset    # wipe and re-scrape
  python scrape_mutations.py "Adrenal Reaction"  # single mutation test
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
HEADERS  = {"User-Agent": "FO76Tracker/1.0 (mutations scraper, personal project)"}

MUTATIONS_OVERVIEW_PAGE = "Mutations (Fallout 76)"
MUTATIONS_CATEGORY      = "Category:Fallout 76 mutations"


def init_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS wiki_mutations (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT UNIQUE NOT NULL,
            positive_effects TEXT DEFAULT '',
            negative_effects TEXT DEFAULT '',
            serum_name       TEXT DEFAULT '',
            wiki_url         TEXT DEFAULT '',
            scraped_at       TEXT DEFAULT (datetime('now'))
        );
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


def clean(text):
    """Collapse whitespace and strip."""
    return re.sub(r"\s+", " ", text).strip()


def parse_overview_page():
    """
    Parse the main 'Mutations (Fallout 76)' wiki page which contains a big
    table listing all mutations with positive and negative effects columns.
    Returns list of dicts: {name, positive_effects, negative_effects, serum_name}
    """
    html = fetch_page_html(MUTATIONS_OVERVIEW_PAGE)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    mutations = []

    for table in soup.find_all("table"):
        headers = [clean(th.get_text()).lower() for th in table.find_all("th")]
        # Look for a table that has columns for mutation name + effects
        has_name    = any("mutation" in h or "name" in h for h in headers)
        has_pos     = any("positive" in h or "benefit" in h for h in headers)
        has_neg     = any("negative" in h or "drawback" in h for h in headers)
        if not (has_name and (has_pos or has_neg)):
            continue

        # Determine column indices from the header row
        header_row = table.find("tr")
        if not header_row:
            continue
        ths = header_row.find_all(["th", "td"])
        col_map = {}
        for i, th in enumerate(ths):
            t = clean(th.get_text()).lower()
            if "mutation" in t or (i == 0 and "name" in t):
                col_map["name"] = i
            elif "positive" in t or "benefit" in t:
                col_map["pos"] = i
            elif "negative" in t or "drawback" in t:
                col_map["neg"] = i
            elif "serum" in t:
                col_map["serum"] = i

        if "name" not in col_map:
            col_map["name"] = 0
        if "pos" not in col_map and len(ths) >= 2:
            col_map["pos"] = 1
        if "neg" not in col_map and len(ths) >= 3:
            col_map["neg"] = 2

        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue

            name_i  = col_map.get("name", 0)
            pos_i   = col_map.get("pos", 1)
            neg_i   = col_map.get("neg", 2)
            ser_i   = col_map.get("serum", -1)

            name = clean(cells[name_i].get_text()) if name_i < len(cells) else ""
            # Strip footnote markers like [1]
            name = re.sub(r"\[\d+\]", "", name).strip()
            if not name or name.lower() in ("mutation", "name", "effect", ""):
                continue

            pos  = clean(cells[pos_i].get_text()) if pos_i < len(cells) else ""
            neg  = clean(cells[neg_i].get_text()) if neg_i < len(cells) else ""
            ser  = clean(cells[ser_i].get_text()) if ser_i != -1 and ser_i < len(cells) else ""

            mutations.append({
                "name":             name,
                "positive_effects": pos,
                "negative_effects": neg,
                "serum_name":       ser,
            })

        if mutations:
            break  # found a valid table

    return mutations


def parse_individual_mutation_page(title):
    """
    Parse a single mutation wiki page.
    Wiki uses a portable infobox (aside) with pi-item pi-data divs.
    Each item has a <p> label and a <div class='pi-data-value'> value.
    """
    html = fetch_page_html(title)
    if not html:
        return {}

    soup = BeautifulSoup(html, "lxml")
    result = {"positive_effects": "", "negative_effects": "", "serum_name": ""}

    # Portable infobox: aside > div.pi-item.pi-data
    for aside in soup.find_all("aside"):
        for item in aside.find_all("div", class_=lambda c: c and "pi-item" in c and "pi-data" in c):
            # Label is the first <p> child; value is div.pi-data-value
            label_p = item.find("p")
            value_div = item.find("div", class_=lambda c: c and "pi-data-value" in c)
            if not label_p or not value_div:
                continue
            lbl = clean(label_p.get_text()).lower()
            val = clean(value_div.get_text())
            if lbl == "positive":
                result["positive_effects"] = val
            elif lbl == "negative":
                result["negative_effects"] = val
            elif "cause" in lbl or "serum" in lbl:
                result["serum_name"] = val

    if result["positive_effects"] or result["negative_effects"]:
        return result

    # Fallback: va-table infobox rows
    infobox = soup.find("table", class_=lambda c: c and ("va-table" in c or "infobox" in c))
    if infobox:
        for row in infobox.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            lbl = clean(cells[0].get_text()).lower()
            val = clean(cells[-1].get_text())
            if "positive" in lbl:
                result["positive_effects"] = val
            elif "negative" in lbl:
                result["negative_effects"] = val
            elif "cause" in lbl or "serum" in lbl:
                result["serum_name"] = val

    return result


def save_mutation(conn, name, pos, neg, serum, force=False):
    url = f"https://fallout.wiki/wiki/{name.replace(' ', '_')}"
    existing = conn.execute("SELECT id FROM wiki_mutations WHERE name=?", (name,)).fetchone()
    if existing and not force:
        return False
    if existing:
        conn.execute(
            "UPDATE wiki_mutations SET positive_effects=?, negative_effects=?, serum_name=?, wiki_url=?, scraped_at=datetime('now') WHERE id=?",
            (pos, neg, serum, url, existing[0])
        )
    else:
        conn.execute(
            "INSERT INTO wiki_mutations (name, positive_effects, negative_effects, serum_name, wiki_url) VALUES (?,?,?,?,?)",
            (name, pos, neg, serum, url)
        )
    conn.commit()
    return True


def main():
    args    = sys.argv[1:]
    reset   = "--reset" in args
    singles = [a for a in args if not a.startswith("--")]

    conn = sqlite3.connect(DB_PATH)
    init_tables(conn)

    if reset:
        conn.execute("DELETE FROM wiki_mutations")
        conn.commit()
        print("Table cleared.")

    # ── Single mutation test ─────────────────────────────────────────
    if singles:
        for name in singles:
            print(f"\nScraping: {name}")
            info = parse_individual_mutation_page(name)
            saved = save_mutation(conn, name,
                                  info.get("positive_effects", ""),
                                  info.get("negative_effects", ""),
                                  info.get("serum_name", ""),
                                  force=True)
            if saved:
                row = conn.execute("SELECT positive_effects, negative_effects, serum_name FROM wiki_mutations WHERE name=?", (name,)).fetchone()
                print(f"  Positive: {row[0][:120]}")
                print(f"  Negative: {row[1][:120]}")
                if row[2]:
                    print(f"  Serum:    {row[2]}")
            else:
                print("  Not saved.")
        conn.close()
        return

    # ── Full scrape — overview page first ───────────────────────────
    print(f"\n{'='*55}")
    print(f"  Phase 1: Parse overview page ({MUTATIONS_OVERVIEW_PAGE})")
    print(f"{'='*55}")

    overview_mutations = parse_overview_page()
    print(f"  Found {len(overview_mutations)} mutations in overview table.\n")

    saved_count = skip_count = 0
    overview_names = set()

    for m in overview_mutations:
        name = m["name"]
        overview_names.add(name)
        try:
            saved = save_mutation(conn, name,
                                  m["positive_effects"],
                                  m["negative_effects"],
                                  m["serum_name"])
            if saved:
                saved_count += 1
                print(f"  OK   {name}")
            else:
                skip_count += 1
        except Exception as e:
            print(f"  FAIL {name} — {e}")

    # ── Phase 2: Category members for any not caught by overview ────
    print(f"\n{'='*55}")
    print(f"  Phase 2: Category members ({MUTATIONS_CATEGORY})")
    print(f"{'='*55}")

    pages = get_category_members(MUTATIONS_CATEGORY)
    print(f"  {len(pages)} pages.\n")

    failed_count = 0
    for title in pages:
        if title in overview_names:
            # already processed; check if we got effects
            row = conn.execute("SELECT positive_effects, negative_effects FROM wiki_mutations WHERE name=?", (title,)).fetchone()
            if row and (row[0] or row[1]):
                continue  # good data exists

        existing = conn.execute("SELECT id, positive_effects, negative_effects FROM wiki_mutations WHERE name=?", (title,)).fetchone()
        if existing and (existing[1] or existing[2]):
            skip_count += 1
            continue  # has good data

        try:
            info  = parse_individual_mutation_page(title)
            saved = save_mutation(conn, title,
                                  info.get("positive_effects", ""),
                                  info.get("negative_effects", ""),
                                  info.get("serum_name", ""),
                                  force=bool(existing))
            if saved:
                saved_count += 1
                print(f"  OK   {title}")
            else:
                skip_count += 1
        except Exception as e:
            print(f"  FAIL {title} — {e}")
            failed_count += 1
        time.sleep(0.4)

    conn.close()
    print(f"\n{'='*55}")
    print(f"  Done. Saved:{saved_count}  Skipped:{skip_count}  Failed:{failed_count}")
    print(f"{'='*55}")


if __name__ == "__main__":
    main()
