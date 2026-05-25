"""
Fallout 76 Legendary Perk Image Downloader
===========================================
Downloads card art for all 26 legendary perks from fallout.fandom.com
and builds static/img/perks/legend_manifest.json.

Run once: python scrape_legendary_perks.py
"""

import json
import time
import requests
from pathlib import Path

SAVE_DIR = Path(__file__).parent / "static" / "img" / "perks"
MANIFEST = SAVE_DIR / "legend_manifest.json"
FANDOM_API = "https://fallout.fandom.com/api.php"
HEADERS = {"User-Agent": "FO76Tracker/1.0 (personal use legendary perk image downloader)"}

# Exact filenames confirmed via allimages API query on fallout.fandom.com
# Critical Savvy has no fandom legend card image — falls back to existing perk image
CARD_FILE_MAP = {
    "Legendary Agility":        "FO76OW_Legend_cardAgility.png",
    "Legendary Charisma":       "FO76OW_Legend_card_Charisma.png",
    "Legendary Endurance":      "FO76OW_Legend_cardEndu.png",
    "Legendary Intelligence":   "FO76OW_Legend_card_Int.png",
    "Legendary Luck":           "FO76OW_Legend_card_Luck.png",
    "Legendary Perception":     "FO76OW_Legend_card_Perc.png",
    "Legendary Strength":       "FO76OW_Legend_card_Str.png",
    "Ammo Factory":             "FO76OW_Legend_card_Ammo_Factory.png",
    "Collateral Damage":        "FO76OW_Legend_card_Collat_Dam_1.png",
    "Detonation Contagion":     "FO76OW_Legend_card_Det_Contang.png",
    "Exploding Palm":           "FO76OW_Legend_card_Expl_palm.png",
    "Far-Flung Fireworks":      "FO76OW_Legend_card_Far_flung.png",
    "Follow Through":           "FO76OW_Legend_cardFollow_through.png",
    "Hack and Slash":           "FO76OW_Legend_card_Hack_Slash.png",
    "Blood Sacrifice!":         "FO76OW_Legend_card_Blood_Sacrf.png",
    "Electric Absorption":      "FO76OW_Legend_card_Elec_Absor.png",
    "Funky Duds":               "FO76OW_Legend_card_Funky_Duds.png",
    "Retribution":              "FO76OW_Legend_card_retrib.png",
    "Sizzling Style":           "FO76OW_Legend_card_sizzstyle.png",
    "Taking One For The Team":  "FO76OW_Legend_card_take_team.png",
    "Brawling Chemist":         "FO76OW_Legend_card_Brawl_chem.png",
    "Master Infiltrator":       "FO76OW_Legend_card_Mast_Inf.png",
    "Power Armor Reboot":       "FO76OW_Legend_card_Power_Armor_reb.png",
    "Power Sprinter":           "FO76OW_Legend_card_Power_Sprint.png",
    "Survival Shortcut":        "FO76OW_Legend_card_surv_short.png",
    "What Rads?":               "FO76OW_Legend_card_what_rads.png",
    # Critical Savvy: no fandom legend card image; app falls back to existing perk image
    "Critical Savvy":           None,
}


def resolve_urls(filenames):
    """Batch resolve File: titles to direct URLs via imageinfo API."""
    urls = {}
    chunk_size = 50
    for i in range(0, len(filenames), chunk_size):
        chunk = filenames[i:i + chunk_size]
        params = {
            "action": "query",
            "titles": "|".join(f"File:{fn}" for fn in chunk),
            "prop": "imageinfo",
            "iiprop": "url",
            "format": "json",
        }
        r = requests.get(FANDOM_API, params=params, headers=HEADERS, timeout=15)
        data = r.json()
        for page in data.get("query", {}).get("pages", {}).values():
            # Normalize: API returns spaces but we key by underscores
            title = page.get("title", "").replace("File:", "").replace(" ", "_")
            ii = page.get("imageinfo", [])
            if ii:
                urls[title] = ii[0]["url"]
        time.sleep(0.3)
    return urls


def download_all():
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {}

    # Collect filenames to resolve
    to_resolve = [fn for fn in CARD_FILE_MAP.values() if fn]
    print(f"Resolving {len(to_resolve)} image URLs from fandom API...")
    resolved = resolve_urls(to_resolve)

    for card_name, wiki_filename in CARD_FILE_MAP.items():
        if wiki_filename is None:
            # Critical Savvy fallback: use the regular perk image if it exists
            fallback = SAVE_DIR / "fo76_perk_critical_savvy.webp"
            if fallback.exists():
                manifest[card_name] = "/static/img/perks/fo76_perk_critical_savvy.webp"
                print(f"  FALLBACK {card_name} -> fo76_perk_critical_savvy.webp")
            else:
                manifest[card_name] = None
                print(f"  NO IMAGE {card_name}")
            continue

        dest = SAVE_DIR / wiki_filename
        if dest.exists():
            manifest[card_name] = f"/static/img/perks/{wiki_filename}"
            print(f"  EXISTS  {card_name} -> {wiki_filename}")
            continue

        url = resolved.get(wiki_filename)
        if not url:
            print(f"  NOT FOUND {card_name} ({wiki_filename})")
            manifest[card_name] = None
            continue

        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            if resp.status_code == 200:
                dest.write_bytes(resp.content)
                manifest[card_name] = f"/static/img/perks/{wiki_filename}"
                print(f"  OK      {card_name} -> {wiki_filename}")
            else:
                print(f"  HTTP {resp.status_code}  {card_name}")
                manifest[card_name] = None
        except Exception as e:
            print(f"  ERR     {card_name}: {e}")
            manifest[card_name] = None

        time.sleep(0.2)

    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"\nManifest written: {MANIFEST}")
    return manifest


if __name__ == "__main__":
    print("=" * 55)
    print("FO76 Legendary Perk Image Downloader")
    print("=" * 55)
    results = download_all()
    found = sum(1 for v in results.values() if v)
    missing = [k for k, v in results.items() if not v]
    print(f"\nDone! {found}/{len(CARD_FILE_MAP)} images mapped.")
    if missing:
        print("Missing:", missing)
