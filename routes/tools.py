"""Tools blueprint: decoder, export, backup, vendor scan, craft calc, quick log."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, make_response, send_file
from datetime import datetime
import os
import io
import csv
import zipfile
import db
from routes.helpers import fs, fi, ff, get_active_char_id, _scan_image, _extract_json

bp = Blueprint('tools', __name__)

SCAN_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'vendor_scans')

EXPORT_CONFIG = {
    'weapons':   ('weapons',        'Weapons'),
    'armor':     ('armor',          'Armor'),
    'power_armor': ('power_armor',  'Power Armor'),
    'mods':      ('mods',           'Mods'),
    'inventory': ('inventory',      'Inventory'),
    'vendor':    ('vendor_stock',   'Vendor Stock'),
    'prices':    ('price_research', 'Price Research'),
    'caps':      ('caps_sessions',  'Caps Sessions'),
    'plans':     ('plans',          'Plans'),
    'builds':    ('builds',         'Builds'),
    'mutations': ('mutations',      'Mutations'),
    'challenges':('challenges',     'Challenges'),
    'fish_log':  ('fish_log',       'Fish Log'),
    'economy':   ('economy_log',    'Economy Log'),
}


# ── Decoder ──────────────────────────────────────────────────────────────────

@bp.route('/decode')
def decode():
    import reference as ref
    seen1, seen2, seen3 = set(), set(), set()
    ref_star1 = []
    for code, (name, _) in ref.SHORTHAND_STAR1.items():
        if name not in seen1:
            seen1.add(name)
            primary = ref.OUR_CODE_STAR1.get(name, code)
            ref_star1.append((primary, name))
    ref_star1.sort(key=lambda x: x[1])

    seen2 = set()
    ref_star2 = []
    for code, (name, _) in ref.SHORTHAND_STAR2.items():
        if name not in seen2:
            seen2.add(name)
            primary = ref.OUR_CODE_STAR2.get(name, code)
            ref_star2.append((primary, name))
    ref_star2.sort(key=lambda x: x[1])

    seen3 = set()
    ref_star3 = []
    for code, (name, _) in ref.SHORTHAND_STAR3.items():
        if name not in seen3:
            seen3.add(name)
            primary = ref.OUR_CODE_STAR3.get(name, code)
            ref_star3.append((primary, name))
    ref_star3.sort(key=lambda x: x[1])

    seen_w = set()
    ref_weapons = []
    for code, name in ref.WEAPON_ALIASES.items():
        if name not in seen_w:
            seen_w.add(name)
            ref_weapons.append((code, name))
    ref_weapons.sort(key=lambda x: x[1])

    seen4 = set()
    ref_star4 = []
    for code, (name, _) in ref.SHORTHAND_STAR4.items():
        if name not in seen4:
            seen4.add(name)
            ref_star4.append((code, name))
    ref_star4.sort(key=lambda x: x[1])

    return render_template('decode.html',
        ref_star1=ref_star1, ref_star2=ref_star2,
        ref_star3=ref_star3, ref_star4=ref_star4,
        ref_weapons=ref_weapons,
        weapon_star1=ref.WEAPON_STAR1, weapon_star2=ref.WEAPON_STAR2,
        weapon_star3=ref.WEAPON_STAR3, weapon_star4=ref.WEAPON_STAR4,
        weapon_aliases=sorted(set(ref.WEAPON_ALIASES.values())))


# ── Export ───────────────────────────────────────────────────────────────────

@bp.route('/export')
def export():
    return render_template('export.html', sections=EXPORT_CONFIG)

@bp.route('/export/<section>.csv')
def export_csv(section):
    if section not in EXPORT_CONFIG:
        return 'Not found', 404
    table, label = EXPORT_CONFIG[section]
    rows = db.query(f'SELECT * FROM {table} ORDER BY id')
    output = io.StringIO()
    writer = csv.writer(output)
    if rows:
        writer.writerow(rows[0].keys())
        writer.writerows(rows)
    resp = make_response(output.getvalue())
    resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
    resp.headers['Content-Disposition'] = f'attachment; filename=fo76_{section}.csv'
    return resp


# ── Vendor Scan (AI image → CSV) ─────────────────────────────────────────────

@bp.route('/vendor-scan', methods=['GET'])
def vendor_scan():
    api_key = db.get_setting('anthropic_api_key', '')
    return render_template('vendor_scan.html', api_key_set=bool(api_key))

@bp.route('/vendor-scan/set-key', methods=['POST'])
def vendor_scan_set_key():
    key = (request.form.get('api_key') or '').strip()
    db.set_setting('anthropic_api_key', key)
    flash('API key saved.', 'success')
    return redirect(url_for('tools.vendor_scan'))

@bp.route('/vendor-scan/process', methods=['POST'])
def vendor_scan_process():
    api_key = db.get_setting('anthropic_api_key', '')
    if not api_key:
        flash('Set your Anthropic API key first.', 'error')
        return redirect(url_for('tools.vendor_scan'))

    files = request.files.getlist('images')
    if not files or not files[0].filename:
        flash('No images uploaded.', 'error')
        return redirect(url_for('tools.vendor_scan'))

    MIME = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}
    today = datetime.now().strftime('%Y-%m-%d')
    timestamp = datetime.now().strftime('%H%M')

    rows = []
    errors = []

    for f in files:
        ext = os.path.splitext(f.filename)[1].lower()
        media_type = MIME.get(ext, 'image/png')
        try:
            raw = _scan_image(f.read(), media_type, api_key)
            data = _extract_json(raw)
            if data is None:
                errors.append(f"{f.filename}: could not parse response")
                continue
            vendor = data.get('vendor_name') or f.filename
            for item in data.get('items', []):
                rows.append({
                    'item_name':   str(item.get('item_name', '')).strip(),
                    'category':    str(item.get('category', '')).strip(),
                    'description': str(item.get('description', '')).strip(),
                    'price_seen':  int(item.get('price', 0) or 0),
                    'source':      vendor,
                    'date_seen':   today,
                    'notes':       '',
                })
        except Exception as e:
            errors.append(f"{f.filename}: {e}")

    if not rows and errors:
        for e in errors:
            flash(e, 'error')
        return redirect(url_for('tools.vendor_scan'))

    os.makedirs(SCAN_OUTPUT_DIR, exist_ok=True)
    filename = f"{today}_{timestamp}_Vendor_Upload.csv"
    filepath = os.path.join(SCAN_OUTPUT_DIR, filename)
    fieldnames = ['item_name', 'category', 'description', 'price_seen', 'source', 'date_seen', 'notes']
    with open(filepath, 'w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    for e in errors:
        flash(e, 'warning')

    wishlist_items = db.query("SELECT * FROM wishlist WHERE found=0")
    hits = []
    for row in rows:
        name_lower = row['item_name'].lower()
        for w in wishlist_items:
            if w['item_name'].lower() in name_lower or name_lower in w['item_name'].lower():
                under_budget = (w['max_price'] == 0 or row['price_seen'] <= w['max_price'])
                hits.append({
                    'scan_item':    row,
                    'wish_item':    w,
                    'under_budget': under_budget,
                })
                break

    return render_template('vendor_scan.html',
                           api_key_set=True,
                           results=rows,
                           errors=errors,
                           filename=filename,
                           wishlist_hits=hits,
                           filepath=filepath)

@bp.route('/vendor-scan/download/<filename>')
def vendor_scan_download(filename):
    safe = os.path.basename(filename)
    filepath = os.path.join(SCAN_OUTPUT_DIR, safe)
    if not os.path.isfile(filepath):
        return 'Not found', 404
    return send_file(filepath, as_attachment=True, download_name=safe)


# ── Backup ───────────────────────────────────────────────────────────────────

@bp.route('/backup')
def backup():
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fo76.db')
    size_kb = round(os.path.getsize(db_path) / 1024, 1) if os.path.isfile(db_path) else 0
    scan_dir = SCAN_OUTPUT_DIR
    scan_files = sorted(os.listdir(scan_dir)) if os.path.isdir(scan_dir) else []
    backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backups')
    auto_backups = sorted(os.listdir(backup_dir), reverse=True) if os.path.isdir(backup_dir) else []
    return render_template('backup.html', size_kb=size_kb, scan_files=scan_files, auto_backups=auto_backups)

@bp.route('/backup/auto/<filename>')
def backup_download_auto(filename):
    safe = os.path.basename(filename)
    backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backups')
    filepath = os.path.join(backup_dir, safe)
    if not os.path.isfile(filepath):
        return 'Not found', 404
    return send_file(filepath, as_attachment=True, download_name=safe)

@bp.route('/backup/download-db')
def backup_download_db():
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fo76.db')
    today = datetime.now().strftime('%Y-%m-%d')
    return send_file(db_path, as_attachment=True, download_name=f'fo76_backup_{today}.db')

@bp.route('/backup/download-zip')
def backup_download_zip():
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fo76.db')
    today = datetime.now().strftime('%Y-%m-%d')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(db_path, f'fo76_backup_{today}.db')
        if os.path.isdir(SCAN_OUTPUT_DIR):
            for fname in os.listdir(SCAN_OUTPUT_DIR):
                fpath = os.path.join(SCAN_OUTPUT_DIR, fname)
                if os.path.isfile(fpath):
                    zf.write(fpath, os.path.join('vendor_scans', fname))
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f'fo76_full_backup_{today}.zip',
                     mimetype='application/zip')


# ── Quick Log ────────────────────────────────────────────────────────────────

@bp.route('/quick-log', methods=['POST'])
def quick_log():
    """AJAX quick-log from the FAB on any page."""
    data     = request.get_json(force=True)
    log_type = data.get('type', '')
    cid      = get_active_char_id()

    if log_type == 'caps':
        amount = int(data.get('amount', 0))
        note   = data.get('note', '')
        db.execute(
            "INSERT INTO caps_sessions (session_date, start_caps, end_caps, note, character_id) VALUES (date('now'),0,?,?,?)",
            (amount, note, cid)
        )
        return jsonify(ok=True, msg=f'+{amount} caps logged')

    if log_type == 'price':
        item_name = data.get('item_name', '').strip()
        price     = int(data.get('price', 0))
        source    = data.get('source', 'Player Vendor')
        if item_name:
            db.execute(
                "INSERT INTO price_research (item_name, category, source, price_seen, notes, created_at) VALUES (?,?,?,?,'',datetime('now'))",
                (item_name, 'Weapon', source, price)
            )
            return jsonify(ok=True, msg=f'{item_name} @ {price}c logged')
        return jsonify(ok=False, error='No item name'), 400

    if log_type == 'economy':
        currency = data.get('currency', '')
        amount   = int(data.get('amount', 0))
        from routes.trading import ECONOMY_CURRENCIES
        if currency in ECONOMY_CURRENCIES and amount != 0:
            db.execute("INSERT INTO economy_log (currency, amount, note, character_id) VALUES (?,?,?,?)",
                       (currency, amount, data.get('note', ''), cid))
            existing = db.get_one("SELECT id, balance FROM economy_balance WHERE currency=? AND character_id=?", (currency, cid))
            if existing:
                db.execute("UPDATE economy_balance SET balance=?, updated_at=datetime('now') WHERE id=?",
                           (existing['balance'] + amount, existing['id']))
            else:
                db.execute("INSERT INTO economy_balance (currency, balance, character_id) VALUES (?,?,?)",
                           (currency, amount, cid))
            return jsonify(ok=True, msg=f'{ECONOMY_CURRENCIES[currency]["label"]}: {"+" if amount > 0 else ""}{amount}')
        return jsonify(ok=False, error='Invalid'), 400

    return jsonify(ok=False, error='Unknown type'), 400
