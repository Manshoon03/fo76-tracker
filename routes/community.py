"""Community blueprint: community board, world finds, fishing."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, make_response
from datetime import datetime, date
import os
import io
import csv
import db
from routes.helpers import fs, fi, get_active_char_id

bp = Blueprint('community', __name__)


# ── World Finds ──────────────────────────────────────────────────────────────

WORLD_FINDS_UPLOAD = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'uploads', 'world_finds')
os.makedirs(WORLD_FINDS_UPLOAD, exist_ok=True)

WORLD_FINDS_ALLOWED = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}

BOBBLEHEAD_NAMES = [
    'Agility', 'Big Guns', 'Charisma', 'Endurance', 'Energy Weapons',
    'Explosives', 'Intelligence', 'Leader', 'Lock Picking', 'Luck',
    'Medicine', 'Melee Weapons', 'Nuka-Cola', 'Perception', 'Repair',
    'Science', 'Small Guns', 'Sneak', 'Speech', 'Strength', 'Unarmed',
]

MAGAZINE_NAMES = [
    'Astoundingly Awesome Tales', 'Backwoodsman', 'Grognak the Barbarian',
    'Guns and Bullets', 'Live & Love', "Pickman's Model", "Scout's Life",
    'Tales from the West Virginia Hills', 'Tesla Science Magazine',
    'Tumblers Today', 'U.S. Covert Operations Manual',
]

FO76_REGIONS = [
    'The Forest', 'Toxic Valley', 'Ash Heap', 'The Mire',
    'Cranberry Bog', 'Savage Divide', 'Skyline Valley',
]


def _save_wf_files(file_list):
    saved = []
    for f in file_list:
        if not f or not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in WORLD_FINDS_ALLOWED:
            continue
        fname = f"wf_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{ext}"
        f.save(os.path.join(WORLD_FINDS_UPLOAD, fname))
        saved.append(fname)
    return saved

def _wf_screenshots(find_id):
    return db.query("SELECT * FROM world_find_screenshots WHERE find_id=? ORDER BY id", (find_id,))

@bp.route('/world-finds')
@bp.route('/world-finds/<filter_type>')
def world_finds(filter_type='all'):
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    q = db.query("SELECT * FROM world_finds ORDER BY found_date DESC, id DESC")
    filter_type = filter_type.lower()
    if filter_type in ('bobblehead', 'magazine', 'other'):
        rows = [r for r in q if r['item_type'].lower() == filter_type]
    else:
        rows = list(q)
        filter_type = 'all'
    counts = {
        'all':        len(q),
        'bobblehead': sum(1 for r in q if r['item_type'].lower() == 'bobblehead'),
        'magazine':   sum(1 for r in q if r['item_type'].lower() == 'magazine'),
        'other':      sum(1 for r in q if r['item_type'].lower() == 'other'),
    }
    all_shots = db.query("SELECT * FROM world_find_screenshots ORDER BY find_id, id")
    shots_map = {}
    for s in all_shots:
        shots_map.setdefault(s['find_id'], []).append(s)
    edit_id   = request.args.get('edit_id', type=int)
    edit_item = db.get_one("SELECT * FROM world_finds WHERE id=?", (edit_id,)) if edit_id else None
    edit_shots = _wf_screenshots(edit_id) if edit_id else []
    return render_template('world_finds.html',
                           rows=rows, filter_type=filter_type, counts=counts,
                           shots_map=shots_map,
                           edit_item=edit_item, edit_id=edit_id, edit_shots=edit_shots,
                           bobblehead_names=BOBBLEHEAD_NAMES,
                           magazine_names=MAGAZINE_NAMES,
                           regions=FO76_REGIONS)

@bp.route('/world-finds/add', methods=['POST'])
def world_finds_add():
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    find_id = db.insert(
        "INSERT INTO world_finds (item_type, item_name, location, region, server_type, notes, found_date) "
        "VALUES (?,?,?,?,?,?,?)",
        (fs('item_type') or 'Bobblehead', fs('item_name'), fs('location'),
         fs('region'), fs('server_type') or 'Public', fs('notes'),
         fs('found_date') or datetime.now().strftime('%Y-%m-%d')),
    )
    for fname in _save_wf_files(request.files.getlist('screenshots')):
        db.insert("INSERT INTO world_find_screenshots (find_id, filename) VALUES (?,?)", (find_id, fname))
    flash('Find logged!', 'success')
    return redirect(url_for('community.world_finds'))

@bp.route('/world-finds/<int:id>/edit', methods=['POST'])
def world_finds_edit(id):
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    db.execute(
        "UPDATE world_finds SET item_type=?, item_name=?, location=?, region=?, "
        "server_type=?, notes=?, found_date=? WHERE id=?",
        (fs('item_type') or 'Bobblehead', fs('item_name'), fs('location'),
         fs('region'), fs('server_type') or 'Public', fs('notes'),
         fs('found_date') or datetime.now().strftime('%Y-%m-%d'), id),
    )
    for fname in _save_wf_files(request.files.getlist('screenshots')):
        db.insert("INSERT INTO world_find_screenshots (find_id, filename) VALUES (?,?)", (id, fname))
    flash('Find updated!', 'success')
    return redirect(url_for('community.world_finds'))

@bp.route('/world-finds/<int:find_id>/screenshot/<int:shot_id>/delete', methods=['POST'])
def world_finds_screenshot_delete(find_id, shot_id):
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    row = db.get_one("SELECT filename FROM world_find_screenshots WHERE id=? AND find_id=?", (shot_id, find_id))
    if row:
        path = os.path.join(WORLD_FINDS_UPLOAD, row['filename'])
        if os.path.isfile(path):
            os.remove(path)
        db.execute("DELETE FROM world_find_screenshots WHERE id=?", (shot_id,))
    return redirect(url_for('community.world_finds', _anchor='') + f'?edit_id={find_id}#addPanel')

@bp.route('/world-finds/<int:id>/delete', methods=['POST'])
def world_finds_delete(id):
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    for row in db.query("SELECT filename FROM world_find_screenshots WHERE find_id=?", (id,)):
        path = os.path.join(WORLD_FINDS_UPLOAD, row['filename'])
        if os.path.isfile(path):
            os.remove(path)
    db.execute("DELETE FROM world_find_screenshots WHERE find_id=?", (id,))
    db.execute("DELETE FROM world_finds WHERE id=?", (id,))
    flash('Find deleted.', 'info')
    return redirect(url_for('community.world_finds'))


# ── Community Board ──────────────────────────────────────────────────────────

@bp.route('/community-board')
def community_board():
    from collections import defaultdict
    pool  = [dict(r) for r in db.query("""
        SELECT * FROM comm_pool
        ORDER BY CASE status WHEN 'Available' THEN 0 WHEN 'Reserved' THEN 1 ELSE 2 END,
                 added_at DESC, id DESC
    """)]
    needs = [dict(r) for r in db.query("""
        SELECT * FROM comm_needs
        ORDER BY CASE status WHEN 'Waiting' THEN 0 WHEN 'Matched' THEN 1 ELSE 2 END,
                 added_at DESC, id DESC
    """)]
    log   = db.query("SELECT * FROM comm_log ORDER BY id DESC LIMIT 100")
    chars = [r['name'] for r in db.query("SELECT name FROM characters ORDER BY name")]
    bal = defaultdict(lambda: {'donated': 0, 'received': 0})
    for p in pool:
        if p['status'] == 'Gone':
            bal[p['donor_name']]['donated'] += 1
    for n in needs:
        if n['status'] == 'Received':
            bal[n['player_name']]['received'] += 1
    scoreboard = sorted(
        [{'player': p, 'donated': v['donated'], 'received': v['received'],
          'score': v['donated'] - v['received']} for p, v in bal.items()],
        key=lambda x: x['score'], reverse=True
    )
    pool_available  = sum(1 for p in pool  if p['status'] in ('Available','Reserved'))
    needs_active    = sum(1 for n in needs if n['status'] in ('Waiting','Matched','Seeking'))
    last_change     = log[0]['logged_at'] if log else None
    return render_template('community_board.html',
                           pool=pool, needs=needs, log=log,
                           scoreboard=scoreboard, chars=chars,
                           pool_available=pool_available, needs_active=needs_active,
                           last_change=last_change)

@bp.route('/community-board/pool/add', methods=['POST'])
def community_board_pool_add():
    donor = fs('donor_name')
    item  = fs('item_name')
    db.insert("""
        INSERT INTO comm_pool
          (donor_name, held_on, item_name, item_type, qty, star1, star2, star3, notes, added_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (donor, fs('held_on'), item, fs('item_type','Mod Box'),
          int(fs('qty') or 1), fs('star1'), fs('star2'), fs('star3'), fs('notes'),
          fs('added_at') or str(date.today())))
    db.insert("INSERT INTO comm_log (action, player_name, item_name, detail) VALUES (?,?,?,?)",
              ('Pool Add', donor, item, f"x{fs('qty') or 1} on {fs('held_on')}"))
    flash(f'Added {item} to the pool.', 'success')
    return redirect(url_for('community.community_board'))

@bp.route('/community-board/pool/<int:id>/edit', methods=['POST'])
def community_board_pool_edit(id):
    db.execute("""
        UPDATE comm_pool
        SET donor_name=?, held_on=?, item_name=?, item_type=?, qty=?,
            star1=?, star2=?, star3=?, notes=?, added_at=?
        WHERE id=?
    """, (fs('donor_name'), fs('held_on'), fs('item_name'), fs('item_type'),
          int(fs('qty') or 1), fs('star1'), fs('star2'), fs('star3'),
          fs('notes'), fs('added_at'), id))
    flash('Updated.', 'success')
    return redirect(url_for('community.community_board'))

@bp.route('/community-board/pool/<int:id>/reserve', methods=['POST'])
def community_board_pool_reserve(id):
    player = fs('reserved_for')
    row    = db.get_one("SELECT * FROM comm_pool WHERE id=?", (id,))
    db.execute("UPDATE comm_pool SET status='Reserved', reserved_for=? WHERE id=?", (player, id))
    if row:
        db.insert("INSERT INTO comm_log (action, player_name, item_name, detail) VALUES (?,?,?,?)",
                  ('Reserved', player, row['item_name'], f"Held by {row['donor_name']} on {row['held_on']}"))
    flash(f'Reserved for {player}.', 'success')
    return redirect(url_for('community.community_board'))

@bp.route('/community-board/pool/<int:id>/gone', methods=['POST'])
def community_board_pool_gone(id):
    row = db.get_one("SELECT * FROM comm_pool WHERE id=?", (id,))
    db.execute("UPDATE comm_pool SET status='Gone' WHERE id=?", (id,))
    if row:
        dest = f" → {row['reserved_for']}" if row['reserved_for'] else ''
        db.insert("INSERT INTO comm_log (action, player_name, item_name, detail) VALUES (?,?,?,?)",
                  ('Donated', row['donor_name'], row['item_name'],
                   f"x{row['qty']} from {row['held_on']}{dest}"))
    flash('Marked as handed off.', 'success')
    return redirect(url_for('community.community_board'))

@bp.route('/community-board/pool/<int:id>/delete', methods=['POST'])
def community_board_pool_delete(id):
    db.execute("DELETE FROM comm_pool WHERE id=?", (id,))
    flash('Removed from pool.', 'info')
    return redirect(url_for('community.community_board'))

@bp.route('/community-board/need/add', methods=['POST'])
def community_board_need_add():
    player = fs('player_name')
    item   = fs('item_wanted')
    db.insert("""
        INSERT INTO comm_needs (player_name, item_wanted, item_type, platform, notes, status, added_at)
        VALUES (?,?,?,?,?,'Waiting',?)
    """, (player, item, fs('item_type','Mod Box'), fs('platform','PC'),
          fs('notes'), fs('added_at') or str(date.today())))
    db.insert("INSERT INTO comm_log (action, player_name, item_name, detail) VALUES (?,?,?,?)",
              ('Need Added', player, item, fs('platform','PC')))
    flash(f'{player} added to the needs board.', 'success')
    return redirect(url_for('community.community_board', tab='needs'))

@bp.route('/community-board/need/<int:id>/edit', methods=['POST'])
def community_board_need_edit(id):
    db.execute("""
        UPDATE comm_needs
        SET player_name=?, item_wanted=?, item_type=?, platform=?, notes=?, added_at=?
        WHERE id=?
    """, (fs('player_name'), fs('item_wanted'), fs('item_type'),
          fs('platform'), fs('notes'), fs('added_at'), id))
    flash('Updated.', 'success')
    return redirect(url_for('community.community_board', tab='needs'))

@bp.route('/community-board/need/<int:id>/match', methods=['POST'])
def community_board_need_match(id):
    row          = db.get_one("SELECT * FROM comm_needs WHERE id=?", (id,))
    matched_item = fs('matched_item')
    matched_from = fs('matched_from')
    db.execute("""
        UPDATE comm_needs SET status='Matched', matched_item=?, fulfilled_by=? WHERE id=?
    """, (matched_item, matched_from, id))
    if row:
        db.insert("INSERT INTO comm_log (action, player_name, item_name, detail) VALUES (?,?,?,?)",
                  ('Matched', row['player_name'], row['item_wanted'],
                   f"Getting {matched_item} from {matched_from}"))
    flash('Marked as matched.', 'success')
    return redirect(url_for('community.community_board', tab='needs'))

@bp.route('/community-board/need/<int:id>/received', methods=['POST'])
def community_board_need_received(id):
    row = db.get_one("SELECT * FROM comm_needs WHERE id=?", (id,))
    db.execute("""
        UPDATE comm_needs SET status='Received', fulfilled_at=? WHERE id=?
    """, (str(date.today()), id))
    if row:
        db.insert("INSERT INTO comm_log (action, player_name, item_name, detail) VALUES (?,?,?,?)",
                  ('Received', row['player_name'], row['item_wanted'],
                   f"From: {row['fulfilled_by'] or 'unknown'}"))
    flash(f"{row['player_name'] if row else 'Player'} marked as received.", 'success')
    return redirect(url_for('community.community_board', tab='needs'))

@bp.route('/community-board/need/<int:id>/delete', methods=['POST'])
def community_board_need_delete(id):
    row = db.get_one("SELECT * FROM comm_needs WHERE id=?", (id,))
    if row:
        db.insert("INSERT INTO comm_log (action, player_name, item_name, detail) VALUES (?,?,?,?)",
                  ('Removed', row['player_name'], row['item_wanted'], fs('reason') or ''))
    db.execute("DELETE FROM comm_needs WHERE id=?", (id,))
    flash('Removed from board.', 'info')
    return redirect(url_for('community.community_board', tab='needs'))

@bp.route('/community-board/export/pool.csv')
def community_board_export_pool():
    rows = db.query("SELECT * FROM comm_pool WHERE status != 'Gone' ORDER BY status, added_at DESC")
    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow(['Donor','Held On','Item','Type','Qty','Star 1','Star 2','Star 3',
                'Status','Reserved For','Notes','Date Added'])
    for r in rows:
        w.writerow([r['donor_name'], r['held_on'], r['item_name'], r['item_type'],
                    r['qty'], r['star1'] or '', r['star2'] or '', r['star3'] or '',
                    r['status'], r['reserved_for'] or '', r['notes'] or '', r['added_at']])
    resp = make_response(buf.getvalue())
    resp.headers['Content-Disposition'] = 'attachment; filename=community_pool.csv'
    resp.headers['Content-Type'] = 'text/csv'
    return resp

@bp.route('/community-board/export/needs.csv')
def community_board_export_needs():
    rows = db.query("SELECT * FROM comm_needs WHERE status != 'Received' ORDER BY status, added_at DESC")
    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow(['Player','Item Wanted','Type','Platform','Status',
                'Matched Item','From','Notes','Date Added'])
    for r in rows:
        w.writerow([r['player_name'], r['item_wanted'], r['item_type'],
                    r['platform'] or '', r['status'],
                    r['matched_item'] or '', r['fulfilled_by'] or '',
                    r['notes'] or '', r['added_at']])
    resp = make_response(buf.getvalue())
    resp.headers['Content-Disposition'] = 'attachment; filename=community_needs.csv'
    resp.headers['Content-Type'] = 'text/csv'
    return resp


# ── Fishing ──────────────────────────────────────────────────────────────────

_RARITY_ORDER = {'Generic':1,'Common':2,'Uncommon':3,'Glowing':4,'Local Legend':5,'Axolotl':6}

@bp.route('/fishing')
def fishing():
    species = db.query("""
        SELECT * FROM fish_species
        ORDER BY CASE rarity
            WHEN 'Generic'      THEN 1
            WHEN 'Common'       THEN 2
            WHEN 'Uncommon'     THEN 3
            WHEN 'Glowing'      THEN 4
            WHEN 'Local Legend' THEN 5
            WHEN 'Axolotl'      THEN 6
            ELSE 7 END, biome, name
    """)
    cid = get_active_char_id()
    log = db.query("SELECT * FROM fish_log WHERE character_id=? ORDER BY caught_at DESC, id DESC LIMIT 100", (cid,))
    total_caught = sum(1 for s in species if s['caught'])
    biome_stats = db.query("""
        SELECT biome, COUNT(*) as total, COALESCE(SUM(caught),0) as caught_count
        FROM fish_species
        WHERE biome IS NOT NULL AND biome != '' AND biome != 'All Regions'
        GROUP BY biome ORDER BY biome
    """)
    log_total = db.get_one("SELECT COUNT(*) as n FROM fish_log WHERE character_id=?", (cid,))['n']
    edit_log_id = request.args.get('edit_log_id', type=int)
    edit_log = db.get_one("SELECT * FROM fish_log WHERE id=? AND character_id=?", (edit_log_id, cid)) if edit_log_id else None

    _rare_case = """SUM(CASE WHEN rarity IN ('Uncommon','Glowing','Local Legend','Axolotl')
                             THEN 1 ELSE 0 END)"""
    _cols = """COUNT(*) as total,
               {rare} as rare_plus,
               SUM(CASE WHEN rarity='Generic'      THEN 1 ELSE 0 END) as generic_cnt,
               SUM(CASE WHEN rarity='Common'       THEN 1 ELSE 0 END) as common_cnt,
               SUM(CASE WHEN rarity='Uncommon'     THEN 1 ELSE 0 END) as uncommon_cnt,
               SUM(CASE WHEN rarity='Glowing'      THEN 1 ELSE 0 END) as glowing_cnt,
               SUM(CASE WHEN rarity='Local Legend' THEN 1 ELSE 0 END) as legend_cnt,
               SUM(CASE WHEN rarity='Axolotl'      THEN 1 ELSE 0 END) as axolotl_cnt""".format(rare=_rare_case)

    bait_analysis = db.query(f"""
        SELECT bait_used as label, {_cols}
        FROM fish_log WHERE character_id=?
          AND bait_used IS NOT NULL AND bait_used != ''
        GROUP BY bait_used HAVING total >= 3
        ORDER BY rare_plus * 100.0 / total DESC
    """, (cid,))

    weather_analysis = db.query(f"""
        SELECT weather as label, {_cols}
        FROM fish_log WHERE character_id=?
          AND weather IS NOT NULL AND weather != ''
        GROUP BY weather HAVING total >= 3
        ORDER BY rare_plus * 100.0 / total DESC
    """, (cid,))

    combo_analysis = db.query(f"""
        SELECT bait_used || ' + ' || weather as label, {_cols}
        FROM fish_log WHERE character_id=?
          AND bait_used IS NOT NULL AND bait_used != ''
          AND weather   IS NOT NULL AND weather   != ''
        GROUP BY bait_used, weather HAVING total >= 5
        ORDER BY rare_plus * 100.0 / total DESC
        LIMIT 10
    """, (cid,))

    spot_analysis = db.query(f"""
        SELECT location as label, {_cols}
        FROM fish_log WHERE character_id=?
          AND location IS NOT NULL AND location != ''
        GROUP BY location HAVING total >= 3
        ORDER BY rare_plus * 100.0 / total DESC
        LIMIT 10
    """, (cid,))

    time_analysis = db.query(f"""
        SELECT
            CASE
                WHEN CAST(substr(caught_time,1,2) AS INTEGER) BETWEEN 5  AND 11 THEN '🌅 Morning (5am–noon)'
                WHEN CAST(substr(caught_time,1,2) AS INTEGER) BETWEEN 12 AND 17 THEN '☀️ Afternoon (noon–6pm)'
                WHEN CAST(substr(caught_time,1,2) AS INTEGER) BETWEEN 18 AND 21 THEN '🌆 Evening (6–10pm)'
                ELSE '🌙 Night (10pm–5am)'
            END as label, {_cols}
        FROM fish_log WHERE character_id=?
          AND caught_time IS NOT NULL AND caught_time != ''
        GROUP BY label HAVING total >= 3
        ORDER BY rare_plus * 100.0 / total DESC
    """, (cid,))

    active_session_id = db.get_setting('fish_session_active_id', '')
    active_session    = None
    session_catches   = 0
    if active_session_id:
        active_session = db.get_one("SELECT * FROM fish_sessions WHERE id=?", (int(active_session_id),))
        if active_session:
            session_catches = db.get_one(
                "SELECT COUNT(*) as n FROM fish_log WHERE character_id=? AND logged_at >= ?",
                (cid, active_session['started_at'])
            )['n']

    recent_sessions = db.query("""
        SELECT s.*,
            CAST(ROUND((julianday(s.ended_at) - julianday(s.started_at)) * 1440) AS INTEGER) as duration_min,
            (SELECT COUNT(*) FROM fish_log fl
             WHERE fl.character_id = s.character_id
               AND fl.logged_at >= s.started_at
               AND fl.logged_at <= s.ended_at) as catch_count
        FROM fish_sessions s
        WHERE s.character_id=? AND s.ended_at IS NOT NULL
        ORDER BY s.started_at DESC LIMIT 10
    """, (cid,))

    return render_template('fishing.html', species=species, log=log,
                           total_caught=total_caught, total_species=len(species),
                           biome_stats=biome_stats, log_total=log_total,
                           bait_analysis=bait_analysis,
                           weather_analysis=weather_analysis,
                           combo_analysis=combo_analysis,
                           spot_analysis=spot_analysis,
                           time_analysis=time_analysis,
                           active_session=active_session,
                           session_catches=session_catches,
                           recent_sessions=recent_sessions,
                           edit_log=edit_log)

@bp.route('/fishing/toggle/<int:sid>', methods=['POST'])
def fishing_toggle(sid):
    from datetime import date as _date
    row = db.get_one("SELECT caught FROM fish_species WHERE id=?", (sid,))
    if not row:
        return jsonify({'ok': False}), 404
    new_val = 0 if row['caught'] else 1
    first = str(_date.today()) if new_val else ''
    db.execute(
        "UPDATE fish_species SET caught=?, first_caught=? WHERE id=?",
        (new_val, first, sid)
    )
    if new_val:
        db.execute("UPDATE fish_species SET catch_count = catch_count + 1 WHERE id=?", (sid,))
    row2 = db.get_one("SELECT catch_count FROM fish_species WHERE id=?", (sid,))
    return jsonify({'ok': True, 'caught': new_val, 'catch_count': row2['catch_count'] if row2 else 0})

@bp.route('/fishing/log', methods=['POST'])
def fishing_log_add():
    from datetime import date as _date
    fish_name = fs('fish_name')
    if not fish_name:
        flash('Fish name required.', 'error')
        return redirect(url_for('community.fishing'))
    db.execute(
        "INSERT INTO fish_log (fish_name, rarity, biome, location, bait_used, weather, notes, caught_at, caught_time, logged_at, character_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,datetime('now'),?)",
        (fish_name, fs('rarity'), fs('biome'), fs('location'),
         fs('bait_used'), fs('weather'), fs('notes'),
         fs('caught_at') or str(_date.today()), fs('caught_time'), get_active_char_id())
    )
    db.execute(
        "UPDATE fish_species SET caught=1, first_caught=COALESCE(NULLIF(first_caught,''), date('now')), "
        "catch_count = catch_count + 1 WHERE name=?", (fish_name,)
    )
    flash(f'Logged: {fish_name}!', 'success')
    return redirect(url_for('community.fishing'))

@bp.route('/fishing/log/<int:lid>/update', methods=['POST'])
def fishing_log_update(lid):
    from datetime import date as _date
    db.execute(
        "UPDATE fish_log SET fish_name=?, rarity=?, biome=?, location=?, "
        "bait_used=?, weather=?, notes=?, caught_at=?, caught_time=? WHERE id=?",
        (fs('fish_name'), fs('rarity'), fs('biome'), fs('location'),
         fs('bait_used'), fs('weather'), fs('notes'),
         fs('caught_at') or str(_date.today()), fs('caught_time'), lid)
    )
    flash('Catch updated.', 'success')
    return redirect(url_for('community.fishing'))

@bp.route('/fishing/log/<int:lid>/delete', methods=['POST'])
def fishing_log_delete(lid):
    db.execute("DELETE FROM fish_log WHERE id=?", (lid,))
    flash('Entry removed.', 'info')
    return redirect(url_for('community.fishing'))

@bp.route('/fishing/session/start', methods=['POST'])
def fishing_session_start():
    cid = get_active_char_id()
    sid = db.insert(
        "INSERT INTO fish_sessions (character_id, started_at) VALUES (?, datetime('now'))", (cid,)
    )
    db.set_setting('fish_session_active_id', str(sid))
    flash('Fishing session started!', 'success')
    return redirect(url_for('community.fishing'))

@bp.route('/fishing/session/end', methods=['POST'])
def fishing_session_end():
    sid_str = db.get_setting('fish_session_active_id', '')
    if not sid_str:
        flash('No active session.', 'warning')
        return redirect(url_for('community.fishing'))
    db.execute("UPDATE fish_sessions SET ended_at=datetime('now') WHERE id=?", (int(sid_str),))
    db.set_setting('fish_session_active_id', '')
    flash('Session saved.', 'success')
    return redirect(url_for('community.fishing'))

@bp.route('/fishing/session/<int:sid>/delete', methods=['POST'])
def fishing_session_delete(sid):
    if db.get_setting('fish_session_active_id', '') == str(sid):
        db.set_setting('fish_session_active_id', '')
    db.execute("DELETE FROM fish_sessions WHERE id=?", (sid,))
    flash('Session deleted.', 'info')
    return redirect(url_for('community.fishing'))
