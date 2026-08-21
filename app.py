import os
import sqlite3
from flask import Flask, g, render_template, request, redirect, url_for, flash, jsonify

app = Flask(__name__)
app.secret_key = 'rod-db-secret'

DB_PATH = os.path.join(os.path.dirname(__file__), 'rod.db')
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), 'schema.sql')

# ── RoD reference data ───────────────────────────────────────────────────────

CLASSES = [
    'Mage', 'Thief', 'Warrior', 'Cleric', 'Druid', 'Vampire',
    'Ranger', 'Paladin', 'Fathomer', 'Nephandi', 'Augurer', 'Bladesinger', 'Barbarian',
    'Prestige: Druid/Cleric', 'Prestige: Mage/Thief', 'Prestige: Warrior/Ranger',
    'Prestige: Cleric/Paladin', 'Prestige: Vampire/Nephandi',
]

RACES = [
    'Human', 'Elf', 'Dwarf', 'Halfling', 'Pixie', 'Half-Ogre', 'Half-Orc',
    'Half-Troll', 'Half-Elf', 'Gith', 'Drow', 'Sea-Elf', 'Gnome',
    'Lizardman', 'Dragonborn', 'Tiefling',
]

SEXES = ['Male', 'Female', 'Its']

ALIGNMENTS = ['Devout', 'Neutral', 'Evil']

# Characters use the display vocabulary above, but item anti-flags use the
# in-game token 'anti-Good' for the good alignment. Translate when filtering.
ALIGN_TO_ANTI = {'Devout': 'Good', 'Neutral': 'Neutral', 'Evil': 'Evil'}

# Wear slots in display order; (slot_key, label, max_count)
WEAR_SLOTS = [
    ('light',   'Light',         1),
    ('finger',  'Finger',        2),
    ('neck',    'Neck',          2),
    ('body',    'Body',         10),
    ('head',    'Head',          1),
    ('legs',    'Legs',          1),
    ('feet',    'Feet',          1),
    ('hands',   'Hands',         1),
    ('arms',    'Arms',          1),
    ('shield',  'Shield',        1),
    ('about',   'About (Cloak)', 10),
    ('waist',   'Waist',         1),
    ('wrist',   'Wrist',         2),
    ('*',       'Wield',         2),
    ('hold',    'Hold',          1),
    ('ears',    'Ears',          1),
    ('eyes',    'Eyes',          1),
    ('back',    'Back',          1),
    ('face',    'Face',          1),
    ('ankle',   'Ankle',         2),
    ('lance',   'Lance',         1),
]

STAT_FIELDS = [
    ('hr',    'HR'),
    ('dr',    'DR'),
    ('hp',    'HP'),
    ('mana',  'Mana'),
    ('str_b', 'STR'),
    ('dex_b', 'DEX'),
    ('int_b', 'INT'),
    ('wis_b', 'WIS'),
    ('con_b', 'CON'),
    ('cha_b', 'CHA'),
    ('lck_b', 'LCK'),
    ('move_b','Move'),
    ('ac',    'AC'),
]

# ── Database helpers ─────────────────────────────────────────────────────────

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop('db', None)
    if db:
        db.close()


def init_db():
    with app.app_context():
        db = get_db()
        with open(SCHEMA_PATH) as f:
            db.executescript(f.read())
        db.commit()


# ── Items ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return redirect(url_for('items'))


@app.route('/items')
def items():
    db = get_db()
    params = []
    clauses = []

    # ---- text filters ----
    name = request.args.get('name', '').strip()
    if name:
        clauses.append("name LIKE ?")
        params.append(f'%{name}%')

    mob = request.args.get('mob', '').strip()
    if mob:
        clauses.append("mob_source LIKE ?")
        params.append(f'%{mob}%')

    area = request.args.get('area', '').strip()
    if area:
        clauses.append("area LIKE ?")
        params.append(f'%{area}%')

    other = request.args.get('other', '').strip()
    if other:
        clauses.append("other LIKE ?")
        params.append(f'%{other}%')

    # ---- dropdown filters ----
    item_type = request.args.get('item_type', '').strip()
    if item_type:
        clauses.append("item_type = ?")
        params.append(item_type)

    wear_loc = request.args.get('wear_loc', '').strip()
    if wear_loc:
        clauses.append("wear_loc = ?")
        params.append(wear_loc)

    # ---- level range ----
    lmin = request.args.get('lmin', '').strip()
    lmax = request.args.get('lmax', '').strip()
    if lmin:
        clauses.append("level_max >= ?")
        params.append(int(lmin))
    if lmax:
        clauses.append("level_min <= ?")
        params.append(int(lmax))

    # ---- stat filters ----
    for field, _ in STAT_FIELDS:
        val = request.args.get(f'stat_{field}', '').strip()
        if val:
            try:
                clauses.append(f"{field} >= ?")
                params.append(int(val))
            except ValueError:
                pass

    # ---- class filter (anti-flag search) ----
    cls_filter = request.args.get('cls', '').strip()
    if cls_filter:
        # exclude items that are anti- for this class; a prestige class
        # ("Prestige: Druid/Cleric") is blocked by either component's anti-flag
        if cls_filter.startswith('Prestige:'):
            components = cls_filter.split(':', 1)[1].strip().split('/')
        else:
            components = [cls_filter]
        for c in components:
            clauses.append("antis NOT LIKE ?")
            params.append(f'%anti-{c.strip()}%')

    # ---- sex filter (anti-flag: anti-Male / anti-Female / anti-Its) ----
    sex_filter = request.args.get('sex', '').strip()
    if sex_filter:
        clauses.append("antis NOT LIKE ?")
        params.append(f'%anti-{sex_filter}%')

    # ---- alignment filter ----
    # Character/UI value is Devout/Neutral/Evil; item flags use anti-Good etc.
    align_filter = request.args.get('align', '').strip()
    if align_filter:
        anti = ALIGN_TO_ANTI.get(align_filter, align_filter)
        clauses.append("antis NOT LIKE ?")
        params.append(f'%anti-{anti}%')

    # ---- race filter ----
    # races is a space-separated allow-list; blank means "no restriction".
    # Pad both sides so 'Elf' doesn't match 'Half-Elf'.
    race_filter = request.args.get('race', '').strip()
    if race_filter:
        clauses.append("(races = '' OR ' ' || races || ' ' LIKE ?)")
        params.append(f'% {race_filter} %')

    # ---- flag toggles ----
    show_oog   = request.args.get('show_oog',   '0') == '1'
    show_pk    = request.args.get('show_pk',    '0') == '1'
    show_gloried = request.args.get('show_gloried', '0') == '1'

    if not show_oog:
        clauses.append("is_oog = 0")
    if not show_pk:
        clauses.append("is_pkill = 0")
    if not show_gloried:
        clauses.append("is_gloried = 0")

    # ---- sort ----
    sort = request.args.get('sort', 'name')
    safe_sort_cols = {'name','level_min','item_type','wear_loc','hr','dr','hp','mana',
                      'str_b','dex_b','int_b','wis_b','con_b','cha_b','lck_b','move_b',
                      'ac','gold','area','flags'}
    if sort not in safe_sort_cols:
        sort = 'name'
    # Name landing reads best A→Z; every other column defaults to descending
    # (highest first). UI column clicks always pass an explicit order.
    default_order = 'asc' if sort == 'name' else 'desc'
    order = request.args.get('order', default_order)
    if order not in ('asc', 'desc'):
        order = default_order

    where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
    sql = f"SELECT * FROM items {where} ORDER BY {sort} {order.upper()} LIMIT 500"
    rows = db.execute(sql, params).fetchall()

    # dropdown option lists
    types = [r[0] for r in db.execute(
        "SELECT DISTINCT item_type FROM items ORDER BY item_type").fetchall()]
    locs  = [r[0] for r in db.execute(
        "SELECT DISTINCT wear_loc FROM items ORDER BY wear_loc").fetchall()]

    total = db.execute(f"SELECT COUNT(*) FROM items {where}", params).fetchone()[0]

    # ---- slot-assignment context ----
    # When opened from a character's gear slot, carry that context so each
    # row can be assigned straight back to the slot.
    assign_char = None
    assign_slot = request.args.get('assign_slot', '').strip()
    if request.args.get('assign_char', '').strip().isdigit() and assign_slot:
        assign_char = db.execute(
            "SELECT * FROM characters WHERE id=?",
            (int(request.args['assign_char']),)
        ).fetchone()

    return render_template('items.html',
        items=rows, types=types, locs=locs,
        args=request.args, stat_fields=STAT_FIELDS,
        total=total, sort=sort, order=order,
        classes=CLASSES, sexes=SEXES, races=RACES, alignments=ALIGNMENTS,
        assign_char=assign_char, assign_slot=assign_slot,
        assign_wanted=request.args.get('assign_wanted', '0'))


@app.route('/item/<int:item_id>')
def item_detail(item_id):
    db = get_db()
    item = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    if item is None:
        flash('Item not found.', 'danger')
        return redirect(url_for('items'))
    return render_template('item_detail.html', item=item, stat_fields=STAT_FIELDS)


@app.route('/item/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_item(item_id):
    db = get_db()
    item = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    if item is None:
        flash('Item not found.', 'danger')
        return redirect(url_for('items'))

    if request.method == 'POST':
        f = request.form

        def fi(key, default=0):
            try:
                return int(f.get(key, default) or default)
            except (ValueError, TypeError):
                return default

        flags     = f.get('flags', '').strip()
        level_txt = f.get('level', '').strip()
        lmin, lmax = fi('level_min'), fi('level_max')
        if not lmin and level_txt:
            from importer import _level_range
            lmin, lmax = _level_range(level_txt)

        db.execute("""
            UPDATE items SET
                name=?, item_type=?, wear_loc=?,
                level=?, level_min=?, level_max=?, weight=?,
                ac=?, d1=?, d2=?,
                hr=?, dr=?, hp=?, mana=?,
                str_b=?, dex_b=?, int_b=?, wis_b=?,
                con_b=?, cha_b=?, lck_b=?, move_b=?,
                item_value=?, gold=?,
                flags=?, antis=?, races=?, other=?,
                mob_source=?, area=?, date_mod=?, editor=?,
                is_oog=?, is_pkill=?, is_gloried=?
            WHERE id=?
        """, (
            f.get('name','').strip(),
            f.get('item_type','').strip().lower(),
            f.get('wear_loc','').strip().lower(),
            level_txt, lmin, lmax,
            f.get('weight','').strip(),
            fi('ac'), f.get('d1','').strip(), f.get('d2','').strip(),
            fi('hr'), fi('dr'), fi('hp'), fi('mana'),
            fi('str_b'), fi('dex_b'), fi('int_b'), fi('wis_b'),
            fi('con_b'), fi('cha_b'), fi('lck_b'), fi('move_b'),
            fi('item_value'), fi('gold'),
            flags, f.get('antis','').strip(),
            f.get('races','').strip(), f.get('other','').strip(),
            f.get('mob_source','').strip(), f.get('area','').strip(),
            f.get('date_mod','').strip(), f.get('editor','').strip(),
            1 if 'not_in_game' in flags.lower() else 0,
            1 if 'pkill' in flags.lower() else 0,
            fi('is_gloried'),
            item_id
        ))
        db.commit()
        flash('Item updated.', 'success')
        return redirect(url_for('item_detail', item_id=item_id))

    return render_template('item_edit.html', item=item, wear_slots=WEAR_SLOTS)


# ── Import ───────────────────────────────────────────────────────────────────

@app.route('/import', methods=['GET', 'POST'])
def import_items():
    if request.method == 'POST':
        path = request.form.get('path', '').strip()
        if not path or not os.path.isfile(path):
            flash(f'File not found: {path}', 'danger')
            return redirect(url_for('import_items'))

        from importer import parse_file
        db = get_db()

        replace = request.form.get('replace') == '1'
        if replace:
            db.execute("DELETE FROM items")

        inserted = updated = skipped = 0
        for item in parse_file(path):
            # Match on name + type + wear_loc to decide insert vs update
            existing = db.execute(
                "SELECT id FROM items WHERE name=? AND item_type=? AND wear_loc=?",
                (item['name'], item['item_type'], item['wear_loc'])
            ).fetchone()

            if existing:
                db.execute("""
                    UPDATE items SET
                        level=?, level_min=?, level_max=?, weight=?, ac=?,
                        d1=?, d2=?, hr=?, dr=?, hp=?, mana=?,
                        str_b=?, dex_b=?, int_b=?, wis_b=?, con_b=?, cha_b=?, lck_b=?, move_b=?,
                        item_value=?, gold=?, flags=?, antis=?, races=?, other=?,
                        mob_source=?, area=?, date_mod=?, editor=?,
                        is_oog=?, is_pkill=?, is_gloried=?
                    WHERE id=?
                """, (
                    item['level'], item['level_min'], item['level_max'],
                    item['weight'], item['ac'],
                    item['d1'], item['d2'], item['hr'], item['dr'], item['hp'], item['mana'],
                    item['str_b'], item['dex_b'], item['int_b'], item['wis_b'],
                    item['con_b'], item['cha_b'], item['lck_b'], item['move_b'],
                    item['item_value'], item['gold'],
                    item['flags'], item['antis'], item['races'], item['other'],
                    item['mob_source'], item['area'], item['date_mod'], item['editor'],
                    item['is_oog'], item['is_pkill'], item['is_gloried'],
                    existing['id']
                ))
                updated += 1
            else:
                db.execute("""
                    INSERT INTO items
                        (item_type, wear_loc, name, level, level_min, level_max, weight, ac,
                         d1, d2, hr, dr, hp, mana,
                         str_b, dex_b, int_b, wis_b, con_b, cha_b, lck_b, move_b,
                         item_value, gold, flags, antis, races, other,
                         mob_source, area, date_mod, editor, is_oog, is_pkill, is_gloried)
                    VALUES
                        (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    item['item_type'], item['wear_loc'], item['name'],
                    item['level'], item['level_min'], item['level_max'],
                    item['weight'], item['ac'],
                    item['d1'], item['d2'], item['hr'], item['dr'], item['hp'], item['mana'],
                    item['str_b'], item['dex_b'], item['int_b'], item['wis_b'],
                    item['con_b'], item['cha_b'], item['lck_b'], item['move_b'],
                    item['item_value'], item['gold'],
                    item['flags'], item['antis'], item['races'], item['other'],
                    item['mob_source'], item['area'], item['date_mod'], item['editor'],
                    item['is_oog'], item['is_pkill'], item['is_gloried']
                ))
                inserted += 1

        db.commit()
        flash(f'Import complete: {inserted} new, {updated} updated, {skipped} skipped.', 'success')
        return redirect(url_for('items'))

    return render_template('import.html')


# ── Identify paste-in ────────────────────────────────────────────────────────

@app.route('/import/identify', methods=['GET', 'POST'])
def import_identify():
    """Step 1: paste raw identify text → parse and show review form."""
    from importer import parse_identify
    parsed = None
    raw_text = ''
    error = None

    if request.method == 'POST':
        raw_text = request.form.get('identify_text', '')
        parsed = parse_identify(raw_text)
        if parsed is None:
            error = "Couldn't find an item name. Make sure the text starts with: Object 'Name' is …"

    return render_template('import_identify.html',
                           parsed=parsed, raw_text=raw_text, error=error,
                           wear_slots=WEAR_SLOTS)


@app.route('/import/identify/save', methods=['POST'])
def save_identify():
    """Step 2: save the reviewed identify form to the DB."""
    f = request.form

    def fi(key, default=0):
        try:
            return int(f.get(key, default) or default)
        except (ValueError, TypeError):
            return default

    flags = f.get('flags', '').strip()
    antis = f.get('antis', '').strip()
    level_txt = f.get('level', '').strip()
    lmin, lmax = (fi('level_min'), fi('level_max'))
    if not lmin and level_txt:
        from importer import _level_range
        lmin, lmax = _level_range(level_txt)

    item = {
        'name':       f.get('name', '').strip(),
        'item_type':  f.get('item_type', '').strip().lower(),
        'wear_loc':   f.get('wear_loc', '').strip().lower(),
        'level':      level_txt,
        'level_min':  lmin,
        'level_max':  lmax,
        'weight':     f.get('weight', '').strip(),
        'ac':         fi('ac'),
        'd1':         f.get('d1', '').strip(),
        'd2':         f.get('d2', '').strip(),
        'hr':         fi('hr'),
        'dr':         fi('dr'),
        'hp':         fi('hp'),
        'mana':       fi('mana'),
        'str_b':      fi('str_b'),
        'dex_b':      fi('dex_b'),
        'int_b':      fi('int_b'),
        'wis_b':      fi('wis_b'),
        'con_b':      fi('con_b'),
        'cha_b':      fi('cha_b'),
        'lck_b':      fi('lck_b'),
        'move_b':     fi('move_b'),
        'item_value': fi('item_value'),
        'gold':       fi('gold'),
        'flags':      flags,
        'antis':      antis,
        'races':      f.get('races', '').strip(),
        'other':      f.get('other', '').strip(),
        'mob_source': f.get('mob_source', '').strip(),
        'area':       f.get('area', '').strip(),
        'date_mod':   f.get('date_mod', '').strip(),
        'editor':     f.get('editor', '').strip(),
        'is_oog':     1 if 'not_in_game' in flags.lower() else 0,
        'is_pkill':   1 if 'pkill' in flags.lower() else 0,
        'is_gloried': fi('is_gloried'),
    }

    if not item['name']:
        flash('Item name is required.', 'danger')
        return redirect(url_for('import_identify'))

    db = get_db()
    existing = db.execute(
        "SELECT id FROM items WHERE name=? AND item_type=? AND wear_loc=?",
        (item['name'], item['item_type'], item['wear_loc'])
    ).fetchone()

    if existing:
        db.execute("""
            UPDATE items SET
                level=?, level_min=?, level_max=?, weight=?, ac=?,
                d1=?, d2=?, hr=?, dr=?, hp=?, mana=?,
                str_b=?, dex_b=?, int_b=?, wis_b=?, con_b=?, cha_b=?, lck_b=?, move_b=?,
                item_value=?, gold=?, flags=?, antis=?, races=?, other=?,
                mob_source=?, area=?, date_mod=?, editor=?, is_oog=?, is_pkill=?, is_gloried=?
            WHERE id=?
        """, (
            item['level'], item['level_min'], item['level_max'], item['weight'], item['ac'],
            item['d1'], item['d2'], item['hr'], item['dr'], item['hp'], item['mana'],
            item['str_b'], item['dex_b'], item['int_b'], item['wis_b'],
            item['con_b'], item['cha_b'], item['lck_b'], item['move_b'],
            item['item_value'], item['gold'],
            item['flags'], item['antis'], item['races'], item['other'],
            item['mob_source'], item['area'], item['date_mod'], item['editor'],
            item['is_oog'], item['is_pkill'], item['is_gloried'],
            existing['id']
        ))
        db.commit()
        flash(f'Updated existing item: {item["name"]}', 'success')
        return redirect(url_for('item_detail', item_id=existing['id']))
    else:
        db.execute("""
            INSERT INTO items
                (item_type, wear_loc, name, level, level_min, level_max, weight, ac,
                 d1, d2, hr, dr, hp, mana,
                 str_b, dex_b, int_b, wis_b, con_b, cha_b, lck_b, move_b,
                 item_value, gold, flags, antis, races, other,
                 mob_source, area, date_mod, editor, is_oog, is_pkill, is_gloried)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            item['item_type'], item['wear_loc'], item['name'],
            item['level'], item['level_min'], item['level_max'],
            item['weight'], item['ac'],
            item['d1'], item['d2'], item['hr'], item['dr'], item['hp'], item['mana'],
            item['str_b'], item['dex_b'], item['int_b'], item['wis_b'],
            item['con_b'], item['cha_b'], item['lck_b'], item['move_b'],
            item['item_value'], item['gold'],
            item['flags'], item['antis'], item['races'], item['other'],
            item['mob_source'], item['area'], item['date_mod'], item['editor'],
            item['is_oog'], item['is_pkill'], item['is_gloried']
        ))
        new_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.commit()
        flash(f'Added new item: {item["name"]}', 'success')
        return redirect(url_for('item_detail', item_id=new_id))


# ── Characters ───────────────────────────────────────────────────────────────

@app.route('/characters')
def characters():
    db = get_db()
    chars = db.execute("SELECT * FROM characters ORDER BY name").fetchall()
    return render_template('characters.html', characters=chars)


@app.route('/characters/new', methods=['GET', 'POST'])
def new_character():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Character name is required.', 'danger')
            return redirect(url_for('new_character'))
        db = get_db()
        try:
            db.execute("""
                INSERT INTO characters
                    (name, char_class, race, sex, level, alignment,
                     base_str, base_dex, base_int, base_wis, base_con,
                     base_cha, base_lck, base_hp, base_mana, base_move)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                name,
                request.form.get('char_class',''),
                request.form.get('race',''),
                request.form.get('sex',''),
                int(request.form.get('level', 50) or 50),
                request.form.get('alignment', 'Neutral'),
                int(request.form.get('base_str', 0) or 0),
                int(request.form.get('base_dex', 0) or 0),
                int(request.form.get('base_int', 0) or 0),
                int(request.form.get('base_wis', 0) or 0),
                int(request.form.get('base_con', 0) or 0),
                int(request.form.get('base_cha', 0) or 0),
                int(request.form.get('base_lck', 0) or 0),
                int(request.form.get('base_hp', 0) or 0),
                int(request.form.get('base_mana', 0) or 0),
                int(request.form.get('base_move', 0) or 0),
            ))
            db.commit()
            char = db.execute("SELECT id FROM characters WHERE name=?", (name,)).fetchone()
            flash(f'Character "{name}" created!', 'success')
            return redirect(url_for('character_detail', char_id=char['id']))
        except sqlite3.IntegrityError:
            flash(f'A character named "{name}" already exists.', 'danger')
    return render_template('new_character.html', classes=CLASSES, races=RACES,
                           sexes=SEXES, alignments=ALIGNMENTS)


@app.route('/characters/<int:char_id>')
def character_detail(char_id):
    db = get_db()
    char = db.execute("SELECT * FROM characters WHERE id=?", (char_id,)).fetchone()
    if char is None:
        flash('Character not found.', 'danger')
        return redirect(url_for('characters'))

    # Build slot grid for current and wanted
    def load_slots(is_wanted):
        rows = db.execute("""
            SELECT cs.slot_name, i.*
            FROM char_slots cs
            LEFT JOIN items i ON cs.item_id = i.id
            WHERE cs.char_id=? AND cs.is_wanted=?
        """, (char_id, is_wanted)).fetchall()
        return {r['slot_name']: r for r in rows}

    current = load_slots(0)
    wanted  = load_slots(1)

    # Build stat totals
    def total_stats(slot_map):
        totals = {f: 0 for f, _ in STAT_FIELDS}
        for _, row in slot_map.items():
            if row['id'] is None:
                continue
            for f, _ in STAT_FIELDS:
                totals[f] += (row[f] or 0)
        return totals

    cur_totals  = total_stats(current)
    want_totals = total_stats(wanted)

    return render_template('character_detail.html',
        char=char, wear_slots=WEAR_SLOTS,
        current=current, wanted=wanted,
        cur_totals=cur_totals, want_totals=want_totals,
        stat_fields=STAT_FIELDS,
        classes=CLASSES, races=RACES, sexes=SEXES, alignments=ALIGNMENTS)


@app.route('/characters/<int:char_id>/delete', methods=['POST'])
def delete_character(char_id):
    db = get_db()
    db.execute("DELETE FROM characters WHERE id=?", (char_id,))
    db.commit()
    flash('Character deleted.', 'success')
    return redirect(url_for('characters'))


@app.route('/characters/<int:char_id>/edit', methods=['POST'])
def edit_character(char_id):
    db = get_db()
    db.execute("""
        UPDATE characters SET
            name=?, char_class=?, race=?, sex=?, level=?, alignment=?,
            base_str=?, base_dex=?, base_int=?, base_wis=?, base_con=?,
            base_cha=?, base_lck=?, base_hp=?, base_mana=?, base_move=?
        WHERE id=?
    """, (
        request.form.get('name','').strip(),
        request.form.get('char_class',''),
        request.form.get('race',''),
        request.form.get('sex',''),
        int(request.form.get('level', 50) or 50),
        request.form.get('alignment', 'Neutral'),
        int(request.form.get('base_str', 0) or 0),
        int(request.form.get('base_dex', 0) or 0),
        int(request.form.get('base_int', 0) or 0),
        int(request.form.get('base_wis', 0) or 0),
        int(request.form.get('base_con', 0) or 0),
        int(request.form.get('base_cha', 0) or 0),
        int(request.form.get('base_lck', 0) or 0),
        int(request.form.get('base_hp', 0) or 0),
        int(request.form.get('base_mana', 0) or 0),
        int(request.form.get('base_move', 0) or 0),
        char_id
    ))
    db.commit()
    flash('Character updated.', 'success')
    return redirect(url_for('character_detail', char_id=char_id))


@app.route('/characters/<int:char_id>/duplicate', methods=['POST'])
def duplicate_character(char_id):
    db = get_db()
    src = db.execute("SELECT * FROM characters WHERE id=?", (char_id,)).fetchone()
    if not src:
        flash('Character not found.', 'danger')
        return redirect(url_for('characters'))
    new_name = src['name'] + ' (copy)'
    try:
        db.execute("""
            INSERT INTO characters
                (name, char_class, race, sex, level, alignment,
                 base_str, base_dex, base_int, base_wis, base_con,
                 base_cha, base_lck, base_hp, base_mana, base_move)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (new_name, src['char_class'], src['race'], src['sex'], src['level'], src['alignment'],
              src['base_str'], src['base_dex'], src['base_int'], src['base_wis'], src['base_con'],
              src['base_cha'], src['base_lck'], src['base_hp'], src['base_mana'], src['base_move']))
        new_id = db.execute("SELECT id FROM characters WHERE name=?", (new_name,)).fetchone()['id']
        # Copy slots
        slots = db.execute(
            "SELECT slot_name, item_id, is_wanted FROM char_slots WHERE char_id=?", (char_id,)
        ).fetchall()
        for s in slots:
            db.execute(
                "INSERT INTO char_slots (char_id, slot_name, item_id, is_wanted) VALUES (?,?,?,?)",
                (new_id, s['slot_name'], s['item_id'], s['is_wanted'])
            )
        db.commit()
        flash(f'Duplicated as "{new_name}".', 'success')
        return redirect(url_for('character_detail', char_id=new_id))
    except sqlite3.IntegrityError:
        flash('A character with that name already exists.', 'danger')
        return redirect(url_for('character_detail', char_id=char_id))


# ── Buff toggles (stat-preview switches, persisted per character) ─────────────

# Maps the front-end toggle id to its characters column.
BUFF_COLUMNS = {
    'levelingSpells': 'buff_leveling',
    'thoricBlessing': 'buff_thoric',
}

@app.route('/characters/<int:char_id>/buff', methods=['POST'])
def set_buff(char_id):
    buff    = request.form.get('buff', '')
    column  = BUFF_COLUMNS.get(buff)
    if column is None:
        return ('unknown buff', 400)
    checked = 1 if request.form.get('checked') == '1' else 0
    db = get_db()
    # column comes from a fixed whitelist above, so this f-string is safe
    db.execute(f"UPDATE characters SET {column}=? WHERE id=?", (checked, char_id))
    db.commit()
    return ('', 204)


# ── Slot assignment ───────────────────────────────────────────────────────────

@app.route('/characters/<int:char_id>/slot', methods=['POST'])
def set_slot(char_id):
    slot_name = request.form.get('slot_name','').strip()
    item_id   = request.form.get('item_id','').strip() or None
    is_wanted = int(request.form.get('is_wanted', 0))
    clear     = request.form.get('clear') == '1'

    db = get_db()
    if clear or item_id is None:
        db.execute(
            "DELETE FROM char_slots WHERE char_id=? AND slot_name=? AND is_wanted=?",
            (char_id, slot_name, is_wanted)
        )
    else:
        existing = db.execute(
            "SELECT id FROM char_slots WHERE char_id=? AND slot_name=? AND is_wanted=?",
            (char_id, slot_name, is_wanted)
        ).fetchone()
        if existing:
            db.execute(
                "UPDATE char_slots SET item_id=? WHERE id=?",
                (int(item_id), existing['id'])
            )
        else:
            db.execute(
                "INSERT INTO char_slots (char_id, slot_name, item_id, is_wanted) VALUES (?,?,?,?)",
                (char_id, slot_name, int(item_id), is_wanted)
            )
    db.commit()
    return redirect(url_for('character_detail', char_id=char_id) + f'#sc-{is_wanted}-{slot_name}')


@app.route('/characters/<int:char_id>/copy_to_wanted', methods=['POST'])
def copy_to_wanted(char_id):
    db = get_db()
    db.execute("DELETE FROM char_slots WHERE char_id=? AND is_wanted=1", (char_id,))
    slots = db.execute(
        "SELECT slot_name, item_id FROM char_slots WHERE char_id=? AND is_wanted=0", (char_id,)
    ).fetchall()
    for s in slots:
        db.execute(
            "INSERT INTO char_slots (char_id, slot_name, item_id, is_wanted) VALUES (?,?,?,1)",
            (char_id, s['slot_name'], s['item_id'])
        )
    db.commit()
    flash('Current equipment copied to wanted list.', 'success')
    return redirect(url_for('character_detail', char_id=char_id))


# ── Item search (JSON for slot picker) ───────────────────────────────────────

@app.route('/api/items')
def api_items():
    db = get_db()
    q    = request.args.get('q', '').strip()
    loc  = request.args.get('wear_loc', '').strip()
    typ  = request.args.get('item_type', '').strip()
    params = []
    clauses = ['1=1']
    if q:
        clauses.append("name LIKE ?")
        params.append(f'%{q}%')
    if loc:
        clauses.append("wear_loc = ?")
        params.append(loc)
    if typ:
        clauses.append("item_type = ?")
        params.append(typ)
    where = 'WHERE ' + ' AND '.join(clauses)
    rows = db.execute(
        f"SELECT id, name, item_type, wear_loc, level FROM items {where} ORDER BY name LIMIT 50",
        params
    ).fetchall()
    return jsonify([dict(r) for r in rows])


# ── Startup ───────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    print("RoD Equipment Database running at http://127.0.0.1:5001")
    app.run(host='0.0.0.0', debug=True, port=5001)
