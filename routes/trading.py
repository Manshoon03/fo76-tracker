"""Trading blueprint: vendor stock, price research, caps ledger, economy,
plans, plan checklist, wishlist, atom shop, vendor advisor, trade post."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, make_response
from datetime import datetime, timedelta, date
import json
import re
import db
from routes.helpers import fs, fi, ff, get_active_char_id, _inv_sync, _inv_delete, _get_anthropic

bp = Blueprint('trading', __name__)


ECONOMY_CURRENCIES = {
    'caps':      {'label': 'Caps',            'icon': '💵', 'daily_limit': 1400, 'max_balance': 40000,  'color': 'var(--accent)', 'quick': [100, 500, 1400]},
    'scrip':     {'label': 'Legendary Scrip', 'icon': '⭐', 'daily_limit': 300,  'max_balance': 11000,  'color': 'var(--amber)',  'quick': [50, 100, 150]},
    'bullion':   {'label': 'Gold Bullion',    'icon': '💰', 'daily_limit': 400,  'max_balance': 10000,  'color': 'var(--gold)',   'quick': [40, 200, 400]},
    'stamps':    {'label': 'Stamps',          'icon': '📮', 'daily_limit': None, 'max_balance': None,   'color': 'var(--blue)',   'quick': [8, 20, 40]},
    'modules':   {'label': 'Leg. Modules',    'icon': '🔩', 'daily_limit': None, 'max_balance': None,   'color': 'var(--purple)', 'quick': [1, 5, 10]},
    'perkcoins': {'label': 'Perk Coins',      'icon': '🎴', 'daily_limit': None, 'max_balance': 150000, 'color': 'var(--accent)', 'quick': [1, 5, 10]},
    'tadpole':   {'label': 'Tadpole Badges',  'icon': '🐸', 'daily_limit': None, 'max_balance': 100,    'color': 'var(--blue)',   'quick': [1, 2, 3]},
    'possum':    {'label': 'Possum Badges',   'icon': '🦝', 'daily_limit': None, 'max_balance': 100,    'color': 'var(--amber)',  'quick': [1, 2, 3]},
}


# ── Vendor Stock ─────────────────────────────────────────────────────────────

@bp.route('/vendor')
def vendor():
    cid = get_active_char_id()
    items = db.query("SELECT * FROM vendor_stock WHERE character_id=? ORDER BY category, name", (cid,))
    edit_id = request.args.get('edit_id', type=int)
    edit_item = db.get_one("SELECT * FROM vendor_stock WHERE id=?", (edit_id,)) if edit_id else None
    total_items = sum(r['qty'] for r in items)
    total_value = sum(r['my_price'] * r['qty'] for r in items)
    return render_template('vendor.html', items=items, edit_item=edit_item,
                           total_items=total_items, total_value=total_value)

@bp.route('/vendor/add', methods=['POST'])
def vendor_add():
    cid = get_active_char_id()
    name = fs('name')
    category = fs('category')
    vid = db.insert(
        "INSERT INTO vendor_stock (name,category,description,qty,my_price,avg_market_price,date_listed,notes,character_id) VALUES (?,?,?,?,?,?,date('now'),?,?)",
        (name, category, fs('description'), fi('qty',1), fi('my_price'), fi('avg_market_price'), fs('notes'), cid)
    )
    if category == 'Weapon':
        wid = db.insert(
            "INSERT INTO weapons (name,wtype,star1,star2,star3,weight,value,status,notes,character_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (name, '', '', '', '', 0, fi('my_price'), 'Sell', '', cid)
        )
        _inv_sync('weapons', wid, name, 'Weapon', '', 1, 0, fi('my_price'), 'Sell')
        db.execute("UPDATE vendor_stock SET linked_table='weapons', linked_id=? WHERE id=?", (wid, vid))
    elif category == 'Armor':
        aid = db.insert(
            "INSERT INTO armor (name,slot,star1,star2,star3,weight,status,notes,character_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (name, '', '', '', '', 0, 'Sell', '', cid)
        )
        _inv_sync('armor', aid, name, 'Armor', '', 1, 0, 0, 'Sell')
        db.execute("UPDATE vendor_stock SET linked_table='armor', linked_id=? WHERE id=?", (aid, vid))
    elif category == 'Mod':
        mid = db.insert(
            "INSERT INTO mods (name,mod_type,applies_to,qty,value_each,status,notes,character_id) VALUES (?,?,?,?,?,?,?,?)",
            (name, 'Normal', '', fi('qty',1), fi('my_price'), 'Sell', '', cid)
        )
        _inv_sync('mods', mid, name, 'Mod', '', fi('qty',1), 0, fi('my_price'), 'Sell')
        db.execute("UPDATE vendor_stock SET linked_table='mods', linked_id=? WHERE id=?", (mid, vid))
    flash('Item added to vendor!', 'success')
    return redirect(url_for('trading.vendor'))

@bp.route('/vendor/<int:id>/update', methods=['POST'])
def vendor_update(id):
    db.execute(
        "UPDATE vendor_stock SET name=?,category=?,description=?,qty=?,my_price=?,avg_market_price=?,notes=? WHERE id=?",
        (fs('name'), fs('category'), fs('description'), fi('qty',1), fi('my_price'), fi('avg_market_price'), fs('notes'), id)
    )
    flash('Updated!', 'success')
    return redirect(url_for('trading.vendor'))

@bp.route('/vendor/<int:id>/sold', methods=['POST'])
def vendor_sold(id):
    db.execute("UPDATE vendor_stock SET qty=MAX(0,qty-1) WHERE id=?", (id,))
    row = db.get_one("SELECT qty FROM vendor_stock WHERE id=?", (id,))
    flash(f'Sold 1 — {row["qty"]} left' if row else 'Sold!', 'success')
    return redirect(url_for('trading.vendor'))

@bp.route('/vendor/<int:id>/relist', methods=['POST'])
def vendor_relist(id):
    db.execute(
        "UPDATE vendor_stock SET my_price=?, date_listed=date('now'), notes=COALESCE(notes,'') || ' — Relisted' WHERE id=?",
        (fi('new_price'), id)
    )
    flash('Relisted!', 'success')
    return redirect(url_for('trading.vendor'))

@bp.route('/vendor/<int:id>/delete', methods=['POST'])
def vendor_delete(id):
    db.execute("DELETE FROM vendor_stock WHERE id=?", (id,))
    flash('Removed from vendor.', 'info')
    return redirect(url_for('trading.vendor'))

@bp.route('/vendor/<int:id>/quick-update', methods=['POST'])
def vendor_quick_update(id):
    data = request.get_json(force=True)
    field = data.get('field')
    value = data.get('value')
    if field == 'qty':
        value = max(1, int(value))
        db.execute("UPDATE vendor_stock SET qty=? WHERE id=?", (value, id))
    elif field == 'my_price':
        value = max(0, int(value))
        db.execute("UPDATE vendor_stock SET my_price=? WHERE id=?", (value, id))
        return jsonify(ok=True, value=f"{value:,}")
    else:
        return jsonify(ok=False), 400
    return jsonify(ok=True, value=value)

@bp.route('/vendor/bulk-reprice', methods=['POST'])
def vendor_bulk_reprice():
    data = request.get_json()
    updates = data.get('updates', [])
    count = 0
    for u in updates:
        db.execute("UPDATE vendor_stock SET my_price=? WHERE id=?", (u['price'], u['id']))
        count += 1
    return jsonify(ok=True, count=count)

@bp.route('/vendor/print')
def vendor_print():
    cid = get_active_char_id()
    items = db.query("SELECT * FROM vendor_stock WHERE character_id=? ORDER BY category, name", (cid,))
    total_items = sum(r['qty'] for r in items)
    total_value = sum(r['my_price'] * r['qty'] for r in items)
    # Group by category
    categories = {}
    for item in items:
        cat = item['category'] or 'Uncategorized'
        categories.setdefault(cat, []).append(item)
    return render_template('vendor_print.html', items=items, categories=categories,
                           total_items=total_items, total_value=total_value)

@bp.route('/vendor/scan', methods=['POST'])
def vendor_scan_import_route():
    from routes.helpers import _scan_image, _extract_json_array
    api_key = db.get_setting('anthropic_api_key', '')
    if not api_key:
        return jsonify(error='No API key set. Go to Vendor Scan → Settings to add your Anthropic key.'), 400
    f = request.files.get('scan_image')
    if not f or not f.filename:
        return jsonify(error='No image uploaded.'), 400
    import os
    MIME = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}
    ext  = os.path.splitext(f.filename)[1].lower()
    media_type = MIME.get(ext, 'image/png')
    _VENDOR_SCAN_PROMPT = """This is a screenshot from Fallout 76 showing a player vendor machine or vendor inventory.

Extract every visible listing and return a JSON array. Each element must have these fields:
{
  "name": "<exact item name>",
  "category": "<one of: Weapon, Armor, Apparel, Mod, Power Armor, Plan, Aid, Ammo, Misc>",
  "qty": <integer quantity listed, default 1>,
  "my_price": <integer cap price shown>,
  "description": "<legendary stars or notes visible — empty string if none>"
}

Rules:
- Extract every item row you can see.
- For prices: use the number shown (no commas). If unclear, use 0.
- For weapons with legendary stars: put the star effects in description (e.g. "Bloodied / FFR / 25ffr").
- Return ONLY a valid JSON array with no explanation.
- If no items visible, return [].
"""
    try:
        raw   = _scan_image(f.read(), media_type, api_key, prompt=_VENDOR_SCAN_PROMPT)
        items = _extract_json_array(raw)
        if items is None:
            return jsonify(error='Could not parse items from image. Try a cleaner screenshot.'), 400
        clean = []
        for item in items:
            if not isinstance(item, dict):
                continue
            clean.append({
                'name':        str(item.get('name', '')).strip(),
                'category':    str(item.get('category', 'Misc')).strip(),
                'qty':         max(1, int(item.get('qty') or 1)),
                'my_price':    max(0, int(item.get('my_price') or 0)),
                'description': str(item.get('description', '')).strip(),
            })
        return jsonify(items=clean)
    except Exception as e:
        return jsonify(error=f'Scan failed: {e}'), 500

@bp.route('/vendor/scan/import', methods=['POST'])
def vendor_scan_import():
    data  = request.get_json(force=True)
    items = data.get('items', [])
    cid   = get_active_char_id()
    added = 0
    updated = 0
    for item in items:
        name = (item.get('name') or '').strip()
        if not name:
            continue
        category = item.get('category', 'Misc')
        qty = max(1, int(item.get('qty') or 1))
        my_price = max(0, int(item.get('my_price') or 0))
        description = item.get('description', '')
        existing = db.get_one(
            "SELECT id FROM vendor_stock WHERE name=? COLLATE NOCASE AND category=? AND character_id=?",
            (name, category, cid))
        if existing:
            db.execute("UPDATE vendor_stock SET qty=?, my_price=? WHERE id=?",
                       (qty, my_price, existing['id']))
            updated += 1
        else:
            vid = db.insert(
                "INSERT INTO vendor_stock (name,category,description,qty,my_price,avg_market_price,date_listed,notes,character_id) "
                "VALUES (?,?,?,?,?,0,date('now'),'',?)",
                (name, category, description, qty, my_price, cid)
            )
            if category == 'Weapon':
                wid = db.insert(
                    "INSERT INTO weapons (name,wtype,star1,star2,star3,weight,value,status,notes,character_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (name, '', '', '', '', 0, my_price, 'Sell', '', cid)
                )
                _inv_sync('weapons', wid, name, 'Weapon', '', qty, 0, my_price, 'Sell')
                db.execute("UPDATE vendor_stock SET linked_table='weapons', linked_id=? WHERE id=?", (wid, vid))
            elif category == 'Armor':
                aid = db.insert(
                    "INSERT INTO armor (name,slot,star1,star2,star3,weight,status,notes,character_id) VALUES (?,?,?,?,?,?,?,?,?)",
                    (name, '', '', '', '', 0, 'Sell', '', cid)
                )
                _inv_sync('armor', aid, name, 'Armor', '', qty, 0, 0, 'Sell')
                db.execute("UPDATE vendor_stock SET linked_table='armor', linked_id=? WHERE id=?", (aid, vid))
            elif category == 'Mod':
                mid = db.insert(
                    "INSERT INTO mods (name,mod_type,applies_to,qty,value_each,status,notes,character_id) VALUES (?,?,?,?,?,?,?,?)",
                    (name, 'Normal', '', qty, my_price, 'Sell', '', cid)
                )
                _inv_sync('mods', mid, name, 'Mod', '', qty, 0, my_price, 'Sell')
                db.execute("UPDATE vendor_stock SET linked_table='mods', linked_id=? WHERE id=?", (mid, vid))
            added += 1
    return jsonify(ok=True, added=added, updated=updated)


# ── Price Research ───────────────────────────────────────────────────────────

@bp.route('/prices')
def prices():
    edit_id = request.args.get('edit_id', type=int)
    page    = max(1, request.args.get('page', 1, type=int))
    PER_PAGE = 100
    total = db.get_one("SELECT COUNT(*) as c FROM price_research")['c']
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = min(page, total_pages)
    offset = (page - 1) * PER_PAGE
    items = db.query("SELECT * FROM price_research ORDER BY created_at DESC LIMIT ? OFFSET ?", (PER_PAGE, offset))
    edit_item = db.get_one("SELECT * FROM price_research WHERE id=?", (edit_id,)) if edit_id else None
    return render_template('prices.html', items=items, edit_item=edit_item,
                           page=page, total_pages=total_pages, total_count=total)

@bp.route('/prices/add', methods=['POST'])
def prices_add():
    db.execute(
        "INSERT INTO price_research (item_name,category,source,price_seen,notes,created_at) VALUES (?,?,?,?,?,datetime('now'))",
        (fs('item_name'), fs('category'), fs('source'), fi('price_seen'), fs('notes'))
    )
    # Check price alerts
    item_name = fs('item_name')
    price = fi('price_seen')
    alerts = db.query("SELECT * FROM price_alerts WHERE active=1 AND item_name=? AND ?<=target_price", (item_name, price))
    if alerts:
        from routes.helpers import discord_notify
        for a in alerts:
            discord_notify(None, embed={
                'title': f'\U0001f514 Price Alert Hit: {item_name}',
                'description': f'Seen at **{price:,}** caps (alert target: \u2264{a["target_price"]:,})',
                'color': 0xFFD700
            })
    flash('Price recorded!', 'success')
    return redirect(url_for('trading.prices'))

@bp.route('/prices/<int:id>/update', methods=['POST'])
def prices_update(id):
    db.execute(
        "UPDATE price_research SET item_name=?,category=?,source=?,price_seen=?,notes=? WHERE id=?",
        (fs('item_name'), fs('category'), fs('source'), fi('price_seen'), fs('notes'), id)
    )
    flash('Updated!', 'success')
    return redirect(url_for('trading.prices'))

@bp.route('/prices/quick-add', methods=['POST'])
def prices_quick_add():
    db.execute(
        "INSERT INTO price_research (item_name,category,source,price_seen,notes,created_at) VALUES (?,?,?,?,?,datetime('now'))",
        (fs('item_name'), 'Weapon', fs('source','Player Vendor'), fi('price_seen'), '')
    )
    flash('Quick price added!', 'success')
    new_id = db.get_one("SELECT MAX(id) as id FROM price_research")['id']
    return redirect(url_for('trading.prices', edit_id=new_id))

@bp.route('/prices/<int:id>/delete', methods=['POST'])
def prices_delete(id):
    db.execute("DELETE FROM price_research WHERE id=?", (id,))
    flash('Deleted.', 'info')
    return redirect(url_for('trading.prices'))

@bp.route('/prices/import', methods=['POST'])
def prices_import():
    import csv, io
    f = request.files.get('csv_file')
    if not f:
        flash('No file selected.', 'error')
        return redirect(url_for('trading.prices'))
    text = f.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text))
    count = 0
    for row in reader:
        name = (row.get('item_name') or '').strip()
        if not name:
            continue
        try:
            price = int(float(row.get('price_seen') or 0))
        except (ValueError, TypeError):
            price = 0
        db.execute(
            "INSERT INTO price_research (item_name,category,source,price_seen,notes,created_at) VALUES (?,?,?,?,?,datetime('now'))",
            (name, row.get('category',''), row.get('source',''), price, row.get('notes',''))
        )
        count += 1
    flash(f'Imported {count} records.', 'success')
    return redirect(url_for('trading.prices'))

@bp.route('/prices/alert-check')
def prices_alert_check():
    alerts = db.query("""
        SELECT p.item_name, p.price_seen, p.source, p.notes, p.created_at
        FROM price_research p
        WHERE p.price_seen <= (
            SELECT COALESCE(AVG(p2.price_seen) * 0.5, 0)
            FROM price_research p2
            WHERE LOWER(p2.item_name) = LOWER(p.item_name)
        )
        ORDER BY p.created_at DESC LIMIT 20
    """)
    return jsonify(alerts=[dict(r) for r in alerts])

@bp.route('/prices/history/<name>')
def prices_history(name):
    rows = db.query(
        "SELECT price_seen, source, created_at FROM price_research WHERE item_name=? COLLATE NOCASE ORDER BY created_at",
        (name,)
    )
    return jsonify(history=[dict(r) for r in rows])


# ── Recipes ───────────────────────────────────────────────────────────────────

@bp.route('/recipes')
def recipes():
    cid = get_active_char_id()
    cat_filter = request.args.get('cat', '')
    edit_id = request.args.get('edit_id', type=int)
    if cat_filter:
        items = db.query("SELECT * FROM recipes WHERE character_id=? AND category=? ORDER BY favourite DESC, name", (cid, cat_filter))
    else:
        items = db.query("SELECT * FROM recipes WHERE character_id=? ORDER BY favourite DESC, category, name", (cid,))
    edit_item = db.get_one("SELECT * FROM recipes WHERE id=?", (edit_id,)) if edit_id else None
    cats = [r['category'] for r in db.query("SELECT DISTINCT category FROM recipes WHERE character_id=? AND category!='' ORDER BY category", (cid,))]
    return render_template('recipes.html', items=items, edit_item=edit_item, cat_filter=cat_filter, categories=cats)

@bp.route('/recipes/add', methods=['POST'])
def recipes_add():
    db.execute(
        "INSERT INTO recipes (name,category,ingredients,learned,favourite,notes,character_id) VALUES (?,?,?,?,?,?,?)",
        (fs('name'), fs('category'), fs('ingredients'),
         1 if request.form.get('learned') else 0,
         1 if request.form.get('favourite') else 0,
         fs('notes'), get_active_char_id())
    )
    flash('Recipe added!', 'success')
    return redirect(url_for('trading.recipes'))

@bp.route('/recipes/<int:id>/update', methods=['POST'])
def recipes_update(id):
    db.execute(
        "UPDATE recipes SET name=?,category=?,ingredients=?,learned=?,favourite=?,notes=? WHERE id=?",
        (fs('name'), fs('category'), fs('ingredients'),
         1 if request.form.get('learned') else 0,
         1 if request.form.get('favourite') else 0,
         fs('notes'), id)
    )
    flash('Recipe updated!', 'success')
    return redirect(url_for('trading.recipes'))

@bp.route('/recipes/<int:id>/delete', methods=['POST'])
def recipes_delete(id):
    db.execute("DELETE FROM recipes WHERE id=?", (id,))
    flash('Recipe removed.', 'info')
    return redirect(url_for('trading.recipes'))

# ── Plans ────────────────────────────────────────────────────────────────────

@bp.route('/plans')
def plans():
    cid = get_active_char_id()
    items = db.query("SELECT * FROM plans WHERE character_id=? ORDER BY category, name", (cid,))
    edit_id = request.args.get('edit_id', type=int)
    edit_item = db.get_one("SELECT * FROM plans WHERE id=?", (edit_id,)) if edit_id else None
    return render_template('plans.html', items=items, edit_item=edit_item)

@bp.route('/plans/add', methods=['POST'])
def plans_add():
    db.execute(
        "INSERT INTO plans (name,category,unlocks,learned,qty_unlearned,sell_price,status,notes,character_id) VALUES (?,?,?,?,?,?,?,?,?)",
        (fs('name'), fs('category'), fs('unlocks'), 1 if request.form.get('learned') else 0,
         fi('qty_unlearned'), fi('sell_price'), fs('status','Keep'), fs('notes'), get_active_char_id())
    )
    flash('Plan added!', 'success')
    return redirect(url_for('trading.plans'))

@bp.route('/plans/<int:id>/update', methods=['POST'])
def plans_update(id):
    db.execute(
        "UPDATE plans SET name=?,category=?,unlocks=?,learned=?,qty_unlearned=?,sell_price=?,status=?,notes=? WHERE id=?",
        (fs('name'), fs('category'), fs('unlocks'), 1 if request.form.get('learned') else 0,
         fi('qty_unlearned'), fi('sell_price'), fs('status','Keep'), fs('notes'), id)
    )
    flash('Plan updated!', 'success')
    return redirect(url_for('trading.plans'))

@bp.route('/plans/<int:id>/delete', methods=['POST'])
def plans_delete(id):
    db.execute("DELETE FROM plans WHERE id=?", (id,))
    flash('Deleted.', 'info')
    return redirect(url_for('trading.plans'))

@bp.route('/plans/bulk', methods=['POST'])
def plans_bulk():
    ids = request.form.getlist('ids')
    action = fs('bulk_action')
    if ids and action == 'delete':
        for i in ids:
            db.execute("DELETE FROM plans WHERE id=?", (int(i),))
    elif ids and action == 'learned':
        for i in ids:
            db.execute("UPDATE plans SET learned=1 WHERE id=?", (int(i),))
    flash(f'Updated {len(ids)} plans.', 'success')
    return redirect(url_for('trading.plans'))

@bp.route('/plans/import-research', methods=['POST'])
def plans_import_research():
    data  = request.get_json()
    plans_data = data.get('plans', [])
    added = 0
    for p in plans_data:
        name = (p.get('name') or '').strip()
        if not name:
            continue
        existing = db.get_one("SELECT id FROM plans WHERE LOWER(name)=LOWER(?)", (name,))
        if existing:
            continue
        db.execute(
            "INSERT INTO plans (name, category, unlocks, learned, qty_unlearned, sell_price, status, notes) VALUES (?,?,?,1,0,?,'Sell','')",
            (name, 'Plan', '', int(p.get('avg_price') or 0))
        )
        added += 1
    return jsonify({'success': True, 'added': added})


# ── Plan Checklist ───────────────────────────────────────────────────────────

@bp.route('/plan-checklist')
def plan_checklist():
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    cid = get_active_char_id()
    rows = db.query("""
        SELECT pc.id, pc.name, pc.category, pc.subcategory, pc.source,
               COALESCE(pl.learned, 0) AS learned,
               COALESCE(pl.qty_dupes, 0) AS qty_dupes
        FROM plan_catalog pc
        LEFT JOIN plan_learned pl
               ON pl.catalog_id = pc.id AND pl.character_id = :cid
        ORDER BY pc.category, pc.name
    """, {'cid': cid})
    from collections import defaultdict
    cats = defaultdict(lambda: {'plans': [], 'total': 0, 'learned': 0})
    for r in rows:
        d = dict(r)
        cat = d['category'] or 'Misc'
        cats[cat]['plans'].append(d)
        cats[cat]['total'] += 1
        cats[cat]['learned'] += 1 if d['learned'] else 0
    cat_order = ['Weapon', 'Melee', 'Armor', 'Power Armor', 'Power Armor Mod',
                 'Weapon Mod', 'Armor Mod', 'CAMP',
                 'Food', 'Drink', 'Chem', 'Serum', 'Alcohol', 'Ammo', 'Misc']
    categories = []
    for c in cat_order:
        if c in cats:
            info = cats[c]
            info['name'] = c
            info['pct'] = round(info['learned'] / info['total'] * 100) if info['total'] else 0
            categories.append(info)
    for c, info in cats.items():
        if c not in cat_order:
            info['name'] = c
            info['pct'] = round(info['learned'] / info['total'] * 100) if info['total'] else 0
            categories.append(info)
    total_plans   = sum(c['total']   for c in categories)
    total_learned = sum(c['learned'] for c in categories)
    overall_pct   = round(total_learned / total_plans * 100) if total_plans else 0
    return render_template('plan_checklist.html',
                           categories=categories,
                           total_plans=total_plans,
                           total_learned=total_learned,
                           overall_pct=overall_pct)

@bp.route('/plan-checklist/toggle', methods=['POST'])
def plan_checklist_toggle():
    if not session.get('logged_in'):
        return ('', 403)
    cid        = get_active_char_id()
    catalog_id = fi('catalog_id')
    learned    = fi('learned')
    db.execute("""
        INSERT INTO plan_learned (catalog_id, character_id, learned)
        VALUES (?, ?, ?)
        ON CONFLICT(catalog_id, character_id)
        DO UPDATE SET learned=excluded.learned
    """, (catalog_id, cid, learned))
    return ('', 204)

@bp.route('/plan-checklist/add', methods=['POST'])
def plan_checklist_add():
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    name     = fs('name')
    category = fs('category', 'Misc')
    source   = fs('source', '')
    if name:
        db.execute(
            "INSERT OR IGNORE INTO plan_catalog (name, category, source) VALUES (?,?,?)",
            (name, category, source)
        )
        flash(f'Plan "{name}" added to catalog.', 'success')
    return redirect(url_for('trading.plan_checklist'))


# ── Caps Ledger ──────────────────────────────────────────────────────────────

@bp.route('/caps')
def caps():
    cid       = get_active_char_id()
    edit_id   = request.args.get('edit_id', type=int)
    edit_item = db.get_one("SELECT * FROM caps_sessions WHERE id=?", (edit_id,)) if edit_id else None
    sessions  = db.query("SELECT *, (end_caps - start_caps) AS net FROM caps_sessions WHERE character_id=? ORDER BY session_date DESC, id DESC", (cid,))
    today      = datetime.now().strftime('%Y-%m-%d')
    week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime('%Y-%m-%d')
    def _net(since=None):
        if since:
            row = db.get_one("SELECT COALESCE(SUM(end_caps - start_caps),0) AS t FROM caps_sessions WHERE character_id=? AND session_date>=?", (cid, since))
        else:
            row = db.get_one("SELECT COALESCE(SUM(end_caps - start_caps),0) AS t FROM caps_sessions WHERE character_id=?", (cid,))
        return int(row['t']) if row else 0
    last = db.get_one("SELECT end_caps FROM caps_sessions WHERE character_id=? ORDER BY session_date DESC, id DESC LIMIT 1", (cid,))
    stats = {
        'current_caps': last['end_caps'] if last else None,
        'today_net':    _net(today),
        'week_net':     _net(week_start),
        'alltime_net':  _net(),
    }
    goal_name   = db.get_setting('caps_goal_name', '')
    goal_amount = int(db.get_setting('caps_goal_amount', 0) or 0)
    current     = stats['current_caps'] or 0
    goal_pct    = min(100, round(current / goal_amount * 100)) if goal_amount else 0
    return render_template('caps_ledger.html', sessions=sessions, edit_item=edit_item,
                           stats=stats, today=today,
                           goal_name=goal_name, goal_amount=goal_amount,
                           goal_pct=goal_pct)

@bp.route('/caps/add', methods=['POST'])
def caps_add():
    try:
        start = int(float(request.form.get('start_caps', 0) or 0))
        end   = int(float(request.form.get('end_caps',   0) or 0))
    except (ValueError, TypeError):
        start = end = 0
    db.execute(
        "INSERT INTO caps_sessions (session_date, start_caps, end_caps, note, character_id) VALUES (?,?,?,?,?)",
        (request.form.get('session_date') or datetime.now().strftime('%Y-%m-%d'),
         start, end,
         (request.form.get('note') or '').strip(),
         get_active_char_id())
    )
    flash('Session logged.', 'success')
    return redirect(url_for('trading.caps'))

@bp.route('/caps/<int:tid>/update', methods=['POST'])
def caps_update(tid):
    try:
        start = int(float(request.form.get('start_caps', 0) or 0))
        end   = int(float(request.form.get('end_caps',   0) or 0))
    except (ValueError, TypeError):
        start = end = 0
    db.execute(
        "UPDATE caps_sessions SET session_date=?, start_caps=?, end_caps=?, note=? WHERE id=?",
        (request.form.get('session_date') or datetime.now().strftime('%Y-%m-%d'),
         start, end,
         (request.form.get('note') or '').strip(),
         tid)
    )
    flash('Session updated.', 'success')
    return redirect(url_for('trading.caps'))

@bp.route('/caps/<int:tid>/delete', methods=['POST'])
def caps_delete(tid):
    db.execute("DELETE FROM caps_sessions WHERE id=?", (tid,))
    flash('Deleted.', 'success')
    return redirect(url_for('trading.caps'))

@bp.route('/caps/goal', methods=['POST'])
def caps_goal_set():
    name   = (request.form.get('goal_name') or '').strip()
    amount = request.form.get('goal_amount', '0') or '0'
    try:
        amount = int(float(amount))
    except (ValueError, TypeError):
        amount = 0
    db.set_setting('caps_goal_name',   name)
    db.set_setting('caps_goal_amount', str(amount))
    flash('Caps goal saved!', 'success')
    return redirect(url_for('trading.caps'))


# ── Economy ──────────────────────────────────────────────────────────────────

@bp.route('/economy')
def economy():
    cid = get_active_char_id()
    today = str(date.today())
    balances = {}
    for key in ECONOMY_CURRENCIES:
        row = db.get_one("SELECT balance FROM economy_balance WHERE currency=? AND character_id=?", (key, cid))
        balances[key] = row['balance'] if row else 0
    daily_earned = {}
    for key in ECONOMY_CURRENCIES:
        row = db.get_one("SELECT COALESCE(SUM(amount),0) as total FROM economy_log WHERE currency=? AND character_id=? AND txn_date=? AND amount>0", (key, cid, today))
        daily_earned[key] = row['total']
    log = db.query("SELECT * FROM economy_log WHERE character_id=? ORDER BY created_at DESC LIMIT 50", (cid,))
    return render_template('economy.html', currencies=ECONOMY_CURRENCIES, balances=balances,
                           daily_earned=daily_earned, log=log)

@bp.route('/economy/log', methods=['POST'])
def economy_log():
    cid = get_active_char_id()
    currency = fs('currency')
    amount = fi('amount', 0)
    note = fs('note')
    if currency not in ECONOMY_CURRENCIES or amount == 0:
        return jsonify(ok=False, error='Invalid currency or amount'), 400
    db.execute("INSERT INTO economy_log (currency, amount, note, character_id) VALUES (?,?,?,?)",
               (currency, amount, note, cid))
    existing = db.get_one("SELECT id, balance FROM economy_balance WHERE currency=? AND character_id=?", (currency, cid))
    if existing:
        db.execute("UPDATE economy_balance SET balance=?, updated_at=datetime('now') WHERE id=?",
                   (existing['balance'] + amount, existing['id']))
    else:
        db.execute("INSERT INTO economy_balance (currency, balance, character_id) VALUES (?,?,?)",
                   (currency, amount, cid))
    flash(f'{ECONOMY_CURRENCIES[currency]["label"]}: {"+" if amount > 0 else ""}{amount}', 'success')
    return redirect(url_for('trading.economy'))

@bp.route('/economy/balance/set', methods=['POST'])
def economy_balance_set():
    cid = get_active_char_id()
    currency = fs('currency')
    new_balance = fi('new_balance', 0)
    if currency not in ECONOMY_CURRENCIES:
        flash('Invalid currency.', 'error')
        return redirect(url_for('trading.economy'))
    existing = db.get_one("SELECT id FROM economy_balance WHERE currency=? AND character_id=?", (currency, cid))
    if existing:
        db.execute("UPDATE economy_balance SET balance=?, updated_at=datetime('now') WHERE id=?",
                   (new_balance, existing['id']))
    else:
        db.execute("INSERT INTO economy_balance (currency, balance, character_id) VALUES (?,?,?)",
                   (currency, new_balance, cid))
    flash(f'{ECONOMY_CURRENCIES[currency]["label"]} balance set to {new_balance}.', 'success')
    return redirect(url_for('trading.economy'))

@bp.route('/economy/log/<int:lid>/delete', methods=['POST'])
def economy_log_delete(lid):
    cid = get_active_char_id()
    entry = db.get_one("SELECT * FROM economy_log WHERE id=? AND character_id=?", (lid, cid))
    if not entry:
        return jsonify(ok=False), 404
    existing = db.get_one("SELECT id, balance FROM economy_balance WHERE currency=? AND character_id=?",
                          (entry['currency'], cid))
    if existing:
        db.execute("UPDATE economy_balance SET balance=?, updated_at=datetime('now') WHERE id=?",
                   (existing['balance'] - entry['amount'], existing['id']))
    db.execute("DELETE FROM economy_log WHERE id=?", (lid,))
    flash('Transaction deleted and balance reversed.', 'info')
    return redirect(url_for('trading.economy'))




# ── Trade Post Generator ────────────────────────────────────────────────────

@bp.route('/trade-post')
def trade_post():
    weapons = db.query(
        "SELECT *, 'weapon' as src_type FROM weapons WHERE status IN ('Sell','Trade') ORDER BY name"
    )
    armor_items = db.query(
        "SELECT *, 'armor' as src_type FROM armor WHERE status IN ('Sell','Trade') ORDER BY name"
    )
    plans_list = db.query(
        "SELECT * FROM plans WHERE qty_unlearned > 0 ORDER BY name"
    )
    mods_list = db.query(
        "SELECT * FROM mods WHERE status IN ('Sell','Trade') ORDER BY name"
    )
    return render_template('trade_post.html', weapons=weapons, armor=armor_items,
                           plans=plans_list, mods=mods_list)


