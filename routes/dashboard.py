"""Dashboard blueprint: index, search, analytics, session start/end."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from datetime import datetime, timedelta, date
import quotes
import db
from routes.helpers import get_active_char_id

bp = Blueprint('dashboard', __name__)


@bp.route('/')
def index():
    cid   = get_active_char_id()
    stats = db.dashboard_stats(cid)
    stats['vendor_items_list'] = db.query(
        "SELECT name, qty, my_price FROM vendor_stock WHERE character_id=? ORDER BY category, name", (cid,)
    )
    silos = {r['silo']: r for r in db.query("SELECT * FROM nuke_codes ORDER BY silo")}
    today = date.today()
    today_week = str(today - timedelta(days=today.weekday()))
    # Session mode data
    session_active = db.get_setting('session_active') == '1'
    session_start_str = db.get_setting('session_start', '')
    # Economy balances + today's earned
    econ_balances = {}
    econ_daily = {}
    today_str = str(today)
    for key in ('scrip', 'bullion', 'stamps', 'modules'):
        row = db.get_one("SELECT balance FROM economy_balance WHERE currency=? AND character_id=?", (key, cid))
        econ_balances[key] = row['balance'] if row else 0
        row = db.get_one("SELECT COALESCE(SUM(amount),0) as total FROM economy_log WHERE currency=? AND character_id=? AND txn_date=? AND amount>0", (key, cid, today_str))
        econ_daily[key] = row['total']
    # Active loadout
    active_loadout_id = int(db.get_setting(f'active_loadout_id_{cid}') or 0)
    lo_weapons = []
    lo_mutations = []
    lo_name = ''
    if active_loadout_id:
        lo = db.get_one("SELECT name FROM loadouts WHERE id=?", (active_loadout_id,))
        if lo:
            lo_name = lo['name']
            lo_weapons = db.query("SELECT w.name, w.wtype FROM weapons w JOIN loadout_weapons lw ON lw.weapon_id=w.id WHERE lw.loadout_id=?", (active_loadout_id,))
            lo_mutations = db.query("SELECT m.name FROM mutations m JOIN loadout_mutations lm ON lm.mutation_id=m.id WHERE lm.loadout_id=?", (active_loadout_id,))
    # Daily tasks with done status (for session mode) — uses FO76 noon reset
    from routes.helpers import fo76_today, fo76_this_monday
    tasks = db.query("SELECT * FROM daily_tasks WHERE active=1 ORDER BY freq, sort_order, name")
    done_daily = {r['task_id'] for r in db.query("SELECT task_id FROM daily_completions WHERE completed_date=?", (fo76_today(),))}
    done_weekly = {r['task_id'] for r in db.query("SELECT task_id FROM daily_completions WHERE completed_date >= ?", (fo76_this_monday(),))}
    # Cross-character summary
    cross_chars = db.query("""
        SELECT c.id, c.name, c.platform, c.char_type,
            (SELECT COUNT(*) FROM weapons w WHERE w.character_id=c.id AND w.status != 'Scrapped') as weapons,
            (SELECT COUNT(*) FROM armor a WHERE a.character_id=c.id AND a.status != 'Scrapped') as armor,
            (SELECT COUNT(*) FROM inventory i WHERE i.character_id=c.id AND i.source_table='') as inventory,
            (SELECT COUNT(*) FROM vendor_stock v WHERE v.character_id=c.id) as vendor_items,
            (SELECT COALESCE(SUM(v2.my_price * v2.qty),0) FROM vendor_stock v2 WHERE v2.character_id=c.id) as vendor_value,
            (SELECT COALESCE(SUM(CASE WHEN i2.fo1st_stored=0 THEN i2.qty * i2.weight_each ELSE 0 END),0)
             FROM inventory i2 WHERE i2.character_id=c.id AND i2.source_table='') as stash_weight
        FROM characters c ORDER BY c.platform, c.name
    """)
    return render_template('index.html', stats=stats,
                           silos=silos, today_week=today_week,
                           quote=quotes.get_random(),
                           session_active=session_active, session_start_str=session_start_str,
                           econ_balances=econ_balances, econ_daily=econ_daily,
                           active_loadout_id=active_loadout_id,
                           lo_name=lo_name, lo_weapons=lo_weapons, lo_mutations=lo_mutations,
                           session_tasks=tasks, done_daily=done_daily, done_weekly=done_weekly,
                           cross_chars=cross_chars)


@bp.route('/search')
def search():
    q = request.args.get('q', '').strip()
    results = db.search_all(q) if len(q) >= 2 else []
    return render_template('search.html', q=q, results=results)


@bp.route('/analytics')
def analytics():
    return render_template('analytics.html')

@bp.route('/analytics/data')
def analytics_data():
    cid = get_active_char_id()
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

    # Economy earnings per week (last 12 weeks)
    econ_rows = db.query("""
        SELECT strftime('%Y-W%W', txn_date) as week, currency,
               COALESCE(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),0) as earned
        FROM economy_log WHERE character_id=?
          AND txn_date >= date('now', '-84 days')
        GROUP BY week, currency ORDER BY week
    """, (cid,))
    econ_weeks = sorted(set(r['week'] for r in econ_rows))
    econ_by_week = {}
    for r in econ_rows:
        econ_by_week.setdefault(r['week'], {})[r['currency']] = r['earned']
    economy = {
        'weeks': econ_weeks,
        'scrip':   [econ_by_week.get(w, {}).get('scrip', 0) for w in econ_weeks],
        'bullion': [econ_by_week.get(w, {}).get('bullion', 0) for w in econ_weeks],
        'stamps':  [econ_by_week.get(w, {}).get('stamps', 0) for w in econ_weeks],
        'modules': [econ_by_week.get(w, {}).get('modules', 0) for w in econ_weeks],
    }

    # Session history (last 20)
    sess_rows = db.query("""
        SELECT started_at, duration_s, caps_delta, scrip_earned, bullion_earned, stamps_earned, tasks_done
        FROM session_history WHERE character_id=? ORDER BY started_at DESC LIMIT 20
    """, (cid,))
    sess_rows = list(reversed(sess_rows))
    sessions = {
        'labels':     [r['started_at'][:16].replace('T', ' ') for r in sess_rows],
        'durations':  [round(r['duration_s'] / 60) for r in sess_rows],
        'caps_delta': [r['caps_delta'] for r in sess_rows],
        'scrip':      [r['scrip_earned'] for r in sess_rows],
        'bullion':    [r['bullion_earned'] for r in sess_rows],
        'stamps':     [r['stamps_earned'] for r in sess_rows],
        'tasks':      [r['tasks_done'] for r in sess_rows],
    }

    # Daily completions per day (last 30 days)
    comp_rows = db.query("""
        SELECT completed_date, COUNT(*) as cnt
        FROM daily_completions
        WHERE completed_date >= date('now', '-30 days')
        GROUP BY completed_date ORDER BY completed_date
    """)
    completions = {
        'labels': [r['completed_date'] for r in comp_rows],
        'values': [r['cnt'] for r in comp_rows],
    }

    # Fish rarity distribution
    fish_rows = db.query("""
        SELECT rarity, COUNT(*) as cnt FROM fish_log
        WHERE character_id=? AND rarity != '' GROUP BY rarity ORDER BY cnt DESC
    """, (cid,))
    fish_rarity = {
        'labels': [r['rarity'] for r in fish_rows],
        'values': [r['cnt'] for r in fish_rows],
    }

    # Caps income vs expense per week (last 12 weeks)
    flow_rows = db.query("""
        SELECT strftime('%Y-W%W', txn_date) as week,
               COALESCE(SUM(CASE WHEN txn_type='income' THEN amount ELSE 0 END),0) as income,
               COALESCE(SUM(CASE WHEN txn_type='expense' THEN amount ELSE 0 END),0) as expense
        FROM caps_ledger WHERE character_id=?
          AND txn_date >= date('now', '-84 days')
        GROUP BY week ORDER BY week
    """, (cid,))
    caps_flow = {
        'weeks':   [r['week'] for r in flow_rows],
        'income':  [r['income'] for r in flow_rows],
        'expense': [r['expense'] for r in flow_rows],
    }

    # Legend run counts
    leg_rows = db.query("""
        SELECT boss_name, run_count FROM legend_runs
        WHERE character_id=? ORDER BY run_count DESC
    """, (cid,))
    legend = {
        'labels': [r['boss_name'] for r in leg_rows],
        'values': [r['run_count'] for r in leg_rows],
    }

    return jsonify({
        'caps':       {'labels': [r['session_date'] for r in caps_rows],  'values': [r['end_caps'] for r in caps_rows]},
        'prices':     {'labels': [r['week'] for r in price_list],         'values': [r['cnt'] for r in price_list]},
        'vendor':     {'labels': [r['name'] for r in vendor_rows],        'values': [r['total_value'] for r in vendor_rows]},
        'economy':    economy,
        'sessions':   sessions,
        'completions': completions,
        'fish_rarity': fish_rarity,
        'caps_flow':  caps_flow,
        'legend':     legend,
    })


@bp.route('/session/start', methods=['POST'])
def session_start():
    cid = get_active_char_id()
    db.set_setting('session_active', '1')
    db.set_setting('session_start', datetime.now().isoformat())
    db.set_setting('session_char_id', str(cid))
    return jsonify(ok=True)

@bp.route('/session/end', methods=['POST'])
def session_end():
    cid = get_active_char_id()
    start_str = db.get_setting('session_start', '')
    if not start_str:
        return jsonify(ok=False, error='No active session'), 400
    start_dt = datetime.fromisoformat(start_str)
    end_dt = datetime.now()
    duration_s = int((end_dt - start_dt).total_seconds())
    tasks_done = db.get_one(
        "SELECT COUNT(*) as cnt FROM daily_completions WHERE completed_at >= ?",
        (start_str,)
    )
    tasks_done = tasks_done['cnt'] if tasks_done else 0
    caps_delta_row = db.get_one(
        "SELECT COALESCE(SUM(CASE WHEN txn_type='income' THEN amount ELSE -amount END), 0) as delta "
        "FROM caps_ledger WHERE character_id=? AND created_at >= ?",
        (cid, start_str)
    )
    caps_delta = caps_delta_row['delta'] if caps_delta_row else 0
    scrip_earned = 0
    bullion_earned = 0
    stamps_earned = 0
    for r in db.query("SELECT currency, COALESCE(SUM(amount),0) as total FROM economy_log WHERE character_id=? AND created_at >= ? AND amount > 0 GROUP BY currency", (cid, start_str)):
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
        'stamps_earned': stamps_earned
    })
