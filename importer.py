"""Parse RoD_Item.txt (pipe-delimited) and in-game identify output into item dicts."""
import re

# Column indices in the pipe-split row
C_TYPE   = 0
C_WEAR   = 1
C_NAME   = 2
C_LEVEL  = 3
C_WEIGHT = 4
C_AC     = 5
C_D1     = 6
C_D2     = 7
C_HR     = 8
C_DR     = 9
C_HP     = 10
C_MANA   = 11
C_STR    = 12
C_DEX    = 13
C_INT    = 14
C_WIS    = 15
C_CON    = 16
C_CHA    = 17
C_LCK    = 18
C_MOVE   = 19
C_IVAL   = 20   # AC value for armor; weapon weight otherwise
C_GOLD   = 21
C_FLAGS  = 22
C_ANTIS  = 23
C_RACES  = 24
C_OTHER  = 25
C_MOB    = 26
C_AREA   = 27
C_DATE   = 28
C_EDITOR = 29


def _int(val):
    val = val.strip()
    if not val:
        return 0
    # accept ranges like "46-49" → use the minimum
    m = re.match(r'^-?\d+', val)
    return int(m.group()) if m else 0


def _level_range(val):
    """Return (min, max) integers from a level string like '46-49' or '50'."""
    val = val.strip()
    m = re.match(r'^(\d+)(?:-(\d+))?', val)
    if not m:
        return 0, 0
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else lo
    return lo, hi


def parse_file(path):
    """
    Yield item dicts from a RoD_Item.txt file.
    Skips the header line and any malformed rows.
    """
    with open(path, encoding='utf-8', errors='replace') as fh:
        for lineno, raw in enumerate(fh, 1):
            if lineno == 1:
                continue  # header
            line = raw.rstrip('\n')
            if not line.strip():
                continue

            cols = [c.strip() for c in line.split('|')]
            if len(cols) < 22:
                continue  # too short to be a real item

            item_type = cols[C_TYPE].lower()
            if not item_type:
                continue

            flags = cols[C_FLAGS] if len(cols) > C_FLAGS else ''
            antis = cols[C_ANTIS] if len(cols) > C_ANTIS else ''
            level_txt = cols[C_LEVEL]
            lmin, lmax = _level_range(level_txt)

            yield {
                'item_type':  item_type,
                'wear_loc':   cols[C_WEAR].lower(),
                'name':       cols[C_NAME],
                'level':      level_txt,
                'level_min':  lmin,
                'level_max':  lmax,
                'weight':     cols[C_WEIGHT] if len(cols) > C_WEIGHT else '',
                'ac':         _int(cols[C_AC]),
                'd1':         cols[C_D1]  if len(cols) > C_D1  else '',
                'd2':         cols[C_D2]  if len(cols) > C_D2  else '',
                'hr':         _int(cols[C_HR]),
                'dr':         _int(cols[C_DR]),
                'hp':         _int(cols[C_HP]),
                'mana':       _int(cols[C_MANA]),
                'str_b':      _int(cols[C_STR]),
                'dex_b':      _int(cols[C_DEX]),
                'int_b':      _int(cols[C_INT]),
                'wis_b':      _int(cols[C_WIS]),
                'con_b':      _int(cols[C_CON]),
                'cha_b':      _int(cols[C_CHA]),
                'lck_b':      _int(cols[C_LCK]),
                'move_b':     _int(cols[C_MOVE]),
                'item_value': _int(cols[C_IVAL]),
                'gold':       _int(cols[C_GOLD]),
                'flags':      flags,
                'antis':      antis,
                'races':      cols[C_RACES] if len(cols) > C_RACES else '',
                'other':      cols[C_OTHER] if len(cols) > C_OTHER else '',
                'mob_source': cols[C_MOB]   if len(cols) > C_MOB   else '',
                'area':       cols[C_AREA]  if len(cols) > C_AREA  else '',
                'date_mod':   cols[C_DATE]  if len(cols) > C_DATE  else '',
                'editor':     cols[C_EDITOR] if len(cols) > C_EDITOR else '',
                'is_oog':     1 if 'not_in_game' in flags.lower() else 0,
                'is_pkill':   1 if 'pkill' in flags.lower() else 0,
                'is_gloried': 0,
            }


# ── Stat name → DB field mapping for identify parser ─────────────────────────

_STAT_MAP = {
    'hit roll': 'hr',        'hitroll': 'hr',       'hit_roll': 'hr',
    'damage roll': 'dr',     'damroll': 'dr',        'damage_roll': 'dr',
    'hp': 'hp',              'hit points': 'hp',     'hit_points': 'hp', 'hits': 'hp',
    'mana': 'mana',          'mana points': 'mana',
    'move': 'move_b',        'movement': 'move_b',   'moves': 'move_b',
    'strength': 'str_b',     'str': 'str_b',
    'dexterity': 'dex_b',    'dex': 'dex_b',
    'intelligence': 'int_b', 'int': 'int_b',
    'wisdom': 'wis_b',       'wis': 'wis_b',
    'constitution': 'con_b', 'con': 'con_b',
    'charisma': 'cha_b',     'cha': 'cha_b',
    'luck': 'lck_b',
    'armor class': 'ac',     'ac': 'ac',
}

_SAVE_MAP = {
    'saving spell':      'SvSp',
    'saving breath':     'SvBr',
    'saving paralysis':  'SvPa',
    'saving rod':        'SvRo',
    'saving poison':     'SvPo',
}

# Tokens in "Special properties:" that belong in antis vs flags
_ANTI_PREFIX = 'anti-'
_FLAG_SKIP = {'none'}

# Wear location aliases from identify text → DB wear_loc values
_WEAR_ALIASES = {
    'wield':           '*',
    'two-handed':      '*',
    'wield two-handed':'*',
    'about body':      'about',
    'about the body':  'about',
    'neck':            'neck',
    'body':            'body',
    'head':            'head',
    'legs':            'legs',
    'feet':            'feet',
    'hands':           'hands',
    'arms':            'arms',
    'about':           'about',
    'waist':           'waist',
    'wrists':          'wrist',
    'wrist':           'wrist',
    'finger':          'finger',
    'light':           'light',
    'hold':            'hold',
    'shield':          'shield',
    'ears':            'ears',
    'eyes':            'eyes',
    'face':            'face',
    'back':            'back',
    'ankle':           'ankle',
    'ankles':          'ankle',
    'lance':           'lance',
}


def _blank_item():
    return {
        'name': '', 'item_type': '', 'wear_loc': '',
        'level': '', 'level_min': 0, 'level_max': 0,
        'weight': '', 'ac': 0, 'd1': '', 'd2': '',
        'hr': 0, 'dr': 0, 'hp': 0, 'mana': 0,
        'str_b': 0, 'dex_b': 0, 'int_b': 0, 'wis_b': 0,
        'con_b': 0, 'cha_b': 0, 'lck_b': 0, 'move_b': 0,
        'item_value': 0, 'gold': 0,
        'flags': '', 'antis': '', 'races': '', 'other': '',
        'mob_source': '', 'area': '', 'date_mod': '', 'editor': '',
        'is_oog': 0, 'is_pkill': 0, 'is_gloried': 0,
    }


def parse_identify(text):
    """
    Parse one block of RoD in-game 'identify' output into an item dict.
    Fields that identify doesn't supply (mob_source, area, antis, races)
    are left blank for the user to fill in.
    Returns None if the text doesn't look like a valid identify.
    """
    item = _blank_item()
    special = []   # accumulates tokens for item['other']

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        # Object 'Name' is infused with your magic... / is an ordinary object.
        m = re.match(r"Object '(.+?)' is", line, re.IGNORECASE)
        if m:
            item['name'] = m.group(1).strip()
            continue

        # It is a level X type, weight Y.
        m = re.match(
            r"It is a level (\d+) ([\w ]+?),\s*weight (\d+)\.", line, re.IGNORECASE
        )
        if m:
            lv = int(m.group(1))
            item['level'] = str(lv)
            item['level_min'] = lv
            item['level_max'] = lv
            item['item_type'] = m.group(2).strip().lower()
            item['weight'] = m.group(3).strip()
            continue

        # Locations it can be worn:  loc1 loc2
        m = re.match(r"Locations? it can be worn:\s*(.*)", line, re.IGNORECASE)
        if m:
            raw_loc = m.group(1).strip().lower()
            item['wear_loc'] = _WEAR_ALIASES.get(raw_loc, raw_loc)
            continue

        # Special properties:  glow hum dark anti-Evil anti-Mage ...
        m = re.match(r"Special properties:\s*(.*)", line, re.IGNORECASE)
        if m:
            tokens = m.group(1).strip().split()
            flags_out = []
            antis_out = []
            for tok in tokens:
                if tok.lower() in _FLAG_SKIP:
                    continue
                if tok.lower().startswith(_ANTI_PREFIX):
                    antis_out.append(tok)
                else:
                    flags_out.append(tok)
            item['flags'] = ' '.join(flags_out)
            item['antis'] = ' '.join(antis_out)
            item['is_oog']   = 1 if 'not_in_game' in item['flags'].lower() else 0
            item['is_pkill'] = 1 if 'pkill'        in item['flags'].lower() else 0
            continue

        # This armor/weapon/item has a gold value of X.
        m = re.match(r"This \w+ has a gold value of (\d+)\.", line, re.IGNORECASE)
        if m:
            item['gold'] = int(m.group(1))
            continue

        # Armor class is X of Y.
        m = re.match(r"Armor class is (\d+) of (\d+)\.", line, re.IGNORECASE)
        if m:
            item['item_value'] = int(m.group(1))
            continue

        # Damage is XdY, hit(Z), damage(W). / type crushing / bonus B
        m = re.match(r"Damage is (\d+)d(\d+)", line, re.IGNORECASE)
        if m:
            ndice = int(m.group(1))
            sdice = int(m.group(2))
            item['d1'] = str(ndice)
            item['d2'] = str(ndice * sdice)
            hm = re.search(r'hit\((-?\d+)\)', line)
            dm = re.search(r'damage\((-?\d+)\)', line)
            if hm:
                item['hr'] = int(hm.group(1))
            if dm:
                item['dr'] = int(dm.group(1))
            tm = re.search(r'\btype\s+(\w+)', line, re.IGNORECASE)
            if tm:
                special.append(f'[{tm.group(1).lower()}]')
            continue

        # Affects X by Y.
        m = re.match(r"Affects (.+?) by (.+?)\.\s*$", line, re.IGNORECASE)
        if m:
            affect = m.group(1).strip().lower()
            val_str = m.group(2).strip()

            if affect == 'affected_by':
                # Special flag-type affects (detect_invis, sneak, hide, pass_door, etc.)
                special.append(val_str)
                continue

            if affect in _STAT_MAP:
                field = _STAT_MAP[affect]
                try:
                    item[field] = int(val_str)
                except ValueError:
                    pass
                continue

            if affect in _SAVE_MAP:
                abbr = _SAVE_MAP[affect]
                try:
                    v = int(val_str)
                    special.append(f'{abbr}{v:+d}')
                except ValueError:
                    pass
                continue

            if affect == 'age':
                try:
                    v = int(val_str)
                    special.append(f'Age_{v:+d}')
                except ValueError:
                    pass
                continue

            # Resist/suscept lines: "resistant" "susceptible" + type
            if affect in ('resistant', 'susceptible'):
                prefix = 'Res' if affect == 'resistant' else 'Sus'
                special.append(f'{prefix}_{val_str}')
                continue

            # Fallback: keep it in other verbatim
            special.append(f'{affect}_{val_str}')
            continue

        # Races that can use this item (some MUD versions show this)
        m = re.match(r"Races?(?:\s+that)?\s+(?:can\s+use|allowed):\s*(.*)", line, re.IGNORECASE)
        if m:
            item['races'] = m.group(1).strip()
            continue

    item['other'] = ' '.join(special)

    # Return None if we couldn't even find a name
    return item if item['name'] else None
