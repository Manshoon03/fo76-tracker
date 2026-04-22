# FO76 Tracker — Development Backlog

Work items in priority order. Pick the highest incomplete item and build it.
Mark items `[x]` when done. Add new discoveries at the bottom of the relevant tier.
See `CLAUDE.md` for all coding conventions and patterns.

---

## How To Use This File

Each item has:
- **Priority** — P1 (do next), P2 (do after P1s), P3 (nice to have)
- **Files** — which files to touch
- **Notes** — enough detail to implement without asking the user

---

## P1 — High Impact, Build These First

### [ ] Discord Webhook Integration
**Why:** Discord is always open. This makes every tracker alert actionable in real-time.
**Files:** `db.py`, `app.py`, `templates/settings.html` (new or extend existing settings page)
**What to build:**
- Settings page (or add to an existing settings/notices area): save `discord_webhook_url` to settings table
- Helper function `_discord_notify(message)` in `app.py` — POST to webhook with a JSON payload using `requests`. Wrap in try/except, fail silently if webhook not set or fails.
- Hook it into:
  - `/nuke-codes/fetch` — notify when codes are fetched successfully: "☢ Nuke codes updated: Alpha XXXXXXXX Bravo XXXXXXXX Charlie XXXXXXXX"
  - `/nuke-codes/update` — same message on manual save
  - Price alert hits — when a price_research record is added that matches an active alert: "🔔 Price hit: [item] seen at [price] (alert: [target])"
  - Daily checklist — morning reminder? Actually skip the scheduled approach (no scheduler running). Instead add a "Send Daily Summary to Discord" button on the /daily page that posts pending tasks.
- Format: Use Discord embed-style JSON (webhook embeds) for clean formatting. Color: green=good, yellow=warning, red=alert.
- Add a "Test Webhook" button on settings that sends a test message.
- No new pip package needed — `requests` already imported.

---

### [x] Price History Charts
**Why:** 3,400+ price records. Currently just a table. Charts make trends visible.
**Files:** `templates/prices.html`, `app.py` (new JSON endpoint)
**What to build:**
- Add Chart.js via CDN (single `<script>` tag in the prices template only — not globally).
- New route `GET /prices/chart-data?item=NAME` → returns JSON: `{labels: [dates], prices: [values], avg: N}`
  - Query: all price_research rows for that item_name, ordered by date_seen
- On the prices page, add a "📈 View Price History" button per item in the averages table
  - Clicking shows a small modal/panel with a line chart for that item
  - Use the `/prices/chart-data` endpoint via fetch
- Also add a "Top Items" chart at the top of the prices page: bar chart of top 10 most-logged items by record count
- Chart colors: use `var(--accent)` for primary line, `var(--gold)` for average line
- Fallback gracefully if no data: show "Not enough data" message

---

### [x] Trading Partner Log
**Why:** Active trader needs to track IGNs, past trades, and reputation.
**Files:** `db.py`, `app.py`, `templates/trade_partners.html` (new), `templates/base.html`
**What to build:**
- New table `trade_partners`: `id, ign TEXT, platform TEXT DEFAULT 'PC', rating TEXT DEFAULT 'Good', trade_count INTEGER DEFAULT 0, notes TEXT, last_trade TEXT, created_at TEXT`
- New table `trade_history`: `id, partner_id INTEGER, trade_date TEXT, gave TEXT, received TEXT, caps_delta INTEGER DEFAULT 0, notes TEXT, created_at TEXT`
- New page `/trade-partners`:
  - Partner list with rating badges (Good=green, Neutral=grey, Bad=red, Blocked=red+warning icon)
  - Quick-log a trade: select partner (or type new), what you gave, what you received, caps amount
  - Partner detail view: trade history with that partner
  - Search by IGN
- Rating quick-buttons: G/N/B/X inline
- Add to sidebar under Trade Post: 🤝 Partners

---

## P2 — Solid Value, Build After P1s

### [x] Analytics / Stats Page
**Why:** The data is there. Charts make it valuable.
**Files:** `app.py`, `templates/analytics.html` (new), `templates/base.html`
**What to build:**
- New page `/analytics` using Chart.js (CDN, template-local only)
- Charts:
  - **Caps over time** — line chart from caps_sessions, showing end_caps per session date
  - **Play time per week** — bar chart from play_sessions grouped by week
  - **Weapons found per week** — bar chart from weapons.created_at
  - **Price records logged per week** — bar chart from price_research.created_at
  - **Top selling items** — pie/bar from vendor_stock by my_price
- New route `GET /analytics/data` → returns all chart data as JSON in one call
- Keep it to one page with collapsible sections per chart
- Add to sidebar under Season: 📊 Analytics

---

### [x] Session Summary
**Why:** Quick recap of what you did each session without manual tracking.
**Files:** `app.py`, `templates/caps_ledger.html`, `templates/playtime.html`
**What to build:**
- New route `GET /session-summary` — shows a comparison of "before vs after" for a date range
  - Inputs: date range (default: today)
  - Shows: caps delta, weapons added/removed, plans added, prices logged, challenges completed, play time
- Actually: simpler approach — add a "Session Report" section to the existing dashboard
  - Store a `session_snapshot` in settings when user clicks "Start Session" (record caps, weapon count, etc.)
  - "End Session" compares current state vs snapshot → flash summary + option to save to notes
- Or even simpler: just add a "What happened today" panel to the dashboard that auto-calculates from today's data (no snapshot needed):
  - Caps logged today (from caps_sessions)
  - Weapons added today (from weapons.created_at)
  - Prices logged today
  - Challenges completed today
  - Play time today

---

### [x] Vendor Route Tracker
**Why:** Server hop vendor routes are repetitive — track which vendors to hit.
**Files:** `db.py`, `app.py`, `templates/vendor_route.html` (new), `templates/base.html`
**What to build:**
- New table `vendor_route_stops`: `id, stop_name TEXT, location TEXT, notes TEXT, last_checked TEXT, sort_order INTEGER DEFAULT 0`
- Page `/vendor-route`:
  - Ordered list of stops (drag-reorder or manual up/down buttons)
  - "Check" button per stop — stamps `last_checked` with today's date
  - Color code: checked today = green, checked this week = yellow, older/never = red
  - "Reset All" button to clear today's checks
  - Add/edit/delete stops
- Add to sidebar: 🗺 Vendor Route (near server-hops)

---

### [ ] Improved Mobile Layout
**Why:** App is network-accessible. Would be useful to check on phone while playing on PC.
**Files:** `static/style.css`, `templates/base.html`
**What to build:**
- Add CSS `@media (max-width: 768px)` rules to `style.css`:
  - Sidebar auto-closes on mobile, shows as overlay
  - Tables switch to card layout (each row becomes a card)
  - Form grid goes single-column
  - Stat grid goes 2x2 instead of 4 across
  - Hide less-important table columns (weight, value) on small screens via `.hide-mobile` class
- Add a `<meta name="theme-color">` and `<link rel="manifest">` to base.html
- Create `static/manifest.json` for PWA installability:
  ```json
  {"name":"FO76 Tracker","short_name":"FO76","start_url":"/","display":"standalone","background_color":"#0a0a0a","theme_color":"#00ff41","icons":[...]}
  ```
- No service worker needed for basic installability on Android Chrome

---

### [ ] Stash Optimizer (AI)
**Why:** "What should I drop?" is the #1 daily FO76 question. Automate it.
**Files:** `app.py`, `templates/stash_optimizer.html` (new), `templates/base.html`
**What to build:**
- New page `/stash-optimizer`
- Button: "Analyze My Stash" — calls Claude with current inventory context
- Builds a prompt with: current stash weight, all weapons with status + condition + value, armor, plans with qty_unlearned > 0
- Claude prompt: "You are a Fallout 76 advisor. Based on this stash snapshot, suggest what to scrap, sell, or keep. Prioritize freeing weight. Consider legendary value (star count, roll quality). Return JSON: {scrap: [...], sell: [...], keep_reason: {...}}"
- Display results as three columns: Scrap / Sell / Keep with reasoning
- "Apply" button marks suggested items with that status
- Requires API key (same as vendor scan)
- Add to sidebar near Vendor Scan: 🤖 Stash Optimizer

---

## P3 — Nice to Have

### [ ] Event Schedule Widget
**Files:** `templates/index.html`, `templates/base.html` or new page
**Notes:** FO76 public events follow a known hourly schedule. Add a static lookup table of event times (hardcoded since Bethesda rarely changes them) and show "Next Event: Radiation Rumble in 23 min" on dashboard. No external API needed — just JavaScript comparing current time to a static schedule table.

---

### [ ] Recipe / Crafting Tracker
**Files:** `db.py`, `app.py`, `templates/recipes.html` (new)
**Notes:** Track which recipes/plans you know. Fields: name, category, ingredients, learned, notes. Separate from Plans (which tracks sellable plans). Focus on crafting recipes you actually use.

---

### [ ] Bulk Vendor Price Update
**Files:** `templates/vendor.html`, `app.py`
**Notes:** Add a "Quick Reprice" mode on the vendor page — show all items in a compact list with just name + price input, "Save All" button at bottom. Faster than editing one at a time. POST to a new `/vendor/bulk-reprice` route that updates all prices in a single transaction.

---

### [ ] Nuke Code History
**Files:** `db.py`, `app.py`, `templates/nuke_codes.html`
**Notes:** Log historical nuke codes to a new `nuke_code_history` table (silo, code, week_of, added_at). Show last 4 weeks in a collapsible panel on the nuke codes page. Useful for verifying codes from previous weeks.

---

### [ ] Challenge Template Library
**Files:** `db.py`, `app.py`, `templates/challenges.html`
**Notes:** Weekly challenges repeat. Add a "Templates" tab that stores common challenge templates (name, type, target, reward). "Add from Template" bulk-inserts them for the new week. Saves re-entering the same 15 challenges every Tuesday reset.

---

### [ ] Print-Friendly Vendor Sheet
**Files:** `templates/vendor.html` or new `templates/vendor_print.html`
**Notes:** Add a `/vendor/print` route that renders a clean, print-styled page of your vendor stock with item names, notations (for weapons), and prices. `@media print` CSS. No nav, no sidebar, just the table. Add a "Print Sheet" button on the vendor page.

---

## Community / Streaming

### [ ] Followed Streamers Page
**Files:** `db.py`, `app.py`, `templates/streamers.html` (new), `templates/base.html`
**What to build:**
- New table `streamers`: `id, name TEXT, platform TEXT (Twitch/YouTube), url TEXT, notes TEXT, active INTEGER DEFAULT 1`
- Page `/streamers`: list of followed FO76 streamers with links + notes
- "Stream tonight?" toggle — mark who's expected to stream tonight
- Quick copy links to open Twitch/YouTube in browser
- Could extend to: schedule notes, items to watch for in their vendor
- Add to sidebar: 📺 Streamers

### [ ] Improved Mobile Layout / PWA
**Files:** `static/style.css`, `templates/base.html`, `static/manifest.json`
**What to build:**
- CSS `@media (max-width: 768px)` rules:
  - Sidebar overlay on mobile (auto-close after nav)
  - Tables → card layout on small screens
  - Form grids → single column
  - Stat grid → 2×2
  - `.hide-mobile` class for low-priority columns
- `<meta name="theme-color">` + `<link rel="manifest">` in base.html
- `static/manifest.json` for PWA installability (Android Chrome "Add to homescreen")

---

## Discovered During Dev (No Priority Assigned Yet)

- The `caps_ledger` table (transactions) is different from `caps_sessions` (session snapshots). Both exist. The Caps Ledger page currently uses caps_sessions. Consider surfacing caps_ledger transactions or removing the unused table.
- `playtime` page tracks play sessions via `play_sessions` table. The stats show today/week/all-time but no per-day chart. Could feed the Analytics page.
- Export page could use a "Print All" / "Export as ZIP" option that packages all CSVs at once (a zip route already exists at `/backup/download-zip`).

---

## Completed

- [x] Weapons — notation column + copy button
- [x] Weapons — duplicate detection + DUP badge
- [x] Weapons — screenshot scanner (Claude Haiku)
- [x] Decoder — "Log This Weapon" inline form
- [x] Nuke Codes — auto-fetch from nukacrypt.com
- [x] Caps Goal Tracker — progress bar + dashboard widget
- [x] Price Alerts — set alert, highlight hits, dashboard widget
- [x] Dashboard — caps balance + wishlist count stat cards
- [x] Ammo Counter — qty tracking, low-stock alerts, dashboard widget
- [x] Daily/Weekly Checklist — pre-seeded tasks, AJAX check/uncheck, dashboard widget
- [x] Legendary Run Log — boss cards, urgency color, log runs
- [x] Server Hop Notes — quick-log, card list
- [x] Build Comparison — side-by-side SPECIAL + radar chart
- [x] Atom Shop Wishlist — want/bought/skip, balance tracker
- [x] Trade Post Generator — Discord/plain/Reddit format, notation built client-side
- [x] Export CSV updates — ammo, legend runs, server hops, atom shop added
- [x] Nav updates — all new pages in sidebar
- [x] Price History Charts — Chart.js line chart per item, modal popup, avg reference line
- [x] Trading Partner Log — IGN list, rating system, trade history log
- [x] Session Summary Widget — today's caps/weapons/prices/challenges/playtime on dashboard
- [x] Analytics Page — 5 charts: caps over time, playtime/week, weapons/week, prices/week, top vendor
- [x] Vendor Route Tracker — stop list, check-off, color coded freshness, reset all
- [x] Fishing Tracker — 48 species checklist, 6 rarity tiers, catch log, progress bar, AJAX toggles
