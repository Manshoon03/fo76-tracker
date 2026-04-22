"""
Fallout 76 Perk Card Image Scraper
===================================
Pulls all FO76 perk card images from the Fallout Wiki and saves them
to static/img/perks/ for use in the build generator.
"""

import os
import time
import json
import requests
from pathlib import Path

SAVE_DIR = Path(__file__).parent / "static" / "img" / "perks"
SAVE_DIR.mkdir(parents=True, exist_ok=True)

API_BASE = "https://fallout.wiki/api.php"
HEADERS  = {"User-Agent": "FO76Tracker/1.0 (personal project perk image scraper)"}

def get_all_perk_image_filenames():
    """Pull all filenames from Category:Fallout 76 perk images via MediaWiki API."""
    filenames = []
    params = {
        "action":  "query",
        "list":    "categorymembers",
        "cmtitle": "Category:Fallout 76 perk images",
        "cmtype":  "file",
        "cmlimit": "500",
        "format":  "json",
    }
    while True:
        r = requests.get(API_BASE, params=params, headers=HEADERS, timeout=15)
        data = r.json()
        members = data.get("query", {}).get("categorymembers", [])
        for m in members:
            filenames.append(m["title"])  # e.g. "File:FO76 perk slugger.png"
        cont = data.get("continue", {}).get("cmcontinue")
        if not cont:
            break
        params["cmcontinue"] = cont
        time.sleep(0.3)
    print(f"Found {len(filenames)} perk image files in category.")
    return filenames


def get_image_urls(filenames):
    """Batch-resolve File: titles to direct image URLs via imageinfo API."""
    urls = {}
    # API accepts up to 50 titles at a time
    chunk_size = 50
    for i in range(0, len(filenames), chunk_size):
        chunk = filenames[i:i+chunk_size]
        params = {
            "action":  "query",
            "titles":  "|".join(chunk),
            "prop":    "imageinfo",
            "iiprop":  "url",
            "format":  "json",
        }
        r = requests.get(API_BASE, params=params, headers=HEADERS, timeout=15)
        data = r.json()
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            title = page.get("title", "")
            ii    = page.get("imageinfo", [])
            if ii:
                urls[title] = ii[0]["url"]
        time.sleep(0.3)
    return urls


def slugify(title):
    """Turn 'File:FO76 perk slugger.png' into 'fo76_perk_slugger.png'."""
    name = title.replace("File:", "").strip()
    name = name.lower().replace(" ", "_")
    return name


def download_images(urls):
    """Download each image, skip if already exists."""
    downloaded = 0
    skipped    = 0
    failed     = 0

    for title, url in urls.items():
        filename = slugify(title)
        dest     = SAVE_DIR / filename
        if dest.exists():
            skipped += 1
            continue
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                dest.write_bytes(r.content)
                downloaded += 1
                print(f"  OK {filename}")
            else:
                print(f"  FAIL {filename} - HTTP {r.status_code}")
                failed += 1
        except Exception as e:
            print(f"  FAIL {filename} - {e}")
            failed += 1
        time.sleep(0.15)  # be polite to the wiki

    return downloaded, skipped, failed


def save_manifest(urls):
    """Save a JSON manifest mapping clean names to filenames for use in the app."""
    manifest = {}
    for title, _ in urls.items():
        filename = slugify(title)
        # Clean display name: "File:FO76 perk slugger.png" → "Slugger"
        clean = title.replace("File:", "").replace("FO76 perk ", "").replace("FO76_perk_", "")
        clean = clean.replace(".png", "").replace(".jpg", "").replace("_", " ").strip().title()
        manifest[clean] = f"/static/img/perks/{filename}"

    manifest_path = Path(__file__).parent / "static" / "img" / "perks" / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"\nManifest saved: {manifest_path}")
    return manifest


if __name__ == "__main__":
    print("=" * 50)
    print("FO76 Perk Card Image Scraper")
    print("=" * 50)

    print("\n[1/3] Fetching image filenames from wiki category...")
    filenames = get_all_perk_image_filenames()

    print("\n[2/3] Resolving image URLs...")
    urls = get_image_urls(filenames)
    print(f"Resolved {len(urls)} image URLs.")

    print(f"\n[3/3] Downloading to {SAVE_DIR} ...")
    downloaded, skipped, failed = download_images(urls)

    print("\n" + "=" * 50)
    print(f"Done! Downloaded: {downloaded} | Skipped: {skipped} | Failed: {failed}")

    manifest = save_manifest(urls)
    print(f"Manifest contains {len(manifest)} entries.")
    print("=" * 50)
