"""Auth blueprint: login, logout, change password, characters."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
import quotes
import db
from routes.helpers import fs, fi, get_active_char_id

bp = Blueprint('auth', __name__)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('dashboard.index'))
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = (request.form.get('password') or '')
        stored_user = db.get_setting('auth_username')
        stored_hash = db.get_setting('auth_password_hash')
        if username == stored_user and check_password_hash(stored_hash, password):
            session.permanent = True
            session['logged_in'] = True
            return redirect(request.args.get('next') or url_for('dashboard.index'))
        flash('Invalid username or password.', 'error')
    return render_template('login.html', quote=quotes.get_random())

@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))

@bp.route('/change-password', methods=['GET', 'POST'])
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
            return redirect(url_for('auth.login'))
    current_user = db.get_setting('auth_username')
    return render_template('change_password.html', current_user=current_user)


# ── Characters ───────────────────────────────────────────────────────────────

@bp.route('/characters')
def characters():
    chars = db.query("SELECT * FROM characters ORDER BY platform, name")
    return render_template('characters.html', chars=chars)

@bp.route('/characters/add', methods=['POST'])
def characters_add():
    name      = fs('name')
    platform  = fs('platform', 'PC')
    char_type = fs('char_type', 'Playable')
    level     = fi('level', 1)
    notes     = fs('notes')
    if not name:
        flash('Name is required.', 'error')
        return redirect(url_for('auth.characters'))
    db.execute(
        "INSERT INTO characters (name, platform, char_type, level, notes) VALUES (?,?,?,?,?)",
        (name, platform, char_type, level, notes)
    )
    flash(f'Character "{name}" added!', 'success')
    return redirect(url_for('auth.characters'))

@bp.route('/characters/<int:cid>/update', methods=['POST'])
def characters_update(cid):
    db.execute(
        "UPDATE characters SET name=?, platform=?, char_type=?, level=?, notes=? WHERE id=?",
        (fs('name'), fs('platform','PC'), fs('char_type','Playable'), fi('level',1), fs('notes'), cid)
    )
    flash('Character updated.', 'success')
    return redirect(url_for('auth.characters'))

@bp.route('/characters/<int:cid>/delete', methods=['POST'])
def characters_delete(cid):
    count = db.get_one("SELECT COUNT(*) AS c FROM characters")
    if count and count['c'] <= 1:
        flash('Cannot delete the only character.', 'error')
        return redirect(url_for('auth.characters'))
    if get_active_char_id() == cid:
        fallback = db.get_one("SELECT id FROM characters WHERE id != ? ORDER BY id LIMIT 1", (cid,))
        db.set_setting('active_character_id', str(fallback['id']) if fallback else '1')
    db.execute("DELETE FROM characters WHERE id=?", (cid,))
    flash('Character deleted.', 'info')
    return redirect(url_for('auth.characters'))

@bp.route('/characters/switch/<int:cid>', methods=['POST'])
def characters_switch(cid):
    row = db.get_one("SELECT id FROM characters WHERE id=?", (cid,))
    if row:
        db.set_setting('active_character_id', str(cid))
    return redirect(request.referrer or url_for('dashboard.index'))

@bp.route('/character', methods=['GET', 'POST'])
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
        return redirect(url_for('auth.character'))
    char = db.get_one("SELECT * FROM characters WHERE id=?", (cid,))
    builds = db.query("SELECT id, name, playstyle FROM builds WHERE character_id=? ORDER BY name", (cid,))
    active_build = None
    if char and char['active_build_id']:
        active_build = db.get_one("SELECT * FROM builds WHERE id=?", (char['active_build_id'],))
    return render_template('character.html', char=char, builds=builds, active_build=active_build)
