from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response, send_file, session, g
from werkzeug.security import generate_password_hash, check_password_hash
import quotes
import reference
import db
import csv
import io
import os
import base64
import json
import zipfile
import re
import threading
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
_anthropic_client = None
def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
    return _anthropic_client

app = Flask(__name__)
app.secret_key = 'fo76-vault-tec-2024'

# Init DB once at startup, not on every request
db.init_db()
db.ensure_nuke_silos()
db.auto_backup()

# ── Nuke code background fetch ────────────────────────────────────────────────
_nuke_fetch = {'running': False}
# If server restarted mid-fetch, the DB status is stuck at "running" — clear it
if db.get_setting('nuke_fetch_status', '').startswith('running|'):
    db.set_setting('nuke_fetch_status', 'fail|Fetch was interrupted (server restarted) — click Fetch to retry')

def _do_nuke_fetch():
    """Background thread: scrape nukacrypt.com and update nuke codes in DB."""
    from datetime import date as _date
    _HDRS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36'}
    SILO_KEYS = {'alpha': 'Alpha', 'bravo': 'Bravo', 'charlie': 'Charlie'}
    _BAD = {'CHARLIE', 'ALPHA', 'BRAVO', 'SITE', 'LAUNCH', 'CODES', 'SILO', 'NUKE'}
    CODE_RE = re.compile(r'\b([A-Z0-9]{7,10})\b')
    try:
        from bs4 import BeautifulSoup
        codes = {}

        # --- Attempt 1: JSON API endpoint ---
        # nukacrypt.com/api/codes returns: {"ALPHA":"61436701","BRAVO":"36758567","CHARLIE":"79473176",...}
        try:
            r = requests.get('https://nukacrypt.com/api/codes', headers=_HDRS, timeout=(5, 8))
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict):
                    for key, silo in SILO_KEYS.items():
                        val = str(data.get(key.upper(), data.get(key, ''))).strip()
                        if val and re.match(r'^[A-Z0-9]{5,12}$', val.upper()) and val.upper() not in _BAD:
                            codes[silo] = val.upper()
                elif isinstance(data, list):
                    for item in data:
                        name = str(item.get('silo', item.get('name', ''))).lower()
                        code = str(item.get('code', item.get('value', ''))).upper().strip()
                        for key, silo in SILO_KEYS.items():
                            if key in name and re.match(r'^[A-Z0-9]{5,12}$', code) and code not in _BAD:
                                codes[silo] = code
        except Exception:
            pass

        # --- Attempt 2: HTML page + embedded JSON ---
        if len(codes) < 3:
            try:
                r = requests.get('https://nukacrypt.com', headers=_HDRS, timeout=(5, 10))
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, 'html.parser')

                    # Next.js / embedded JSON in <script> tags
                    for script in soup.find_all('script'):
                        stext = script.get_text() or ''
                        if not any(k in stext.lower() for k in SILO_KEYS):
                            continue
                        upper = stext.upper()
                        for key, silo in SILO_KEYS.items():
                            if silo in codes:
                                continue
                            idx = upper.find(key.upper())
                            if idx != -1:
                                chunk = upper[max(0, idx - 5):idx + 120]
                                m = CODE_RE.search(chunk)
                                if m and m.group(1) not in _BAD:
                                    codes[silo] = m.group(1)

                    # Plain-text fallback
                    if len(codes) < 3:
                        full = soup.get_text(separator=' ').upper()
                        for key, silo in SILO_KEYS.items():
                            if silo in codes:
                                continue
                            search_start = 0
                            while True:
                                idx = full.find(key.upper(), search_start)
                                if idx == -1:
                                    break
                                chunk = full[idx:idx + 120]
                                m = CODE_RE.search(chunk)
                                if m and m.group(1) not in _BAD:
                                    codes[silo] = m.group(1)
                                    break
                                search_start = idx + 1
            except Exception:
                pass

        if codes:
            week_of = str(_date.today() - timedelta(days=_date.today().weekday()))
            for silo, code in codes.items():
                db.execute(
                    "UPDATE nuke_codes SET code=?, week_of=?, updated_at=date('now') WHERE silo=?",
                    (code, week_of, silo),
                )
            found = ', '.join(sorted(codes.keys()))
            db.set_setting('nuke_fetch_status', f'ok|Fetched {found} — {datetime.now().strftime("%b %d %H:%M")}')
        else:
            db.set_setting('nuke_fetch_status',
                           f'fail|Could not parse codes from nukacrypt.com — enter manually '
                           f'({datetime.now().strftime("%H:%M")})')
    except ImportError:
        db.set_setting('nuke_fetch_status', 'fail|beautifulsoup4 not installed — run: pip install beautifulsoup4')
    except Exception as e:
        db.set_setting('nuke_fetch_status', f'fail|Fetch error: {str(e)[:100]}')
    finally:
        _nuke_fetch['running'] = False

app.permanent_session_lifetime = timedelta(days=30)

def _ensure_default_credentials():
    if not db.get_setting('auth_username'):
        db.set_setting('auth_username', 'admin')
        db.set_setting('auth_password_hash', generate_password_hash('fo76tracker'))
        print("=" * 50)
        print("  DEFAULT LOGIN CREDENTIALS")
        print("  Username: admin")
        print("  Password: fo76tracker")
        print("  Change these at /change-password")
        print("=" * 50)

_ensure_default_credentials()

@app.context_processor
def inject_reference():
    weapon_names = sorted(set(
        r['name'].replace(' (Fallout 76)', '').strip()
        for r in db.query("SELECT name FROM wiki_weapons ORDER BY name")
    ))
    armor_names = [r['name'] for r in db.query("SELECT name FROM wiki_armor ORDER BY name")]
    return {'ref': reference, 'wiki_weapon_names': weapon_names, 'wiki_armor_names': armor_names}

@app.context_processor
def inject_characters():
    all_chars = db.query("SELECT * FROM characters ORDER BY platform, name")
    cid = get_active_char_id()
    active_char = db.get_one("SELECT * FROM characters WHERE id=?", (cid,))
    return {'all_chars': all_chars, 'active_char': active_char}


def get_active_char_id():
    """Return the active character id (int), defaulting to 1."""
    try:
        return int(db.get_setting('active_character_id') or 1)
    except (ValueError, TypeError):
        return 1

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

@app.teardown_appcontext
def close_db_conn(error):
    """Close the per-request DB connection after every request."""
    conn = g.pop('db_conn', None)
    if conn is not None:
        db._managed_ids.discard(id(conn))
        conn.close()

@app.before_request
def require_login():
    if request.path.startswith('/static'):
        return
    if request.path in ('/login', '/logout'):
        return
    if not session.get('logged_in'):
        return redirect(url_for('login', next=request.path))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = (request.form.get('password') or '')
        stored_user = db.get_setting('auth_username')
        stored_hash = db.get_setting('auth_password_hash')
        if username == stored_user and check_password_hash(stored_hash, password):
            session.permanent = True
            session['logged_in'] = True
            return redirect(request.args.get('next') or url_for('index'))
        flash('Invalid username or password.', 'error')
    return render_template('login.html', quote=quotes.get_random())

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/change-password', methods=['GET', 'POST'])
def change_password():
    if request.method == 'POST':
        current  = request.form.get('current_password', '')
        new_pw   = request.form.get('new_password', '')
        confirm  = request.form.get('confirm_password', '')
        new_user = (request.form.get('username') or '').strip()
        stored_hash = db.get_setting('auth_password_hash')
        if not check_password_hash(stored_hash, current):
            flash('Current password is incorrect.', 'error')
        elif new_pw != confirm:
            flash('New passwords do not match.', 'error')
        elif len(new_pw) < 4:
            flash('Password must be at least 4 characters.', 'error')
        else:
            if new_user:
                db.set_setting('auth_username', new_user)
            if new_pw:
                db.set_setting('auth_password_hash', generate_password_hash(new_pw))
            flash('Credentials updated. Please log in again.', 'success')
            session.clear()
            return redirect(url_for('login'))
    current_user = db.get_setting('auth_username')
    return render_template('change_password.html', current_user=current_user)


# ── Characters ───────────────────────────────────────────────────────────────

@app.route('/characters')
def characters():
    chars = db.query("SELECT * FROM characters ORDER BY platform, name")
    return render_template('characters.html', chars=chars)

@app.route('/characters/add', methods=['POST'])
def characters_add():
    name      = fs('name')
    platform  = fs('platform', 'PC')
    char_type = fs('char_type', 'Playable')
    level     = fi('level', 1)
    notes     = fs('notes')
    if not name:
        flash('Name is required.', 'error')
        return redirect(url_for('characters'))
    db.execute(
        "INSERT INTO characters (name, platform, char_type, level, notes) VALUES (?,?,?,?,?)",
        (name, platform, char_type, level, notes)
    )
    flash(f'Character "{name}" added!', 'success')
    return redirect(url_for('characters'))

@app.route('/characters/<int:cid>/update', methods=['POST'])
def characters_update(cid):
    db.execute(
        "UPDATE characters SET name=?, platform=?, char_type=?, level=?, notes=? WHERE id=?",
        (fs('name'), fs('platform','PC'), fs('char_type','Playable'), fi('level',1), fs('notes'), cid)
    )
    flash('Character updated.', 'success')
    return redirect(url_for('characters'))

@app.route('/characters/<int:cid>/delete', methods=['POST'])
def characters_delete(cid):
    # Don't delete the last character
    count = db.get_one("SELECT COUNT(*) AS c FROM characters")
    if count and count['c'] <= 1:
        flash('Cannot delete the only character.', 'error')
        return redirect(url_for('characters'))
    # If deleting active character, switch to character 1 (or first available)
    if get_active_char_id() == cid:
        fallback = db.get_one("SELECT id FROM characters WHERE id != ? ORDER BY id LIMIT 1", (cid,))
        db.set_setting('active_character_id', str(fallback['id']) if fallback else '1')
    db.execute("DELETE FROM characters WHERE id=?", (cid,))
    flash('Character deleted.', 'info')
    return redirect(url_for('characters'))

@app.route('/characters/switch/<int:cid>', methods=['POST'])
def characters_switch(cid):
    row = db.get_one("SELECT id FROM characters WHERE id=?", (cid,))
    if row:
        db.set_setting('active_character_id', str(cid))
    return redirect(request.referrer or url_for('index'))


# ── Helpers ──────────────────────────────────────────────────────────────────

def fi(key, default=0):
    """Get form int value."""
    try:
        return int(request.form.get(key, default))
    except (ValueError, TypeError):
        return default

def ff(key, default=0.0):
    """Get form float value."""
    try:
        return float(request.form.get(key, default))
    except (ValueError, TypeError):
        return default

def fs(key, default=''):
    """Get form string value."""
    return request.form.get(key, default).strip()

def _inv_sync(source_table, source_id, name, category, sub_type, qty, weight, value, status, cid=None):
    """Create or update the inventory mirror entry for a section record."""
    if cid is None:
        cid = get_active_char_id()
    existing = db.get_one(
        "SELECT id FROM inventory WHERE source_table=? AND source_id=?",
        (source_table, source_id)
    )
    if existing:
        db.execute(
            "UPDATE inventory SET name=?,category=?,sub_type=?,qty=?,weight_each=?,value_each=?,status=?,character_id=? WHERE id=?",
            (name, category, sub_type, qty, weight, value, status, cid, existing['id'])
        )
    else:
        db.execute(
            "INSERT INTO inventory (name,category,sub_type,qty,weight_each,value_each,status,source_table,source_id,character_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (name, category, sub_type, qty, weight, value, status, source_table, source_id, cid)
        )

def _inv_delete(source_table, source_id):
    """Remove the inventory mirror for a deleted section record."""
    db.execute(
        "DELETE FROM inventory WHERE source_table=? AND source_id=?",
        (source_table, source_id)
    )

# ── Dashboard ────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    from datetime import date, timedelta
    cid   = get_active_char_id()
    stats = db.dashboard_stats(cid)
    # Mule dashboard: include vendor listings list
    stats['vendor_items_list'] = db.query(
        "SELECT name, qty, my_price FROM vendor_stock WHERE character_id=? ORDER BY category, name", (cid,)
    )
    silos = {r['silo']: r for r in db.query("SELECT * FROM nuke_codes ORDER BY silo")}
    today = date.today()
    today_week = str(today - timedelta(days=today.weekday()))
    # Season quick stats
    season_data = {
        'name':    db.get_setting('season_name'),
        'cur_rank': db.get_setting('current_rank'),
        'tgt_rank': db.get_setting('target_rank'),
        'cur_score': int(db.get_setting('current_score') or 0),
        'tgt_score': int(db.get_setting('target_score')  or 0),
        'days_left': None,
        'pct': 0,
    }
    try:
        from datetime import date as _date
        if season_data['tgt_score']:
            season_data['pct'] = min(100, round(season_data['cur_score'] / season_data['tgt_score'] * 100))
        end_str = db.get_setting('season_end')
        if end_str:
            season_data['days_left'] = max(0, (_date.fromisoformat(end_str) - _date.today()).days)
    except Exception:
        pass
    return render_template('index.html', stats=stats,
                           silos=silos, today_week=today_week,
                           season=season_data, quote=quotes.get_random())

# ── Search ───────────────────────────────────────────────────────────────────

@app.route('/search')
def search():
    q = request.args.get('q', '').strip()
    results = db.search_all(q) if len(q) >= 2 else []
    return render_template('search.html', q=q, results=results)

# ── Perk Cards ───────────────────────────────────────────────────────────────

@app.route('/perk-cards')
def perk_cards():
    cid = get_active_char_id()
    items = db.query("SELECT * FROM perk_cards WHERE character_id=? ORDER BY special, name", (cid,))
    edit_id = request.args.get('edit_id', type=int)
    edit_item = db.get_one("SELECT * FROM perk_cards WHERE id=?", (edit_id,)) if edit_id else None
    # Wiki perk browser data — all perks with ranks
    wiki_perks_rows = db.query(
        "SELECT p.name, p.special, p.is_legendary, p.max_rank, p.description, "
        "GROUP_CONCAT(r.rank || '|' || r.effect, '~~') as rank_data "
        "FROM wiki_perks p LEFT JOIN wiki_perk_ranks r ON r.perk_id=p.id "
        "GROUP BY p.id ORDER BY p.special, p.name"
    )
    # Build dict keyed by special for the browser
    from collections import defaultdict
    wiki_perks_by_special = defaultdict(list)
    for row in wiki_perks_rows:
        entry = dict(row)
        ranks = []
        if entry['rank_data']:
            for part in entry['rank_data'].split('~~'):
                if '|' in part:
                    rk, eff = part.split('|', 1)
                    ranks.append({'rank': int(rk), 'effect': eff})
        entry['ranks'] = ranks
        del entry['rank_data']
        grp = 'Legendary' if entry['is_legendary'] else entry['special']
        wiki_perks_by_special[grp].append(entry)
    logged_perks = {r['name'].lower() for r in db.query("SELECT name FROM perk_cards WHERE character_id=?", (cid,))}
    return render_template('perk_cards.html', items=items, edit_item=edit_item,
                           wiki_perks_by_special=dict(wiki_perks_by_special),
                           logged_perks=logged_perks)

@app.route('/perk-cards/add', methods=['POST'])
def perk_cards_add():
    db.execute(
        "INSERT INTO perk_cards (name,special,current_rank,max_rank,copies_owned,effect,used_in,can_scrap,notes,character_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (fs('name'), fs('special','S'), fi('current_rank',1), fi('max_rank',3),
         fi('copies_owned',1), fs('effect'), fs('used_in'), fs('can_scrap','No'), fs('notes'), get_active_char_id())
    )
    flash('Perk card added!', 'success')
    return redirect(url_for('perk_cards'))

@app.route('/perk-cards/<int:id>/update', methods=['POST'])
def perk_cards_update(id):
    db.execute(
        "UPDATE perk_cards SET name=?,special=?,current_rank=?,max_rank=?,copies_owned=?,effect=?,used_in=?,can_scrap=?,notes=? WHERE id=?",
        (fs('name'), fs('special','S'), fi('current_rank',1), fi('max_rank',3),
         fi('copies_owned',1), fs('effect'), fs('used_in'), fs('can_scrap','No'), fs('notes'), id)
    )
    flash('Perk card updated!', 'success')
    return redirect(url_for('perk_cards'))

@app.route('/perk-cards/<int:id>/delete', methods=['POST'])
def perk_cards_delete(id):
    db.execute("DELETE FROM perk_cards WHERE id=?", (id,))
    flash('Deleted.', 'info')
    return redirect(url_for('perk_cards'))

# ── Builds ───────────────────────────────────────────────────────────────────

@app.route('/builds')
def builds():
    cid = get_active_char_id()
    items = [dict(r) for r in db.query("SELECT *, (s+p+e+c+i+a+l) as total FROM builds WHERE character_id=? ORDER BY name", (cid,))]
    edit_id = request.args.get('edit_id', type=int)
    edit_item = db.get_one("SELECT * FROM builds WHERE id=?", (edit_id,)) if edit_id else None
    wiki_perks_list = [r['name'] for r in db.query("SELECT name FROM wiki_perks ORDER BY name")]
    # Mutations linked to builds
    mut_rows = db.query("SELECT build_id, name, effects_positive, effects_negative FROM mutations WHERE character_id=? AND build_id > 0", (cid,))
    mutations_by_build = {}
    for r in mut_rows:
        bid = r['build_id']
        mutations_by_build.setdefault(bid, []).append({
            'name': r['name'], 'pos': r['effects_positive'], 'neg': r['effects_negative']
        })
    # Weapons & armor for inventory picker and modal
    inv_weapons = [dict(r) for r in db.query("SELECT id, name, wtype, star1, star2, star3, star4, status, build_id FROM weapons WHERE character_id=? ORDER BY name", (cid,))]
    inv_armor   = [dict(r) for r in db.query("SELECT id, name, slot, material, star1, star2, star3, star4, status, build_id FROM armor WHERE character_id=? ORDER BY name", (cid,))]
    return render_template('builds.html', items=items, edit_item=edit_item,
                           wiki_perks_list=wiki_perks_list,
                           mutations_by_build=mutations_by_build,
                           inv_weapons=inv_weapons, inv_armor=inv_armor)

@app.route('/builds/add', methods=['POST'])
def builds_add():
    pcj = fs('perk_cards_json')
    db.execute(
        "INSERT INTO builds (name,playstyle,s,p,e,c,i,a,l,key_cards,notes,perk_cards_json,character_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (fs('name'), fs('playstyle'), fi('s',1), fi('p',1), fi('e',1), fi('c',1),
         fi('i',1), fi('a',1), fi('l',1), fs('key_cards'), fs('notes'), pcj, get_active_char_id())
    )
    build_id = db.query("SELECT last_insert_rowid() as id")[0]['id']
    _assign_build_gear(build_id, request.form.getlist('weapon_ids'), request.form.getlist('armor_ids'))
    flash('Build added!', 'success')
    return redirect(url_for('builds'))

@app.route('/builds/<int:id>/update', methods=['POST'])
def builds_update(id):
    pcj = fs('perk_cards_json')
    db.execute(
        "UPDATE builds SET name=?,playstyle=?,s=?,p=?,e=?,c=?,i=?,a=?,l=?,key_cards=?,notes=?,perk_cards_json=? WHERE id=?",
        (fs('name'), fs('playstyle'), fi('s',1), fi('p',1), fi('e',1), fi('c',1),
         fi('i',1), fi('a',1), fi('l',1), fs('key_cards'), fs('notes'), pcj, id)
    )
    _assign_build_gear(id, request.form.getlist('weapon_ids'), request.form.getlist('armor_ids'))
    flash('Build updated!', 'success')
    return redirect(url_for('builds'))

def _assign_build_gear(build_id, weapon_ids, armor_ids):
    """Clear old gear assignments for this build, then assign selected ones."""
    db.execute("UPDATE weapons SET build_id=0 WHERE build_id=?", (build_id,))
    db.execute("UPDATE armor   SET build_id=0 WHERE build_id=?", (build_id,))
    for wid in weapon_ids:
        if wid: db.execute("UPDATE weapons SET build_id=? WHERE id=?", (build_id, int(wid)))
    for aid in armor_ids:
        if aid: db.execute("UPDATE armor   SET build_id=? WHERE id=?", (build_id, int(aid)))

@app.route('/builds/<int:id>/delete', methods=['POST'])
def builds_delete(id):
    db.execute("DELETE FROM builds WHERE id=?", (id,))
    flash('Deleted.', 'info')
    return redirect(url_for('builds'))

# ── Character ─────────────────────────────────────────────────────────────────

@app.route('/character', methods=['GET', 'POST'])
def character():
    cid = get_active_char_id()
    if request.method == 'POST':
        db.execute(
            "UPDATE characters SET name=?, level=?, notes=?, active_build_id=?, "
            "special_s=?, special_p=?, special_e=?, special_c=?, special_i=?, special_a=?, special_l=? "
            "WHERE id=?",
            (
                fs('char_name'), fi('char_level', 1), fs('char_notes'),
                fi('char_build_id') or None,
                fi('char_special_s', 1), fi('char_special_p', 1), fi('char_special_e', 1),
                fi('char_special_c', 1), fi('char_special_i', 1), fi('char_special_a', 1),
                fi('char_special_l', 1), cid
            )
        )
        flash('Character saved!', 'success')
        return redirect(url_for('character'))
    char = db.get_one("SELECT * FROM characters WHERE id=?", (cid,))
    builds = db.query("SELECT id, name, playstyle FROM builds WHERE character_id=? ORDER BY name", (cid,))
    active_build = None
    if char and char['active_build_id']:
        active_build = db.get_one("SELECT * FROM builds WHERE id=?", (char['active_build_id'],))
    return render_template('character.html', char=char, builds=builds, active_build=active_build)

# ── Mutations ─────────────────────────────────────────────────────────────────

@app.route('/mutations')
def mutations():
    cid = get_active_char_id()
    filter_active = request.args.get('active', '')
    edit_id = request.args.get('edit_id', type=int)
    if filter_active == '1':
        items = db.query("SELECT * FROM mutations WHERE character_id=? AND active=1 ORDER BY name", (cid,))
    elif filter_active == '0':
        items = db.query("SELECT * FROM mutations WHERE character_id=? AND active=0 ORDER BY name", (cid,))
    else:
        items = db.query("SELECT * FROM mutations WHERE character_id=? ORDER BY active DESC, name", (cid,))
    edit_item = db.get_one("SELECT * FROM mutations WHERE id=?", (edit_id,)) if edit_id else None
    builds = db.query("SELECT id, name FROM builds WHERE character_id=? ORDER BY name", (cid,))
    wiki_rows = db.query("SELECT name, positive_effects, negative_effects, serum_name, wiki_url FROM wiki_mutations ORDER BY name")
    wiki_mutations = {r['name']: dict(r) for r in wiki_rows}
    logged_names = {r['name'].lower() for r in db.query("SELECT name FROM mutations WHERE character_id=?", (cid,))}
    return render_template('mutations.html', items=items, edit_item=edit_item,
                           filter_active=filter_active, builds=builds,
                           mutation_names=reference.MUTATION_NAMES,
                           wiki_mutations=wiki_mutations,
                           logged_names=logged_names)

@app.route('/mutations/add', methods=['POST'])
def mutations_add():
    db.execute(
        "INSERT INTO mutations (name,effects_positive,effects_negative,active,build_id,notes,character_id) VALUES (?,?,?,?,?,?,?)",
        (fs('name'), fs('effects_positive'), fs('effects_negative'),
         1 if request.form.get('active') else 0, fi('build_id'), fs('notes'), get_active_char_id())
    )
    flash('Mutation added!', 'success')
    return redirect(url_for('mutations'))

@app.route('/mutations/<int:id>/update', methods=['POST'])
def mutations_update(id):
    db.execute(
        "UPDATE mutations SET name=?,effects_positive=?,effects_negative=?,active=?,build_id=?,notes=? WHERE id=?",
        (fs('name'), fs('effects_positive'), fs('effects_negative'),
         1 if request.form.get('active') else 0, fi('build_id'), fs('notes'), id)
    )
    flash('Updated!', 'success')
    return redirect(url_for('mutations'))

@app.route('/mutations/<int:id>/delete', methods=['POST'])
def mutations_delete(id):
    db.execute("DELETE FROM mutations WHERE id=?", (id,))
    flash('Deleted.', 'info')
    return redirect(url_for('mutations'))

@app.route('/mutations/<int:id>/toggle', methods=['POST'])
def mutations_toggle(id):
    row = db.get_one("SELECT active FROM mutations WHERE id=?", (id,))
    if row:
        db.execute("UPDATE mutations SET active=? WHERE id=?", (0 if row['active'] else 1, id))
    return redirect(url_for('mutations'))

# ── Weapons ──────────────────────────────────────────────────────────────────

@app.route('/weapons')
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
    # Scan pre-fill params
    scan = {k: request.args.get(k, '') for k in
            ('scan_name','scan_wtype','scan_star1','scan_star2','scan_star3','scan_star4','scan_cond')}
    scan_active = any(scan.values())
    return render_template('weapons.html', items=items, edit_item=edit_item,
                           status_filter=status_filter, dupes=dupes,
                           scan=scan, scan_active=scan_active)

@app.route('/weapons/add', methods=['POST'])
def weapons_add():
    wid = db.insert(
        "INSERT INTO weapons (name,wtype,damage_type,star1,star2,star3,star4,mods,condition_pct,weight,value,status,notes,character_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (fs('name'), fs('wtype'), fs('damage_type','Ballistic'), fs('star1'), fs('star2'), fs('star3'), fs('star4'),
         fs('mods'), fi('condition_pct',100), ff('weight'), fi('value'), fs('status','Keep'), fs('notes'), get_active_char_id())
    )
    _inv_sync('weapons', wid, fs('name'), 'Weapon', fs('wtype'), 1, ff('weight'), fi('value'), fs('status','Keep'))
    flash('Weapon added!', 'success')
    return redirect(url_for('weapons'))

@app.route('/weapons/<int:id>/update', methods=['POST'])
def weapons_update(id):
    db.execute(
        "UPDATE weapons SET name=?,wtype=?,damage_type=?,star1=?,star2=?,star3=?,star4=?,mods=?,condition_pct=?,weight=?,value=?,status=?,notes=? WHERE id=?",
        (fs('name'), fs('wtype'), fs('damage_type','Ballistic'), fs('star1'), fs('star2'), fs('star3'), fs('star4'),
         fs('mods'), fi('condition_pct',100), ff('weight'), fi('value'), fs('status','Keep'), fs('notes'), id)
    )
    _inv_sync('weapons', id, fs('name'), 'Weapon', fs('wtype'), 1, ff('weight'), fi('value'), fs('status','Keep'))
    flash('Weapon updated!', 'success')
    return redirect(url_for('weapons'))

@app.route('/weapons/<int:id>/delete', methods=['POST'])
def weapons_delete(id):
    _inv_delete('weapons', id)
    db.execute("DELETE FROM weapons WHERE id=?", (id,))
    flash('Deleted.', 'info')
    return redirect(url_for('weapons'))

@app.route('/weapons/<int:id>/status', methods=['POST'])
def weapons_status(id):
    db.execute("UPDATE weapons SET status=? WHERE id=?", (fs('status'), id))
    return redirect(url_for('weapons'))

@app.route('/weapons/bulk', methods=['POST'])
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
    return redirect(url_for('weapons'))

# ── Armor ────────────────────────────────────────────────────────────────────

@app.route('/armor')
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

@app.route('/armor/add', methods=['POST'])
def armor_add():
    aid = db.insert(
        "INSERT INTO armor (name,slot,material,star1,star2,star3,star4,mods,dr,er,rr,weight,status,notes,character_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (fs('name'), fs('slot'), fs('material'), fs('star1'), fs('star2'), fs('star3'), fs('star4'),
         fs('mods'), fi('dr'), fi('er'), fi('rr'), ff('weight'), fs('status','Keep'), fs('notes'), get_active_char_id())
    )
    _inv_sync('armor', aid, fs('name'), 'Armor', fs('slot'), 1, ff('weight'), 0, fs('status','Keep'))
    flash('Armor added!', 'success')
    return redirect(url_for('armor'))

@app.route('/armor/<int:id>/update', methods=['POST'])
def armor_update(id):
    db.execute(
        "UPDATE armor SET name=?,slot=?,material=?,star1=?,star2=?,star3=?,star4=?,mods=?,dr=?,er=?,rr=?,weight=?,status=?,notes=? WHERE id=?",
        (fs('name'), fs('slot'), fs('material'), fs('star1'), fs('star2'), fs('star3'), fs('star4'),
         fs('mods'), fi('dr'), fi('er'), fi('rr'), ff('weight'), fs('status','Keep'), fs('notes'), id)
    )
    _inv_sync('armor', id, fs('name'), 'Armor', fs('slot'), 1, ff('weight'), 0, fs('status','Keep'))
    flash('Armor updated!', 'success')
    return redirect(url_for('armor'))

@app.route('/armor/<int:id>/delete', methods=['POST'])
def armor_delete(id):
    _inv_delete('armor', id)
    db.execute("DELETE FROM armor WHERE id=?", (id,))
    flash('Deleted.', 'info')
    return redirect(url_for('armor'))

@app.route('/armor/<int:id>/status', methods=['POST'])
def armor_status(id):
    db.execute("UPDATE armor SET status=? WHERE id=?", (fs('status'), id))
    return redirect(url_for('armor'))

@app.route('/armor/bulk', methods=['POST'])
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
    return redirect(url_for('armor'))

# ── Power Armor ───────────────────────────────────────────────────────────────

@app.route('/power-armor')
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

@app.route('/power-armor/add', methods=['POST'])
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
    return redirect(url_for('power_armor'))

@app.route('/power-armor/<int:id>/update', methods=['POST'])
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
    return redirect(url_for('power_armor'))

@app.route('/power-armor/<int:id>/delete', methods=['POST'])
def power_armor_delete(id):
    _inv_delete('power_armor', id)
    db.execute("DELETE FROM power_armor WHERE id=?", (id,))
    flash('Deleted.', 'info')
    return redirect(url_for('power_armor'))

@app.route('/power-armor/<int:id>/status', methods=['POST'])
def power_armor_status(id):
    status = fs('status', 'Keep')
    db.execute("UPDATE power_armor SET status=? WHERE id=?", (status, id))
    row = db.get_one("SELECT name, pa_set, slot, weight, value FROM power_armor WHERE id=?", (id,))
    if row:
        sub = (row['pa_set'] + ' ' + row['slot']).strip()
        _inv_sync('power_armor', id, row['name'], 'Power Armor', sub, 1, row['weight'], row['value'], status)
    return redirect(url_for('power_armor'))

@app.route('/power-armor/bulk', methods=['POST'])
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
    return redirect(url_for('power_armor'))

# ── Mods ─────────────────────────────────────────────────────────────────────

@app.route('/mods')
def mods():
    cid = get_active_char_id()
    items = db.query("SELECT * FROM mods WHERE character_id=? ORDER BY applies_to, name", (cid,))
    edit_id = request.args.get('edit_id', type=int)
    edit_item = db.get_one("SELECT * FROM mods WHERE id=?", (edit_id,)) if edit_id else None
    return render_template('mods.html', items=items, edit_item=edit_item)

@app.route('/mods/add', methods=['POST'])
def mods_add():
    mid = db.insert(
        "INSERT INTO mods (name,mod_type,applies_to,effect,qty,value_each,status,notes,character_id) VALUES (?,?,?,?,?,?,?,?,?)",
        (fs('name'), fs('mod_type','Normal'), fs('applies_to'), fs('effect'), fi('qty',1), fi('value_each'), fs('status','Keep'), fs('notes'), get_active_char_id())
    )
    sub = (fs('mod_type','Normal') + ' — ' + fs('applies_to')).strip(' —')
    _inv_sync('mods', mid, fs('name'), 'Mod', sub, fi('qty',1), 0, fi('value_each'), fs('status','Keep'))
    flash('Mod added!', 'success')
    return redirect(url_for('mods'))

@app.route('/mods/<int:id>/update', methods=['POST'])
def mods_update(id):
    db.execute(
        "UPDATE mods SET name=?,mod_type=?,applies_to=?,effect=?,qty=?,value_each=?,status=?,notes=? WHERE id=?",
        (fs('name'), fs('mod_type','Normal'), fs('applies_to'), fs('effect'), fi('qty',1), fi('value_each'), fs('status','Keep'), fs('notes'), id)
    )
    sub = (fs('mod_type','Normal') + ' — ' + fs('applies_to')).strip(' —')
    _inv_sync('mods', id, fs('name'), 'Mod', sub, fi('qty',1), 0, fi('value_each'), fs('status','Keep'))
    flash('Mod updated!', 'success')
    return redirect(url_for('mods'))

@app.route('/mods/<int:id>/delete', methods=['POST'])
def mods_delete(id):
    _inv_delete('mods', id)
    db.execute("DELETE FROM mods WHERE id=?", (id,))
    flash('Deleted.', 'info')
    return redirect(url_for('mods'))

@app.route('/mods/bulk', methods=['POST'])
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
    return redirect(url_for('mods'))

# ── Vendor ───────────────────────────────────────────────────────────────────

@app.route('/vendor')
def vendor():
    cid = get_active_char_id()
    items = db.query("SELECT * FROM vendor_stock WHERE character_id=? ORDER BY category, name", (cid,))
    edit_id = request.args.get('edit_id', type=int)
    edit_item = db.get_one("SELECT * FROM vendor_stock WHERE id=?", (edit_id,)) if edit_id else None
    return render_template('vendor.html', items=items, edit_item=edit_item)

@app.route('/vendor/add', methods=['POST'])
def vendor_add():
    name     = fs('name')
    category = fs('category')
    qty      = fi('qty', 1)
    price    = fi('my_price')
    notes    = fs('notes')

    cid = get_active_char_id()
    # Insert vendor record first
    vid = db.insert(
        "INSERT INTO vendor_stock (name,category,description,qty,my_price,avg_market_price,date_listed,notes,character_id) VALUES (?,?,?,?,?,?,?,?,?)",
        (name, category, fs('description'), qty, price, fi('avg_market_price'), fs('date_listed'), notes, cid)
    )

    if category == 'Weapon':
        # Create weapon record with bonus fields from vendor form
        wid = db.insert(
            "INSERT INTO weapons (name,wtype,star1,star2,star3,weight,value,status,notes,character_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (name, fs('wtype'), fs('star1'), fs('star2'), fs('star3'),
             ff('weight'), price, 'Sell', notes, cid)
        )
        _inv_sync('weapons', wid, name, 'Weapon', fs('wtype'), qty, ff('weight'), price, 'Sell')

    elif category == 'Armor':
        # Create armor record
        aid = db.insert(
            "INSERT INTO armor (name,slot,star1,star2,star3,weight,status,notes,character_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (name, fs('slot'), fs('star1'), fs('star2'), fs('star3'),
             ff('weight'), 'Sell', notes, cid)
        )
        _inv_sync('armor', aid, name, 'Armor', fs('slot'), qty, ff('weight'), 0, 'Sell')

    elif category == 'Mod':
        # Create mod record
        mid = db.insert(
            "INSERT INTO mods (name,mod_type,applies_to,qty,value_each,status,notes,character_id) VALUES (?,?,?,?,?,?,?,?)",
            (name, fs('mod_type','Normal'), fs('applies_to'), qty, price, 'Sell', notes, cid)
        )
        sub = (fs('mod_type','Normal') + ' — ' + fs('applies_to')).strip(' —')
        _inv_sync('mods', mid, name, 'Mod', sub, qty, 0, price, 'Sell')

    # Aid, Ammo, Plan, Misc etc. — vendor is tracked independently.
    # Inventory shows total owned; vendor shows what's listed. No auto-sync.

    flash('Added to vendor!', 'success')
    return redirect(url_for('vendor'))

@app.route('/vendor/<int:id>/update', methods=['POST'])
def vendor_update(id):
    db.execute(
        "UPDATE vendor_stock SET name=?,category=?,description=?,qty=?,my_price=?,avg_market_price=?,date_listed=?,notes=? WHERE id=?",
        (fs('name'), fs('category'), fs('description'), fi('qty',1), fi('my_price'),
         fi('avg_market_price'), fs('date_listed'), fs('notes'), id)
    )
    flash('Vendor item updated!', 'success')
    return redirect(url_for('vendor'))

@app.route('/vendor/<int:id>/delete', methods=['POST'])
def vendor_delete(id):
    row = db.get_one("SELECT name, category, qty FROM vendor_stock WHERE id=?", (id,))
    if row:
        category = row['category']
        if category in ('Weapon', 'Armor', 'Mod'):
            # Find the linked specialized record by name+status='Sell', then revert its inventory to Keep
            section_map = {'Weapon': 'weapons', 'Armor': 'armor', 'Mod': 'mods'}
            tbl = section_map[category]
            # Find the most recently created matching section record
            sec_row = db.get_one(
                "SELECT id FROM " + tbl + " WHERE name=? AND status='Sell' ORDER BY id DESC LIMIT 1",
                (row['name'],)
            )
            if sec_row:
                inv = db.get_one(
                    "SELECT id FROM inventory WHERE source_table=? AND source_id=?",
                    (tbl, sec_row['id'])
                )
                if inv:
                    db.execute("UPDATE inventory SET status='Keep' WHERE id=?", (inv['id'],))
        # else: Aid/Ammo/Misc — inventory is independent, no automatic update
    db.execute("DELETE FROM vendor_stock WHERE id=?", (id,))
    flash('Removed from vendor. Inventory updated.', 'info')
    return redirect(url_for('vendor'))

@app.route('/vendor/<int:id>/sold', methods=['POST'])
def vendor_sold(id):
    row = db.get_one("SELECT name, category FROM vendor_stock WHERE id=?", (id,))
    if row and row['category'] in ('Weapon', 'Armor', 'Mod'):
        section_map = {'Weapon': 'weapons', 'Armor': 'armor', 'Mod': 'mods'}
        tbl = section_map[row['category']]
        sec_row = db.get_one(
            "SELECT id FROM " + tbl + " WHERE name=? AND status='Sell' ORDER BY id DESC LIMIT 1",
            (row['name'],)
        )
        if sec_row:
            inv = db.get_one("SELECT id FROM inventory WHERE source_table=? AND source_id=?", (tbl, sec_row['id']))
            if inv:
                db.execute("DELETE FROM inventory WHERE id=?", (inv['id'],))
            db.execute("DELETE FROM " + tbl + " WHERE id=?", (sec_row['id'],))
    db.execute("DELETE FROM vendor_stock WHERE id=?", (id,))
    flash('Sold! Removed from inventory.', 'success')
    return redirect(url_for('vendor'))

@app.route('/vendor/wipe', methods=['POST'])
def vendor_wipe():
    items = db.query("SELECT name, category FROM vendor_stock")
    section_map = {'Weapon': 'weapons', 'Armor': 'armor', 'Mod': 'mods'}
    for row in items:
        if row['category'] in section_map:
            tbl = section_map[row['category']]
            sec_row = db.get_one(
                "SELECT id FROM " + tbl + " WHERE name=? AND status='Sell' ORDER BY id DESC LIMIT 1",
                (row['name'],)
            )
            if sec_row:
                inv = db.get_one("SELECT id FROM inventory WHERE source_table=? AND source_id=?", (tbl, sec_row['id']))
                if inv:
                    db.execute("DELETE FROM inventory WHERE id=?", (inv['id'],))
                db.execute("DELETE FROM " + tbl + " WHERE id=?", (sec_row['id'],))
    db.execute("DELETE FROM vendor_stock")
    flash('Vendor wiped. Items removed from inventory.', 'info')
    return redirect(url_for('vendor'))

# ── Price Research ───────────────────────────────────────────────────────────

@app.route('/prices')
def prices():
    q        = request.args.get('q', '').strip()
    page     = request.args.get('page', 1, type=int)
    per_page = 100
    offset   = (page - 1) * per_page
    like     = f'%{q}%'

    if q:
        total_count = db.get_one(
            "SELECT COUNT(*) as n FROM price_research WHERE item_name LIKE ?", (like,))['n']
        items = db.query(
            "SELECT * FROM price_research WHERE item_name LIKE ?"
            " ORDER BY item_name, created_at DESC LIMIT ? OFFSET ?",
            (like, per_page, offset))
    else:
        total_count = db.get_one("SELECT COUNT(*) as n FROM price_research")['n']
        items = db.query(
            "SELECT * FROM price_research ORDER BY item_name, created_at DESC LIMIT ? OFFSET ?",
            (per_page, offset))

    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page        = max(1, min(page, total_pages))

    if q:
        avgs = db.query("""
            SELECT item_name, COUNT(*) as cnt,
                   MIN(price_seen) as min_p, MAX(price_seen) as max_p,
                   ROUND(AVG(price_seen)) as avg_p,
                   ROUND(AVG(price_seen)*0.9) as suggested
            FROM price_research WHERE item_name LIKE ?
            GROUP BY item_name ORDER BY item_name
        """, (like,))
    else:
        avgs = db.query("""
            SELECT item_name, COUNT(*) as cnt,
                   MIN(price_seen) as min_p, MAX(price_seen) as max_p,
                   ROUND(AVG(price_seen)) as avg_p,
                   ROUND(AVG(price_seen)*0.9) as suggested
            FROM price_research
            GROUP BY item_name ORDER BY cnt DESC LIMIT 50
        """)
    edit_id   = request.args.get('edit_id', type=int)
    edit_item = db.get_one("SELECT * FROM price_research WHERE id=?", (edit_id,)) if edit_id else None
    alerts    = db.query("SELECT * FROM price_alerts WHERE active=1 ORDER BY item_name")
    alert_targets = {r['item_name']: r['target_price'] for r in alerts}
    return render_template('prices.html', items=items, avgs=avgs, edit_item=edit_item,
                           alerts=alerts, alert_targets=alert_targets,
                           total_count=total_count, page=page, total_pages=total_pages, q=q)

@app.route('/prices/add', methods=['POST'])
def prices_add():
    db.execute(
        "INSERT INTO price_research (item_name,category,description,price_seen,source,date_seen,notes) VALUES (?,?,?,?,?,?,?)",
        (fs('item_name'), fs('category'), fs('description'), fi('price_seen'),
         fs('source'), fs('date_seen'), fs('notes'))
    )
    flash('Price logged!', 'success')
    return redirect(url_for('prices'))

@app.route('/prices/<int:id>/update', methods=['POST'])
def prices_update(id):
    db.execute(
        "UPDATE price_research SET item_name=?,category=?,description=?,price_seen=?,source=?,date_seen=?,notes=? WHERE id=?",
        (fs('item_name'), fs('category'), fs('description'), fi('price_seen'),
         fs('source'), fs('date_seen'), fs('notes'), id)
    )
    flash('Price updated!', 'success')
    return redirect(url_for('prices'))

@app.route('/prices/<int:id>/copy', methods=['POST'])
def prices_copy(id):
    row = db.get_one("SELECT * FROM price_research WHERE id=?", (id,))
    if row:
        db.execute(
            "INSERT INTO price_research (item_name,category,description,price_seen,source,date_seen,notes) VALUES (?,?,?,?,?,?,?)",
            (row['item_name'], row['category'], row['description'], row['price_seen'],
             row['source'], row['date_seen'], row['notes'])
        )
        flash(f'Copied — edit the new entry below.', 'success')
    return redirect(url_for('prices', edit_id=db.get_one("SELECT MAX(id) as id FROM price_research")['id']))

@app.route('/prices/<int:id>/delete', methods=['POST'])
def prices_delete(id):
    db.execute("DELETE FROM price_research WHERE id=?", (id,))
    flash('Deleted.', 'info')
    return redirect(url_for('prices'))

@app.route('/prices/import', methods=['POST'])
def prices_import():
    f = request.files.get('csvfile')
    if not f or not f.filename.endswith('.csv'):
        flash('Please upload a .csv file.', 'error')
        return redirect(url_for('prices'))
    stream = io.StringIO(f.stream.read().decode('utf-8'))
    reader = csv.DictReader(stream)
    imported = 0
    skipped = 0
    for row in reader:
        name = (row.get('item_name') or '').strip()
        price_raw = (row.get('price_seen') or '0').strip()
        if not name:
            skipped += 1
            continue
        try:
            price = int(float(price_raw))
        except (ValueError, TypeError):
            price = 0
        db.execute(
            "INSERT INTO price_research (item_name,category,description,price_seen,source,date_seen,notes) VALUES (?,?,?,?,?,?,?)",
            (name,
             (row.get('category') or '').strip(),
             (row.get('description') or '').strip(),
             price,
             (row.get('source') or '').strip(),
             (row.get('date_seen') or '').strip(),
             (row.get('notes') or '').strip())
        )
        imported += 1
    flash(f'Imported {imported} price records. {skipped} rows skipped (no item name).', 'success')
    return redirect(url_for('prices'))

@app.route('/prices/alert/add', methods=['POST'])
def prices_alert_add():
    item_name = (request.form.get('item_name') or '').strip()
    try:
        target = int(float(request.form.get('target_price', 0) or 0))
    except (ValueError, TypeError):
        target = 0
    if item_name:
        existing = db.get_one("SELECT id FROM price_alerts WHERE item_name=?", (item_name,))
        if existing:
            db.execute("UPDATE price_alerts SET target_price=?, active=1 WHERE id=?",
                       (target, existing['id']))
        else:
            db.execute("INSERT INTO price_alerts (item_name, target_price) VALUES (?,?)",
                       (item_name, target))
        flash(f'Alert set: {item_name} @ {target:,} caps.', 'success')
    return redirect(url_for('prices'))

@app.route('/prices/alert/<int:aid>/delete', methods=['POST'])
def prices_alert_delete(aid):
    db.execute("DELETE FROM price_alerts WHERE id=?", (aid,))
    flash('Alert removed.', 'info')
    return redirect(url_for('prices'))

@app.route('/prices/chart-data')
def prices_chart_data():
    item = request.args.get('item', '').strip()
    if not item:
        return jsonify({'error': 'item required'}), 400
    rows = db.query(
        "SELECT date_seen, price_seen FROM price_research WHERE item_name=? ORDER BY date_seen, id",
        (item,)
    )
    labels = [r['date_seen'] for r in rows]
    prices = [r['price_seen'] for r in rows]
    avg = round(sum(prices) / len(prices)) if prices else 0
    return jsonify({'labels': labels, 'prices': prices, 'avg': avg, 'item': item})

# ── Plans ────────────────────────────────────────────────────────────────────

@app.route('/plans')
def plans():
    cid = get_active_char_id()
    items = db.query("SELECT * FROM plans WHERE character_id=? ORDER BY category, name", (cid,))
    edit_id = request.args.get('edit_id', type=int)
    edit_item = db.get_one("SELECT * FROM plans WHERE id=?", (edit_id,)) if edit_id else None
    # Unique plan names from price research not yet in plans tracker
    existing_plans = {r['name'].lower() for r in db.query("SELECT name FROM plans WHERE character_id=?", (cid,))}
    research_plans = db.query("""
        SELECT item_name, COUNT(*) as seen, ROUND(AVG(price_seen)) as avg_price
        FROM price_research WHERE category='Plan'
        GROUP BY LOWER(item_name) ORDER BY item_name
    """)
    importable = [dict(r) for r in research_plans
                  if r['item_name'].lower() not in existing_plans]
    return render_template('plans.html', items=items, edit_item=edit_item, importable=importable)

@app.route('/plans/add', methods=['POST'])
def plans_add():
    db.execute(
        "INSERT INTO plans (name,category,unlocks,learned,qty_unlearned,sell_price,status,notes,character_id) VALUES (?,?,?,?,?,?,?,?,?)",
        (fs('name'), fs('category'), fs('unlocks'),
         1 if request.form.get('learned') else 0,
         fi('qty_unlearned'), fi('sell_price'), fs('status','Keep'), fs('notes'), get_active_char_id())
    )
    flash('Plan added!', 'success')
    return redirect(url_for('plans'))

@app.route('/plans/<int:id>/update', methods=['POST'])
def plans_update(id):
    db.execute(
        "UPDATE plans SET name=?,category=?,unlocks=?,learned=?,qty_unlearned=?,sell_price=?,status=?,notes=? WHERE id=?",
        (fs('name'), fs('category'), fs('unlocks'),
         1 if request.form.get('learned') else 0,
         fi('qty_unlearned'), fi('sell_price'), fs('status','Keep'), fs('notes'), id)
    )
    flash('Plan updated!', 'success')
    return redirect(url_for('plans'))

@app.route('/plans/<int:id>/delete', methods=['POST'])
def plans_delete(id):
    db.execute("DELETE FROM plans WHERE id=?", (id,))
    flash('Deleted.', 'info')
    return redirect(url_for('plans'))

@app.route('/plans/bulk', methods=['POST'])
def plans_bulk():
    ids = request.form.getlist('ids')
    action = fs('bulk_action')
    if ids and action == 'delete':
        for i in ids:
            db.execute("DELETE FROM plans WHERE id=?", (int(i),))
    elif ids and action in ('Keep','Sell','Scrap'):
        for i in ids:
            db.execute("UPDATE plans SET status=? WHERE id=?", (action, int(i)))
    flash(f'Updated {len(ids)} items.', 'success')
    return redirect(url_for('plans'))

# ── Inventory ────────────────────────────────────────────────────────────────

@app.route('/inventory')
def inventory():
    cid = get_active_char_id()
    cat_filter = request.args.get('cat', '')
    edit_id = request.args.get('edit_id', type=int)
    if cat_filter:
        items = db.query("SELECT * FROM inventory WHERE character_id=? AND category=? ORDER BY name", (cid, cat_filter))
    else:
        items = db.query("SELECT * FROM inventory WHERE character_id=? ORDER BY category, name", (cid,))
    edit_item = db.get_one("SELECT * FROM inventory WHERE id=?", (edit_id,)) if edit_id else None
    # Vendor allocation lookup: (name, category) → qty currently listed in vendor
    vendor_qtys = {}
    for v in db.query("SELECT name, category, SUM(qty) as total FROM vendor_stock WHERE character_id=? GROUP BY name, category", (cid,)):
        vendor_qtys[(v['name'], v['category'])] = v['total']
    return render_template('inventory.html', items=items, edit_item=edit_item,
                           cat_filter=cat_filter, vendor_qtys=vendor_qtys)

@app.route('/inventory/add', methods=['POST'])
def inventory_add():
    db.execute(
        "INSERT INTO inventory (name,category,sub_type,qty,weight_each,value_each,status,notes,fo1st_stored,character_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (fs('name'), fs('category'), fs('sub_type'), fi('qty',1),
         ff('weight_each'), fi('value_each'), fs('status','Keep'), fs('notes'),
         1 if request.form.get('fo1st_stored') else 0, get_active_char_id())
    )
    flash('Item added!', 'success')
    return redirect(url_for('inventory'))

@app.route('/inventory/<int:id>/update', methods=['POST'])
def inventory_update(id):
    db.execute(
        "UPDATE inventory SET name=?,category=?,sub_type=?,qty=?,weight_each=?,value_each=?,status=?,notes=?,fo1st_stored=? WHERE id=?",
        (fs('name'), fs('category'), fs('sub_type'), fi('qty',1),
         ff('weight_each'), fi('value_each'), fs('status','Keep'), fs('notes'),
         1 if request.form.get('fo1st_stored') else 0, id)
    )
    flash('Updated!', 'success')
    return redirect(url_for('inventory'))

@app.route('/inventory/<int:id>/delete', methods=['POST'])
def inventory_delete(id):
    db.execute("DELETE FROM inventory WHERE id=?", (id,))
    flash('Deleted.', 'info')
    return redirect(url_for('inventory'))

@app.route('/inventory/bulk', methods=['POST'])
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
    return redirect(url_for('inventory'))

@app.route('/inventory/<int:id>/toggle-fo1st', methods=['POST'])
def inventory_toggle_fo1st(id):
    row = db.get_one("SELECT fo1st_stored FROM inventory WHERE id=?", (id,))
    if not row:
        return jsonify(error='not found'), 404
    new_val = 0 if row['fo1st_stored'] else 1
    db.execute("UPDATE inventory SET fo1st_stored=? WHERE id=?", (new_val, id))
    return jsonify(fo1st=new_val)

@app.route('/inventory/<int:id>/quick-update', methods=['POST'])
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

@app.route('/vendor/<int:id>/quick-update', methods=['POST'])
def vendor_quick_update(id):
    data = request.get_json(force=True)
    field = data.get('field')
    value = data.get('value')
    if field == 'qty':
        try:
            value = max(0, int(value))
        except (ValueError, TypeError):
            return jsonify(error='invalid'), 400
        db.execute("UPDATE vendor_stock SET qty=? WHERE id=?", (value, id))
    elif field == 'my_price':
        try:
            value = max(0, int(value))
        except (ValueError, TypeError):
            return jsonify(error='invalid'), 400
        db.execute("UPDATE vendor_stock SET my_price=? WHERE id=?", (value, id))
    else:
        return jsonify(error='unknown field'), 400
    return jsonify(ok=True, value=value)

# ── Challenges ───────────────────────────────────────────────────────────────

@app.route('/challenges')
def challenges():
    cid = get_active_char_id()
    ctype_filter = request.args.get('type', 'incomplete')
    edit_id = request.args.get('edit_id', type=int)
    ORDER = "CASE ctype WHEN 'Daily' THEN 1 WHEN 'Weekly' THEN 2 WHEN 'Season' THEN 3 ELSE 4 END, name"
    if ctype_filter == 'incomplete':
        items = db.query(f"SELECT * FROM challenges WHERE character_id=? AND completed=0 AND active=1 ORDER BY {ORDER}", (cid,))
    elif ctype_filter == 'done':
        items = db.query(f"SELECT * FROM challenges WHERE character_id=? AND completed=1 AND active=1 ORDER BY {ORDER}", (cid,))
    elif ctype_filter == 'dormant':
        items = db.query(f"SELECT * FROM challenges WHERE character_id=? AND active=0 ORDER BY {ORDER}", (cid,))
    elif ctype_filter in ('Daily','Weekly','Season','Static'):
        items = db.query(f"SELECT * FROM challenges WHERE character_id=? AND ctype=? AND active=1 ORDER BY completed, name", (cid, ctype_filter))
    else:
        items = db.query(f"SELECT * FROM challenges WHERE character_id=? AND active=1 ORDER BY completed, {ORDER}", (cid,))
    edit_item = db.get_one("SELECT * FROM challenges WHERE id=?", (edit_id,)) if edit_id else None
    counts = {
        'Daily':   db.get_one("SELECT COUNT(*) as n, SUM(completed) as done FROM challenges WHERE character_id=? AND ctype='Daily'  AND active=1", (cid,)),
        'Weekly':  db.get_one("SELECT COUNT(*) as n, SUM(completed) as done FROM challenges WHERE character_id=? AND ctype='Weekly' AND active=1", (cid,)),
        'Season':  db.get_one("SELECT COUNT(*) as n, SUM(completed) as done FROM challenges WHERE character_id=? AND ctype='Season' AND active=1", (cid,)),
        'Static':  db.get_one("SELECT COUNT(*) as n, SUM(completed) as done FROM challenges WHERE character_id=? AND ctype='Static' AND active=1", (cid,)),
        'dormant': db.get_one("SELECT COUNT(*) as n, 0 as done FROM challenges WHERE character_id=? AND active=0", (cid,)),
    }
    return render_template('challenges.html', items=items, edit_item=edit_item,
                           ctype_filter=ctype_filter, counts=counts)

@app.route('/challenges/add', methods=['POST'])
def challenges_add():
    db.execute(
        "INSERT INTO challenges (name,ctype,category,description,progress,target,completed,score_reward,atoms_reward,reward,repeatable,notes,character_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (fs('name'), fs('ctype','Daily'), fs('category'), fs('description'),
         fi('progress',0), fi('target',1), 1 if request.form.get('completed') else 0,
         fi('score_reward'), fi('atoms_reward'), fs('reward'),
         1 if request.form.get('repeatable') else 0, fs('notes'), get_active_char_id())
    )
    flash('Challenge added!', 'success')
    return redirect(url_for('challenges'))

@app.route('/challenges/<int:id>/update', methods=['POST'])
def challenges_update(id):
    db.execute(
        "UPDATE challenges SET name=?,ctype=?,category=?,description=?,progress=?,target=?,completed=?,score_reward=?,atoms_reward=?,reward=?,repeatable=?,notes=? WHERE id=?",
        (fs('name'), fs('ctype','Daily'), fs('category'), fs('description'),
         fi('progress',0), fi('target',1), 1 if request.form.get('completed') else 0,
         fi('score_reward'), fi('atoms_reward'), fs('reward'),
         1 if request.form.get('repeatable') else 0, fs('notes'), id)
    )
    flash('Challenge updated!', 'success')
    return redirect(url_for('challenges'))

@app.route('/challenges/<int:id>/delete', methods=['POST'])
def challenges_delete(id):
    db.execute("DELETE FROM challenges WHERE id=?", (id,))
    flash('Deleted.', 'info')
    return redirect(url_for('challenges'))

@app.route('/challenges/<int:id>/toggle', methods=['POST'])
def challenges_toggle(id):
    row = db.get_one("SELECT completed, name, repeatable, target FROM challenges WHERE id=?", (id,))
    new_val = 0 if row['completed'] else 1
    if new_val and row['repeatable']:
        # Repeatable: increment count, reset for next round
        db.execute(
            "UPDATE challenges SET times_completed=times_completed+1, progress=0, completed=0, completed_at='' WHERE id=?",
            (id,)
        )
        updated = db.get_one("SELECT times_completed FROM challenges WHERE id=?", (id,))
        return jsonify({'ok': True, 'completed': False, 'repeatable': True,
                        'times_completed': updated['times_completed'], 'target': row['target'], 'name': row['name']})
    elif new_val:
        db.execute("UPDATE challenges SET completed=1, completed_at=date('now'), times_completed=times_completed+1 WHERE id=?", (id,))
    else:
        db.execute("UPDATE challenges SET completed=0, completed_at='' WHERE id=?", (id,))
    return jsonify({'ok': True, 'completed': bool(new_val), 'name': row['name']})

@app.route('/challenges/<int:id>/increment', methods=['POST'])
def challenges_increment(id):
    db.execute("UPDATE challenges SET progress=MIN(progress+1, target) WHERE id=?", (id,))
    row = db.get_one("SELECT name, progress, target, repeatable FROM challenges WHERE id=?", (id,))
    completed = row['progress'] >= row['target']
    if completed and row['repeatable']:
        db.execute(
            "UPDATE challenges SET times_completed=times_completed+1, progress=0, completed=0, completed_at='' WHERE id=?",
            (id,)
        )
        updated = db.get_one("SELECT times_completed FROM challenges WHERE id=?", (id,))
        return jsonify({'ok': True, 'progress': 0, 'target': row['target'],
                        'completed': False, 'repeatable': True,
                        'times_completed': updated['times_completed'], 'name': row['name']})
    elif completed:
        db.execute("UPDATE challenges SET completed=1, completed_at=date('now'), times_completed=times_completed+1 WHERE id=?", (id,))
    return jsonify({'ok': True, 'progress': row['progress'], 'target': row['target'],
                    'completed': completed and not row['repeatable'], 'name': row['name']})

@app.route('/challenges/<int:id>/activate', methods=['POST'])
def challenges_activate(id):
    db.execute("UPDATE challenges SET active=1, completed=0, progress=0 WHERE id=?", (id,))
    return redirect(url_for('challenges', type='incomplete'))

@app.route('/challenges/reset/<ctype>', methods=['POST'])
def challenges_reset(ctype):
    label = {'daily': 'Daily', 'weekly': 'Weekly'}.get(ctype)
    if not label:
        return redirect(url_for('challenges'))
    # Track missed count for anything not completed this period
    # Track missed on non-repeatables that weren't completed
    db.execute("UPDATE challenges SET missed_count=missed_count+1 WHERE ctype=? AND completed=0 AND repeatable=0 AND active=1", (label,))
    # Non-repeatables: reset progress/completion for new period
    db.execute("UPDATE challenges SET completed=0, progress=0, completed_at='' WHERE ctype=? AND repeatable=0", (label,))
    # Repeatables: go dormant — must be manually reactivated for the new day
    db.execute("UPDATE challenges SET active=0, completed=0, progress=0, completed_at='' WHERE ctype=? AND repeatable=1", (label,))
    flash(f'{label} challenges reset. Repeatables are now dormant — reactivate when ready.', 'success')
    return redirect(url_for('challenges'))

# ── Quick Log (AJAX) ──────────────────────────────────────────────────────────

@app.route('/quick-log', methods=['POST'])
def quick_log():
    section = fs('ql_section', 'price')
    try:
        cid = get_active_char_id()
        if section == 'price':
            db.execute(
                "INSERT INTO price_research (item_name, category, price_seen, source, date_seen) VALUES (?,?,?,?,date('now'))",
                (fs('ql_item_name'), fs('ql_category'), fi('ql_price'), fs('ql_source', 'Vendor'))
            )
            msg = f"Price logged: {fs('ql_item_name')} — {fi('ql_price'):,} caps"
        elif section == 'weapon':
            wid = db.insert(
                "INSERT INTO weapons (name, wtype, star1, star2, star3, star4, status, character_id) VALUES (?,?,?,?,?,?,?,?)",
                (fs('ql_name'), fs('ql_wtype'), fs('ql_star1'), fs('ql_star2'), fs('ql_star3'), fs('ql_star4'), fs('ql_status','Keep'), cid)
            )
            _inv_sync('weapons', wid, fs('ql_name'), 'Weapon', fs('ql_wtype'), 1, 0, 0, fs('ql_status','Keep'), cid)
            msg = f"Weapon logged: {fs('ql_name')}"
        elif section == 'armor':
            aid = db.insert(
                "INSERT INTO armor (name, slot, star1, star2, star3, star4, status, character_id) VALUES (?,?,?,?,?,?,?,?)",
                (fs('ql_name'), fs('ql_slot'), fs('ql_star1'), fs('ql_star2'), fs('ql_star3'), fs('ql_star4'), fs('ql_status','Keep'), cid)
            )
            _inv_sync('armor', aid, fs('ql_name'), 'Armor', fs('ql_slot'), 1, 0, 0, fs('ql_status','Keep'), cid)
            msg = f"Armor logged: {fs('ql_name')}"
        elif section == 'plan':
            db.execute(
                "INSERT INTO plans (name, category, learned, qty_unlearned, character_id) VALUES (?,?,?,?,?)",
                (fs('ql_name'), fs('ql_category'),
                 1 if request.form.get('ql_learned') else 0, fi('ql_qty_unlearned'), cid)
            )
            msg = f"Plan logged: {fs('ql_name')}"
        elif section == 'inventory':
            db.execute(
                "INSERT INTO inventory (name, category, qty, status, character_id) VALUES (?,?,?,?,?)",
                (fs('ql_name'), fs('ql_category'), fi('ql_qty',1), fs('ql_status','Keep'), cid)
            )
            msg = f"Logged: {fs('ql_name')} x{fi('ql_qty',1)}"
        elif section == 'challenge':
            cid = fi('ql_challenge_id')
            if not cid:
                return jsonify({'ok': False, 'message': 'No challenge selected'})
            action = fs('ql_action', 'increment')
            if action == 'complete':
                db.execute("UPDATE challenges SET completed=1, completed_at=date('now'), times_completed=times_completed+1 WHERE id=?", (cid,))
                c = db.get_one("SELECT name FROM challenges WHERE id=?", (cid,))
                msg = f"Complete: {c['name']}"
            else:
                db.execute("UPDATE challenges SET progress=MIN(progress+1, target) WHERE id=?", (cid,))
                c = db.get_one("SELECT name, progress, target FROM challenges WHERE id=?", (cid,))
                msg = f"{c['name']}: {c['progress']}/{c['target']}"
                if c['progress'] >= c['target']:
                    db.execute("UPDATE challenges SET completed=1, completed_at=date('now'), times_completed=times_completed+1 WHERE id=?", (cid,))
        else:
            return jsonify({'ok': False, 'message': 'Unknown section'})
        return jsonify({'ok': True, 'message': msg})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)})

@app.route('/api/item-search')
def api_item_search():
    q = (request.args.get('q') or '').strip().lower()
    if len(q) < 2:
        return jsonify([])

    results = []

    def add_matches(names, category):
        for name in names:
            if q in name.lower():
                results.append({'name': name, 'category': category})

    add_matches(reference.PLAN_NAMES,  'Plan')
    add_matches(reference.FOOD_ITEMS,  'Food/Drink')
    add_matches(reference.CHEMS,       'Aid')
    add_matches(reference.AMMO_NAMES,  'Ammo')
    add_matches(reference.COMPONENTS,  'Component')
    add_matches(reference.MOD_NAMES,   'Mod')

    for w in db.query("SELECT name FROM wiki_weapons WHERE LOWER(name) LIKE ? LIMIT 15", (f'%{q}%',)):
        results.append({'name': w['name'], 'category': 'Weapon'})
    for a in db.query("SELECT name FROM wiki_armor WHERE LOWER(name) LIKE ? LIMIT 10", (f'%{q}%',)):
        results.append({'name': a['name'], 'category': 'Armor'})

    starts   = [r for r in results if r['name'].lower().startswith(q)]
    contains = [r for r in results if not r['name'].lower().startswith(q)]
    return jsonify((starts + contains)[:25])

@app.route('/api/challenges-active')
def api_challenges_active():
    rows = db.query("SELECT id, name, ctype, progress, target FROM challenges WHERE completed=0 ORDER BY ctype, name")
    return jsonify([dict(r) for r in rows])

@app.route('/api/challenges-repeatables')
def api_challenges_repeatables():
    rows = db.query("""
        SELECT id, name, ctype, progress, target, times_completed
        FROM challenges
        WHERE repeatable=1 AND ctype IN ('Daily','Weekly')
        ORDER BY ctype, name
    """)
    return jsonify([dict(r) for r in rows])

# ── Export CSV ───────────────────────────────────────────────────────────────

EXPORT_CONFIG = {
    'perk-cards':       ('perk_cards',      'Perk Cards'),
    'builds':           ('builds',          'Builds'),
    'weapons':          ('weapons',         'Weapons'),
    'armor':            ('armor',           'Armor'),
    'power-armor':      ('power_armor',     'Power Armor'),
    'mods':             ('mods',            'Mods'),
    'vendor':           ('vendor_stock',    'Vendor Stock'),
    'prices':           ('price_research',  'Price Research'),
    'plans':            ('plans',           'Plans'),
    'inventory':        ('inventory',       'Inventory'),
    'challenges':       ('challenges',      'Challenges'),
    'mutations':        ('mutations',       'Mutations'),
    'season-score-log': ('season_score_log','Season Score Log'),
    'caps-ledger':      ('caps_ledger',     'Caps Ledger'),
    'ammo':             ('ammo',            'Ammo Counter'),
    'legend-runs':      ('legend_runs',     'Legendary Runs'),
    'atom-shop':        ('atom_shop',       'Atom Shop Wishlist'),
}

@app.route('/craft-calc')
def craft_calc():
    return render_template('craft_calc.html')

# ── Build Generator ────────────────────────────────────────────────────────────
@app.route('/build-generator')
def build_generator():
    return render_template('build_generator.html')

@app.route('/build-generator/generate', methods=['POST'])
def build_generator_generate():
    data   = request.get_json()
    race   = data.get('race',   'Human')
    health = data.get('health', 'Full Health')
    weapon = data.get('weapon', 'Two-Handed Melee')
    notes  = data.get('notes',  '')

    bloodied_hint = "Focus on low-health perks: Nerd Rage, Serendipity, Dodgy, Blocker." if health == 'Bloodied' else ""
    ghoul_hint    = "Include Ghoulish and radiation perks since race is Ghoul." if race == 'Ghoul' else ""

    prompt = f"""You are a Fallout 76 expert. Generate an optimized build for:
Race: {race}
Health Style: {health}
Primary Weapon: {weapon}
Notes: {notes or 'None'}
{bloodied_hint}
{ghoul_hint}

Return ONLY valid JSON matching this structure exactly:
{{
  "name": "Short descriptive build name",
  "summary": "2-3 sentence overview",
  "special": {{"s":0,"p":0,"e":0,"c":0,"i":0,"a":0,"l":0}},
  "perk_cards": [
    {{"name":"Exact in-game perk name","special":"S","rank":3,"max_rank":3,"reason":"Why this perk at this rank"}}
  ],
  "legendary_perks": [
    {{"name":"Legendary perk name","rank":6,"max_rank":6,"reason":"Why and at what rank"}}
  ],
  "weapons": ["Weapon with legendary prefix and effects"],
  "armor": "Armor set with legendary effects",
  "mutations": ["Mutation name"],
  "playstyle_notes": "Detailed tips for this build"
}}

Rules:
- SPECIAL total must be exactly 56 (max 15 per stat, min 1)
- Include 12-15 perk cards — use EXACT in-game names, specify the recommended rank (not always max — some perks are only needed at rank 1, others at rank 3 for full effect) and the actual max_rank for that card
- Include 2-4 legendary perks (unlocked at level 50+, e.g. Legendary Charisma, Legendary Strength) with recommended rank (1-6, not always max)
- Return only the JSON object, no markdown, no explanation"""

    try:
        client   = _get_anthropic()
        response = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=2000,
            messages=[
                {'role': 'user',      'content': prompt},
                {'role': 'assistant', 'content': '{'}
            ]
        )
        text  = '{' + response.content[0].text.strip()
        text  = re.sub(r'```[\w]*\s*$', '', text).strip()
        build = json.loads(text)
        return jsonify({'success': True, 'build': build})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/build-generator/save', methods=['POST'])
def build_generator_save():
    data     = request.get_json()
    sp       = data.get('special', {})
    cards    = data.get('perk_cards', [])
    weapons  = ', '.join(data.get('weapons', []))
    armor    = data.get('armor', '')
    muts     = ', '.join(data.get('mutations', []))
    notes_parts = []
    if weapons: notes_parts.append(f"Weapons: {weapons}")
    if armor:   notes_parts.append(f"Armor: {armor}")
    if muts:    notes_parts.append(f"Mutations: {muts}")
    if data.get('playstyle_notes'): notes_parts.append(data['playstyle_notes'])
    try:
        leg_perks = data.get('legendary_perks', [])
        db.execute(
            "INSERT INTO builds (name,playstyle,s,p,e,c,i,a,l,key_cards,notes,perk_cards_json,legendary_perks_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (data.get('name','AI Build'), data.get('summary',''),
             sp.get('s',1), sp.get('p',1), sp.get('e',1), sp.get('c',1),
             sp.get('i',1), sp.get('a',1), sp.get('l',1),
             ', '.join(c['name'] for c in cards),
             '\n'.join(notes_parts),
             json.dumps(cards),
             json.dumps(leg_perks))
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ── Weapon Advisor ─────────────────────────────────────────────────────────────
@app.route('/weapon-advisor')
def weapon_advisor():
    try:
        weapons = db.query(
            "SELECT id, name, weapon_type, damage, fire_rate, range, ammo_type "
            "FROM wiki_weapons ORDER BY weapon_type, name"
        )
    except Exception:
        weapons = []
    # Group by type for the select dropdown
    grouped = {}
    for w in weapons:
        t = w['weapon_type'] or 'Other'
        grouped.setdefault(t, []).append(dict(w))
    return render_template('weapon_advisor.html', grouped=grouped)

@app.route('/weapon-advisor/analyze', methods=['POST'])
def weapon_advisor_analyze():
    data      = request.get_json()
    weapon_id = data.get('weapon_id')
    race      = data.get('race',   'Human')
    health    = data.get('health', 'Full Health')
    goals     = data.get('goals',  '').strip()

    # Pull weapon + mods from DB
    try:
        weapon = db.get_one(
            "SELECT name, weapon_type, damage, fire_rate, range, ammo_type "
            "FROM wiki_weapons WHERE id=?", (weapon_id,)
        )
        mods_rows = db.query(
            "SELECT slot, mod_name, description, is_default "
            "FROM wiki_weapon_mods WHERE weapon_id=? ORDER BY slot, id",
            (weapon_id,)
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

    if not weapon:
        return jsonify({'success': False, 'error': 'Weapon not found'}), 404

    # Format mods by slot for the prompt
    slots = {}
    for m in mods_rows:
        slots.setdefault(m['slot'], []).append(
            f"- {m['mod_name']}" +
            (f" (default)" if m['is_default'] else "") +
            (f" — {m['description']}" if m['description'] else "")
        )

    mods_block = ""
    for slot, entries in slots.items():
        if slot.lower() in ('appearance',):
            continue
        mods_block += f"\n[{slot}]\n" + "\n".join(entries) + "\n"

    if not mods_block.strip():
        mods_block = "No mod data available — use general FO76 knowledge for this weapon."

    prompt = f"""You are a Fallout 76 expert build advisor. Provide a full optimization guide.

WEAPON: {weapon['name']} ({weapon['weapon_type']})
Base Damage: {weapon['damage']} | Fire Rate: {weapon['fire_rate']} | Range: {weapon['range']} | Ammo: {weapon['ammo_type'] or 'N/A'}

AVAILABLE MODIFICATIONS:
{mods_block}

PLAYER PROFILE:
Race: {race}
Health Style: {health}
Goals/Notes: {goals or 'General optimization'}

Return ONLY valid JSON (no markdown, no explanation):
{{
  "weapon_summary": "2-3 sentences on this weapon's role and what makes it strong",
  "mod_recommendations": [
    {{
      "slot": "Slot name",
      "recommended": "Exact mod name",
      "reason": "Why this is optimal for the player's setup",
      "alternatives": [{{"mod": "mod name", "when": "situational reason"}}],
      "avoid": [{{"mod": "mod name", "why": "why to skip it"}}]
    }}
  ],
  "legendary_setup": {{
    "star1": "Legendary prefix",
    "star1_reason": "Why",
    "star1_alt": "Alternative prefix if budget/playstyle differs",
    "star2": "2nd star effect",
    "star2_reason": "Why",
    "star3": "3rd star effect",
    "star3_reason": "Why"
  }},
  "hidden_gems": [
    "Non-obvious tip or combo most players miss"
  ],
  "special": {{"s":0,"p":0,"e":0,"c":0,"i":0,"a":0,"l":0}},
  "perk_cards": [
    {{"name":"Exact perk name","special":"S","rank":2,"max_rank":3,"reason":"Why this perk at this specific rank"}}
  ],
  "legendary_perks": [
    {{"name":"Legendary perk name","rank":4,"max_rank":6,"reason":"Why and at what rank"}}
  ],
  "mutations": ["Mutation name"],
  "playstyle_notes": "Detailed tips for playing this build effectively"
}}

Rules:
- SPECIAL must total exactly 56 (each 1-15)
- 12-15 perk cards covering damage, survivability, QoL
- Use exact in-game perk and mutation names
- Specify the RECOMMENDED rank (not always max rank — e.g. Tenderizer is good at rank 1, some perks only need rank 1 for the key effect)
- Include 2-3 legendary perks (level 50+ cards like Legendary Strength, Electric Absorption) with recommended rank (1-6)
- For mod slots with no data, give recommendations from your FO76 knowledge
- hidden_gems: 2-4 non-obvious tips the average player wouldn't know"""

    try:
        client   = _get_anthropic()
        response = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=3000,
            messages=[
                {'role': 'user',      'content': prompt},
                {'role': 'assistant', 'content': '{'}
            ]
        )
        text  = '{' + response.content[0].text.strip()
        text  = re.sub(r'```[\w]*\s*$', '', text).strip()
        result = json.loads(text)
        result['weapon_name'] = weapon['name']
        result['weapon_type'] = weapon['weapon_type']
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/weapon-advisor/save-build', methods=['POST'])
def weapon_advisor_save_build():
    data  = request.get_json()
    sp    = data.get('special', {})
    cards = data.get('perk_cards', [])
    mods_chosen = data.get('mods_chosen', {})  # slot → mod_name

    notes_parts = [
        f"Weapon: {data.get('weapon_name','')}",
        f"Mods: {', '.join(f'{s}: {m}' for s,m in mods_chosen.items())}",
    ]
    leg = data.get('legendary_setup', {})
    if leg:
        notes_parts.append(
            f"Legendary: {leg.get('star1','')} / {leg.get('star2','')} / {leg.get('star3','')}"
        )
    if data.get('mutations'):
        notes_parts.append(f"Mutations: {', '.join(data['mutations'])}")
    if data.get('playstyle_notes'):
        notes_parts.append(data['playstyle_notes'])

    try:
        leg_perks = data.get('legendary_perks', [])
        db.execute(
            "INSERT INTO builds (name,playstyle,s,p,e,c,i,a,l,key_cards,notes,perk_cards_json,legendary_perks_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                data.get('build_name', f"{data.get('weapon_name','')} Build"),
                data.get('weapon_summary', ''),
                sp.get('s',1), sp.get('p',1), sp.get('e',1), sp.get('c',1),
                sp.get('i',1), sp.get('a',1), sp.get('l',1),
                ', '.join(c['name'] for c in cards),
                '\n'.join(notes_parts),
                json.dumps(cards),
                json.dumps(leg_perks)
            )
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/export')
def export():
    return render_template('export.html', sections=EXPORT_CONFIG)

@app.route('/export/<section>.csv')
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

# ── Wishlist ─────────────────────────────────────────────────────────────────

@app.route('/wishlist')
def wishlist():
    edit_item = None
    edit_id = request.args.get('edit_id', type=int)
    if edit_id:
        edit_item = db.get_one("SELECT * FROM wishlist WHERE id=?", (edit_id,))
    show = request.args.get('show', 'active')
    if show == 'found':
        items = db.query("SELECT * FROM wishlist WHERE found=1 ORDER BY created_at DESC")
    else:
        items = db.query("SELECT * FROM wishlist WHERE found=0 ORDER BY CASE priority WHEN 'High' THEN 1 WHEN 'Normal' THEN 2 ELSE 3 END, created_at DESC")
    return render_template('wishlist.html', items=items, edit_item=edit_item, show=show)

@app.route('/wishlist/add', methods=['POST'])
def wishlist_add():
    try:
        max_price = int(float(request.form.get('max_price') or 0))
    except (ValueError, TypeError):
        max_price = 0
    db.execute(
        "INSERT INTO wishlist (item_name,category,max_price,priority,description,notes) VALUES (?,?,?,?,?,?)",
        ((request.form.get('item_name') or '').strip(),
         (request.form.get('category') or '').strip(),
         max_price,
         request.form.get('priority') or 'Normal',
         (request.form.get('description') or '').strip(),
         (request.form.get('notes') or '').strip())
    )
    flash('Added to wishlist.', 'success')
    return redirect(url_for('wishlist'))

@app.route('/wishlist/<int:wid>/update', methods=['POST'])
def wishlist_update(wid):
    try:
        max_price = int(float(request.form.get('max_price') or 0))
    except (ValueError, TypeError):
        max_price = 0
    db.execute(
        "UPDATE wishlist SET item_name=?,category=?,max_price=?,priority=?,description=?,notes=? WHERE id=?",
        ((request.form.get('item_name') or '').strip(),
         (request.form.get('category') or '').strip(),
         max_price,
         request.form.get('priority') or 'Normal',
         (request.form.get('description') or '').strip(),
         (request.form.get('notes') or '').strip(),
         wid)
    )
    flash('Wishlist item updated.', 'success')
    return redirect(url_for('wishlist'))

@app.route('/wishlist/<int:wid>/found', methods=['POST'])
def wishlist_found(wid):
    db.execute("UPDATE wishlist SET found=1 WHERE id=?", (wid,))
    flash('Marked as found!', 'success')
    return redirect(url_for('wishlist'))

@app.route('/wishlist/<int:wid>/unfound', methods=['POST'])
def wishlist_unfound(wid):
    db.execute("UPDATE wishlist SET found=0 WHERE id=?", (wid,))
    return redirect(url_for('wishlist'))

@app.route('/wishlist/<int:wid>/delete', methods=['POST'])
def wishlist_delete(wid):
    db.execute("DELETE FROM wishlist WHERE id=?", (wid,))
    flash('Removed from wishlist.', 'success')
    return redirect(url_for('wishlist'))

# ── Caps Ledger ──────────────────────────────────────────────────────────────

@app.route('/caps')
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

@app.route('/caps/add', methods=['POST'])
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
    return redirect(url_for('caps'))

@app.route('/caps/<int:tid>/update', methods=['POST'])
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
    return redirect(url_for('caps'))

@app.route('/caps/<int:tid>/delete', methods=['POST'])
def caps_delete(tid):
    db.execute("DELETE FROM caps_sessions WHERE id=?", (tid,))
    flash('Deleted.', 'success')
    return redirect(url_for('caps'))

@app.route('/caps/goal', methods=['POST'])
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
    return redirect(url_for('caps'))

# ── Vendor Scan (AI image → CSV) ─────────────────────────────────────────────

SCAN_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vendor_scans')

_SCAN_PROMPT = """You are reading a Fallout 76 vendor shop screenshot.
Extract every item listed for sale. Return ONLY valid JSON — no markdown, no explanation.

Format:
{
  "vendor_name": "<vendor username shown at top, or empty string>",
  "items": [
    {"item_name": "<name>", "price": <integer caps>, "category": "<category>", "description": "<desc>"}
  ]
}

Rules:
- item_name: strip quantity like "(25)" or "(Known)" prefix. For standalone legendary mods, prefix with "Mod: ".
- price: integer only, no symbols.
- category: one of Weapon / Armor / Power Armor / Plan / Aid / Ammo / Apparel / Mod / Food/Drink / Misc
- description: legendary star rating as "1-star"/"2-star"/"3-star", or other notable detail, else empty string.
- If no vendor items visible, return {"vendor_name": "", "items": []}.
"""

def _extract_json(text):
    """Robustly pull JSON object from model response."""
    text = text.strip()
    start = text.find('{')
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i+1])
                except json.JSONDecodeError:
                    return None
    return None

def _scan_image(image_bytes, media_type, api_key, prompt=None):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    b64 = base64.standard_b64encode(image_bytes).decode('utf-8')
    msg = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=2048,
        messages=[{
            'role': 'user',
            'content': [
                {'type': 'image', 'source': {'type': 'base64', 'media_type': media_type, 'data': b64}},
                {'type': 'text', 'text': prompt or _SCAN_PROMPT},
            ]
        }]
    )
    return msg.content[0].text

@app.route('/vendor-scan', methods=['GET'])
def vendor_scan():
    api_key = db.get_setting('anthropic_api_key', '')
    return render_template('vendor_scan.html', api_key_set=bool(api_key))

@app.route('/vendor-scan/set-key', methods=['POST'])
def vendor_scan_set_key():
    key = (request.form.get('api_key') or '').strip()
    db.set_setting('anthropic_api_key', key)
    flash('API key saved.', 'success')
    return redirect(url_for('vendor_scan'))

@app.route('/vendor-scan/process', methods=['POST'])
def vendor_scan_process():
    api_key = db.get_setting('anthropic_api_key', '')
    if not api_key:
        flash('Set your Anthropic API key first.', 'error')
        return redirect(url_for('vendor_scan'))

    files = request.files.getlist('images')
    if not files or not files[0].filename:
        flash('No images uploaded.', 'error')
        return redirect(url_for('vendor_scan'))

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
        return redirect(url_for('vendor_scan'))

    # Build CSV
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

    # Check scanned items against wishlist
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

@app.route('/vendor-scan/download/<filename>')
def vendor_scan_download(filename):
    # Sanitize: only allow files in SCAN_OUTPUT_DIR
    safe = os.path.basename(filename)
    filepath = os.path.join(SCAN_OUTPUT_DIR, safe)
    if not os.path.isfile(filepath):
        return 'Not found', 404
    return send_file(filepath, as_attachment=True, download_name=safe)

# ── Backup ────────────────────────────────────────────────────────────────────

# ── Weapon Screenshot Scanner ─────────────────────────────────────────────────

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

@app.route('/weapons/scan', methods=['POST'])
def weapons_scan():
    api_key = db.get_setting('anthropic_api_key', '')
    if not api_key:
        flash('Set your Anthropic API key in Vendor Scan settings first.', 'error')
        return redirect(url_for('weapons'))
    f = request.files.get('scan_image')
    if not f or not f.filename:
        flash('No image uploaded.', 'error')
        return redirect(url_for('weapons'))
    MIME = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}
    ext = os.path.splitext(f.filename)[1].lower()
    media_type = MIME.get(ext, 'image/png')
    try:
        raw = _scan_image(f.read(), media_type, api_key, prompt=_WEAPON_SCAN_PROMPT)
        data = _extract_json(raw)
        if not data:
            flash('Could not parse weapon from image — add it manually.', 'error')
            return redirect(url_for('weapons'))
        return redirect(url_for('weapons',
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
        return redirect(url_for('weapons'))


# ── Inventory Screenshot Scan ─────────────────────────────────────────────────

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
- For Aid/Chems/Food: category is "Aid", "Chem", or "Food/Drink".
- For ammo (e.g. ".308 Rounds", "5mm Rounds"): category is "Ammo".
- For junk components (Steel, Aluminum, Wood, etc.): category is "Component".
- If item looks like a plan or recipe: category is "Plan".
- If unsure of category, use "Misc".
- Return ONLY a valid JSON array with no explanation.
- If no items are visible, return [].
"""

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


def _extract_json_array(text):
    """Pull a JSON array from model response."""
    text = text.strip()
    # Find first '[' and last ']'
    start = text.find('[')
    end   = text.rfind(']')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end+1])
        except Exception:
            pass
    # Fallback: try whole text
    try:
        return json.loads(text)
    except Exception:
        return None


@app.route('/inventory/scan', methods=['POST'])
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
        # Normalise fields
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


@app.route('/inventory/scan/import', methods=['POST'])
def inventory_scan_import():
    data = request.get_json(force=True)
    items = data.get('items', [])
    cid   = get_active_char_id()
    count = 0
    for item in items:
        name = (item.get('name') or '').strip()
        if not name:
            continue
        db.execute(
            "INSERT INTO inventory (name,category,sub_type,qty,weight_each,value_each,status,notes,fo1st_stored,character_id) "
            "VALUES (?,?,?,?,?,?,?,?,0,?)",
            (name, item.get('category','Misc'), '', max(1, int(item.get('qty') or 1)),
             round(float(item.get('weight_each') or 0), 3),
             max(0, int(item.get('value_each') or 0)),
             'Keep', item.get('notes',''), cid)
        )
        count += 1
    return jsonify(ok=True, count=count)


# ── Vendor Screenshot Scan ────────────────────────────────────────────────────

@app.route('/vendor/scan', methods=['POST'])
def vendor_scan_import_route():
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


@app.route('/vendor/scan/import', methods=['POST'])
def vendor_scan_import():
    data  = request.get_json(force=True)
    items = data.get('items', [])
    cid   = get_active_char_id()
    count = 0
    for item in items:
        name = (item.get('name') or '').strip()
        if not name:
            continue
        db.execute(
            "INSERT INTO vendor_stock (name,category,description,qty,my_price,avg_market_price,date_listed,notes,character_id) "
            "VALUES (?,?,?,?,?,0,date('now'),'',?)",
            (name, item.get('category','Misc'), item.get('description',''),
             max(1, int(item.get('qty') or 1)),
             max(0, int(item.get('my_price') or 0)), cid)
        )
        count += 1
    return jsonify(ok=True, count=count)


@app.route('/backup')
def backup():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fo76.db')
    size_kb = round(os.path.getsize(db_path) / 1024, 1) if os.path.isfile(db_path) else 0
    scan_dir = SCAN_OUTPUT_DIR
    scan_files = sorted(os.listdir(scan_dir)) if os.path.isdir(scan_dir) else []
    backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backups')
    auto_backups = sorted(os.listdir(backup_dir), reverse=True) if os.path.isdir(backup_dir) else []
    return render_template('backup.html', size_kb=size_kb, scan_files=scan_files, auto_backups=auto_backups)

@app.route('/backup/auto/<filename>')
def backup_download_auto(filename):
    safe = os.path.basename(filename)
    backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backups')
    filepath = os.path.join(backup_dir, safe)
    if not os.path.isfile(filepath):
        return 'Not found', 404
    return send_file(filepath, as_attachment=True, download_name=safe)

@app.route('/backup/download-db')
def backup_download_db():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fo76.db')
    today = datetime.now().strftime('%Y-%m-%d')
    return send_file(db_path, as_attachment=True, download_name=f'fo76_backup_{today}.db')

@app.route('/backup/download-zip')
def backup_download_zip():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fo76.db')
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


@app.route('/decode')
def decode():
    import reference as ref
    # Build reference table rows: one primary code per effect
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



# ── News / RSS ───────────────────────────────────────────────────────────────


# ── Season Tracker ────────────────────────────────────────────────────────────

@app.route('/season', methods=['GET', 'POST'])
def season():
    from datetime import date
    keys = ['season_name','season_end','current_rank','current_score',
            'target_rank','target_score','score_per_daily','score_per_weekly',
            'repeatable_per_day','bonus_score','stash_cap']
    if request.method == 'POST':
        for k in keys:
            db.set_setting(k, request.form.get(k, '').strip())
        flash('Season data saved!', 'success')
        return redirect(url_for('season'))
    data = {k: db.get_setting(k) for k in keys}
    # Pull Daily + Weekly challenge score totals from the challenge tracker
    ch = db.get_one("""
        SELECT
            COALESCE(SUM(CASE WHEN ctype='Daily'  AND repeatable=0 THEN score_reward ELSE 0 END), 0) AS daily_total,
            COALESCE(SUM(CASE WHEN ctype='Weekly' AND repeatable=0 THEN score_reward ELSE 0 END), 0) AS weekly_total,
            COALESCE(COUNT(CASE WHEN ctype='Daily'  AND repeatable=0 THEN 1 END), 0)                 AS daily_count,
            COALESCE(COUNT(CASE WHEN ctype='Weekly' AND repeatable=0 THEN 1 END), 0)                 AS weekly_count,
            COALESCE(SUM(CASE WHEN repeatable=1 AND ctype IN ('Daily','Weekly')
                              THEN times_completed * score_reward ELSE 0 END), 0)                    AS repeatable_earned
        FROM challenges
    """)
    ch_stats = dict(ch) if ch else {}
    calc = {}
    try:
        cur     = int(data['current_score']    or 0)
        tgt     = int(data['target_score']     or 0)
        spd     = int(data['score_per_daily']  or 0)
        spw     = int(data['score_per_weekly'] or 0)
        rpd     = int(data['repeatable_per_day'] or 0)
        bonus   = int(data['bonus_score']      or 0)
        raw_gap = max(0, tgt - cur)
        eff_gap = max(0, raw_gap - bonus)
        eff_daily = spd + (rpd * 150)
        calc['raw_gap']         = raw_gap
        calc['bonus']           = bonus
        calc['gap']             = eff_gap
        calc['eff_daily']       = eff_daily
        calc['pct']             = min(100, round(cur / tgt * 100)) if tgt else 0
        calc['dailies_needed']  = -(-eff_gap // eff_daily) if eff_daily else '?'
        calc['weeklies_needed'] = -(-eff_gap // spw)       if spw       else '?'
        if data['season_end']:
            end = date.fromisoformat(data['season_end'])
            days_left = (end - date.today()).days
            calc['days_left']  = max(0, days_left)
            calc['weeks_left'] = max(0, days_left) // 7
    except Exception:
        pass
    score_log = db.query("SELECT * FROM season_score_log ORDER BY log_date DESC LIMIT 30")
    actual_avg = 0
    if score_log:
        actual_avg = round(sum(r['score_earned'] for r in score_log) / len(score_log))
    calc['actual_avg'] = actual_avg
    return render_template('season.html', data=data, calc=calc, ch=ch_stats, score_log=score_log)

@app.route('/season/log', methods=['POST'])
def season_log():
    from datetime import date as _date
    db.execute(
        "INSERT INTO season_score_log (log_date, score_earned, notes) VALUES (?,?,?)",
        (fs('log_date') or str(_date.today()), fi('score_earned'), fs('notes'))
    )
    flash('Score logged!', 'success')
    return redirect(url_for('season'))

@app.route('/season/log/<int:id>/delete', methods=['POST'])
def season_log_delete(id):
    db.execute("DELETE FROM season_score_log WHERE id=?", (id,))
    flash('Entry deleted.', 'info')
    return redirect(url_for('season'))

# ── Nuke Codes ───────────────────────────────────────────────────────────────

@app.route('/nuke-codes')
def nuke_codes():
    from datetime import date, timedelta
    silos = {r['silo']: r for r in db.query("SELECT * FROM nuke_codes ORDER BY silo")}
    today = date.today()
    today_week = str(today - timedelta(days=today.weekday()))
    fetch_status  = db.get_setting('nuke_fetch_status', '')
    fetch_running = _nuke_fetch.get('running', False)
    return render_template('nuke_codes.html', silos=silos, today_week=today_week,
                           fetch_status=fetch_status, fetch_running=fetch_running)

@app.route('/nuke-codes/update', methods=['POST'])
def nuke_codes_update():
    from datetime import date
    # Find the most recent Monday as week_of
    today = date.today()
    week_of = str(today - __import__('datetime').timedelta(days=today.weekday()))
    for silo in ('Alpha', 'Bravo', 'Charlie'):
        code  = fs(f'code_{silo.lower()}')
        notes = fs(f'notes_{silo.lower()}')
        db.execute(
            "UPDATE nuke_codes SET code=?, notes=?, week_of=?, updated_at=date('now') WHERE silo=?",
            (code, notes, week_of, silo)
        )
    flash('Nuke codes updated!', 'success')
    return redirect(url_for('nuke_codes'))

@app.route('/nuke-codes/fetch', methods=['POST'])
def nuke_codes_fetch():
    if _nuke_fetch.get('running'):
        flash('Fetch already in progress — refresh in a moment.', 'warning')
        return redirect(url_for('nuke_codes'))
    _nuke_fetch['running'] = True
    db.set_setting('nuke_fetch_status', 'running|Contacting nukacrypt.com...')
    threading.Thread(target=_do_nuke_fetch, daemon=True).start()
    flash('Fetching codes in background — refresh in a few seconds.', 'info')
    return redirect(url_for('nuke_codes'))

# ── Ammo Counter ─────────────────────────────────────────────────────────────

@app.route('/ammo')
def ammo():
    cid = get_active_char_id()
    items = db.query("SELECT * FROM ammo WHERE character_id=? ORDER BY ammo_type", (cid,))
    edit_id = request.args.get('edit_id', type=int)
    edit_item = db.get_one("SELECT * FROM ammo WHERE id=?", (edit_id,)) if edit_id else None
    low = [r for r in items if r['low_threshold'] > 0 and r['qty'] < r['low_threshold']]
    return render_template('ammo.html', items=items, edit_item=edit_item, low=low)

@app.route('/ammo/add', methods=['POST'])
def ammo_add():
    db.execute(
        "INSERT INTO ammo (ammo_type, qty, low_threshold, notes, updated_at, character_id) VALUES (?,?,?,?,date('now'),?)",
        (fs('ammo_type'), fi('qty'), fi('low_threshold'), fs('notes'), get_active_char_id())
    )
    flash('Ammo added!', 'success')
    return redirect(url_for('ammo'))

@app.route('/ammo/<int:id>/update', methods=['POST'])
def ammo_update(id):
    db.execute(
        "UPDATE ammo SET ammo_type=?, qty=?, low_threshold=?, notes=?, updated_at=date('now') WHERE id=?",
        (fs('ammo_type'), fi('qty'), fi('low_threshold'), fs('notes'), id)
    )
    flash('Updated!', 'success')
    return redirect(url_for('ammo'))

@app.route('/ammo/<int:id>/delete', methods=['POST'])
def ammo_delete(id):
    db.execute("DELETE FROM ammo WHERE id=?", (id,))
    flash('Deleted.', 'info')
    return redirect(url_for('ammo'))

@app.route('/ammo/<int:id>/qty', methods=['POST'])
def ammo_qty(id):
    delta = fi('delta', 0)
    row = db.get_one("SELECT qty FROM ammo WHERE id=?", (id,))
    if row:
        new_qty = max(0, int(row['qty']) + delta)
        db.execute("UPDATE ammo SET qty=?, updated_at=date('now') WHERE id=?", (new_qty, id))
        return jsonify({'qty': new_qty})
    return jsonify({'qty': 0})

# ── Daily / Weekly Checklist ──────────────────────────────────────────────────

@app.route('/daily')
def daily():
    from datetime import date as _date
    today = str(_date.today())
    this_monday = str(_date.today() - timedelta(days=_date.today().weekday()))
    tasks = db.query("SELECT * FROM daily_tasks WHERE active=1 ORDER BY freq, sort_order, name")
    # Get completed task IDs for today (daily) and this week (weekly)
    done_daily = {r['task_id'] for r in db.query(
        "SELECT task_id FROM daily_completions WHERE completed_date=?", (today,)
    )}
    done_weekly = {r['task_id'] for r in db.query(
        "SELECT task_id FROM daily_completions WHERE completed_date >= ?", (this_monday,)
    )}
    return render_template('daily.html', tasks=tasks,
                           done_daily=done_daily, done_weekly=done_weekly,
                           today=today, this_monday=this_monday)

@app.route('/daily/complete/<int:tid>', methods=['POST'])
def daily_complete(tid):
    from datetime import date as _date
    task = db.get_one("SELECT freq FROM daily_tasks WHERE id=?", (tid,))
    if not task:
        return jsonify({'ok': False})
    today = str(_date.today())
    this_monday = str(_date.today() - timedelta(days=_date.today().weekday()))
    key_date = today if task['freq'] == 'daily' else this_monday
    existing = db.get_one(
        "SELECT id FROM daily_completions WHERE task_id=? AND completed_date=?",
        (tid, key_date)
    )
    if not existing:
        db.execute("INSERT INTO daily_completions (task_id, completed_date) VALUES (?,?)",
                   (tid, key_date))
    return jsonify({'ok': True, 'done': True})

@app.route('/daily/uncomplete/<int:tid>', methods=['POST'])
def daily_uncomplete(tid):
    from datetime import date as _date
    task = db.get_one("SELECT freq FROM daily_tasks WHERE id=?", (tid,))
    if not task:
        return jsonify({'ok': False})
    today = str(_date.today())
    this_monday = str(_date.today() - timedelta(days=_date.today().weekday()))
    key_date = today if task['freq'] == 'daily' else this_monday
    db.execute("DELETE FROM daily_completions WHERE task_id=? AND completed_date=?",
               (tid, key_date))
    return jsonify({'ok': True, 'done': False})

@app.route('/daily/task/add', methods=['POST'])
def daily_task_add():
    name = fs('name')
    freq = fs('freq', 'daily')
    if name:
        db.execute("INSERT INTO daily_tasks (name, freq) VALUES (?,?)", (name, freq))
        flash(f'Task "{name}" added!', 'success')
    return redirect(url_for('daily'))

@app.route('/daily/task/<int:tid>/delete', methods=['POST'])
def daily_task_delete(tid):
    db.execute("DELETE FROM daily_completions WHERE task_id=?", (tid,))
    db.execute("DELETE FROM daily_tasks WHERE id=?", (tid,))
    flash('Task removed.', 'info')
    return redirect(url_for('daily'))

# ── Legendary Run Tracker ─────────────────────────────────────────────────────

@app.route('/legend-runs')
def legend_runs():
    cid = get_active_char_id()
    from datetime import date as _date
    bosses = db.query("SELECT * FROM legend_runs WHERE character_id=? ORDER BY boss_name", (cid,))
    today = _date.today()
    boss_list = []
    for b in bosses:
        days_since = None
        if b['last_run']:
            try:
                last = _date.fromisoformat(b['last_run'])
                days_since = (today - last).days
            except Exception:
                pass
        boss_list.append({'row': b, 'days_since': days_since})
    return render_template('legend_runs.html', bosses=boss_list,
                           today=str(today))

@app.route('/legend-runs/log', methods=['POST'])
def legend_runs_log():
    from datetime import date as _date
    boss_id = fi('boss_id')
    run_date = fs('run_date') or str(_date.today())
    notes = fs('notes')
    db.execute(
        "UPDATE legend_runs SET last_run=?, run_count=run_count+1, notes=?, updated_at=date('now') WHERE id=?",
        (run_date, notes, boss_id)
    )
    flash('Run logged!', 'success')
    return redirect(url_for('legend_runs'))

@app.route('/legend-runs/add', methods=['POST'])
def legend_runs_add():
    name = fs('boss_name')
    if name:
        db.execute("INSERT INTO legend_runs (boss_name, character_id) VALUES (?,?)", (name, get_active_char_id()))
        flash(f'{name} added!', 'success')
    return redirect(url_for('legend_runs'))

@app.route('/legend-runs/<int:id>/delete', methods=['POST'])
def legend_runs_delete(id):
    db.execute("DELETE FROM legend_runs WHERE id=?", (id,))
    flash('Removed.', 'info')
    return redirect(url_for('legend_runs'))

@app.route('/legend-runs/<int:id>/reset', methods=['POST'])
def legend_runs_reset(id):
    db.execute("UPDATE legend_runs SET last_run='', run_count=0, notes='' WHERE id=?", (id,))
    flash('Reset.', 'info')
    return redirect(url_for('legend_runs'))


# ── Build Comparison ──────────────────────────────────────────────────────────

@app.route('/builds/compare')
def builds_compare():
    all_builds = db.query("SELECT * FROM builds ORDER BY name")
    b1_id = request.args.get('b1', type=int)
    b2_id = request.args.get('b2', type=int)
    b1 = db.get_one("SELECT * FROM builds WHERE id=?", (b1_id,)) if b1_id else None
    b2 = db.get_one("SELECT * FROM builds WHERE id=?", (b2_id,)) if b2_id else None
    return render_template('builds_compare.html', all_builds=all_builds, b1=b1, b2=b2)

# ── Atom Shop Wishlist ────────────────────────────────────────────────────────

@app.route('/atom-shop')
def atom_shop():
    items = db.query("SELECT * FROM atom_shop ORDER BY status, name")
    edit_id = request.args.get('edit_id', type=int)
    edit_item = db.get_one("SELECT * FROM atom_shop WHERE id=?", (edit_id,)) if edit_id else None
    atoms_balance = int(db.get_setting('atoms_balance', 0) or 0)
    return render_template('atom_shop.html', items=items, edit_item=edit_item,
                           atoms_balance=atoms_balance)

@app.route('/atom-shop/add', methods=['POST'])
def atom_shop_add():
    db.execute(
        "INSERT INTO atom_shop (name, category, cost_atoms, status, available, notes) VALUES (?,?,?,?,?,?)",
        (fs('name'), fs('category'), fi('cost_atoms'), fs('status','Want'),
         1 if request.form.get('available') else 0, fs('notes'))
    )
    flash('Added!', 'success')
    return redirect(url_for('atom_shop'))

@app.route('/atom-shop/<int:id>/update', methods=['POST'])
def atom_shop_update(id):
    db.execute(
        "UPDATE atom_shop SET name=?, category=?, cost_atoms=?, status=?, available=?, notes=? WHERE id=?",
        (fs('name'), fs('category'), fi('cost_atoms'), fs('status','Want'),
         1 if request.form.get('available') else 0, fs('notes'), id)
    )
    flash('Updated!', 'success')
    return redirect(url_for('atom_shop'))

@app.route('/atom-shop/<int:id>/status', methods=['POST'])
def atom_shop_status(id):
    db.execute("UPDATE atom_shop SET status=? WHERE id=?", (fs('status'), id))
    return redirect(url_for('atom_shop'))

@app.route('/atom-shop/<int:id>/delete', methods=['POST'])
def atom_shop_delete(id):
    db.execute("DELETE FROM atom_shop WHERE id=?", (id,))
    flash('Removed.', 'info')
    return redirect(url_for('atom_shop'))

@app.route('/atom-shop/balance', methods=['POST'])
def atom_shop_balance():
    db.set_setting('atoms_balance', str(fi('atoms_balance')))
    flash('Balance updated.', 'success')
    return redirect(url_for('atom_shop'))

# ── Trade Post Generator ──────────────────────────────────────────────────────

@app.route('/trade-post')
def trade_post():
    weapons = db.query(
        "SELECT *, 'weapon' as src_type FROM weapons WHERE status IN ('Sell','Trade') ORDER BY name"
    )
    armor = db.query(
        "SELECT *, 'armor' as src_type FROM armor WHERE status IN ('Sell','Trade') ORDER BY name"
    )
    plans = db.query(
        "SELECT * FROM plans WHERE qty_unlearned > 0 ORDER BY name"
    )
    mods = db.query(
        "SELECT * FROM mods WHERE status IN ('Sell','Trade') ORDER BY name"
    )
    return render_template('trade_post.html', weapons=weapons, armor=armor,
                           plans=plans, mods=mods)

# ── Analytics ─────────────────────────────────────────────────────────────────

@app.route('/analytics')
def analytics():
    return render_template('analytics.html')

@app.route('/analytics/data')
def analytics_data():
    conn = db.get_db()
    caps_rows = conn.execute(
        "SELECT session_date, end_caps FROM caps_sessions ORDER BY session_date, id"
    ).fetchall()
    price_rows = conn.execute("""
        SELECT strftime('%Y-W%W', created_at) as week, COUNT(*) as cnt
        FROM price_research GROUP BY week ORDER BY week DESC LIMIT 12
    """).fetchall()
    vendor_rows = conn.execute("""
        SELECT name, SUM(my_price * qty) as total_value
        FROM vendor_stock GROUP BY name ORDER BY total_value DESC LIMIT 10
    """).fetchall()
    price_list  = list(reversed([dict(r) for r in price_rows]))
    return jsonify({
        'caps':    {'labels': [r['session_date'] for r in caps_rows],  'values': [r['end_caps'] for r in caps_rows]},
        'prices':  {'labels': [r['week'] for r in price_list],         'values': [r['cnt'] for r in price_list]},
        'vendor':  {'labels': [r['name'] for r in vendor_rows],        'values': [r['total_value'] for r in vendor_rows]},
    })

# ── Fishing Tracker ───────────────────────────────────────────────────────────

_RARITY_ORDER = {'Generic':1,'Common':2,'Uncommon':3,'Glowing':4,'Local Legend':5,'Axolotl':6}

@app.route('/fishing')
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
    return render_template('fishing.html', species=species, log=log,
                           total_caught=total_caught, total_species=len(species),
                           biome_stats=biome_stats, log_total=log_total)

@app.route('/fishing/toggle/<int:sid>', methods=['POST'])
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
    return jsonify({'ok': True, 'caught': new_val})

@app.route('/fishing/log', methods=['POST'])
def fishing_log_add():
    from datetime import date as _date
    fish_name = fs('fish_name')
    if not fish_name:
        flash('Fish name required.', 'error')
        return redirect(url_for('fishing'))
    db.execute(
        "INSERT INTO fish_log (fish_name, rarity, biome, location, bait_used, weather, notes, caught_at, character_id) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (fish_name, fs('rarity'), fs('biome'), fs('location'),
         fs('bait_used'), fs('weather'), fs('notes'),
         fs('caught_at') or str(_date.today()), get_active_char_id())
    )
    # Auto-mark species as caught if it matches
    db.execute(
        "UPDATE fish_species SET caught=1, first_caught=COALESCE(NULLIF(first_caught,''), date('now')) "
        "WHERE name=? AND caught=0", (fish_name,)
    )
    flash(f'Logged: {fish_name}!', 'success')
    return redirect(url_for('fishing'))

@app.route('/fishing/log/<int:lid>/delete', methods=['POST'])
def fishing_log_delete(lid):
    db.execute("DELETE FROM fish_log WHERE id=?", (lid,))
    flash('Entry removed.', 'info')
    return redirect(url_for('fishing'))

# ── Legendary Mods ─────────────────────────────────────────────────────────────
@app.route('/legendary-mods')
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
    # Completion stats
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

@app.route('/legendary-mods/status', methods=['POST'])
def legendary_mods_status():
    """AJAX — cycle effect status: locked → seeking → unlocked → locked."""
    eid    = request.form.get('id', type=int)
    status = request.form.get('status', '')
    if eid and status in ('locked', 'seeking', 'unlocked'):
        db.execute("UPDATE legendary_effects SET status=? WHERE id=?", (status, eid))
    return ('', 204)

@app.route('/legendary-mods/count', methods=['POST'])
def legendary_mods_count():
    """AJAX — update mod_count for an effect."""
    eid   = request.form.get('id', type=int)
    count = request.form.get('count', type=int)
    if eid is not None and count is not None:
        db.execute("UPDATE legendary_effects SET mod_count=? WHERE id=?", (max(0, count), eid))
    return ('', 204)

@app.route('/legendary-mods/qty', methods=['POST'])
def legendary_mods_qty():
    """AJAX — update qty for mods_inventory or bobbleheads."""
    table = request.form.get('table')
    rid   = request.form.get('id', type=int)
    qty   = request.form.get('qty', type=int)
    if table == 'inventory' and rid is not None:
        db.execute("UPDATE legendary_mods_inventory SET qty=? WHERE id=?", (qty, rid))
    elif table == 'bobble' and rid is not None:
        db.execute("UPDATE bobbleheads SET qty=? WHERE id=?", (qty, rid))
    return ('', 204)

# ── Quick-add JSON endpoints (one-click from wiki references) ──────────────────
@app.route('/mutations/quick-add', methods=['POST'])
def mutations_quick_add():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'No name'}), 400
    existing = db.get_one("SELECT id, active FROM mutations WHERE LOWER(name)=LOWER(?)", (name,))
    if existing:
        return jsonify({'success': True, 'already_exists': True,
                        'id': existing['id'], 'active': existing['active']})
    db.execute(
        "INSERT INTO mutations (name, effects_positive, effects_negative, active, build_id, notes) VALUES (?,?,?,1,0,'')",
        (name, data.get('positive', ''), data.get('negative', ''))
    )
    return jsonify({'success': True, 'already_exists': False})


@app.route('/perk-cards/quick-add', methods=['POST'])
def perk_cards_quick_add():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'No name'}), 400
    existing = db.get_one("SELECT id FROM perk_cards WHERE LOWER(name)=LOWER(?)", (name,))
    if existing:
        return jsonify({'success': True, 'already_exists': True, 'id': existing['id']})
    db.execute(
        "INSERT INTO perk_cards (name, special, current_rank, max_rank, copies_owned, effect, used_in, can_scrap, notes) VALUES (?,?,?,?,1,?,'','No','')",
        (name, data.get('special', 'S'), data.get('rank', 1),
         data.get('max_rank', 3), data.get('effect', ''))
    )
    return jsonify({'success': True, 'already_exists': False})


@app.route('/plans/import-research', methods=['POST'])
def plans_import_research():
    data  = request.get_json()
    plans = data.get('plans', [])
    added = 0
    for p in plans:
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


@app.route('/armor/parse', methods=['POST'])
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


# ── Vendor Pricing Assistant ───────────────────────────────────────────────────
@app.route('/vendor-advisor')
def vendor_advisor():
    stock = db.query("""
        SELECT v.id, v.name, v.category, v.qty, v.my_price, v.notes,
               COUNT(p.id)            AS times_seen,
               ROUND(AVG(p.price_seen))  AS avg_seen,
               MIN(p.price_seen)         AS low_seen,
               MAX(p.price_seen)         AS high_seen
        FROM vendor_stock v
        LEFT JOIN price_research p
               ON LOWER(p.item_name) LIKE '%' || LOWER(v.name) || '%'
        GROUP BY v.id
        ORDER BY v.category, v.name
    """)
    return render_template('vendor_advisor.html', stock=[dict(r) for r in stock])


@app.route('/vendor-advisor/analyze', methods=['POST'])
def vendor_advisor_analyze():
    stock = db.query("""
        SELECT v.id, v.name, v.category, v.qty, v.my_price, v.notes,
               COUNT(p.id)               AS times_seen,
               ROUND(AVG(p.price_seen))  AS avg_seen,
               MIN(p.price_seen)         AS low_seen,
               MAX(p.price_seen)         AS high_seen
        FROM vendor_stock v
        LEFT JOIN price_research p
               ON LOWER(p.item_name) LIKE '%' || LOWER(v.name) || '%'
        GROUP BY v.id
        ORDER BY v.category, v.name
    """)

    lines = []
    for r in stock:
        mkt = (f"market avg {r['avg_seen']}c, low {r['low_seen']}c, high {r['high_seen']}c "
               f"({r['times_seen']} sightings)") if r['times_seen'] else "no market data recorded"
        price_str = f"{r['my_price']}c" if r['my_price'] else "unpriced (0c)"
        lines.append(f"- {r['name']} ({r['category']}, qty {r['qty']}): listed at {price_str} — {mkt}")

    prompt = f"""You are a Fallout 76 vendor pricing expert. Analyze this player's vendor stock against their market research data and give concrete pricing advice.

VENDOR STOCK vs MARKET DATA:
{chr(10).join(lines)}

For each item return one of these verdicts:
- "fair" — price is reasonable for the market
- "overpriced" — significantly above market avg, likely not selling
- "underpriced" — significantly below market avg, leaving caps on the table
- "raise" — unpriced (0c) or very low, should be listed higher
- "no_data" — not enough market data to judge

Be direct. If market avg is much lower than their price, say overpriced. If they have 0c listed, say raise.
Serums and mutations typically sell for 500-1500c. Plans vary wildly by rarity. Weapons depend heavily on legendary effects.

Return ONLY a valid JSON array (no markdown):
[
  {{
    "name": "Exact item name from the list",
    "verdict": "fair|overpriced|underpriced|raise|no_data",
    "suggested_price": 0,
    "reason": "One concise sentence explaining the verdict and suggested price"
  }}
]

Include every item from the list. suggested_price should be 0 if no_data."""

    try:
        client   = _get_anthropic()
        response = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=2000,
            messages=[
                {'role': 'user',      'content': prompt},
                {'role': 'assistant', 'content': '['}
            ]
        )
        text  = '[' + response.content[0].text.strip()
        text  = re.sub(r'```[\w]*\s*$', '', text).strip()
        advice = json.loads(text)
        return jsonify({'success': True, 'advice': advice})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Legendary Mod Optimizer ────────────────────────────────────────────────────
@app.route('/legendary-optimizer')
def legendary_optimizer():
    builds = db.query("SELECT id, name, playstyle FROM builds ORDER BY name")
    inv    = db.query("SELECT name, star_level, qty FROM legendary_mods_inventory WHERE qty > 0 ORDER BY star_level, name")
    craft  = db.query("SELECT name, star_level, requires_to_craft FROM legendary_craftable WHERE have_materials=1 ORDER BY star_level, name")
    return render_template('legendary_optimizer.html',
                           builds=[dict(b) for b in builds],
                           inv=[dict(r) for r in inv],
                           craftable=[dict(r) for r in craft])

@app.route('/legendary-optimizer/analyze', methods=['POST'])
def legendary_optimizer_analyze():
    data      = request.get_json()
    playstyle = data.get('playstyle', '').strip()
    item_type = data.get('item_type', 'weapon')   # 'weapon' or 'armor'
    build_id  = data.get('build_id')

    # Build context from saved build if selected
    build_ctx = ''
    if build_id:
        b = db.get_one("SELECT * FROM builds WHERE id=?", (build_id,))
        if b:
            b = dict(b)
            try:
                perks = json.loads(b.get('perk_cards_json') or '[]')
                perk_names = ', '.join(p['name'] for p in perks) if perks else b.get('key_cards','')
            except Exception:
                perk_names = b.get('key_cards', '')
            build_ctx = (f"Build: {b['name']}\nPlaystyle: {b['playstyle']}\n"
                         f"SPECIAL: S{b['s']} P{b['p']} E{b['e']} C{b['c']} I{b['i']} A{b['a']} L{b['l']}\n"
                         f"Key Perks: {perk_names}")

    # Format inventory by star level
    inv  = db.query("SELECT name, star_level, qty FROM legendary_mods_inventory WHERE qty > 0 ORDER BY star_level, name")
    cft  = db.query("SELECT name, star_level, requires_to_craft FROM legendary_craftable WHERE have_materials=1 ORDER BY star_level, name")

    inv_by_star  = {}
    for r in inv:
        inv_by_star.setdefault(r['star_level'], []).append(f"{r['name']} (x{r['qty']})")
    cft_by_star  = {}
    for r in cft:
        cft_by_star.setdefault(r['star_level'], []).append(f"{r['name']} (craft: {r['requires_to_craft']})")

    inv_lines = []
    for star in sorted(set(list(inv_by_star) + list(cft_by_star))):
        have = inv_by_star.get(star, [])
        can  = cft_by_star.get(star, [])
        if have: inv_lines.append(f"Star {star} IN INVENTORY: {', '.join(have)}")
        if can:  inv_lines.append(f"Star {star} CRAFTABLE NOW: {', '.join(can)}")

    stars_note = "1-star, 2-star, 3-star" if item_type == 'weapon' else "1-star, 2-star, 3-star, 4-star"

    prompt = f"""You are a Fallout 76 legendary mod expert.

PLAYER CONTEXT:
{build_ctx if build_ctx else f'Playstyle / goal: {playstyle}'}

LEGENDARY MODS AVAILABLE (inventory + craftable):
{chr(10).join(inv_lines) if inv_lines else 'No mods logged yet.'}

TASK: Recommend the best legendary mod combination for a {item_type} for this build.
Choose {stars_note}. ONLY recommend mods the player actually has in inventory or can craft right now.
If they are missing a clearly better option, note it under priority_note.

Return ONLY valid JSON (no markdown):
{{
  "assessment": "2-3 sentence summary of the recommended setup and its synergy with the build",
  "recommendations": [
    {{
      "star": 1,
      "mod": "Exact mod name",
      "reason": "Why this is the best choice for this star slot",
      "availability": "in_stock",
      "qty": 0
    }}
  ],
  "alternatives": [
    {{
      "star": 1,
      "mod": "Alternative mod name",
      "reason": "When this is better than the primary pick"
    }}
  ],
  "priority_note": "What to farm/craft first if anything is suboptimal"
}}

availability must be one of: in_stock, craftable, missing"""

    try:
        client   = _get_anthropic()
        response = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=1500,
            messages=[
                {'role': 'user',      'content': prompt},
                {'role': 'assistant', 'content': '{'}
            ]
        )
        text  = '{' + response.content[0].text.strip()
        text  = re.sub(r'```[\w]*\s*$', '', text).strip()
        result = json.loads(text)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Build Coach ─────────────────────────────────────────────────────────────────
@app.route('/build-coach')
def build_coach():
    builds = db.query("SELECT id, name, playstyle, s,p,e,c,i,a,l, key_cards, notes, perk_cards_json, legendary_perks_json FROM builds ORDER BY name")
    return render_template('build_coach.html', builds=[dict(b) for b in builds])

@app.route('/build-coach/analyze', methods=['POST'])
def build_coach_analyze():
    data     = request.get_json()
    build_id = data.get('build_id')
    if not build_id:
        return jsonify({'success': False, 'error': 'No build selected'}), 400

    b = db.get_one("SELECT * FROM builds WHERE id=?", (build_id,))
    if not b:
        return jsonify({'success': False, 'error': 'Build not found'}), 404
    b = dict(b)

    # Parse perk cards
    try:
        perks = json.loads(b.get('perk_cards_json') or '[]')
    except Exception:
        perks = []
    if not perks and b.get('key_cards'):
        perks = [{'name': n.strip(), 'rank': 1, 'max_rank': 3} for n in b['key_cards'].split(',') if n.strip()]

    perk_lines = '\n'.join(f"  - {p['name']} (Rank {p.get('rank',1)}/{p.get('max_rank',3)})" for p in perks) or '  None recorded'

    # Parse notes sections
    notes = b.get('notes', '') or ''
    weapons_line = next((l.replace('Weapons:','').strip() for l in notes.splitlines() if l.startswith('Weapons:')), '')
    armor_line   = next((l.replace('Armor:','').strip()   for l in notes.splitlines() if l.startswith('Armor:')),   '')
    muts_line    = next((l.replace('Mutations:','').strip() for l in notes.splitlines() if l.startswith('Mutations:')), '')

    # Legendary perks
    try:
        leg_perks = json.loads(b['legendary_perks_json'] or '[]')
    except Exception:
        leg_perks = []
    leg_lines = '\n'.join(f"  - {lp['name']} (Rank {lp.get('rank',1)}/{lp.get('max_rank',6)})" for lp in leg_perks) or '  None recorded'

    prompt = f"""You are a Fallout 76 build optimization expert. Analyze this build and provide specific, actionable coaching.

BUILD: {b['name']}
PLAYSTYLE: {b['playstyle'] or 'Not specified'}
SPECIAL: S{b['s']} P{b['p']} E{b['e']} C{b['c']} I{b['i']} A{b['a']} L{b['l']} (total: {sum([b['s'],b['p'],b['e'],b['c'],b['i'],b['a'],b['l']])})

PERK CARDS:
{perk_lines}

LEGENDARY PERKS:
{leg_lines}

WEAPONS: {weapons_line or 'Not specified'}
ARMOR: {armor_line or 'Not specified'}
MUTATIONS: {muts_line or 'Not specified'}

Provide concrete coaching. Be specific but BRIEF — one sentence per reason max. Limit perk_changes to top 5 most impactful. Limit special_suggestions to stats that actually need changing. Limit mutation_suggestions to top 3.

Return ONLY valid JSON (no markdown):
{{
  "assessment": "Honest 2-3 sentence overall evaluation — what works, what doesn't",
  "rating": 7,
  "special_suggestions": [
    {{
      "stat": "Strength",
      "current": 6,
      "suggested": 8,
      "reason": "Why to change this"
    }}
  ],
  "perk_changes": [
    {{
      "action": "add",
      "name": "Perk Name",
      "rank": 3,
      "special": "S",
      "reason": "Why to add this"
    }},
    {{
      "action": "remove",
      "name": "Perk Name",
      "reason": "Why to drop this"
    }},
    {{
      "action": "change_rank",
      "name": "Perk Name",
      "from_rank": 1,
      "to_rank": 3,
      "reason": "Why to change rank"
    }}
  ],
  "mutation_suggestions": [
    {{
      "action": "add",
      "name": "Mutation Name",
      "reason": "Why this mutation helps this build"
    }}
  ],
  "legendary_targets": "What legendary effects to aim for on weapons and armor",
  "priority": "Top 1-2 things to do first for the biggest improvement"
}}

rating is 1-10. action must be one of: add, remove, change_rank"""

    try:
        client   = _get_anthropic()
        response = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=3500,
            messages=[
                {'role': 'user',      'content': prompt},
                {'role': 'assistant', 'content': '{'}
            ]
        )
        if response.stop_reason == 'max_tokens':
            return jsonify({'success': False, 'error': 'Response too long — try a build with fewer perk cards.'}), 500
        text   = '{' + response.content[0].text.strip()
        text   = re.sub(r'```[\w]*\s*$', '', text).strip()
        result = json.loads(text)
        return jsonify({'success': True, 'result': result, 'build': dict(b)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Weapon Quick Parse ──────────────────────────────────────────────────────────
@app.route('/weapons/parse', methods=['POST'])
def weapons_parse():
    """Parse free-text item description into structured weapon fields."""
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


# ── World Finds ──────────────────────────────────────────────────────────────

WORLD_FINDS_UPLOAD = os.path.join(os.path.dirname(__file__), 'static', 'uploads', 'world_finds')
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
    """Save a list of uploaded files to world_finds upload dir. Returns list of filenames."""
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
    """Return list of screenshot rows for a find."""
    return db.query("SELECT * FROM world_find_screenshots WHERE find_id=? ORDER BY id", (find_id,))


@app.route('/world-finds')
@app.route('/world-finds/<filter_type>')
def world_finds(filter_type='all'):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
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
    # Build screenshot map {find_id: [row, ...]}
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


@app.route('/world-finds/add', methods=['POST'])
def world_finds_add():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
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
    return redirect(url_for('world_finds'))


@app.route('/world-finds/<int:id>/edit', methods=['POST'])
def world_finds_edit(id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
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
    return redirect(url_for('world_finds'))


@app.route('/world-finds/<int:find_id>/screenshot/<int:shot_id>/delete', methods=['POST'])
def world_finds_screenshot_delete(find_id, shot_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    row = db.get_one("SELECT filename FROM world_find_screenshots WHERE id=? AND find_id=?", (shot_id, find_id))
    if row:
        path = os.path.join(WORLD_FINDS_UPLOAD, row['filename'])
        if os.path.isfile(path):
            os.remove(path)
        db.execute("DELETE FROM world_find_screenshots WHERE id=?", (shot_id,))
    return redirect(url_for('world_finds', _anchor='') + f'?edit_id={find_id}#addPanel')


@app.route('/world-finds/<int:id>/delete', methods=['POST'])
def world_finds_delete(id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    for row in db.query("SELECT filename FROM world_find_screenshots WHERE find_id=?", (id,)):
        path = os.path.join(WORLD_FINDS_UPLOAD, row['filename'])
        if os.path.isfile(path):
            os.remove(path)
    db.execute("DELETE FROM world_find_screenshots WHERE find_id=?", (id,))
    db.execute("DELETE FROM world_finds WHERE id=?", (id,))
    flash('Find deleted.', 'info')
    return redirect(url_for('world_finds'))


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
