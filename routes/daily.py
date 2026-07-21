"""Daily blueprint: challenges, daily checklist, activities (formerly legend runs),
nuke codes, season, ammo."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from datetime import datetime, timedelta, date
import threading
import db
from routes.helpers import fs, fi, get_active_char_id

bp = Blueprint('daily', __name__)

# ── Nuke code background thread state ────────────────────────────────────────
_nuke_fetch = {}

def _do_nuke_fetch():
    """Background thread: scrape nukacrypt.com and update nuke codes in DB."""
    import re as _re
    _HDRS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36'}
    SILO_KEYS = {'alpha': 'Alpha', 'bravo': 'Bravo', 'charlie': 'Charlie'}
    _BAD = {'CHARLIE', 'ALPHA', 'BRAVO', 'SITE', 'LAUNCH', 'CODES', 'SILO', 'NUKE'}
    CODE_RE = _re.compile(r'\b([A-Z0-9]{7,10})\b')
    try:
        import requests
        from bs4 import BeautifulSoup
        codes = {}
        # --- Attempt 1: JSON API endpoint ---
        try:
            r = requests.get('https://nukacrypt.com/api/codes', headers=_HDRS, timeout=(5, 8))
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict):
                    for key, silo in SILO_KEYS.items():
                        val = str(data.get(key.upper(), data.get(key, ''))).strip()
                        if val and _re.match(r'^[A-Z0-9]{5,12}$', val.upper()) and val.upper() not in _BAD:
                            codes[silo] = val.upper()
                elif isinstance(data, list):
                    for item in data:
                        name = str(item.get('silo', item.get('name', ''))).lower()
                        code = str(item.get('code', item.get('value', ''))).upper().strip()
                        for key, silo in SILO_KEYS.items():
                            if key in name and _re.match(r'^[A-Z0-9]{5,12}$', code) and code not in _BAD:
                                codes[silo] = code
        except Exception:
            pass
        # --- Attempt 2: HTML page + embedded JSON ---
        if len(codes) < 3:
            try:
                r = requests.get('https://nukacrypt.com', headers=_HDRS, timeout=(5, 10))
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, 'html.parser')
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
            week_of = str(date.today() - timedelta(days=date.today().weekday()))
            for silo, code in codes.items():
                db.execute(
                    "UPDATE nuke_codes SET code=?, week_of=?, updated_at=date('now') WHERE silo=?",
                    (code, week_of, silo),
                )
            found = ', '.join(sorted(codes.keys()))
            db.set_setting('nuke_fetch_status', f'ok|Fetched {found} — {datetime.now().strftime("%b %d %H:%M")}')
            try:
                from routes.helpers import discord_notify
                code_list = ' / '.join(f'{s}: {c}' for s, c in sorted(codes.items()))
                discord_notify(None, embed={
                    'title': '☢ Nuke Codes Updated',
                    'description': code_list,
                    'color': 0xFF6600
                })
            except Exception:
                pass
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


# ── Challenges ───────────────────────────────────────────────────────────────

@bp.route('/challenges')
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
    total_score = db.get_one(
        "SELECT COALESCE(SUM(score_reward),0) as total FROM challenges "
        "WHERE character_id=? AND completed=1 AND active=1", (cid,)
    )['total']
    booster_pct = int(db.get_setting('score_booster_pct', '0'))
    return render_template('challenges.html', items=items, edit_item=edit_item,
                           ctype_filter=ctype_filter, counts=counts,
                           total_score=total_score, booster_pct=booster_pct)

@bp.route('/challenges/booster', methods=['POST'])
def challenges_booster():
    db.set_setting('score_booster_pct', str(fi('pct', 0)))
    return jsonify(ok=True)

@bp.route('/challenges/scan', methods=['POST'])
def challenges_scan():
    """Scan a screenshot of the challenges screen and return parsed challenges."""
    from routes.helpers import _scan_image, _extract_json
    api_key = db.get_setting('anthropic_api_key', '')
    if not api_key:
        return jsonify(ok=False, error='Set your Anthropic API key in Vendor Scan settings first.')
    f = request.files.get('image')
    if not f or not f.filename:
        return jsonify(ok=False, error='No image uploaded.')
    import os
    MIME = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}
    ext = os.path.splitext(f.filename)[1].lower()
    media_type = MIME.get(ext, 'image/png')
    prompt = """You are reading a Fallout 76 challenges screen screenshot (from the in-game menu).
Extract every challenge visible. Return ONLY valid JSON — no markdown, no explanation.

Format:
{
  "challenges": [
    {
      "name": "<challenge name>",
      "type": "<Daily, Weekly, Season, or Static>",
      "description": "<what to do, e.g. 'Kill 5 Super Mutants'>",
      "target": <integer goal number, default 1>,
      "score_reward": <SCORE points awarded, integer, default 250 for Daily / 1000 for Weekly>,
      "category": "<Combat/Exploration/Social/Crafting/Survival/Collection/Event or empty>"
    }
  ]
}

Rules:
- type: "Daily" if it resets daily. "Weekly" if it resets weekly. "Season" for seasonal/scoreboard challenges. "Static" for lifetime or permanent challenges.
- target: the number you need to reach (e.g. "Kill 5 enemies" → 5, "Complete an event" → 1)
- score_reward: read from the screenshot if visible. If not visible, default 250 for Daily, 1000 for Weekly.
- category: infer from the challenge description. Combat for kills, Exploration for locations, etc.
- If no challenges are visible, return {"challenges": []}
"""
    try:
        raw = _scan_image(f.read(), media_type, api_key, prompt=prompt)
        data = _extract_json(raw)
        if data is None or 'challenges' not in data:
            return jsonify(ok=False, error='Could not parse challenges from screenshot.')
        return jsonify(ok=True, challenges=data['challenges'])
    except Exception as e:
        return jsonify(ok=False, error=str(e)[:200])

@bp.route('/challenges/scan/import', methods=['POST'])
def challenges_scan_import():
    """Import scanned challenges."""
    cid = get_active_char_id()
    data = request.get_json()
    items = data.get('items', [])
    count = 0
    for item in items:
        db.execute(
            "INSERT INTO challenges (name,ctype,category,description,progress,target,completed,score_reward,atoms_reward,reward,repeatable,notes,character_id) VALUES (?,?,?,?,0,?,0,?,0,'',0,'',?)",
            (item.get('name', ''), item.get('type', 'Daily'), item.get('category', ''),
             item.get('description', ''), int(item.get('target', 1)),
             int(item.get('score_reward', 0)), cid)
        )
        count += 1
    return jsonify(ok=True, count=count)

@bp.route('/challenges/add', methods=['POST'])
def challenges_add():
    db.execute(
        "INSERT INTO challenges (name,ctype,category,description,progress,target,completed,score_reward,atoms_reward,reward,repeatable,notes,character_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (fs('name'), fs('ctype','Daily'), fs('category'), fs('description'),
         fi('progress',0), fi('target',1), 1 if request.form.get('completed') else 0,
         fi('score_reward'), fi('atoms_reward'), fs('reward'),
         1 if request.form.get('repeatable') else 0, fs('notes'), get_active_char_id())
    )
    flash('Challenge added!', 'success')
    return redirect(url_for('daily.challenges'))

@bp.route('/challenges/<int:id>/update', methods=['POST'])
def challenges_update(id):
    db.execute(
        "UPDATE challenges SET name=?,ctype=?,category=?,description=?,progress=?,target=?,completed=?,score_reward=?,atoms_reward=?,reward=?,repeatable=?,notes=? WHERE id=?",
        (fs('name'), fs('ctype','Daily'), fs('category'), fs('description'),
         fi('progress',0), fi('target',1), 1 if request.form.get('completed') else 0,
         fi('score_reward'), fi('atoms_reward'), fs('reward'),
         1 if request.form.get('repeatable') else 0, fs('notes'), id)
    )
    flash('Challenge updated!', 'success')
    return redirect(url_for('daily.challenges'))

@bp.route('/challenges/<int:id>/delete', methods=['POST'])
def challenges_delete(id):
    db.execute("DELETE FROM challenges WHERE id=?", (id,))
    flash('Deleted.', 'info')
    return redirect(url_for('daily.challenges'))

@bp.route('/challenges/<int:id>/toggle', methods=['POST'])
def challenges_toggle(id):
    row = db.get_one("SELECT completed, name, repeatable, target, progress, score_reward FROM challenges WHERE id=?", (id,))
    new_val = 0 if row['completed'] else 1
    db.execute("UPDATE challenges SET completed=?, completed_at=CASE WHEN ?=1 THEN datetime('now') ELSE NULL END WHERE id=?",
               (new_val, new_val, id))
    if new_val and row['repeatable']:
        db.execute("UPDATE challenges SET times_completed = times_completed + 1 WHERE id=?", (id,))
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        times = db.get_one("SELECT times_completed FROM challenges WHERE id=?", (id,))
        return jsonify(ok=True, completed=new_val, progress=row['progress'], target=row['target'],
                       score_reward=row['score_reward'] or 0, name=row['name'],
                       repeatable=bool(row['repeatable']),
                       times_completed=times['times_completed'] if times else 0)
    return redirect(url_for('daily.challenges', type='incomplete'))

@bp.route('/challenges/<int:id>/progress', methods=['POST'])
def challenges_progress(id):
    delta = fi('delta', 1)
    row = db.get_one("SELECT progress, target, score_reward, name, repeatable, times_completed FROM challenges WHERE id=?", (id,))
    if row:
        new_prog = max(0, row['progress'] + delta)
        completed = 1 if new_prog >= row['target'] else 0
        if completed and row['repeatable']:
            # Auto-reset repeatable challenges
            db.execute("UPDATE challenges SET progress=0, completed=0, times_completed=times_completed+1 WHERE id=?", (id,))
            updated = db.get_one("SELECT times_completed FROM challenges WHERE id=?", (id,))
            return jsonify(ok=True, progress=0, target=row['target'], completed=0,
                           score_reward=row['score_reward'] or 0, name=row['name'],
                           repeatable=True, times_completed=updated['times_completed'])
        else:
            db.execute("UPDATE challenges SET progress=?, completed=CASE WHEN ?>=target THEN 1 ELSE completed END WHERE id=?",
                       (new_prog, new_prog, id))
            return jsonify(ok=True, progress=new_prog, target=row['target'], completed=completed,
                           score_reward=row['score_reward'] or 0, name=row['name'],
                           repeatable=bool(row['repeatable']), times_completed=row['times_completed'] or 0)
    return jsonify(ok=False)

@bp.route('/challenges/reset/daily', methods=['POST'])
def challenges_reset_daily():
    cid = get_active_char_id()
    db.execute("DELETE FROM challenges WHERE character_id=? AND ctype='Daily' AND active=1", (cid,))
    flash('Daily challenges cleared — ready for new entries.', 'success')
    return redirect(url_for('daily.challenges'))

@bp.route('/challenges/reset/weekly', methods=['POST'])
def challenges_reset_weekly():
    cid = get_active_char_id()
    db.execute("DELETE FROM challenges WHERE character_id=? AND ctype='Weekly' AND active=1", (cid,))
    flash('Weekly challenges cleared — ready for new entries.', 'success')
    return redirect(url_for('daily.challenges'))

@bp.route('/challenges/<int:id>/dormant', methods=['POST'])
def challenges_dormant(id):
    db.execute("UPDATE challenges SET active=0 WHERE id=?", (id,))
    flash('Challenge moved to dormant.', 'info')
    return redirect(url_for('daily.challenges'))

@bp.route('/challenges/<int:id>/activate', methods=['POST'])
def challenges_activate(id):
    db.execute("UPDATE challenges SET active=1 WHERE id=?", (id,))
    flash('Challenge reactivated.', 'success')
    return redirect(url_for('daily.challenges'))

# ── Challenge Templates ──────────────────────────────────────────────────────

@bp.route('/challenges/templates')
def challenge_templates():
    cid = get_active_char_id()
    templates = db.query("SELECT * FROM challenge_templates WHERE character_id=? ORDER BY ctype, name", (cid,))
    edit_id = request.args.get('edit_id', type=int)
    edit_item = db.get_one("SELECT * FROM challenge_templates WHERE id=?", (edit_id,)) if edit_id else None
    return render_template('challenge_templates.html', templates=templates, edit_item=edit_item)

@bp.route('/challenges/templates/add', methods=['POST'])
def challenge_template_add():
    db.execute(
        "INSERT INTO challenge_templates (name,ctype,category,description,target,score_reward,atoms_reward,reward,repeatable,character_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (fs('name'), fs('ctype','Daily'), fs('category'), fs('description'),
         fi('target',1), fi('score_reward'), fi('atoms_reward'), fs('reward'),
         1 if request.form.get('repeatable') else 0, get_active_char_id())
    )
    flash('Template saved!', 'success')
    return redirect(url_for('daily.challenge_templates'))

@bp.route('/challenges/templates/<int:id>/update', methods=['POST'])
def challenge_template_update(id):
    db.execute(
        "UPDATE challenge_templates SET name=?,ctype=?,category=?,description=?,target=?,score_reward=?,atoms_reward=?,reward=?,repeatable=? WHERE id=?",
        (fs('name'), fs('ctype','Daily'), fs('category'), fs('description'),
         fi('target',1), fi('score_reward'), fi('atoms_reward'), fs('reward'),
         1 if request.form.get('repeatable') else 0, id)
    )
    flash('Template updated!', 'success')
    return redirect(url_for('daily.challenge_templates'))

@bp.route('/challenges/templates/<int:id>/delete', methods=['POST'])
def challenge_template_delete(id):
    db.execute("DELETE FROM challenge_templates WHERE id=?", (id,))
    flash('Template removed.', 'info')
    return redirect(url_for('daily.challenge_templates'))

@bp.route('/challenges/templates/save-from/<int:id>', methods=['POST'])
def challenge_template_save_from(id):
    """Save an existing challenge as a template."""
    row = db.get_one("SELECT * FROM challenges WHERE id=?", (id,))
    if row:
        db.execute(
            "INSERT INTO challenge_templates (name,ctype,category,description,target,score_reward,atoms_reward,reward,repeatable,character_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (row['name'], row['ctype'], row['category'], row['description'],
             row['target'], row['score_reward'], row['atoms_reward'], row['reward'],
             row['repeatable'], row['character_id'])
        )
        flash(f'Template saved from "{row["name"]}"!', 'success')
    return redirect(url_for('daily.challenge_templates'))

@bp.route('/challenges/templates/apply', methods=['POST'])
def challenge_templates_apply():
    """Bulk-insert selected templates as new challenges."""
    cid = get_active_char_id()
    ids = request.form.getlist('template_ids')
    count = 0
    for tid in ids:
        t = db.get_one("SELECT * FROM challenge_templates WHERE id=?", (int(tid),))
        if t:
            db.execute(
                "INSERT INTO challenges (name,ctype,category,description,progress,target,completed,score_reward,atoms_reward,reward,repeatable,notes,character_id) VALUES (?,?,?,?,0,?,0,?,?,?,?,?,?)",
                (t['name'], t['ctype'], t['category'], t['description'],
                 t['target'], t['score_reward'], t['atoms_reward'], t['reward'],
                 t['repeatable'], '', cid)
            )
            count += 1
    flash(f'{count} challenge(s) added from templates!', 'success')
    return redirect(url_for('daily.challenges'))


# ── Daily Checklist ──────────────────────────────────────────────────────────

@bp.route('/daily')
def daily_checklist():
    from routes.helpers import fo76_today, fo76_this_monday
    today = fo76_today()
    this_monday = fo76_this_monday()
    tasks = db.query("SELECT * FROM daily_tasks WHERE active=1 ORDER BY freq, sort_order, name")
    done_daily = {r['task_id'] for r in db.query(
        "SELECT task_id FROM daily_completions WHERE completed_date=?", (today,)
    )}
    done_weekly = {r['task_id'] for r in db.query(
        "SELECT task_id FROM daily_completions WHERE completed_date >= ?", (this_monday,)
    )}
    return render_template('daily.html', tasks=tasks,
                           done_daily=done_daily, done_weekly=done_weekly,
                           today=today, this_monday=this_monday)

@bp.route('/daily/complete/<int:tid>', methods=['POST'])
def daily_complete(tid):
    from routes.helpers import fo76_today, fo76_this_monday
    task = db.get_one("SELECT freq FROM daily_tasks WHERE id=?", (tid,))
    if not task:
        return jsonify({'ok': False})
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
    return jsonify({'ok': True, 'done': True})

@bp.route('/daily/uncomplete/<int:tid>', methods=['POST'])
def daily_uncomplete(tid):
    from routes.helpers import fo76_today, fo76_this_monday
    task = db.get_one("SELECT freq FROM daily_tasks WHERE id=?", (tid,))
    if not task:
        return jsonify({'ok': False})
    today = fo76_today()
    this_monday = fo76_this_monday()
    key_date = today if task['freq'] == 'daily' else this_monday
    db.execute("DELETE FROM daily_completions WHERE task_id=? AND completed_date=?",
               (tid, key_date))
    return jsonify({'ok': True, 'done': False})

@bp.route('/daily/task/add', methods=['POST'])
def daily_task_add():
    name = fs('name')
    freq = fs('freq', 'daily')
    if name:
        db.execute("INSERT INTO daily_tasks (name, freq) VALUES (?,?)", (name, freq))
        flash(f'Task "{name}" added!', 'success')
    return redirect(url_for('daily.daily_checklist'))

@bp.route('/daily/task/<int:tid>/delete', methods=['POST'])
def daily_task_delete(tid):
    db.execute("DELETE FROM daily_completions WHERE task_id=?", (tid,))
    db.execute("DELETE FROM daily_tasks WHERE id=?", (tid,))
    flash('Task removed.', 'info')
    return redirect(url_for('daily.daily_checklist'))


# ── Activities (formerly Legend Runs) ──────────────────────────────────────────

@bp.route('/activities')
def activities():
    cid = get_active_char_id()
    from datetime import date as _date
    type_filter = request.args.get('type', 'all')
    sql = "SELECT * FROM legend_runs WHERE character_id=?"
    params = [cid]
    if type_filter == 'boss':
        sql += " AND activity_type='Boss'"
    elif type_filter == 'event':
        sql += " AND activity_type='Public Event'"
    sql += " ORDER BY activity_type, boss_name"
    rows = db.query(sql, tuple(params))
    today = _date.today()
    boss_list = []
    for b in rows:
        days_since = None
        if b['last_run']:
            try:
                last = _date.fromisoformat(b['last_run'])
                days_since = (today - last).days
            except Exception:
                pass
        boss_list.append({'row': b, 'days_since': days_since})
    edit_id = request.args.get('edit_id', type=int)
    edit_item = db.get_one("SELECT * FROM legend_runs WHERE id=?", (edit_id,)) if edit_id else None
    return render_template('activities.html', bosses=boss_list, today=str(today),
                           type_filter=type_filter, edit_item=edit_item)

@bp.route('/activities/log', methods=['POST'])
def activities_log():
    from datetime import date as _date
    boss_id = fi('boss_id')
    run_date = fs('run_date') or str(_date.today())
    notes = fs('notes')
    db.execute(
        "UPDATE legend_runs SET last_run=?, run_count=run_count+1, notes=?, updated_at=date('now') WHERE id=?",
        (run_date, notes, boss_id)
    )
    flash('Run logged!', 'success')
    return redirect(url_for('daily.activities'))

@bp.route('/activities/add', methods=['POST'])
def activities_add():
    name = fs('boss_name')
    activity_type = fs('activity_type') or 'Boss'
    if name:
        db.execute("INSERT INTO legend_runs (boss_name, character_id, activity_type) VALUES (?,?,?)",
                   (name, get_active_char_id(), activity_type))
        flash(f'{name} added!', 'success')
    return redirect(url_for('daily.activities'))

@bp.route('/activities/<int:id>/delete', methods=['POST'])
def activities_delete(id):
    db.execute("DELETE FROM legend_runs WHERE id=?", (id,))
    flash('Removed.', 'info')
    return redirect(url_for('daily.activities'))

@bp.route('/activities/<int:id>/edit', methods=['POST'])
def activities_edit(id):
    name = fs('boss_name')
    run_count = fi('run_count', -1)
    activity_type = fs('activity_type')
    updates = []
    params = []
    if name:
        updates.append('boss_name=?')
        params.append(name)
    if run_count >= 0:
        updates.append('run_count=?')
        params.append(run_count)
    if activity_type:
        updates.append('activity_type=?')
        params.append(activity_type)
    if updates:
        updates.append("updated_at=date('now')")
        params.append(id)
        db.execute(f"UPDATE legend_runs SET {', '.join(updates)} WHERE id=?", tuple(params))
        flash('Activity updated!', 'success')
    return redirect(url_for('daily.activities'))

@bp.route('/activities/<int:id>/reset', methods=['POST'])
def activities_reset(id):
    db.execute("UPDATE legend_runs SET last_run='', run_count=0, notes='' WHERE id=?", (id,))
    flash('Reset.', 'info')
    return redirect(url_for('daily.activities'))

# Old URL redirects for backward compat
@bp.route('/legend-runs')
def legend_runs():
    return redirect(url_for('daily.activities', **request.args), code=301)

@bp.route('/legend-runs/log', methods=['POST'])
def legend_runs_log():
    return redirect(url_for('daily.activities_log'), code=307)

@bp.route('/legend-runs/add', methods=['POST'])
def legend_runs_add():
    return redirect(url_for('daily.activities_add'), code=307)

@bp.route('/legend-runs/<int:id>/delete', methods=['POST'])
def legend_runs_delete(id):
    return redirect(url_for('daily.activities_delete', id=id), code=307)

@bp.route('/legend-runs/<int:id>/reset', methods=['POST'])
def legend_runs_reset(id):
    return redirect(url_for('daily.activities_reset', id=id), code=307)


# ── Nuke Codes ───────────────────────────────────────────────────────────────

@bp.route('/nuke-codes')
def nuke_codes():
    from datetime import date as _date, timedelta as _td
    silos = {r['silo']: r for r in db.query("SELECT * FROM nuke_codes ORDER BY silo")}
    today = _date.today()
    today_week = str(today - _td(days=today.weekday()))
    fetch_status  = db.get_setting('nuke_fetch_status', '')
    fetch_running = _nuke_fetch.get('running', False)
    return render_template('nuke_codes.html', silos=silos, today_week=today_week,
                           fetch_status=fetch_status, fetch_running=fetch_running)

@bp.route('/nuke-codes/update', methods=['POST'])
def nuke_codes_update():
    from datetime import date as _date
    today = _date.today()
    week_of = str(today - timedelta(days=today.weekday()))
    for silo in ('Alpha', 'Bravo', 'Charlie'):
        code  = fs(f'code_{silo.lower()}')
        notes = fs(f'notes_{silo.lower()}')
        db.execute(
            "UPDATE nuke_codes SET code=?, notes=?, week_of=?, updated_at=date('now') WHERE silo=?",
            (code, notes, week_of, silo)
        )
    flash('Nuke codes updated!', 'success')
    try:
        from routes.helpers import discord_notify
        codes = {s: fs(f'code_{s.lower()}') for s in ('Alpha', 'Bravo', 'Charlie') if fs(f'code_{s.lower()}')}
        if codes:
            code_list = ' / '.join(f'{s}: {c}' for s, c in sorted(codes.items()))
            discord_notify(None, embed={'title': '☢ Nuke Codes Updated', 'description': code_list, 'color': 0xFF6600})
    except Exception:
        pass
    return redirect(url_for('daily.nuke_codes'))

@bp.route('/nuke-codes/fetch', methods=['POST'])
def nuke_codes_fetch():
    if _nuke_fetch.get('running'):
        flash('Fetch already in progress — refresh in a moment.', 'warning')
        return redirect(url_for('daily.nuke_codes'))
    _nuke_fetch['running'] = True
    db.set_setting('nuke_fetch_status', 'running|Contacting nukacrypt.com...')
    threading.Thread(target=_do_nuke_fetch, daemon=True).start()
    flash('Fetching codes in background — refresh in a few seconds.', 'info')
    return redirect(url_for('daily.nuke_codes'))


