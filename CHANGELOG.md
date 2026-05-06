# FO76 Tracker — Changelog

All notable changes to this project are documented here.
Format: Version | Date | What changed

---

## [0.12.0] — 2026-05-05

### Added
- **Multi-character support** — full character management across PC, Xbox, PS5, PS4.
  - New `characters` table with name, platform, type (Playable / Mule), level, notes
  - Default "PC Main" character seeded on first run (id=1); all existing data migrated to it
  - `character_id` column added to 19 tables via safe `ALTER TABLE` migrations (DEFAULT 1)
  - `get_active_char_id()` helper reads `active_character_id` from settings
  - `inject_characters()` context processor injects `active_char` + `all_chars` into every template
  - Character switcher widget in header — shows platform badge + name, dropdown to switch instantly
  - Characters page (`/characters`) — grouped by platform, add/edit inline, delete, Switch button
  - Active character highlighted with green border + ACTIVE badge
  - All list/add/edit routes now scope data by active character (vendor, inventory, weapons, armor, mods, plans, builds, perk cards, challenges, ammo, caps, mutations, power armor, legend runs, fishing, session journal)
  - `_inv_sync()` helper updated with optional `cid` param; Quick Log tags all inserts with active character
- **Mule character dashboard** — Mule-type characters get a stripped-down dashboard (vendor stock, caps, inventory count, recent prices). Full Playable view unchanged.
- **Screenshot scan → import** for Inventory and Vendor.
  - Upload a PNG/JPG/WEBP FO76 screenshot — Claude Haiku reads items via vision
  - Returns editable preview table; every field (name, category, qty, weight/price, notes) is editable inline before importing
  - Select All / None checkboxes + Import Selected button for bulk import
  - Routes: `POST /inventory/scan`, `POST /inventory/scan/import`, `POST /vendor/scan`, `POST /vendor/scan/import`
  - `_scan_image()` + `_extract_json_array()` helpers added
  - Scan panel added to Inventory and Vendor pages (collapsible, above table)

### Removed
- **Session Journal** — removed all `/session-journal` routes, `session_journal.html` template, `_save_sj_files()` / `_sj_screenshots()` helpers, upload dir setup, and sidebar link.
- **Spawn Notes** — removed all `/spawn-notes` routes, `spawn_notes.html` template, `_save_sn_files()` / `_sn_screenshots()` helpers, upload dir setup, and sidebar link. World Finds untouched.

---

## [0.11.0] — 2026-05-01

### Removed
- **Notices system** — removed `/notices` routes, `notices.html` template, dashboard widget, sidebar link, and CSS classes. Table definition kept dormant in `db.py`; existing data unaffected.
- **Server Hops tracker** — removed all routes, `server_hops.html` template, and sidebar link.
- **Vendor Route tracker** — removed all routes (`/vendor-route/*`), `vendor_route.html` template, and sidebar link.
- **Playtime Tracker** — removed `/playtime` routes, `playtime.html` template, `_fmt_duration()` helper, sidebar link, dashboard "Today's Summary" Playtime link, `today_play_mins` DB query from `dashboard_stats()`, and "Play Time per Week" chart from Analytics.
- **Weapons Found per Week** — removed analytics chart and `weapon_rows` query from `/analytics/data`.
- **Trade Partners** — removed all `/trade-partners` and `/trade-history` routes, `trade_partners.html` template, and sidebar link. Tables kept dormant.

### Fixed
- **Nuke codes fetch stuck at "running" after server restart** — on startup, any `nuke_fetch_status` DB value beginning with `running|` is now reset to a `fail|` message with instructions to retry. Previously the fetch would appear to be running forever after a crash or manual restart.

### Changed
- **UI — full visual refresh** — base font bumped from 13 px → 15 px, line-height 1.5 → 1.6, sidebar expanded width 196 px → 224 px. Table cell padding, stat card padding, button sizes, badge sizes, form input font size, and max content width all increased for improved readability.
- **Analytics page** — now shows three charts only: Caps Over Time, Prices Logged per Week, Top Vendor Items by Value.
- **Dashboard "Today's Summary"** — shows Caps Today, Weapons Added, Prices Logged, Challenges Done. Play time stat removed.

---

## [0.10.0] — 2026-04-27

### Added
- **World Finds tracker** (`/world-finds`) — log bobbleheads, magazines, and other items found in the world.
  - Item types: Bobblehead, Magazine, Other — with pre-populated name autocomplete (datalist) per type
  - Fields: item name, location description, region (all 9 FO76 regions), server type (public/private/friend), date found, notes
  - Filter tabs: All / Bobbleheads / Magazines / Other with live counts
  - **Multi-screenshot support** — attach multiple screenshots per find; stored in `world_find_screenshots` table (one-to-many)
  - Horizontal scrollable photo strip on each find card
  - Individual screenshot delete buttons in edit mode (removes file + DB row, no page reload)
  - Full-screen lightbox with ‹ › previous/next navigation, keyboard arrow support, Esc to close
  - Live upload preview strip before submitting (shows thumbnails of selected files)
  - `world_finds` and `world_find_screenshots` tables added via safe migration
  - Sidebar entry 🗺 World Finds (after Fishing)

### Fixed
- **Flask server freezing on concurrent requests** — `run.py` was launching a single-threaded
  Werkzeug server. Added `threaded=True` to `app.run()`. This caused playtime stop and other
  routes to time out whenever a nuke code fetch (blocking HTTP) was in progress simultaneously.
- **Nuke codes fetch blocking the server** — the `/nuke-codes/fetch` route was performing a
  synchronous `requests.get()` call on the main thread, freezing all other requests for up to
  10 seconds. Rewritten to spawn a background daemon thread (`threading.Thread`) and return
  immediately. A `_nuke_fetch` global tracks running/status state across threads.
- **Nuke codes not updating after fetch** — nukacrypt.com JSON API returns a flat dict
  `{"ALPHA":"code","BRAVO":"code","CHARLIE":"code"}` but the parser only handled lists and
  nested dicts. Added direct flat-dict parsing via `data.get(key.upper())` as the primary
  parse path. Codes now save correctly on every successful fetch.
- **SQLite connection timeout** — added `timeout=10` to `sqlite3.connect()` in `db.py` to
  prevent indefinite hangs when the DB is locked during concurrent access.

### Changed
- **Nuke Codes page** — fetch button disabled and status banner shown while fetch is running;
  page auto-refreshes every 4 seconds until fetch completes. Success/failure banner displayed
  after each fetch attempt with color-coded result.

## [0.9.0] — 2026-04-19

### Added
- **Price History Charts** — Chart.js line graph per item on the Prices page.
  - 📈 button in the averages table opens a modal with a price-over-time line chart
  - Average price shown as a dashed reference line
  - New route `GET /prices/chart-data?item=NAME` returns JSON (labels, prices, avg)
  - Chart.js loaded via CDN on the Prices page only (not globally)
  - Graceful fallback: "Not enough data" message if fewer than 2 data points
- **Trading Partner Log** (`/trade-partners`) — track every trader you deal with.
  - Partner list: IGN, platform (PC/Xbox/PS), rating (Good/Neutral/Bad/Blocked), trade count, last trade date
  - Rating quick-buttons G/N/B/X inline on each partner card (AJAX, no reload)
  - Partner detail view: full trade history with that IGN
  - Quick-log trade form: date, what you gave, what you received, caps ± amount, notes
  - IGN search / filter
  - `trade_partners` and `trade_history` tables added via safe migration
  - Sidebar entry 🤝 Partners (under Trade Post)
- **Session Summary Widget** — "What happened today" panel auto-calculated on dashboard from today's data.
  - Caps delta today (from caps_sessions)
  - Weapons added today
  - Prices logged today
  - Challenges completed today
  - Play time today (formatted as Xh Ym)
  - No snapshot needed — all live from DB
- **Analytics Page** (`/analytics`) — charts from your existing data.
  - Caps balance over time (line chart)
  - Play time per week (bar chart)
  - Weapons found per week (bar chart)
  - Prices logged per week (bar chart)
  - Top vendor items by value (horizontal bar chart)
  - New route `GET /analytics/data` returns all chart data as JSON in one call
  - Chart.js loaded via CDN on analytics page only
  - Sidebar entry 📊 Analytics
- **Vendor Route Tracker** (`/vendor-route`) — server-hop vendor stop list.
  - Ordered list of vendor stops with name, location, notes
  - "Check" button per stop stamps `last_checked` with today's date (AJAX)
  - Color coded: ✅ green = checked today, 🟡 gold = this week, 🔴 red = older, ⬜ grey = never
  - "Reset All Checks" to clear today's marks
  - Add/delete stops
  - `vendor_route_stops` table added via safe migration
  - Sidebar entry 🗺 Vendor Route (near Server Hops)

- **Fishing Tracker** (`/fishing`) — full species checklist + catch log.
  - 48 pre-seeded species across 6 rarity tiers: Generic, Common (Sawgills), Uncommon, Glowing, Local Legends, Axolotls
  - Region/biome and weather requirements noted per species
  - Toggle caught/uncaught per species (AJAX, no reload) — tracks first caught date
  - Progress bar showing completion (X/48 caught)
  - Log individual catches with bait used, weather, location, notes
  - Logging a catch auto-marks the species as caught in the checklist
  - Stat cards: total caught, axolotls, local legends, glowing fish counts
  - Sidebar entry 🎣 Fishing
  - Data sourced from NukaKnights datamine + Fallout Wiki

### Changed
- **Dashboard** — new "Today's Summary" widget shows session recap above the Vault-Tec quote

---

## [0.8.0] — 2026-03-17

### Added
- **Price Research — Bulk CSV Import** — upload a `.csv` file (item_name, category,
  description, price_seen, source, date_seen, notes) to bulk-insert price records.
  Rows with no item name are skipped. Flash message reports imported vs skipped count.
- **Price Research — Edit & Copy** — inline edit via `?edit_id=N` pre-fills the
  collapsible form. Copy button duplicates any row for fast entry of same item at a
  different price or source.
- **Sticky table headers (prices)** — price table now has its own scroll zone
  (`max-height: 60vh`). Column headers freeze as you scroll through large datasets.
  Two-col ratio widened to 3:2 giving the main table more room.
- **Playtime Tracker** (`/playtime`) — manual start/stop session logging.
  - Live elapsed timer while session is running
  - Stats: today / this week / all-time totals
  - Full session history table with delete
  - Sidebar entry ⏱
- **Home network access** — `run.py` now binds to `0.0.0.0`. Startup console prints
  both `127.0.0.1` and the local network IP so other devices on the same WiFi can connect.
- **Vendor Scan** (`/vendor-scan`) — AI-powered vendor screenshot processor.
  - Upload PNG/JPG/WEBP screenshots of FO76 vendor shops
  - Claude Haiku API reads each image and extracts items (name, price, category,
    description, vendor name)
  - Results saved as `YYYY-MM-DD_HHMM_Vendor_Upload.csv` in `vendor_scans/`
  - Download link + preview table shown after processing
  - API key stored in settings table (never exported)
  - ~$0.003 per image (Haiku tier)
- **Wishlist** (`/wishlist`) — hunt list for items you're looking for.
  - Fields: item name, category, max price (0 = any), priority (High/Normal/Low),
    description, notes
  - Active list sorted by priority — High floats to top
  - Mark as Found moves item to found history
  - **Vendor Scan integration** — after every scan, results are checked against your
    active wishlist. Matches surface in a gold alert box showing item, vendor, price
    vs budget (green = under, red = over)
  - Sidebar entry ⭐
- **Backup page** (`/backup`) — central backup hub.
  - Download DB as date-stamped `.db` file
  - Download full `.zip` (DB + all vendor scan CSVs)
  - Lists saved vendor scan CSVs with individual download links
  - Restore instructions on page
  - Sidebar entry 💾
- **Auto-backup on startup** — every time the app launches, `fo76.db` is copied to
  `backups/` with a timestamp. Keeps the 7 most recent copies automatically. Old
  backups pruned silently. Visible and downloadable on the Backup page.
- **Login / Authentication** — session-based password protection.
  - Login page styled to match terminal theme ("ENTER VAULT")
  - Sessions last 30 days — log in once per browser
  - Default credentials: `admin` / `fo76tracker` (printed to console on first run)
  - Change username + password at `/change-password` (logs out on save)
  - 🔒 and ⏻ icons in header for account and logout
  - All routes protected except `/static` and `/login`
- **Caps Ledger** (`/caps`) — income and expense tracker for in-game caps.
  - Transaction types: Income / Expense
  - Income categories: Net Start, Vendor Sale, Player Trade, NPC Sale, Questing,
    Events, Daily Ops, Found/Looted, Other
  - Expense categories: Player Vendor, Buying from Player, NPC Vendor, Plans/Recipes,
    Ammo, Mods, Apparel, Fast Travel, Other
  - Stats: Net Balance, All Time In/Out, This Week Net, Today Net
  - Category dropdown switches automatically with type toggle
  - Full edit/delete. Exported via Export CSV page
  - Sidebar entry 💵 (between Prices and Plans)
- **Lunchbox burst animation** — completing a challenge triggers a particle burst
  from the complete button: 16 particles (⭐★💰✦☢✓+🎊) in random directions, a
  brief gold screen flash, and a row highlight pulse. Fires on ✓ toggle, repeatable
  done, and final +1 increment.

### Changed
- **Challenge default view = Incomplete** — page now defaults to showing only active,
  incomplete challenges. Clutter from completed rows eliminated. Filter tabs updated:
  Incomplete | All Active | Done | Daily | Weekly | Season | Static | Dormant
- **Completed challenges fade out** — after the lunchbox animation, completed rows
  slide and fade off screen (0.5s transition). Still visible under "Done" and
  "All Active" filter tabs.
- **Repeatable challenges go Dormant on reset** — Reset Dailies / Reset Weeklies now
  sends repeatable challenges to a Dormant state instead of just resetting progress.
  Dormant challenges disappear from the active list and reappear in the Dormant tab.
  Each has a ▶ Activate button to bring it back for the new day. Non-repeatables
  reset as before.
- **BAT file restart prompt** — after the server stops (Ctrl+C or crash), the console
  window asks "Restart? (Y/N)" before closing. Y restarts the server, N exits cleanly.
- **Export page** — added Power Armor, Mutations, and Season Score Log sections that
  were missing from `EXPORT_CONFIG` and the export icons dict.

### Security
- Session secret key in place (still hardcoded — move to `.env` before any public release)
- File upload type validation on vendor scan (PNG/JPG/WEBP only)
- Backup download uses `os.path.basename()` to prevent path traversal
- API key excluded from all route responses; stored only in settings table

---

## [0.7.0] — 2026-03-16

### Added
- **Power Armor section** (`/power-armor`) — dedicated tracker for PA pieces with set,
  slot, legendary stars, mods, condition %, weight, value, status. Full inventory sync.
  Quick K/$✗ status buttons. Filter by status tabs. Bulk action support. PA weight now
  included in dashboard stash weight widget.
- **Mutations tracker** (`/mutations`) — log active/inactive mutations with positive and
  negative effects. Link mutations to a build. One-click active/inactive toggle.
- **Character sheet** (`/character`) — name, level, active build link, full S.P.E.C.I.A.L.
  distribution (1–15 per stat). Right panel renders a character card with SPECIAL bars
  and active build details.
- **Bulk status changes** — Weapons, Armor, Power Armor, Mods, Inventory, and Plans pages
  now have a checkbox column + bulk action bar. Select any rows, pick a status or delete,
  apply in one click. Header checkbox selects all visible rows.
- **Season score per day log** — daily score log on the Season page. Log score earned each
  day with optional notes. Stats panel shows actual avg score/day vs projected estimate.

---

## [0.6.3] — 2026-03-16

### Added
- **Season ↔ Challenge tracker tie-in** — Season page now reads live from the challenges
  table (Daily + Weekly only, non-repeatable) and shows:
  - "From your challenge tracker" widget on the stats panel: daily set value, weekly set
    value, and all-time repeatable score earned (times_completed × score_reward)
  - "← use" links next to the Est. Score per Daily/Weekly inputs that auto-fill the field
    with the value calculated from your logged challenges — no manual guessing

### Fixed
- **Repeatable challenges crossing out** — template now only applies `completed-row`
  styling to non-repeatable challenges. JS toggle/increment both defensively remove the
  class on repeatable completion. Repeatables can no longer appear struck-through.

---

## [0.6.2] — 2026-03-16

### Changed
- **Season Tracker — improved projections**
  - Added **Repeatable Completions/Day** field: each completion adds 150 score to the
    effective daily score estimate (shown in breakdown as "X daily + Y repeatable")
  - Added **Bonus Score Already Earned** field: one-off score from double score weekends
    or events is subtracted from the gap before calculating dailies/weeklies needed
  - Score per daily/weekly fields relabeled as estimates (avg) to reflect real-world variance
  - Stats panel now shows a gap breakdown: raw gap → minus bonus → effective gap to close
  - Added how-to-find help text: Main Menu → Seasons tab in-game
  - Added note that score per rank is non-uniform; check in-game scoreboard for thresholds

### Fixed
- **Challenge countdowns** — daily and weekly reset timers now correctly target noon
  instead of midnight. Weekly label updated to "Tue Noon".

---

## [0.6.1] — 2026-03-15

### Added
- **Fallout 1st Container support** — inventory items can now be flagged as stored in a
  FO1st container (Scrapbox / Ammo Storage). Flagged items are excluded from the stash
  weight calculation on the dashboard. Toggle via checkbox in the add/edit form or the
  quick 📦 button on each row. DB column `fo1st_stored INTEGER DEFAULT 0` added via safe
  migration.
- **Apparel category** — added to all category dropdowns: Vendor, Inventory (form + filter
  tabs), Price Research, and both Quick Log sections (Price + Item). Behaves like Aid/Ammo
  (no specialized section sync).

### Fixed
- Dashboard crash when `stash_cap` setting has never been saved (no row in settings table).
  Fetchone now safely defaults to 1200 instead of raising `TypeError`.

---

## [0.6.0] — 2026-03-15

### Added
- **Repeatable Challenges** — challenges can now be flagged as Repeatable (new toggle in the
  add/edit form). When a repeatable challenge is marked complete (via toggle or +1 reaching
  target), it auto-resets progress to 0 and increments the all-time `times_completed` counter
  instead of locking the row as done. A ↺ indicator column shows which challenges are repeatable.
  DB column `repeatable INTEGER DEFAULT 0` added via safe migration.
- **Stash Weight Widget (Dashboard)** — new widget above the notices section shows total tracked
  stash weight (weapons + armor + other inventory) vs. your configured stash cap. Color-coded
  progress bar: green → gold at 70%, red at 90%. Breakdown by category shown beneath the bar.
- **Season Score Tracker** (`/season`) — new page to track your current season progress:
  - Input: season name, end date, current/target rank and score, score per daily/weekly, stash cap
  - Output: score gap, days/weeks left, dailies/weeklies needed to reach target rank
  - On-track vs. behind-pace indicator with week buffer count
  - Stash cap set here is shared with the dashboard stash weight widget
  - Season data stored in `settings` table (key/value)
  - Compact season widget on dashboard (rank progress bar + days left)
- **Season sidebar item** — 🏆 Season added to the sidebar between Notices and News.

### Changed
- **Dashboard** — stash weight widget and season widget now appear above notices, providing
  at-a-glance status for two of the most time-sensitive tracker areas.

---

## [0.5.5] — 2026-03-15

### Added
- **Challenge all-time tracking** — two new columns per challenge: "Done" (times completed
  across all resets) and "Missed" (times the reset fired while the challenge was still
  incomplete). Both persist through resets and accumulate indefinitely.
- **Challenge reset records missed** — reset now increments `missed_count` on any challenge
  that wasn't completed before resetting, giving a true picture of completion rate over time.
- **Inventory "In Vendor" column** — shows how many of each item are currently listed in
  your vendor, derived live from vendor_stock. Total qty (what you own) and vendor qty
  (what you're selling) are kept separate — no more double-counting.
- **Inventory filter tabs** — added Weapon, Armor, Mod filter tabs so synced items from those
  sections are filterable. Fixed "Food" tab → "Food/Drink" to match the category rename.

### Changed
- **Vendor ↔ Inventory model clarified** — for stackable items (Aid, Ammo, Misc, etc.),
  vendor and inventory are now fully independent trackers. Adding/removing a vendor listing
  no longer modifies inventory quantity. The inventory shows what you own; the vendor shows
  what you're selling — the "In Vendor" column bridges them visually.
- **Weapon/Armor/Mod vendor adds** still sync to their respective sections and inventory
  (unchanged from 0.5.4), since those are unique items.

---

## [0.5.4] — 2026-03-15

### Added
- **Cross-section inventory sync** — adding, editing, or deleting a Weapon/Armor/Mod now
  automatically creates, updates, or removes the matching Inventory entry. Each synced row
  stores `source_table` + `source_id` so updates are idempotent (no duplicates).
- **Quick Log → Inventory sync** — logging a Weapon or Armor via the Quick Log FAB also
  creates the corresponding Inventory mirror entry.
- **Vendor → specialized section sync** — adding a vendor listing with category Weapon, Armor,
  or Mod now also creates a record in the corresponding section table and links inventory via
  the section link. Other categories (Aid, Ammo, Plan, Misc, etc.) still use name+category
  deduplication in inventory.
- **Vendor delete → smart inventory revert** — deleting a Weapon/Armor/Mod vendor listing
  reverts the linked inventory entry status to Keep (rather than deleting). Other categories
  decrement qty and remove if it reaches zero.
- **Vendor form — conditional extra fields** — selecting Weapon shows Weapon Type + Stars +
  Weight fields; Armor shows Slot + Stars + Weight; Mod shows Mod Type + Applies To. Fields
  appear/disappear dynamically via JS and are hidden by default.
- **Draggable Quick Log FAB** — the `+` button can now be dragged anywhere on screen (mouse
  and touch). Position is saved to `localStorage` and restored on reload. A click without
  drag still opens Quick Log.
- **DB migration** — two new columns added to `inventory` via safe `ALTER TABLE`:
  `source_table TEXT DEFAULT ''` and `source_id INTEGER DEFAULT 0`.
- **`db.insert()` helper** — new function that returns `lastrowid` after an INSERT.

### Fixed
- **Sidebar scroll** — items below Inventory were unreachable on short screens. Changed
  `.app-sidebar` from `overflow: hidden` to `overflow-x: hidden; overflow-y: auto` with a
  thin 3px webkit scrollbar.
- **Quick Log tab scrollbar** — tab row now shows a thin 3px horizontal scrollbar
  (`scrollbar-width: thin`) so users can tell it is scrollable when tabs overflow.

---

## [0.5.3] — 2026-03-15

### Added
- **Vendor → Inventory auto-sync** — adding a vendor listing now automatically creates a matching
  inventory entry (same name, category, qty, price as value, status=Sell).
- **Vendor delete → Inventory update** — removing a vendor listing decrements the matching
  inventory item's qty by the vendor qty. If qty reaches 0 or below, the inventory entry is
  removed entirely (sold = gone).
- **Mod type field** — mods now have a Type dropdown: Normal, Legendary 1-Star, 2-Star, 3-Star.
  Legendary mods show a gold ★N badge in the table. DB column added via safe migration.
- **Food/Drink merged** into single category option across all dropdowns (Prices, Inventory,
  Quick Log price, Quick Log inventory).

---

## [0.5.2] — 2026-03-15

### Added
- **Challenge Score & Atoms reward tracking** — two new numeric fields (Score Reward, Atoms Reward)
  per challenge, in addition to the existing free-text "Other Reward" field. Values display in
  gold (score) and blue (atoms) in the table. Columns added to DB via safe `ALTER TABLE` migration.

### Changed
- **Theme picker moved to header bar** — four color dots now always visible in the top nav,
  no longer buried in the collapsed sidebar.
- **Sidebar defaults to open** — first-time visitors see labeled nav items immediately; collapsing
  saves the preference. Prior behavior required explicitly opening to see any labels.

---

## [0.5.1] — 2026-03-15

### Changed
- **Notices dashboard-only** — active notice banners removed from every page; notices now appear
  only as a widget on the Dashboard. The global `context_processor` was replaced with a direct
  query in the `index()` route.
- **Nuke Codes dashboard-only** — nuke code silo status widget added to Dashboard (shows current
  code + stale indicator per silo). Codes were never shown site-wide but are now surfaced on the
  main page without navigating to `/nuke-codes`.
- Removed notice count badge from sidebar (notices visible on dashboard instead).

---

## [0.5.0] — 2026-03-15

### Added
- **Sidebar navigation redesign** — collapsible icon-only sidebar replaces top nav bar
  - Collapses to 54px icon rail; expands to 196px with labels on click or `M` key
  - State persisted to `localStorage` — survives page reloads
  - Hover tooltips on collapsed state
  - Active page highlighted with accent left-border
  - Notices badge on sidebar item shows active notice count
- **4 color themes** — switchable via dot picker at bottom of sidebar
  - Vault Green (default), Brotherhood Blue, Nuka Red, Ghoul Teal
  - Applied immediately via `data-theme` attribute; persisted to `localStorage`
  - Flash-free: theme applied before first render via inline script
- **Notices / Reminders system** (`/notices`)
  - Post notices with priority levels: Info, Warning, Urgent
  - Optional expiry date — notices auto-hide after expiry
  - Urgent and Warning notices display as banners across every page
  - Active notice count shown as badge on sidebar
  - `notices` table in SQLite
- **Nuke Codes tracker** (`/nuke-codes`)
  - Three silos: Alpha, Bravo, Charlie — pre-seeded at startup
  - Large code display with glow effect, stale detection vs. current week
  - Notes field per silo (e.g. "verified by NukaCrypt")
  - Quick links to NukaCrypt and r/fo76 nuke code posts
  - `nuke_codes` table in SQLite
- **X (Twitter) quick links on News page** — @BethesdaSupport, @BethesdaStudios, @Fallout, r/fo76, FO76 Wiki

---

## [0.4.0] — 2026-03-15

### Added
- **RSS News Feed** (`/news`)
  - Pre-configured feeds: r/fo76 Hot, r/fo76 New, r/Fallout
  - Add any RSS or Atom feed URL (Reddit, gaming sites, etc.)
  - Enable/disable individual feeds without deleting them
  - 30-minute in-memory cache — no hammering servers while gaming
  - Parallel fetch with timeout so slow feeds don't block the page
  - Stale cache served automatically if a feed goes down
  - Force refresh button
  - News widget on Dashboard (served from cache only — never blocks)
  - `feeds` table in SQLite for user-managed feed list

---

## [0.3.0] — 2026-03-15

### Added
- **Quick Log** — floating `+` button (or press `Q`) accessible on every page
  - Logs to: Price Research, Weapon, Armor, Plan, Inventory, Challenge
  - AJAX submit — no page reload, toast notification confirms entry
  - "Keep Open" checkbox for rapid back-to-back logging (e.g. vendor hopping)
  - Press `Escape` to close
- **Challenges Tracker** (`/challenges`)
  - Four challenge types: Daily, Weekly, Season, Static
  - Live countdown timers to next Daily reset (midnight) and Weekly reset (Tuesday)
  - Reset Dailies / Reset Weeklies buttons with confirmation
  - Progress bar tracking for multi-step challenges (e.g. 47/100 kills)
  - AJAX +1 and ✓ Complete buttons — no page reload while gaming
  - Filter by type tabs (All / Daily / Weekly / Season / Static)
- **Export to CSV** (`/export`)
  - Individual download button per section
  - Download All — triggers all 10 exports in sequence
  - Sections: Perk Cards, Builds, Weapons, Armor, Mods, Vendor, Prices, Plans, Inventory, Challenges
- **Food / Drink** added to Price Research category dropdown
- **Toast notification system** — replaces flash messages for AJAX actions

---

## [0.2.0] — 2026-03-15

### Performance fixes
- **`init_db()` moved to startup** — was previously running a 9-table SQL script on
  every single request via `@app.before_request`. Now runs once at app start only.
- **Dashboard queries collapsed** — 14 separate DB round-trips replaced with a single
  SQL query using subselects. Significant reduction in dashboard load time.
- **SQLite performance pragmas added**
  - `PRAGMA journal_mode=WAL` — allows reads during writes, reduces blocking
  - `PRAGMA cache_size=-8000` — 8 MB in-memory cache, reduces disk hits
  - `PRAGMA synchronous=NORMAL` — faster writes, still crash-safe
  - `PRAGMA temp_store=MEMORY` — temp tables stay in RAM
- **Google Fonts removed** — Share Tech Mono font now served locally from
  `static/fonts/ShareTechMono.ttf`. Eliminates network dependency on every page load.

---

## [0.1.0] — 2026-03-15

### Initial build
- Flask 3.0 + SQLite backend (`fo76.db` on E: drive)
- Fallout terminal theme (dark green, amber accents, monospace font)
- Global search bar across all sections
- Client-side table filtering on every page (no reload)
- Collapsible add/edit forms — edit reuses add form via `?edit_id=N`
- Auto-fills today's date on date fields
- Keyboard shortcut: `Q` opens Quick Log

### Sections
| Section | Key features |
|---|---|
| Perk Cards | SPECIAL dropdown, scrap flag, used-in-builds field. Scrappable rows highlight red. |
| Builds | SPECIAL point planner with live total counter. Turns red if over 56 pts. |
| Weapons | One-click K/$✗ status buttons. Filter by status tab. Legendary star fields. |
| Armor | Same as weapons. DR/ER/RR columns. Slot selector. |
| Mods | Qty × value auto-totalled. |
| My Vendor | vs-market % calculated live as you type. |
| Price Research | Log prices → auto-calculates min/avg/max/suggested (10% below avg) per item. |
| Plans & Recipes | Learned checkbox, dupe counter, dupes flagged on dashboard. |
| Inventory | Category filter tabs, running total weight + value in table footer. |
| Dashboard | At-a-glance counts, action alerts, recent prices, price averages. |

---

## Planned / Backlog (Parking Lot)

- [ ] Image gallery — per-item screenshots (weapons/armor/builds). Parked to avoid scope creep.
- [ ] Weapon/Armor/Plans screenshot scanning — extend Vendor Scan AI to other sections
- [ ] Mobile responsive layout — revisit if project goes public on GitHub
- [x] Reference data / smart dropdowns — all major forms now have autocomplete datalists (v0.10.0)

### Completed
- [x] Nuke codes auto-fetch — background fetch from nukacrypt.com API (v0.10.0)
- [x] Error pages — custom 404/500 templates (v0.8.0 or earlier)
- [x] World Finds tracker with multi-screenshot support (v0.10.0)

### Removed features (no longer in app)
- Session Journal — removed v0.12.0 (replaced by World Finds + character tracking)
- Spawn Notes — removed v0.12.0 (not used)
- Trade Partners / Trade History — removed v0.11.0 (low usage, clutter)
- Notices system — removed v0.11.0 (never used)
- Server Hops tracker — removed v0.11.0 (not needed)
- Vendor Route tracker — removed v0.11.0 (not needed)
- Playtime Tracker — removed v0.11.0 (not needed)

## Dumb Idea Lot

- [ ] Keybinds for challenges (e.g. Shift+2 = complete Daily 2) — too many edge cases

---

## Project info

- **Location:** `E:\Projects\fo76-tracker\`
- **Stack:** Python 3.13, Flask 3.0, SQLite
- **Launch:** `run.bat` on Desktop or `python run.py` in project folder
- **Database:** `E:\Projects\fo76-tracker\fo76.db`
