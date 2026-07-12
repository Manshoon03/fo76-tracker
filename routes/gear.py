"""Gear blueprint: weapons, armor, power armor, mods, legendary mods,
inventory, stash overview, weapon advisor, legendary optimizer."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
import json
import re
import os
import db
from routes.helpers import fs, fi, ff, get_active_char_id, _inv_sync, _inv_delete, _get_anthropic, _scan_image, _extract_json, _extract_json_array

bp = Blueprint('gear', __name__)


# ── Weapons ──────────────────────────────────────────────────────────────────

@bp.route('/weapons')
def weapons():
    cid = get_active_char_id()
    status_filter = request.args.get('status', '')
    edit_id = request.args.get('edit_id', type=int)
    if status_filter:
        items = db.query("SELECT * FROM weapons WHERE character_id=? AND status=? ORDER BY name", (cid, status_filter))
    else:
        items = db.query("SELECT * FROM weapons WHERE character_id=? ORDER BY name", (cid,))
    edit_item = db.get_one("SELECT * FROM weapons WHERE id=?", (edit_id,)) if edit_id else None
    dupes_rows = db.query("SELECT name FROM weapons WHERE character_id=? GROUP BY name HAVING COUNT(*) > 1", (cid,))
    dupes = {r['name'] for r in dupes_rows}
    scan = {k: request.args.get(k, '') for k in
            ('scan_name','scan_wtype','scan_star1','scan_star2','scan_star3','scan_star4','scan_cond')}
    scan_active = any(scan.values())
    return render_template('weapons.html', items=items, edit_item=edit_item,
                           status_filter=status_filter, dupes=dupes,
                           scan=scan, scan_active=scan_active)

@bp.route('/weapons/add', methods=['POST'])
def weapons_add():
    wid = db.insert(
        "INSERT INTO weapons (name,wtype,damage_type,star1,star2,star3,star4,mods,condition_pct,weight,value,status,notes,character_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (fs('name'), fs('wtype'), fs('damage_type','Ballistic'), fs('star1'), fs('star2'), fs('star3'), fs('star4'),
         fs('mods'), fi('condition_pct',100), ff('weight'), fi('value'), fs('status','Keep'), fs('notes'), get_active_char_id())
    )
    _inv_sync('weapons', wid, fs('name'), 'Weapon', fs('wtype'), 1, ff('weight'), fi('value'), fs('status','Keep'))
    flash('Weapon added!', 'success')
    return redirect(url_for('gear.weapons'))

@bp.route('/weapons/<int:id>/update', methods=['POST'])
def weapons_update(id):
    db.execute(
        "UPDATE weapons SET name=?,wtype=?,damage_type=?,star1=?,star2=?,star3=?,star4=?,mods=?,condition_pct=?,weight=?,value=?,status=?,notes=? WHERE id=?",
        (fs('name'), fs('wtype'), fs('damage_type','Ballistic'), fs('star1'), fs('star2'), fs('star3'), fs('star4'),
         fs('mods'), fi('condition_pct',100), ff('weight'), fi('value'), fs('status','Keep'), fs('notes'), id)
    )
    _inv_sync('weapons', id, fs('name'), 'Weapon', fs('wtype'), 1, ff('weight'), fi('value'), fs('status','Keep'))
    flash('Weapon updated!', 'success')
    return redirect(url_for('gear.weapons'))

@bp.route('/weapons/<int:id>/delete', methods=['POST'])
def weapons_delete(id):
    _inv_delete('weapons', id)
    db.execute("DELETE FROM weapons WHERE id=?", (id,))
    flash('Deleted.', 'info')
    return redirect(url_for('gear.weapons'))

@bp.route('/weapons/<int:id>/status', methods=['POST'])
def weapons_status(id):
    db.execute("UPDATE weapons SET status=? WHERE id=?", (fs('status'), id))
    return redirect(url_for('gear.weapons'))

@bp.route('/weapons/bulk', methods=['POST'])
def weapons_bulk():
    ids = request.form.getlist('ids')
    action = fs('bulk_action')
    if ids and action == 'delete':
        for i in ids:
            _inv_delete('weapons', int(i))
            db.execute("DELETE FROM weapons WHERE id=?", (int(i),))
    elif ids and action in ('Keep','Sell','Scrap','Stash'):
        for i in ids:
            db.execute("UPDATE weapons SET status=? WHERE id=?", (action, int(i)))
            row = db.get_one("SELECT name,wtype,weight,value FROM weapons WHERE id=?", (int(i),))
            if row:
                _inv_sync('weapons', int(i), row['name'], 'Weapon', row['wtype'], 1, row['weight'], row['value'], action)
    flash(f'Updated {len(ids)} items.', 'success')
    return redirect(url_for('gear.weapons'))

_WEAPON_SCAN_PROMPT = """You are reading a Fallout 76 weapon card screenshot.
Extract the weapon details. Return ONLY valid JSON — no markdown, no explanation.

Format:
{
  "weapon_name": "<weapon name>",
  "weapon_type": "<type: Rifle/Pistol/Shotgun/SMG/Heavy/Melee 1H/Melee 2H/Bow/Crossbow/Thrown/Flamer or empty>",
  "star1": "<first legendary effect name or empty>",
  "star2": "<second legendary effect name or empty>",
  "star3": "<third legendary effect name or empty>",
  "star4": "<fourth legendary effect name or empty>",
  "condition_pct": <integer 0-100>
}

Rules:
- weapon_name: full name, e.g. "Railway Rifle", "The Fixer", "Handmade Rifle"
- star1/2/3/4: full effect name, e.g. "Bloodied", "Explosive", "V.A.T.S. Optimized"
- condition_pct: weapon durability percentage, default 100 if not visible
- If no weapon visible, return all fields as empty strings and condition_pct as 100
"""

@bp.route('/weapons/scan', methods=['POST'])
def weapons_scan():
    api_key = db.get_setting('anthropic_api_key', '')
    if not api_key:
        flash('Set your Anthropic API key in Vendor Scan settings first.', 'error')
        return redirect(url_for('gear.weapons'))
    f = request.files.get('scan_image')
    if not f or not f.filename:
        flash('No image uploaded.', 'error')
        return redirect(url_for('gear.weapons'))
    MIME = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}
    ext = os.path.splitext(f.filename)[1].lower()
    media_type = MIME.get(ext, 'image/png')
    try:
        raw = _scan_image(f.read(), media_type, api_key, prompt=_WEAPON_SCAN_PROMPT)
        data = _extract_json(raw)
        if not data:
            flash('Could not parse weapon from image — add it manually.', 'error')
            return redirect(url_for('gear.weapons'))
        return redirect(url_for('gear.weapons',
            scan_name=data.get('weapon_name', ''),
            scan_wtype=data.get('weapon_type', ''),
            scan_star1=data.get('star1', ''),
            scan_star2=data.get('star2', ''),
            scan_star3=data.get('star3', ''),
            scan_star4=data.get('star4', ''),
            scan_cond=data.get('condition_pct', 100),
        ))
    except Exception as e:
        flash(f'Scan failed: {e}', 'error')
        return redirect(url_for('gear.weapons'))

@bp.route('/weapons/parse', methods=['POST'])
def weapons_parse():
    data  = request.get_json()
    text  = (data.get('text') or '').strip()
    if not text:
        return jsonify({'success': False, 'error': 'No text provided'}), 400

    prompt = f"""You are a Fallout 76 item parser. The player typed a weapon description.
Extract structured fields. Use standard FO76 terminology.

INPUT: "{text}"

Return ONLY valid JSON:
{{
  "name": "Base weapon name (e.g. Fixer, Handmade, Gatling Plasma)",
  "weapon_type": "One of: Rifle, Commando, Pistol, Shotgun, Sniper, Heavy Gun, Two-Handed Melee, One-Handed Melee, Unarmed, Bow, Thrown",
  "legendary_1star": "1-star legendary effect or empty string",
  "legendary_2star": "2-star legendary effect or empty string",
  "legendary_3star": "3-star legendary effect or empty string",
  "ammo_type": "Ammo type or empty string",
  "notes": "Any extra details"
}}

Common shorthand: B=Bloodied, AA=Anti-Armor, E=Explosive, Q=Quad, TS=Two Shot, J=Junkie's, V=Vampire's, FFR=Faster Fire Rate, FR=Fire Rate, SW=Swing Speed, SS=Swing Speed, 25FR=25% faster fire rate, 50B=50% more limb damage, 15RL=15% faster reload, +1S=+1 Strength, 25vats=25% less VATS cost"""

    try:
        client   = _get_anthropic()
        response = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=400,
            messages=[
                {'role': 'user',      'content': prompt},
                {'role': 'assistant', 'content': '{'}
            ]
        )
        t     = '{' + response.content[0].text.strip()
        t     = re.sub(r'```[\w]*\s*$', '', t).strip()
        fields = json.loads(t)
        return jsonify({'success': True, 'fields': fields})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Armor ────────────────────────────────────────────────────────────────────

@bp.route('/armor')
def armor():
    cid = get_active_char_id()
    status_filter = request.args.get('status', '')
    edit_id = request.args.get('edit_id', type=int)
    if status_filter:
        items = db.query("SELECT * FROM armor WHERE character_id=? AND status=? ORDER BY name", (cid, status_filter))
    else:
        items = db.query("SELECT * FROM armor WHERE character_id=? ORDER BY slot, name", (cid,))
    edit_item = db.get_one("SELECT * FROM armor WHERE id=?", (edit_id,)) if edit_id else None
    wiki_armor_names = [r['name'] for r in db.query("SELECT name FROM wiki_armor ORDER BY name")]
    return render_template('armor.html', items=items, edit_item=edit_item,
                           status_filter=status_filter, wiki_armor_names=wiki_armor_names)

@bp.route('/armor/add', methods=['POST'])
def armor_add():
    aid = db.insert(
        "INSERT INTO armor (name,slot,material,star1,star2,star3,star4,mods,dr,er,rr,weight,status,notes,character_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (fs('name'), fs('slot'), fs('material'), fs('star1'), fs('star2'), fs('star3'), fs('star4'),
         fs('mods'), fi('dr'), fi('er'), fi('rr'), ff('weight'), fs('status','Keep'), fs('notes'), get_active_char_id())
    )
    _inv_sync('armor', aid, fs('name'), 'Armor', fs('slot'), 1, ff('weight'), 0, fs('status','Keep'))
    flash('Armor added!', 'success')
    return redirect(url_for('gear.armor'))

@bp.route('/armor/<int:id>/update', methods=['POST'])
def armor_update(id):
    db.execute(
        "UPDATE armor SET name=?,slot=?,material=?,star1=?,star2=?,star3=?,star4=?,mods=?,dr=?,er=?,rr=?,weight=?,status=?,notes=? WHERE id=?",
        (fs('name'), fs('slot'), fs('material'), fs('star1'), fs('star2'), fs('star3'), fs('star4'),
         fs('mods'), fi('dr'), fi('er'), fi('rr'), ff('weight'), fs('status','Keep'), fs('notes'), id)
    )
    _inv_sync('armor', id, fs('name'), 'Armor', fs('slot'), 1, ff('weight'), 0, fs('status','Keep'))
    flash('Armor updated!', 'success')
    return redirect(url_for('gear.armor'))

@bp.route('/armor/<int:id>/delete', methods=['POST'])
def armor_delete(id):
    _inv_delete('armor', id)
    db.execute("DELETE FROM armor WHERE id=?", (id,))
    flash('Deleted.', 'info')
    return redirect(url_for('gear.armor'))

@bp.route('/armor/<int:id>/status', methods=['POST'])
def armor_status(id):
    db.execute("UPDATE armor SET status=? WHERE id=?", (fs('status'), id))
    return redirect(url_for('gear.armor'))

@bp.route('/armor/bulk', methods=['POST'])
def armor_bulk():
    ids = request.form.getlist('ids')
    action = fs('bulk_action')
    if ids and action == 'delete':
        for i in ids:
            _inv_delete('armor', int(i))
            db.execute("DELETE FROM armor WHERE id=?", (int(i),))
    elif ids and action in ('Keep','Sell','Scrap','Stash'):
        for i in ids:
            db.execute("UPDATE armor SET status=? WHERE id=?", (action, int(i)))
            row = db.get_one("SELECT name,slot,weight FROM armor WHERE id=?", (int(i),))
            if row:
                _inv_sync('armor', int(i), row['name'], 'Armor', row['slot'], 1, row['weight'], 0, action)
    flash(f'Updated {len(ids)} items.', 'success')
    return redirect(url_for('gear.armor'))

@bp.route('/armor/parse', methods=['POST'])
def armor_parse():
    data = request.get_json()
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'success': False, 'error': 'No text provided'}), 400

    prompt = f"""You are a Fallout 76 item parser. Parse this armor description into structured fields.

INPUT: "{text}"

Return ONLY valid JSON:
{{
  "name": "Armor set name (e.g. Marine Armor, Ultracite Armor, Wood Armor)",
  "slot": "One of: Chest, Left Arm, Right Arm, Left Leg, Right Leg, Helmet, Full Set",
  "material": "Material/type (e.g. Marine, Ultracite, Wood, Robot, Raider, Scout)",
  "legendary_1star": "1-star legendary effect or empty string",
  "legendary_2star": "2-star legendary effect or empty string",
  "legendary_3star": "3-star legendary effect or empty string",
  "legendary_4star": "4-star effect or empty string",
  "notes": "Any extra details"
}}

Common shorthand: OE=Overeater's, U=Unyielding, Bol=Bolstering, Cham=Chameleon, Van=Vanguard's, AP=AP Refresh, Sent=Sentinel's, Cav=Cavalier's, Pow=Powered"""

    try:
        client   = _get_anthropic()
        response = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=400,
            messages=[
                {'role': 'user',      'content': prompt},
                {'role': 'assistant', 'content': '{'}
            ]
        )
        t     = '{' + response.content[0].text.strip()
        t     = re.sub(r'```[\w]*\s*$', '', t).strip()
        fields = json.loads(t)
        return jsonify({'success': True, 'fields': fields})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Power Armor ──────────────────────────────────────────────────────────────

@bp.route('/power-armor')
def power_armor():
    cid = get_active_char_id()
    status_filter = request.args.get('status', '')
    edit_id = request.args.get('edit_id', type=int)
    if status_filter:
        items = db.query("SELECT * FROM power_armor WHERE character_id=? AND status=? ORDER BY name", (cid, status_filter))
    else:
        items = db.query("SELECT * FROM power_armor WHERE character_id=? ORDER BY name", (cid,))
    edit_item = db.get_one("SELECT * FROM power_armor WHERE id=?", (edit_id,)) if edit_id else None
    return render_template('power_armor.html', items=items, edit_item=edit_item, status_filter=status_filter)

@bp.route('/power-armor/add', methods=['POST'])
def power_armor_add():
    cid  = get_active_char_id()
    name = fs('name')
    pid = db.insert(
        "INSERT INTO power_armor (name,pa_set,slot,star1,star2,star3,star4,mods,condition_pct,weight,value,status,notes,character_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (name, fs('pa_set'), fs('slot'), fs('star1'), fs('star2'), fs('star3'), fs('star4'),
         fs('mods'), fi('condition_pct', 100), ff('weight'), fi('value'), fs('status','Keep'), fs('notes'), cid)
    )
    sub = (fs('pa_set') + ' ' + fs('slot')).strip()
    _inv_sync('power_armor', pid, name, 'Power Armor', sub, 1, ff('weight'), fi('value'), fs('status','Keep'), cid)
    flash('Power armor added!', 'success')
    return redirect(url_for('gear.power_armor'))

@bp.route('/power-armor/<int:id>/update', methods=['POST'])
def power_armor_update(id):
    name = fs('name')
    db.execute(
        "UPDATE power_armor SET name=?,pa_set=?,slot=?,star1=?,star2=?,star3=?,star4=?,mods=?,condition_pct=?,weight=?,value=?,status=?,notes=? WHERE id=?",
        (name, fs('pa_set'), fs('slot'), fs('star1'), fs('star2'), fs('star3'), fs('star4'),
         fs('mods'), fi('condition_pct', 100), ff('weight'), fi('value'), fs('status','Keep'), fs('notes'), id)
    )
    sub = (fs('pa_set') + ' ' + fs('slot')).strip()
    _inv_sync('power_armor', id, name, 'Power Armor', sub, 1, ff('weight'), fi('value'), fs('status','Keep'))
    flash('Updated!', 'success')
    return redirect(url_for('gear.power_armor'))

@bp.route('/power-armor/<int:id>/delete', methods=['POST'])
def power_armor_delete(id):
    _inv_delete('power_armor', id)
    db.execute("DELETE FROM power_armor WHERE id=?", (id,))
    flash('Deleted.', 'info')
    return redirect(url_for('gear.power_armor'))

@bp.route('/power-armor/<int:id>/status', methods=['POST'])
def power_armor_status(id):
    status = fs('status', 'Keep')
    db.execute("UPDATE power_armor SET status=? WHERE id=?", (status, id))
    row = db.get_one("SELECT name, pa_set, slot, weight, value FROM power_armor WHERE id=?", (id,))
    if row:
        sub = (row['pa_set'] + ' ' + row['slot']).strip()
        _inv_sync('power_armor', id, row['name'], 'Power Armor', sub, 1, row['weight'], row['value'], status)
    return redirect(url_for('gear.power_armor'))

@bp.route('/power-armor/bulk', methods=['POST'])
def power_armor_bulk():
    ids = request.form.getlist('ids')
    action = fs('bulk_action')
    if ids and action == 'delete':
        for i in ids:
            _inv_delete('power_armor', int(i))
            db.execute("DELETE FROM power_armor WHERE id=?", (int(i),))
    elif ids and action in ('Keep','Sell','Scrap','Stash'):
        for i in ids:
            db.execute("UPDATE power_armor SET status=? WHERE id=?", (action, int(i)))
    flash(f'Updated {len(ids)} items.', 'success')
    return redirect(url_for('gear.power_armor'))


# ── Mods ─────────────────────────────────────────────────────────────────────

@bp.route('/mods')
def mods():
    cid = get_active_char_id()
    items = db.query("SELECT * FROM mods WHERE character_id=? ORDER BY applies_to, name", (cid,))
    edit_id = request.args.get('edit_id', type=int)
    edit_item = db.get_one("SELECT * FROM mods WHERE id=?", (edit_id,)) if edit_id else None
    return render_template('mods.html', items=items, edit_item=edit_item)

@bp.route('/mods/add', methods=['POST'])
def mods_add():
    mid = db.insert(
        "INSERT INTO mods (name,mod_type,applies_to,effect,qty,value_each,status,notes,character_id) VALUES (?,?,?,?,?,?,?,?,?)",
        (fs('name'), fs('mod_type','Normal'), fs('applies_to'), fs('effect'), fi('qty',1), fi('value_each'), fs('status','Keep'), fs('notes'), get_active_char_id())
    )
    sub = (fs('mod_type','Normal') + ' — ' + fs('applies_to')).strip(' —')
    _inv_sync('mods', mid, fs('name'), 'Mod', sub, fi('qty',1), 0, fi('value_each'), fs('status','Keep'))
    flash('Mod added!', 'success')
    return redirect(url_for('gear.mods'))

@bp.route('/mods/<int:id>/update', methods=['POST'])
def mods_update(id):
    db.execute(
        "UPDATE mods SET name=?,mod_type=?,applies_to=?,effect=?,qty=?,value_each=?,status=?,notes=? WHERE id=?",
        (fs('name'), fs('mod_type','Normal'), fs('applies_to'), fs('effect'), fi('qty',1), fi('value_each'), fs('status','Keep'), fs('notes'), id)
    )
    sub = (fs('mod_type','Normal') + ' — ' + fs('applies_to')).strip(' —')
    _inv_sync('mods', id, fs('name'), 'Mod', sub, fi('qty',1), 0, fi('value_each'), fs('status','Keep'))
    flash('Mod updated!', 'success')
    return redirect(url_for('gear.mods'))

@bp.route('/mods/<int:id>/delete', methods=['POST'])
def mods_delete(id):
    _inv_delete('mods', id)
    db.execute("DELETE FROM mods WHERE id=?", (id,))
    flash('Deleted.', 'info')
    return redirect(url_for('gear.mods'))

@bp.route('/mods/bulk', methods=['POST'])
def mods_bulk():
    ids = request.form.getlist('ids')
    action = fs('bulk_action')
    if ids and action == 'delete':
        for i in ids:
            _inv_delete('mods', int(i))
            db.execute("DELETE FROM mods WHERE id=?", (int(i),))
    elif ids and action in ('Keep','Sell','Scrap','Stash'):
        for i in ids:
            db.execute("UPDATE mods SET status=? WHERE id=?", (action, int(i)))
    flash(f'Updated {len(ids)} items.', 'success')
    return redirect(url_for('gear.mods'))


# ── Legendary Mods ───────────────────────────────────────────────────────────

@bp.route('/legendary-mods')
def legendary_mods():
    import json as _json
    effects = []
    for r in db.query("SELECT * FROM legendary_effects ORDER BY star, name"):
        e = dict(r)
        try:
            e['components'] = _json.loads(e.get('extra_components') or '[]')
        except Exception:
            e['components'] = []
        try:
            e['sources'] = _json.loads(e.get('acquisition_sources') or '[]')
        except Exception:
            e['sources'] = []
        e['cats'] = [c.strip() for c in (e.get('categories') or '').split(',') if c.strip()]
        effects.append(e)
    total   = len(effects)
    unlocked = sum(1 for e in effects if e['status'] == 'unlocked')
    seeking  = sum(1 for e in effects if e['status'] == 'seeking')
    by_star  = {}
    for s in [1,2,3,4]:
        grp = [e for e in effects if e['star'] == s]
        by_star[s] = {'total': len(grp), 'unlocked': sum(1 for e in grp if e['status'] == 'unlocked')}
    inventory = [dict(r) for r in db.query(
        "SELECT * FROM legendary_mods_inventory ORDER BY star_level, name")]
    bobbles   = [dict(r) for r in db.query(
        "SELECT * FROM bobbleheads ORDER BY name")]
    return render_template('legendary_mods.html',
                           effects=effects, total=total,
                           unlocked=unlocked, seeking=seeking,
                           by_star=by_star,
                           inventory=inventory, bobbles=bobbles)

@bp.route('/legendary-mods/status', methods=['POST'])
def legendary_mods_status():
    eid    = request.form.get('id', type=int)
    status = request.form.get('status', '')
    if eid and status in ('locked', 'seeking', 'unlocked'):
        db.execute("UPDATE legendary_effects SET status=? WHERE id=?", (status, eid))
    return ('', 204)

@bp.route('/legendary-mods/count', methods=['POST'])
def legendary_mods_count():
    eid   = request.form.get('id', type=int)
    count = request.form.get('count', type=int)
    if eid is not None and count is not None:
        db.execute("UPDATE legendary_effects SET mod_count=? WHERE id=?", (max(0, count), eid))
    return ('', 204)

@bp.route('/legendary-mods/qty', methods=['POST'])
def legendary_mods_qty():
    table = request.form.get('table')
    rid   = request.form.get('id', type=int)
    qty   = request.form.get('qty', type=int)
    if table == 'inventory' and rid is not None:
        db.execute("UPDATE legendary_mods_inventory SET qty=? WHERE id=?", (qty, rid))
    elif table == 'bobble' and rid is not None:
        db.execute("UPDATE bobbleheads SET qty=? WHERE id=?", (qty, rid))
    return ('', 204)

@bp.route('/legendary-mods/add-effect', methods=['POST'])
def legendary_mods_add_effect():
    name = fs('name')
    if not name:
        flash('Name required.', 'error')
        return redirect(url_for('gear.legendary_mods'))
    cats = ','.join(request.form.getlist('categories'))
    db.execute(
        "INSERT OR IGNORE INTO legendary_effects "
        "(name, description, star, categories, legendary_modules, status, custom) "
        "VALUES (?,?,?,?,?,?,1)",
        (name, fs('description'), fi('star', 1), cats,
         fi('legendary_modules', 15), fs('status') or 'locked')
    )
    flash(f'Added effect: {name}', 'success')
    return redirect(url_for('gear.legendary_mods'))

@bp.route('/legendary-mods/delete-effect/<int:eid>', methods=['POST'])
def legendary_mods_delete_effect(eid):
    db.execute("DELETE FROM legendary_effects WHERE id=? AND custom=1", (eid,))
    flash('Effect removed.', 'info')
    return redirect(url_for('gear.legendary_mods'))

@bp.route('/legendary-mods/add-inventory', methods=['POST'])
def legendary_mods_add_inventory():
    name = fs('name')
    if not name:
        flash('Name required.', 'error')
        return redirect(url_for('gear.legendary_mods'))
    db.execute(
        "INSERT INTO legendary_mods_inventory (name, star_level, qty, notes, custom) VALUES (?,?,?,?,1)",
        (name, fi('star_level', 1), fi('qty', 0), fs('notes'))
    )
    flash(f'Added to inventory: {name}', 'success')
    return redirect(url_for('gear.legendary_mods'))

@bp.route('/legendary-mods/delete-inventory/<int:iid>', methods=['POST'])
def legendary_mods_delete_inventory(iid):
    db.execute("DELETE FROM legendary_mods_inventory WHERE id=?", (iid,))
    flash('Removed from inventory.', 'info')
    return redirect(url_for('gear.legendary_mods'))


# ── Inventory ────────────────────────────────────────────────────────────────

@bp.route('/inventory')
def inventory():
    cid = get_active_char_id()
    cat_filter = request.args.get('cat', '')
    page = max(1, request.args.get('page', 1, type=int))
    edit_id = request.args.get('edit_id', type=int)
    PER_PAGE = 100
    where = "WHERE character_id=?"
    params = [cid]
    if cat_filter:
        where += " AND category=?"
        params.append(cat_filter)
    total_count = db.get_one(f"SELECT COUNT(*) as cnt FROM inventory {where}", params)['cnt']
    totals_row = db.get_one(
        f"SELECT COALESCE(SUM(qty * weight_each), 0) as total_wt, COALESCE(SUM(qty * value_each), 0) as total_val "
        f"FROM inventory {where} AND fo1st_stored=0", params)
    total_wt = totals_row['total_wt']
    total_val = int(totals_row['total_val'])
    total_pages = max(1, (total_count + PER_PAGE - 1) // PER_PAGE)
    page = min(page, total_pages)
    offset = (page - 1) * PER_PAGE
    order = "ORDER BY name" if cat_filter else "ORDER BY category, name"
    items = db.query(f"SELECT * FROM inventory {where} {order} LIMIT ? OFFSET ?", params + [PER_PAGE, offset])
    edit_item = db.get_one("SELECT * FROM inventory WHERE id=?", (edit_id,)) if edit_id else None
    vendor_qtys = {}
    for v in db.query("SELECT name, category, SUM(qty) as total FROM vendor_stock WHERE character_id=? GROUP BY name, category", (cid,)):
        vendor_qtys[(v['name'], v['category'])] = v['total']
    return render_template('inventory.html', items=items, edit_item=edit_item,
                           cat_filter=cat_filter, vendor_qtys=vendor_qtys,
                           page=page, total_pages=total_pages, total_count=total_count,
                           total_wt=total_wt, total_val=total_val)

@bp.route('/inventory/add', methods=['POST'])
def inventory_add():
    db.execute(
        "INSERT INTO inventory (name,category,sub_type,qty,weight_each,value_each,status,notes,fo1st_stored,perishable,character_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (fs('name'), fs('category'), fs('sub_type'), fi('qty',1),
         ff('weight_each'), fi('value_each'), fs('status','Keep'), fs('notes'),
         1 if request.form.get('fo1st_stored') else 0,
         1 if request.form.get('perishable') else 0, get_active_char_id())
    )
    flash('Item added!', 'success')
    return redirect(url_for('gear.inventory'))

@bp.route('/inventory/<int:id>/update', methods=['POST'])
def inventory_update(id):
    db.execute(
        "UPDATE inventory SET name=?,category=?,sub_type=?,qty=?,weight_each=?,value_each=?,status=?,notes=?,fo1st_stored=?,perishable=? WHERE id=?",
        (fs('name'), fs('category'), fs('sub_type'), fi('qty',1),
         ff('weight_each'), fi('value_each'), fs('status','Keep'), fs('notes'),
         1 if request.form.get('fo1st_stored') else 0,
         1 if request.form.get('perishable') else 0, id)
    )
    flash('Updated!', 'success')
    return redirect(url_for('gear.inventory'))

@bp.route('/inventory/<int:id>/delete', methods=['POST'])
def inventory_delete(id):
    db.execute("DELETE FROM inventory WHERE id=?", (id,))
    flash('Deleted.', 'info')
    return redirect(url_for('gear.inventory'))

@bp.route('/inventory/bulk', methods=['POST'])
def inventory_bulk():
    ids = request.form.getlist('ids')
    action = fs('bulk_action')
    if ids and action == 'delete':
        for i in ids:
            db.execute("DELETE FROM inventory WHERE id=?", (int(i),))
    elif ids and action in ('Keep','Sell','Scrap','Use','Donate'):
        for i in ids:
            db.execute("UPDATE inventory SET status=? WHERE id=?", (action, int(i)))
    flash(f'Updated {len(ids)} items.', 'success')
    return redirect(url_for('gear.inventory'))

@bp.route('/inventory/<int:id>/toggle-fo1st', methods=['POST'])
def inventory_toggle_fo1st(id):
    row = db.get_one("SELECT fo1st_stored FROM inventory WHERE id=?", (id,))
    if not row:
        return jsonify(error='not found'), 404
    new_val = 0 if row['fo1st_stored'] else 1
    db.execute("UPDATE inventory SET fo1st_stored=? WHERE id=?", (new_val, id))
    return jsonify(fo1st=new_val)

@bp.route('/inventory/<int:id>/quick-update', methods=['POST'])
def inventory_quick_update(id):
    data = request.get_json(force=True)
    field = data.get('field')
    value = data.get('value')
    if field == 'qty':
        try:
            value = max(0, int(value))
        except (ValueError, TypeError):
            return jsonify(error='invalid'), 400
        db.execute("UPDATE inventory SET qty=? WHERE id=?", (value, id))
    elif field == 'status':
        if value not in ('Keep','Sell','Scrap','Use','Donate'):
            return jsonify(error='invalid'), 400
        db.execute("UPDATE inventory SET status=? WHERE id=?", (value, id))
    else:
        return jsonify(error='unknown field'), 400
    return jsonify(ok=True, value=value)

_INV_SCAN_PROMPT = """This is a screenshot from Fallout 76 showing the player's inventory, stash, or Pip-Boy items screen.

Extract every visible item and return a JSON array. Each element must have these fields:
{
  "name": "<exact item name>",
  "category": "<one of: Aid, Ammo, Junk, Food/Drink, Chem, Component, Apparel, Weapon, Armor, Mod, Plan, Misc>",
  "qty": <integer, default 1 if not shown>,
  "weight_each": <float, default 0 if not shown>,
  "value_each": <integer cap value per item, default 0 if not shown>,
  "notes": "<any relevant info: legendary stars, condition, variant — empty string if none>"
}

Rules:
- Include every item you can read. Do not skip lines.
- Magazines (e.g. "Astoundingly Awesome Tales", "Backwoodsman", "Grognak the Barbarian", "Guns and Bullets", "Live & Love", "Scout's Life", "Tales from the West Virginia Hills", "Tesla Science", "Tumblers Today", "U.S. Covert Operations Manual"): category is "Aid".
- Bobbleheads (e.g. "Bobblehead: Strength", "Bobblehead: Perception", any "Bobblehead:" item) and Glowing Bobbleheads: category is "Aid".
- Stimpaks, RadAway, Rad-X, Disease Cure, Blood Packs, Antibiotics, Purified Water, Nuka-Cola variants, Buffout, Mentats, Psycho, Med-X, Overdrive, and other consumables/chems: category is "Aid".
- Cooked/raw food and drinks (Brahmin Milk, Grilled Radstag, Corn Soup, etc.): category is "Food/Drink".
- Ammo (e.g. ".308 Rounds", "5mm Rounds", "Fusion Core", "Plasma Cartridge"): category is "Ammo".
- Junk components (Steel, Aluminum, Wood, Screws, Springs, etc.): category is "Component".
- Plans and Recipes (e.g. "Plan: ", "Recipe: "): category is "Plan".
- Holotapes: category is "Misc".
- Notes and Keys: category is "Misc".
- If unsure of category, use "Misc".
- Return ONLY a valid JSON array with no explanation.
- If no items are visible, return [].
"""

@bp.route('/inventory/scan', methods=['POST'])
def inventory_scan():
    api_key = db.get_setting('anthropic_api_key', '')
    if not api_key:
        return jsonify(error='No API key set. Go to Vendor Scan → Settings to add your Anthropic key.'), 400
    f = request.files.get('scan_image')
    if not f or not f.filename:
        return jsonify(error='No image uploaded.'), 400
    MIME = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}
    ext  = os.path.splitext(f.filename)[1].lower()
    media_type = MIME.get(ext, 'image/png')
    try:
        raw   = _scan_image(f.read(), media_type, api_key, prompt=_INV_SCAN_PROMPT)
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
                'weight_each': round(float(item.get('weight_each') or 0), 3),
                'value_each':  max(0, int(item.get('value_each') or 0)),
                'notes':       str(item.get('notes', '')).strip(),
            })
        return jsonify(items=clean)
    except Exception as e:
        return jsonify(error=f'Scan failed: {e}'), 500

@bp.route('/inventory/scan/import', methods=['POST'])
def inventory_scan_import():
    data = request.get_json(force=True)
    items = data.get('items', [])
    cid   = get_active_char_id()
    count = 0
    updated = 0
    scanned_names = set()
    scanned_categories = set()
    for item in items:
        name = (item.get('name') or '').strip()
        if not name:
            continue
        category = item.get('category', 'Misc')
        qty = max(1, int(item.get('qty') or 1))
        weight_each = round(float(item.get('weight_each') or 0), 3)
        value_each = max(0, int(item.get('value_each') or 0))
        scanned_names.add((name.lower(), category))
        scanned_categories.add(category)
        existing = db.get_one(
            "SELECT id FROM inventory WHERE name=? COLLATE NOCASE AND category=? AND character_id=?",
            (name, category, cid))
        if existing:
            db.execute("UPDATE inventory SET qty=?, weight_each=?, value_each=?, status=CASE WHEN status='Missing?' THEN 'Keep' ELSE status END WHERE id=?",
                       (qty, weight_each, value_each, existing['id']))
            updated += 1
        else:
            db.execute(
                "INSERT INTO inventory (name,category,sub_type,qty,weight_each,value_each,status,notes,fo1st_stored,character_id) "
                "VALUES (?,?,?,?,?,?,?,?,0,?)",
                (name, category, '', qty, weight_each, value_each, 'Keep', item.get('notes',''), cid))
            count += 1
    flagged = 0
    if scanned_categories:
        placeholders = ','.join('?' * len(scanned_categories))
        existing_items = db.query(
            f"SELECT id, name, category FROM inventory WHERE character_id=? AND category IN ({placeholders}) AND status != 'Missing?'",
            (cid, *scanned_categories))
        for row in existing_items:
            if (row['name'].lower(), row['category']) not in scanned_names:
                db.execute("UPDATE inventory SET status='Missing?' WHERE id=?", (row['id'],))
                flagged += 1
    return jsonify(ok=True, count=count, updated=updated, flagged=flagged)


# ── Stash Overview ───────────────────────────────────────────────────────────

@bp.route('/stash-overview')
def stash_overview():
    chars = db.query("SELECT * FROM characters ORDER BY char_type, name")
    cat_filter = request.args.get('cat', '')
    page = max(1, request.args.get('page', 1, type=int))
    PER_PAGE = 100
    union_sql = """
        SELECT w.id, w.name, 'Weapons' as category, COALESCE(w.wtype,'') as detail,
               1 as qty, COALESCE(w.weight,0) as weight, w.status,
               c.name as char_name, c.char_type, w.character_id, 'weapons' as tbl,
               COALESCE(w.star1,'') || ' ' || COALESCE(w.star2,'') || ' ' || COALESCE(w.star3,'') as stars
        FROM weapons w JOIN characters c ON w.character_id=c.id
        UNION ALL
        SELECT a.id, a.name, 'Armor', COALESCE(a.slot,''),
               1, COALESCE(a.weight,0), a.status,
               c.name, c.char_type, a.character_id, 'armor',
               COALESCE(a.star1,'') || ' ' || COALESCE(a.star2,'') || ' ' || COALESCE(a.star3,'')
        FROM armor a JOIN characters c ON a.character_id=c.id
        UNION ALL
        SELECT m.id, m.name, 'Mods', COALESCE(m.mod_type,''),
               m.qty, 0, m.status,
               c.name, c.char_type, m.character_id, 'mods', ''
        FROM mods m JOIN characters c ON m.character_id=c.id
        UNION ALL
        SELECT p.id, p.name, 'Plans', COALESCE(p.category,''),
               COALESCE(p.qty_unlearned,1), 0, p.status,
               c.name, c.char_type, p.character_id, 'plans', ''
        FROM plans p JOIN characters c ON p.character_id=c.id
        UNION ALL
        SELECT i.id, i.name, COALESCE(i.category,'Misc'), COALESCE(i.sub_type,''),
               i.qty, COALESCE(i.weight_each,0)*COALESCE(i.qty,1), i.status,
               c.name, c.char_type, i.character_id, 'inventory', ''
        FROM inventory i JOIN characters c ON i.character_id=c.id
    """
    count_rows = db.query(f"SELECT category, COUNT(*) as cnt FROM ({union_sql}) GROUP BY category")
    cat_counts = {r['category']: r['cnt'] for r in count_rows}
    grand_total = sum(cat_counts.values())
    if cat_filter:
        filtered_total = cat_counts.get(cat_filter, 0)
        total_pages = max(1, (filtered_total + PER_PAGE - 1) // PER_PAGE)
        page = min(page, total_pages)
        offset = (page - 1) * PER_PAGE
        items = db.query(
            f"SELECT * FROM ({union_sql}) WHERE category=? ORDER BY char_name, name LIMIT ? OFFSET ?",
            (cat_filter, PER_PAGE, offset))
    else:
        filtered_total = grand_total
        total_pages = max(1, (filtered_total + PER_PAGE - 1) // PER_PAGE)
        page = min(page, total_pages)
        offset = (page - 1) * PER_PAGE
        items = db.query(
            f"SELECT * FROM ({union_sql}) ORDER BY char_name, name LIMIT ? OFFSET ?",
            (PER_PAGE, offset))
    return render_template('stash_overview.html',
        chars=chars, items=items, cat_filter=cat_filter,
        cat_counts=cat_counts, total=filtered_total,
        page=page, total_pages=total_pages)

@bp.route('/stash-overview/transfer', methods=['POST'])
def stash_overview_transfer():
    data = request.get_json(force=True)
    table = data.get('table')
    item_id = int(data.get('id', 0))
    target_cid = int(data.get('target_cid', 0))
    if table not in ('weapons', 'armor', 'mods', 'plans', 'inventory'):
        return jsonify(error='invalid table'), 400
    if not item_id or not target_cid:
        return jsonify(error='missing fields'), 400
    target = db.get_one("SELECT id, name FROM characters WHERE id=?", (target_cid,))
    if not target:
        return jsonify(error='character not found'), 404
    db.execute(f"UPDATE {table} SET character_id=? WHERE id=?", (target_cid, item_id))
    if table in ('weapons', 'armor', 'mods'):
        db.execute("UPDATE inventory SET character_id=? WHERE source_table=? AND source_id=?",
                   (target_cid, table, item_id))
    return jsonify(ok=True, target_name=target['name'])


