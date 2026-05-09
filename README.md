# FO76 Tracker

A personal Fallout 76 companion app — track weapons, armor, builds, plans, vendor stock, caps, challenges, fishing, and more. Runs locally on your PC and is accessible from any device on your home network.

---

## Requirements

- **Python 3.10+** (tested on 3.13)
- **pip** (comes with Python)
- Windows 10/11 (runs on Mac/Linux too, but `run.bat` is Windows-only — use `python run.py` instead)

---

## Installation

### 1. Clone or download the project

```bash
git clone https://github.com/yourname/fo76-tracker.git
cd fo76-tracker
```

Or download and extract the ZIP from GitHub.

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

Packages installed:

| Package | Used for |
|---|---|
| `flask` | Web framework |
| `anthropic` | Claude AI (vendor scan + inventory scan) |
| `requests` | Nuke code fetch, RSS feeds |
| `beautifulsoup4` | RSS feed parsing |

### 3. Run the app

**Windows — double-click:**
```
run.bat
```

**Command line (any OS):**
```bash
python run.py
```

The app will:
- Create `fo76.db` automatically on first run
- Seed the database with default data (daily tasks, fish species, plan catalog, default character)
- Print your default login credentials to the console
- Open your browser to `http://127.0.0.1:5000`

---

## First Login

Default credentials printed to the console on first run:

```
Username: admin
Password: fo76tracker
```

**Change your password immediately** at:
```
http://127.0.0.1:5000/change-password
```

Sessions last 30 days — you only need to log in once per browser.

---

## Database Setup

No manual setup required. On first run, `init_db()` automatically:

- Creates all tables in `fo76.db`
- Seeds the **Plan Checklist** with 1,869 plans and recipes from the Fallout Wiki
- Seeds fish species (48 species across 6 rarity tiers)
- Seeds default daily/weekly tasks (Daily Challenges, Daily Ops, Earle, Scorchbeast Queen, etc.)
- Seeds a default **"PC Main"** character (id=1)
- Creates a default admin account (`admin` / `fo76tracker`)

The database file lives at `fo76.db` in the project folder. It is **gitignored** — your personal game data never leaves your machine.

### Backups

The app auto-backups `fo76.db` to the `backups/` folder every time it starts, keeping the 7 most recent copies. You can also download a backup manually from the **Backup** page (`/backup`).

---

## Accessing from Other Devices

The app binds to `0.0.0.0:5000` so any device on your home network can reach it. The console prints your local IP on startup:

```
  This PC:   http://127.0.0.1:5000
  Network:   http://192.168.1.X:5000
```

Use the **Network** URL on your phone, tablet, or other PC.

---

## Claude AI Features (Optional)

Some features use the Anthropic Claude API (Claude Haiku). These are optional — the rest of the app works without them.

| Feature | Where to configure |
|---|---|
| Vendor Scan — scan vendor screenshots and extract items | `/vendor-scan` → paste API key |
| Inventory Scan — scan inventory screenshots | `/inventory` → same key |

The API key is stored in the database (`settings` table), never in code or files. It is excluded from all exports and backups.

**Get an API key:** https://console.anthropic.com

Cost is approximately **$0.003 per image scan** using Claude Haiku.

---

## Project Structure

```
fo76-tracker/
├── app.py                   # All routes
├── db.py                    # Database helpers + init + seeding
├── reference.py             # Autocomplete data (weapon names, legendary effects, etc.)
├── legendary_effects_data.py# Legendary mod seed data
├── plan_catalog_seed.json   # 1,869 FO76 plans — seeded into DB on first run
├── quotes.py                # Random Vault-Tec terminal quotes
├── run.py                   # App entry point (opens browser, prints network IP)
├── run.bat                  # Windows launcher
├── requirements.txt
├── fo76.db                  # SQLite database (gitignored — created on first run)
├── static/
│   ├── app.js               # Global JS (quick log, toasts, sidebar, themes)
│   ├── style.css            # All styles + 4 color themes
│   └── fonts/               # Share Tech Mono (served locally, no CDN)
├── templates/               # One HTML per page + base.html
├── backups/                 # Auto-backups (gitignored)
└── vendor_scans/            # CSV output from vendor scan AI (gitignored)
```

---

## Features

| Section | Description |
|---|---|
| Dashboard | At-a-glance stats, action alerts, stash weight, season progress, nuke codes, news |
| Characters | Multi-character support (PC, Xbox, PS4, PS5) — all data scoped per character |
| Perk Cards | Track owned cards, ranks, scrappable dupes |
| Builds | SPECIAL planner with perk card and legendary perk assignments |
| Weapons | Legendary stars, mods, condition, status (Keep/Sell/Scrap) |
| Armor | Same as weapons + DR/ER/RR stats |
| Power Armor | Full PA piece tracker with legendary and condition |
| Mutations | Active/inactive with positive/negative effects, linked to builds |
| Mods | Legendary and normal mods inventory |
| My Vendor | Stock list with vs-market % calculator |
| Vendor Advisor | Suggested sell prices based on your price research history |
| Vendor Scan | AI scan vendor screenshots → extract items automatically |
| Prices | Price research log with min/avg/max per item and price history charts |
| Caps Ledger | Income/expense tracker with categories |
| Plans | Manual plan tracker (owned plans with dupe count and sell price) |
| **Plan Checklist** | **Full 1,869-plan catalog from the Fallout Wiki — track learned/missing per character, filter by category, search** |
| Inventory | Full stash tracker with FO1st container flag |
| Challenges | Daily/weekly/season/static challenges with AJAX completion, lunchbox animation |
| Ammo | Ammo counter with low-stock alerts |
| Season | Season rank progress tracker with score projections |
| Fishing | 48-species catch tracker with rarity tiers and catch log |
| World Finds | Log bobbleheads, magazines, and world items with screenshots |
| Nuke Codes | Current week's codes with auto-fetch from nukacrypt.com |
| Wishlist | Hunt list — flags matches found during vendor scans |
| Atom Shop | Track wanted Atom Shop items |
| Trade Post | Copy-paste trade post generator |
| Shorthand Decoder | Decode FO76 weapon shorthand (e.g. `BLD FFR 90` → Bloodied, Faster Fire Rate, -90% weight) |
| Analytics | Caps over time, prices logged, vendor value charts |
| Backup | Download DB, view and restore auto-backups |
| Global Search | Search across all sections from the header |
| Quick Log | Floating `+` button — log prices, weapons, items without leaving the current page |

---

## Themes

Four color themes switchable from the header bar:

| Theme | Accent |
|---|---|
| Vault Green (default) | `#22c55e` |
| Brotherhood Blue | `#3b82f6` |
| Nuka Red | `#ef4444` |
| Ghoul Teal | `#14b8a6` |

Theme choice is saved to `localStorage` — survives page reloads.

---

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `Q` | Open Quick Log |
| `M` | Toggle sidebar expand/collapse |
| `Escape` | Close Quick Log / close lightbox |

---

## Version

Current version: **0.13.0** — see [CHANGELOG.md](CHANGELOG.md) for full history.
