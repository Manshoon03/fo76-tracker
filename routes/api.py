"""API blueprint: item search, challenge APIs, fish APIs, legend run APIs, caps APIs,
economy APIs, daily task APIs, session APIs."""
from flask import Blueprint, request, jsonify
from datetime import datetime, date
import db
from routes.helpers import fi, fs, get_active_char_id, fo76_today, fo76_this_monday

bp = Blueprint('api', __name__, url_prefix='/api')


@bp.route('/search')
def api_search():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    results = db.search_all(q)
    return jsonify(results)


@bp.route('/item-search')
def item_search():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    items = db.query(
        "SELECT DISTINCT item_name FROM price_research WHERE item_name LIKE ? ORDER BY item_name LIMIT 20",
        (f'%{q}%',)
    )
    return jsonify([r['item_name'] for r in items])


@bp.route('/challenge/<int:cid>/complete', methods=['POST'])
def challenge_complete(cid):
    db.execute("UPDATE challenges SET completed=1, completed_at=datetime('now') WHERE id=?", (cid,))
    return jsonify(ok=True)


@bp.route('/challenge/<int:cid>/uncomplete', methods=['POST'])
def challenge_uncomplete(cid):
    db.execute("UPDATE challenges SET completed=0, completed_at=NULL WHERE id=?", (cid,))
    return jsonify(ok=True)


# ── Fish APIs (companion) ───────────────────────────────────────────────────

@bp.route('/fish/species')
def fish_species():
    species = db.query("""
        SELECT id, name, rarity, biome, caught, catch_count
        FROM fish_species ORDER BY biome, name
    """)
    return jsonify([dict(r) for r in species])


@bp.route('/fish/log', methods=['POST'])
def fish_log():
    cid = get_active_char_id()
    data = request.get_json(force=True)
    fish_name = data.get('fish_name', '').strip()
    if not fish_name:
        return jsonify(ok=False, error='Fish name required'), 400
    db.execute(
        "INSERT INTO fish_log (fish_name, location, bait_used, caught_at, logged_at, character_id) "
        "VALUES (?,?,?,date('now'),datetime('now'),?)",
        (fish_name, data.get('location', ''), data.get('bait_used', ''), cid)
    )
    db.execute(
        "UPDATE fish_species SET caught=1, first_caught=COALESCE(NULLIF(first_caught,''), date('now')), "
        "catch_count = catch_count + 1 WHERE name=?", (fish_name,)
    )
    return jsonify(ok=True, message=f'Logged: {fish_name}!')


# ── Legend Run APIs (companion) ──────────────────────────────────────────────

@bp.route('/legend-runs/bosses')
def legend_runs_bosses():
    cid = get_active_char_id()
    bosses = db.query("SELECT id, boss_name, run_count, last_run FROM legend_runs WHERE character_id=? ORDER BY boss_name", (cid,))
    return jsonify([dict(r) for r in bosses])


@bp.route('/legend-run/log', methods=['POST'])
def legend_run_log():
    data = request.get_json(force=True)
    boss_id = data.get('boss_id')
    if not boss_id:
        return jsonify(ok=False, error='Boss ID required'), 400
    db.execute(
        "UPDATE legend_runs SET last_run=date('now'), run_count=run_count+1, updated_at=date('now') WHERE id=?",
        (boss_id,)
    )
    return jsonify(ok=True, message='Run logged!')


# ── Caps API (companion) ────────────────────────────────────────────────────

@bp.route('/caps/log', methods=['POST'])
def caps_log():
    cid = get_active_char_id()
    data = request.get_json(force=True)
    amount = data.get('amount', 0)
    txn_type = data.get('txn_type', 'income')
    category = data.get('category', '')
    description = data.get('description', '')
    if not amount:
        return jsonify(ok=False, error='Amount required'), 400
    db.execute(
        "INSERT INTO caps_ledger (txn_type, amount, category, description, character_id) VALUES (?,?,?,?,?)",
        (txn_type, abs(amount), category, description, cid)
    )
    sign = '+' if txn_type == 'income' else '-'
    return jsonify(ok=True, message=f'Caps {sign}{abs(amount)} logged!')


# ── Economy APIs (companion) ────────────────────────────────────────────────

@bp.route('/economy/currencies')
def economy_currencies():
    from routes.trading import ECONOMY_CURRENCIES
    result = {}
    cid = get_active_char_id()
    for key, info in ECONOMY_CURRENCIES.items():
        row = db.get_one("SELECT balance FROM economy_balance WHERE currency=? AND character_id=?", (key, cid))
        result[key] = {
            'label': info['label'],
            'icon': info['icon'],
            'quick': info['quick'],
            'balance': row['balance'] if row else 0,
        }
    return jsonify(result)


@bp.route('/economy/log', methods=['POST'])
def economy_log():
    from routes.trading import ECONOMY_CURRENCIES
    cid = get_active_char_id()
    data = request.get_json(force=True)
    currency = data.get('currency', '')
    amount = data.get('amount', 0)
    note = data.get('note', '')
    if currency not in ECONOMY_CURRENCIES or amount == 0:
        return jsonify(ok=False, error='Invalid currency or amount'), 400
    db.execute("INSERT INTO economy_log (currency, amount, note, character_id) VALUES (?,?,?,?)",
               (currency, amount, note, cid))
    existing = db.get_one("SELECT id, balance FROM economy_balance WHERE currency=? AND character_id=?", (currency, cid))
    if existing:
        new_bal = existing['balance'] + amount
        db.execute("UPDATE economy_balance SET balance=?, updated_at=datetime('now') WHERE id=?",
                   (new_bal, existing['id']))
    else:
        new_bal = amount
        db.execute("INSERT INTO economy_balance (currency, balance, character_id) VALUES (?,?,?)",
                   (currency, new_bal, cid))
    label = ECONOMY_CURRENCIES[currency]['label']
    sign = '+' if amount > 0 else ''
    return jsonify(ok=True, message=f'{label}: {sign}{amount}', balance=new_bal)


# ── Daily Task APIs (companion) ─────────────────────────────────────────────

@bp.route('/daily/tasks')
def daily_tasks():
    today = fo76_today()
    this_monday = fo76_this_monday()
    tasks = db.query("SELECT * FROM daily_tasks WHERE active=1 ORDER BY freq, sort_order, name")
    done_daily = {r['task_id'] for r in db.query(
        "SELECT task_id FROM daily_completions WHERE completed_date=?", (today,)
    )}
    done_weekly = {r['task_id'] for r in db.query(
        "SELECT task_id FROM daily_completions WHERE completed_date >= ?", (this_monday,)
    )}
    result = []
    for t in tasks:
        done = t['id'] in (done_daily if t['freq'] == 'daily' else done_weekly)
        result.append({'id': t['id'], 'name': t['name'], 'freq': t['freq'], 'done': done})
    return jsonify(result)


@bp.route('/daily/complete/<int:tid>', methods=['POST'])
def daily_complete(tid):
    task = db.get_one("SELECT freq FROM daily_tasks WHERE id=?", (tid,))
    if not task:
        return jsonify(ok=False, error='Task not found'), 404
    today = fo76_today()
    this_monday = fo76_this_monday()
    key_date = today if task['freq'] == 'daily' else this_monday
    existing = db.get_one(
        "SELECT id FROM daily_completions WHERE task_id=? AND completed_date=?",
        (tid, key_date)
    )
    if not existing:
        db.execute("INSERT INTO daily_completions (task_id, completed_date) VALUES (?,?)",
                   (tid, key_date))
    return jsonify(ok=True, done=True)


@bp.route('/daily/uncomplete/<int:tid>', methods=['POST'])
def daily_uncomplete(tid):
    task = db.get_one("SELECT freq FROM daily_tasks WHERE id=?", (tid,))
    if not task:
        return jsonify(ok=False, error='Task not found'), 404
    today = fo76_today()
    this_monday = fo76_this_monday()
    key_date = today if task['freq'] == 'daily' else this_monday
    db.execute("DELETE FROM daily_completions WHERE task_id=? AND completed_date=?",
               (tid, key_date))
    return jsonify(ok=True, done=False)


# ── Character APIs (companion) ──────────────────────────────────────────────

@bp.route('/characters')
def characters():
    chars = db.query("SELECT id, name, platform, char_type FROM characters ORDER BY platform, name")
    active_id = get_active_char_id()
    return jsonify(characters=[dict(r) for r in chars], active_id=active_id)


# ── Session APIs (companion) ────────────────────────────────────────────────

@bp.route('/session/start', methods=['POST'])
def session_start():
    data = request.get_json(force=True) if request.data else {}
    cid = data.get('character_id') or get_active_char_id()
    db.set_setting('session_active', '1')
    db.set_setting('session_start', datetime.now().isoformat())
    db.set_setting('session_char_id', str(cid))
    # Also set the active character so all other endpoints use it
    db.set_setting('active_character_id', str(cid))
    return jsonify(ok=True, character_id=cid)


@bp.route('/session/end', methods=['POST'])
def session_end():
    cid = get_active_char_id()
    start_str = db.get_setting('session_start', '')
    if not start_str:
        return jsonify(ok=False, error='No active session'), 400
    start_dt = datetime.fromisoformat(start_str)
    end_dt = datetime.now()
    duration_s = int((end_dt - start_dt).total_seconds())
    tasks_done_row = db.get_one(
        "SELECT COUNT(*) as cnt FROM daily_completions WHERE completed_at >= ?",
        (start_str,)
    )
    tasks_done = tasks_done_row['cnt'] if tasks_done_row else 0
    caps_delta_row = db.get_one(
        "SELECT COALESCE(SUM(CASE WHEN txn_type='income' THEN amount ELSE -amount END), 0) as delta "
        "FROM caps_ledger WHERE character_id=? AND created_at >= ?",
        (cid, start_str)
    )
    caps_delta = caps_delta_row['delta'] if caps_delta_row else 0
    scrip_earned = bullion_earned = stamps_earned = 0
    for r in db.query(
        "SELECT currency, COALESCE(SUM(amount),0) as total FROM economy_log "
        "WHERE character_id=? AND created_at >= ? AND amount > 0 GROUP BY currency",
        (cid, start_str)
    ):
        if r['currency'] == 'scrip': scrip_earned = r['total']
        elif r['currency'] == 'bullion': bullion_earned = r['total']
        elif r['currency'] == 'stamps': stamps_earned = r['total']
    db.execute(
        "INSERT INTO session_history (character_id, started_at, ended_at, duration_s, tasks_done, caps_delta, scrip_earned, bullion_earned, stamps_earned) VALUES (?,?,?,?,?,?,?,?,?)",
        (cid, start_str, end_dt.isoformat(), duration_s, tasks_done, caps_delta, scrip_earned, bullion_earned, stamps_earned)
    )
    db.set_setting('session_active', '0')
    db.set_setting('session_start', '')
    db.set_setting('session_char_id', '')
    hours = duration_s // 3600
    minutes = (duration_s % 3600) // 60
    dur_str = f'{hours}h {minutes}m' if hours else f'{minutes}m'
    return jsonify(ok=True, summary={
        'duration': dur_str, 'duration_s': duration_s,
        'tasks_done': tasks_done, 'caps_delta': caps_delta,
        'scrip_earned': scrip_earned, 'bullion_earned': bullion_earned,
        'stamps_earned': stamps_earned,
    })


@bp.route('/session/status')
def session_status():
    active = db.get_setting('session_active') == '1'
    start_str = db.get_setting('session_start', '')
    duration_s = 0
    if active and start_str:
        try:
            duration_s = int((datetime.now() - datetime.fromisoformat(start_str)).total_seconds())
        except Exception:
            pass
    return jsonify(ok=True, active=active, duration_s=duration_s)
