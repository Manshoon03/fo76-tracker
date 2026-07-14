"""FO76 Tracker — Flask app shell.

All routes live in routes/*.py blueprints.
This file handles app creation, config, context processors,
error handlers, auth middleware, and blueprint registration.
"""
from flask import Flask, render_template, request, redirect, url_for, session, g
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
import os
import reference
import db

app = Flask(__name__)
app.secret_key = 'fo76-vault-tec-2024'
app.permanent_session_lifetime = timedelta(days=30)

APP_VERSION = '0.19.0'
APP_START   = datetime.now()

# ── Init DB ──────────────────────────────────────────────────────────────────
db.init_db()
db.ensure_nuke_silos()
db.auto_backup()

# Clear stuck nuke fetch status on restart
if db.get_setting('nuke_fetch_status', '').startswith('running|'):
    db.set_setting('nuke_fetch_status', 'fail|Fetch was interrupted (server restarted) — click Fetch to retry')

# ── Default credentials ─────────────────────────────────────────────────────
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

COMPANION_API_KEY = os.environ.get('FO76_COMPANION_KEY', 'fo76companion')

# ── Helper (needed by context processor) ─────────────────────────────────────
def get_active_char_id():
    try:
        return int(db.get_setting('active_character_id') or 1)
    except (ValueError, TypeError):
        return 1

# ── Context processors ───────────────────────────────────────────────────────
@app.context_processor
def inject_reference():
    weapon_names = sorted(set(
        r['name'].replace(' (Fallout 76)', '').strip()
        for r in db.query("SELECT name FROM wiki_weapons ORDER BY name")
    ))
    armor_names = [r['name'] for r in db.query("SELECT name FROM wiki_armor ORDER BY name")]
    return {'ref': reference, 'wiki_weapon_names': weapon_names, 'wiki_armor_names': armor_names}

@app.context_processor
def inject_app_info():
    return {
        'APP_VERSION': APP_VERSION,
        'app_start_ms': int(APP_START.timestamp() * 1000)
    }

@app.context_processor
def inject_characters():
    all_chars = db.query("SELECT * FROM characters ORDER BY platform, name")
    cid = get_active_char_id()
    active_char = db.get_one("SELECT * FROM characters WHERE id=?", (cid,))
    return {'all_chars': all_chars, 'active_char': active_char}

# ── Auth middleware ──────────────────────────────────────────────────────────
@app.before_request
def require_login():
    if request.path.startswith('/static'):
        return
    if request.path in ('/login', '/logout'):
        return
    if request.path.startswith('/api/') and \
            request.headers.get('X-Companion-Key') == COMPANION_API_KEY:
        return
    if not session.get('logged_in'):
        return redirect(url_for('auth.login', next=request.path))

# ── Error handlers ───────────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

@app.teardown_appcontext
def close_db_conn(error):
    conn = g.pop('db_conn', None)
    if conn is not None:
        db._managed_ids.discard(id(conn))
        conn.close()

# ── Register blueprints ─────────────────────────────────────────────────────
from routes.auth import bp as auth_bp
from routes.dashboard import bp as dashboard_bp
from routes.builds import bp as builds_bp
from routes.gear import bp as gear_bp
from routes.trading import bp as trading_bp
from routes.daily import bp as daily_bp
from routes.tools import bp as tools_bp
from routes.community import bp as community_bp
from routes.api import bp as api_bp

app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(builds_bp)
app.register_blueprint(gear_bp)
app.register_blueprint(trading_bp)
app.register_blueprint(daily_bp)
app.register_blueprint(tools_bp)
app.register_blueprint(community_bp)
app.register_blueprint(api_bp)

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', '0') == '1', host='127.0.0.1', port=5000)
