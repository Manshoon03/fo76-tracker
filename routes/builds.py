"""Builds blueprint: builds, perk cards, legendary perks, mutations, loadouts, build generator, build coach, compare."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from pathlib import Path
import json
import re
import db
import reference
from routes.helpers import fs, fi, get_active_char_id, _get_anthropic

bp = Blueprint('builds', __name__)


# ── Perk Cards ───────────────────────────────────────────────────────────────

@bp.route('/perk-cards')
def perk_cards():
    cid = get_active_char_id()
    items = db.query("SELECT * FROM perk_cards WHERE character_id=? ORDER BY special, name", (cid,))
    edit_id = request.args.get('edit_id', type=int)
    edit_item = db.get_one("SELECT * FROM perk_cards WHERE id=?", (edit_id,)) if edit_id else None
    wiki_perks_rows = db.query(
        "SELECT p.name, p.special, p.is_legendary, p.max_rank, p.description, "
        "GROUP_CONCAT(r.rank || '|' || r.effect, '~~') as rank_data "
        "FROM wiki_perks p LEFT JOIN wiki_perk_ranks r ON r.perk_id=p.id "
        "GROUP BY p.id ORDER BY p.special, p.name"
    )
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

@bp.route('/perk-cards/add', methods=['POST'])
def perk_cards_add():
    db.execute(
        "INSERT INTO perk_cards (name,special,current_rank,max_rank,copies_owned,effect,used_in,can_scrap,notes,character_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (fs('name'), fs('special','S'), fi('current_rank',1), fi('max_rank',3),
         fi('copies_owned',1), fs('effect'), fs('used_in'), fs('can_scrap','No'), fs('notes'), get_active_char_id())
    )
    flash('Perk card added!', 'success')
    return redirect(url_for('builds.perk_cards'))

@bp.route('/perk-cards/<int:id>/update', methods=['POST'])
def perk_cards_update(id):
    db.execute(
        "UPDATE perk_cards SET name=?,special=?,current_rank=?,max_rank=?,copies_owned=?,effect=?,used_in=?,can_scrap=?,notes=? WHERE id=?",
        (fs('name'), fs('special','S'), fi('current_rank',1), fi('max_rank',3),
         fi('copies_owned',1), fs('effect'), fs('used_in'), fs('can_scrap','No'), fs('notes'), id)
    )
    flash('Perk card updated!', 'success')
    return redirect(url_for('builds.perk_cards'))

@bp.route('/perk-cards/<int:id>/delete', methods=['POST'])
def perk_cards_delete(id):
    db.execute("DELETE FROM perk_cards WHERE id=?", (id,))
    flash('Deleted.', 'info')
    return redirect(url_for('builds.perk_cards'))

@bp.route('/perk-cards/quick-add', methods=['POST'])
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


# ── Legendary Perks ──────────────────────────────────────────────────────────

@bp.route('/legendary-perks')
def legendary_perks():
    from reference import LEGENDARY_PERK_CARDS, LEGENDARY_PERK_SLOT_UNLOCKS
    cid   = get_active_char_id()
    char  = db.get_one("SELECT * FROM characters WHERE id=?", (cid,))
    slots = db.query("SELECT * FROM legendary_perk_slots WHERE character_id=? ORDER BY slot_num", (cid,))
    slot_map = {r['slot_num']: dict(r) for r in slots}
    manifest_path = Path('static/img/perks/legend_manifest.json')
    legend_images = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    return render_template('legendary_perks.html',
                           slot_map=slot_map,
                           legendary_cards=LEGENDARY_PERK_CARDS,
                           slot_unlocks=LEGENDARY_PERK_SLOT_UNLOCKS,
                           legend_images=legend_images,
                           char=char)

@bp.route('/legendary-perks/set', methods=['POST'])
def legendary_perks_set():
    data      = request.get_json()
    cid       = get_active_char_id()
    slot_num  = int(data.get('slot_num', 1))
    card_name = (data.get('card_name') or '').strip()
    rank      = max(1, min(4, int(data.get('rank', 1))))
    notes     = (data.get('notes') or '').strip()
    existing  = db.get_one(
        "SELECT id FROM legendary_perk_slots WHERE character_id=? AND slot_num=?",
        (cid, slot_num)
    )
    if existing:
        db.execute(
            "UPDATE legendary_perk_slots SET card_name=?,rank=?,notes=?,updated_at=date('now') WHERE id=?",
            (card_name, rank, notes, existing['id'])
        )
    else:
        db.insert(
            "INSERT INTO legendary_perk_slots (character_id,slot_num,card_name,rank,notes) VALUES (?,?,?,?,?)",
            (cid, slot_num, card_name, rank, notes)
        )
    return jsonify({'success': True})

@bp.route('/legendary-perks/clear/<int:slot_num>', methods=['POST'])
def legendary_perks_clear(slot_num):
    cid = get_active_char_id()
    db.execute("DELETE FROM legendary_perk_slots WHERE character_id=? AND slot_num=?", (cid, slot_num))
    return jsonify({'success': True})


# ── Builds ───────────────────────────────────────────────────────────────────

@bp.route('/builds')
def builds():
    cid = get_active_char_id()
    items = [dict(r) for r in db.query("SELECT *, (s+p+e+c+i+a+l) as total FROM builds WHERE character_id=? ORDER BY name", (cid,))]
    edit_id = request.args.get('edit_id', type=int)
    edit_item = db.get_one("SELECT * FROM builds WHERE id=?", (edit_id,)) if edit_id else None
    wiki_perks_list = [r['name'] for r in db.query("SELECT name FROM wiki_perks ORDER BY name")]
    mut_rows = db.query("SELECT build_id, name, effects_positive, effects_negative FROM mutations WHERE character_id=? AND build_id > 0", (cid,))
    mutations_by_build = {}
    for r in mut_rows:
        bid = r['build_id']
        mutations_by_build.setdefault(bid, []).append({
            'name': r['name'], 'pos': r['effects_positive'], 'neg': r['effects_negative']
        })
    inv_weapons = [dict(r) for r in db.query("SELECT id, name, wtype, star1, star2, star3, star4, status, build_id FROM weapons WHERE character_id=? ORDER BY name", (cid,))]
    inv_armor   = [dict(r) for r in db.query("SELECT id, name, slot, material, star1, star2, star3, star4, status, build_id FROM armor WHERE character_id=? ORDER BY name", (cid,))]
    return render_template('builds.html', items=items, edit_item=edit_item,
                           wiki_perks_list=wiki_perks_list,
                           mutations_by_build=mutations_by_build,
                           inv_weapons=inv_weapons, inv_armor=inv_armor)

@bp.route('/builds/add', methods=['POST'])
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
    return redirect(url_for('builds.builds'))

@bp.route('/builds/<int:id>/update', methods=['POST'])
def builds_update(id):
    pcj = fs('perk_cards_json')
    db.execute(
        "UPDATE builds SET name=?,playstyle=?,s=?,p=?,e=?,c=?,i=?,a=?,l=?,key_cards=?,notes=?,perk_cards_json=? WHERE id=?",
        (fs('name'), fs('playstyle'), fi('s',1), fi('p',1), fi('e',1), fi('c',1),
         fi('i',1), fi('a',1), fi('l',1), fs('key_cards'), fs('notes'), pcj, id)
    )
    _assign_build_gear(id, request.form.getlist('weapon_ids'), request.form.getlist('armor_ids'))
    flash('Build updated!', 'success')
    return redirect(url_for('builds.builds'))

def _assign_build_gear(build_id, weapon_ids, armor_ids):
    db.execute("UPDATE weapons SET build_id=0 WHERE build_id=?", (build_id,))
    db.execute("UPDATE armor   SET build_id=0 WHERE build_id=?", (build_id,))
    for wid in weapon_ids:
        if wid: db.execute("UPDATE weapons SET build_id=? WHERE id=?", (build_id, int(wid)))
    for aid in armor_ids:
        if aid: db.execute("UPDATE armor   SET build_id=? WHERE id=?", (build_id, int(aid)))

@bp.route('/builds/<int:id>/delete', methods=['POST'])
def builds_delete(id):
    db.execute("DELETE FROM builds WHERE id=?", (id,))
    flash('Deleted.', 'info')
    return redirect(url_for('builds.builds'))


# ── Mutations ────────────────────────────────────────────────────────────────

@bp.route('/mutations')
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
    builds_list = db.query("SELECT id, name FROM builds WHERE character_id=? ORDER BY name", (cid,))
    wiki_rows = db.query("SELECT name, positive_effects, negative_effects, serum_name, wiki_url FROM wiki_mutations ORDER BY name")
    wiki_mutations = {r['name']: dict(r) for r in wiki_rows}
    logged_names = {r['name'].lower() for r in db.query("SELECT name FROM mutations WHERE character_id=?", (cid,))}
    return render_template('mutations.html', items=items, edit_item=edit_item,
                           filter_active=filter_active, builds=builds_list,
                           mutation_names=reference.MUTATION_NAMES,
                           wiki_mutations=wiki_mutations,
                           logged_names=logged_names)

@bp.route('/mutations/add', methods=['POST'])
def mutations_add():
    db.execute(
        "INSERT INTO mutations (name,effects_positive,effects_negative,active,build_id,notes,character_id) VALUES (?,?,?,?,?,?,?)",
        (fs('name'), fs('effects_positive'), fs('effects_negative'),
         1 if request.form.get('active') else 0, fi('build_id'), fs('notes'), get_active_char_id())
    )
    flash('Mutation added!', 'success')
    return redirect(url_for('builds.mutations'))

@bp.route('/mutations/<int:id>/update', methods=['POST'])
def mutations_update(id):
    db.execute(
        "UPDATE mutations SET name=?,effects_positive=?,effects_negative=?,active=?,build_id=?,notes=? WHERE id=?",
        (fs('name'), fs('effects_positive'), fs('effects_negative'),
         1 if request.form.get('active') else 0, fi('build_id'), fs('notes'), id)
    )
    flash('Updated!', 'success')
    return redirect(url_for('builds.mutations'))

@bp.route('/mutations/<int:id>/delete', methods=['POST'])
def mutations_delete(id):
    db.execute("DELETE FROM mutations WHERE id=?", (id,))
    flash('Deleted.', 'info')
    return redirect(url_for('builds.mutations'))

@bp.route('/mutations/<int:id>/toggle', methods=['POST'])
def mutations_toggle(id):
    row = db.get_one("SELECT active FROM mutations WHERE id=?", (id,))
    if row:
        db.execute("UPDATE mutations SET active=? WHERE id=?", (0 if row['active'] else 1, id))
    return redirect(url_for('builds.mutations'))

@bp.route('/mutations/quick-add', methods=['POST'])
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


# ── Loadouts ─────────────────────────────────────────────────────────────────

@bp.route('/loadouts')
def loadouts():
    cid = get_active_char_id()
    items = db.query("SELECT * FROM loadouts WHERE character_id=? ORDER BY name", (cid,))
    stat_rows = db.query("""
        SELECT loadout_id, 'weapon' AS kind, COUNT(*) AS cnt FROM loadout_weapons GROUP BY loadout_id
        UNION ALL
        SELECT loadout_id, 'armor', COUNT(*) FROM loadout_armor GROUP BY loadout_id
        UNION ALL
        SELECT loadout_id, 'mutation', COUNT(*) FROM loadout_mutations GROUP BY loadout_id
    """)
    gear_stats = {}
    for r in stat_rows:
        gear_stats.setdefault(r['loadout_id'], {})
        gear_stats[r['loadout_id']][r['kind']] = r['cnt']
    active_loadout_id = int(db.get_setting(f'active_loadout_id_{cid}') or 0)
    builds_list = db.query("SELECT id, name FROM builds WHERE character_id=? ORDER BY name", (cid,))
    weapons = db.query("SELECT id, name, wtype, star1, star2, star3 FROM weapons WHERE character_id=? ORDER BY name", (cid,))
    armor_items = db.query("SELECT id, name, slot, star1, star2, star3 FROM armor WHERE character_id=? ORDER BY name", (cid,))
    muts = db.query("SELECT id, name FROM mutations WHERE character_id=? AND active=1 ORDER BY name", (cid,))
    edit_id = request.args.get('edit_id', type=int)
    edit_item = db.get_one("SELECT * FROM loadouts WHERE id=?", (edit_id,)) if edit_id else None
    edit_weapon_ids = set()
    edit_armor_ids = set()
    edit_mutation_ids = set()
    if edit_item:
        edit_weapon_ids = {r['weapon_id'] for r in db.query("SELECT weapon_id FROM loadout_weapons WHERE loadout_id=?", (edit_id,))}
        edit_armor_ids = {r['armor_id'] for r in db.query("SELECT armor_id FROM loadout_armor WHERE loadout_id=?", (edit_id,))}
        edit_mutation_ids = {r['mutation_id'] for r in db.query("SELECT mutation_id FROM loadout_mutations WHERE loadout_id=?", (edit_id,))}
    return render_template('loadouts.html', items=items, gear_stats=gear_stats,
                           active_loadout_id=active_loadout_id, builds=builds_list,
                           weapons=weapons, armor=armor_items, mutations=muts,
                           edit_item=edit_item, edit_weapon_ids=edit_weapon_ids,
                           edit_armor_ids=edit_armor_ids, edit_mutation_ids=edit_mutation_ids)

def _assign_loadout_gear(lid, weapon_ids, armor_ids, mutation_ids):
    db.execute("DELETE FROM loadout_weapons WHERE loadout_id=?", (lid,))
    db.execute("DELETE FROM loadout_armor WHERE loadout_id=?", (lid,))
    db.execute("DELETE FROM loadout_mutations WHERE loadout_id=?", (lid,))
    for wid in weapon_ids:
        if wid:
            db.execute("INSERT INTO loadout_weapons (loadout_id, weapon_id) VALUES (?,?)", (lid, int(wid)))
    for aid in armor_ids:
        if aid:
            db.execute("INSERT INTO loadout_armor (loadout_id, armor_id) VALUES (?,?)", (lid, int(aid)))
    for mid in mutation_ids:
        if mid:
            db.execute("INSERT INTO loadout_mutations (loadout_id, mutation_id) VALUES (?,?)", (lid, int(mid)))

@bp.route('/loadouts/add', methods=['POST'])
def loadouts_add():
    cid = get_active_char_id()
    db.execute("INSERT INTO loadouts (name, build_id, notes, character_id) VALUES (?,?,?,?)",
               (fs('name'), fi('build_id', 0), fs('notes'), cid))
    lid = db.query("SELECT last_insert_rowid() as id")[0]['id']
    _assign_loadout_gear(lid, request.form.getlist('weapon_ids'),
                         request.form.getlist('armor_ids'),
                         request.form.getlist('mutation_ids'))
    flash('Loadout created!', 'success')
    return redirect(url_for('builds.loadouts'))

@bp.route('/loadouts/<int:lid>/update', methods=['POST'])
def loadouts_update(lid):
    db.execute("UPDATE loadouts SET name=?, build_id=?, notes=? WHERE id=?",
               (fs('name'), fi('build_id', 0), fs('notes'), lid))
    _assign_loadout_gear(lid, request.form.getlist('weapon_ids'),
                         request.form.getlist('armor_ids'),
                         request.form.getlist('mutation_ids'))
    flash('Loadout updated!', 'success')
    return redirect(url_for('builds.loadouts'))

@bp.route('/loadouts/<int:lid>/delete', methods=['POST'])
def loadouts_delete(lid):
    db.execute("DELETE FROM loadout_weapons WHERE loadout_id=?", (lid,))
    db.execute("DELETE FROM loadout_armor WHERE loadout_id=?", (lid,))
    db.execute("DELETE FROM loadout_mutations WHERE loadout_id=?", (lid,))
    db.execute("DELETE FROM loadouts WHERE id=?", (lid,))
    cid = get_active_char_id()
    if db.get_setting(f'active_loadout_id_{cid}') == str(lid):
        db.set_setting(f'active_loadout_id_{cid}', '0')
    flash('Loadout deleted.', 'info')
    return redirect(url_for('builds.loadouts'))

@bp.route('/loadouts/<int:lid>/activate', methods=['POST'])
def loadouts_activate(lid):
    cid = get_active_char_id()
    db.set_setting(f'active_loadout_id_{cid}', str(lid))
    return jsonify(ok=True)

@bp.route('/loadouts/<int:lid>/deactivate', methods=['POST'])
def loadouts_deactivate(lid):
    cid = get_active_char_id()
    db.set_setting(f'active_loadout_id_{cid}', '0')
    return jsonify(ok=True)

@bp.route('/loadouts/<int:lid>')
def loadout_detail(lid):
    cid = get_active_char_id()
    loadout = db.get_one("SELECT * FROM loadouts WHERE id=?", (lid,))
    if not loadout:
        flash('Loadout not found.', 'error')
        return redirect(url_for('builds.loadouts'))
    weapons = db.query("""SELECT w.* FROM weapons w
        JOIN loadout_weapons lw ON lw.weapon_id=w.id
        WHERE lw.loadout_id=? ORDER BY w.name""", (lid,))
    armor_items = db.query("""SELECT a.* FROM armor a
        JOIN loadout_armor la ON la.armor_id=a.id
        WHERE la.loadout_id=? ORDER BY a.name""", (lid,))
    muts = db.query("""SELECT m.* FROM mutations m
        JOIN loadout_mutations lm ON lm.mutation_id=m.id
        WHERE lm.loadout_id=? ORDER BY m.name""", (lid,))
    build = db.get_one("SELECT name FROM builds WHERE id=?", (loadout['build_id'],)) if loadout['build_id'] else None
    active_loadout_id = int(db.get_setting(f'active_loadout_id_{cid}') or 0)
    return render_template('loadout_detail.html', loadout=loadout, weapons=weapons,
                           armor=armor_items, mutations=muts, build=build,
                           active_loadout_id=active_loadout_id)


# ── Build Generator ──────────────────────────────────────────────────────────

@bp.route('/build-generator')
def build_generator():
    return render_template('build_generator.html')

@bp.route('/build-generator/generate', methods=['POST'])
def build_generator_generate():
    data   = request.get_json()
    race   = data.get('race',   'Human')
    health = data.get('health', 'Full Health')
    weapon = data.get('weapon', 'Two-Handed Melee')
    notes  = data.get('notes',  '')

    bloodied_hint = "Focus on low-health perks: Nerd Rage, Serendipity, Dodgy, Blocker." if health == 'Bloodied' else ""
    ghoul_hint    = "Include Ghoulish and radiation perks since race is Ghoul." if race == 'Ghoul' else ""
    user_notes = f"\n\nIMPORTANT — The user specifically requested: {notes}\nYou MUST incorporate these requirements into the build. Do not ignore them." if notes else ""

    prompt = f"""You are a Fallout 76 endgame build expert. Generate a META-OPTIMIZED build based on current publicly known game balance, community consensus, and proven endgame strategies.

Build request:
- Race: {race}
- Health Style: {health}
- Primary Weapon: {weapon}
{bloodied_hint}
{ghoul_hint}
{user_notes}

Return ONLY valid JSON matching this structure exactly:
{{
  "name": "Short descriptive build name",
  "summary": "2-3 sentence overview explaining why this is meta",
  "special": {{"s":0,"p":0,"e":0,"c":0,"i":0,"a":0,"l":0}},
  "perk_cards": [
    {{"name":"Exact in-game perk name","special":"S","rank":3,"max_rank":3,"reason":"Why this perk at this rank"}}
  ],
  "legendary_perks": [
    {{"name":"Legendary perk name","rank":4,"max_rank":4,"reason":"Why and at what rank"}}
  ],
  "weapons": ["Weapon with legendary prefix and effects"],
  "armor": "Armor set with legendary effects",
  "mutations": ["Mutation name"],
  "playstyle_notes": "Detailed tips for this build"
}}

Rules:
- SPECIAL total must be exactly 56 (max 15 per stat, min 1)
- Include 12-15 perk cards — use EXACT in-game names, specify the recommended rank (not always max — some perks are only needed at rank 1, others at rank 3 for full effect) and the actual max_rank for that card
- Include 2-4 legendary perks with recommended rank and max_rank (e.g. Legendary Strength max_rank 4, What Rads max_rank 4, Follow Through max_rank 4)
- Use meta-proven legendary prefixes: Anti-Armor, Bloodied, Quad, Vampire's, Aristocrat's — with 25% faster fire rate, explosive, 50% crit damage as appropriate
- Recommend actual meta mutations (Marsupial, Speed Demon, Adrenal Reaction for bloodied, etc.)
- Base recommendations on what endgame players actually run, not just what sounds reasonable
- Return only the JSON object, no markdown, no explanation"""

    try:
        client   = _get_anthropic()
        response = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=2500,
            messages=[
                {'role': 'user', 'content': prompt}
            ]
        )
        text = response.content[0].text.strip()
        text = re.sub(r'^```[\w]*\s*', '', text)
        text = re.sub(r'```\s*$', '', text).strip()
        build = json.loads(text)
        return jsonify({'success': True, 'build': build})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/build-generator/save', methods=['POST'])
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


