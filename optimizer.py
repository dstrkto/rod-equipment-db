"""
Equipment optimizer for RoD characters.

Goal model (per the user's spec + dyrdex.com prestige data):
  * Must-max stats STR/DEX/INT/WIS are hard targets — reach the class cap.
  * CON has no hard cap; it stacks invisibly past the shown value, so it is
    always maximized (secondary priority in Balanced mode).
  * LCK and CHA never need maxing.
  * A chosen goal (HP / Mana / Moves / HR / DR / Combat / AC / CON) is then
    maximized with whatever gear budget remains ("goal first in goal modes").
  * Buffs that count toward caps come from the character's saved toggles.

Algorithm: cap-aware greedy per slot. For each wear slot the best-scoring
eligible item(s) are chosen; scores reward closing unmet caps first, then the
goal, and never reward stat points wasted past a cap. It's a strong heuristic
(reviewable, not a proven optimum) — the user applies it to Wanted gear.
"""

# ── Base class stat roles ─────────────────────────────────────────────────────
# cap: primary=25, secondary=22, deficient=18, other=20. CON has no hard cap.
BASE_CLASS_STATS = {
    'Mage':        {'primary': 'int_b', 'secondary': 'wis_b', 'deficient': 'str_b'},
    'Cleric':      {'primary': 'wis_b', 'secondary': 'int_b', 'deficient': 'dex_b'},
    'Thief':       {'primary': 'dex_b', 'secondary': 'cha_b', 'deficient': 'wis_b'},
    'Warrior':     {'primary': 'str_b', 'secondary': 'dex_b', 'deficient': 'int_b'},
    'Vampire':     {'primary': 'dex_b', 'secondary': 'int_b', 'deficient': None},
    'Druid':       {'primary': 'wis_b', 'secondary': 'con_b', 'deficient': 'cha_b'},
    'Ranger':      {'primary': 'str_b', 'secondary': 'wis_b', 'deficient': 'cha_b'},
    'Augurer':     {'primary': 'wis_b', 'secondary': 'lck_b', 'deficient': 'dex_b'},
    'Paladin':     {'primary': 'str_b', 'secondary': 'wis_b', 'deficient': 'int_b'},
    'Nephandi':    {'primary': 'int_b', 'secondary': 'dex_b', 'deficient': 'lck_b'},
    'Fathomer':    {'primary': 'dex_b', 'secondary': 'int_b', 'deficient': 'con_b'},
    'Bladesinger': {'primary': 'dex_b', 'secondary': 'str_b', 'deficient': 'lck_b'},
    'Barbarian':   {'primary': 'str_b', 'secondary': 'con_b', 'deficient': 'int_b'},
}

# ── Exact multi-class prestige caps (dyrdex.com) ──────────────────────────────
# key: (primary_class, secondary_class); values are the must-max stat caps.
# Table order there is Str/Int/Wis/Dex (Con/Cha/Lck omitted — not must-max).
_P = {
    ('Thief', 'Warrior'):   (21, 20, 18, 25),
    ('Thief', 'Druid'):     (20, 20, 19, 25),
    ('Thief', 'Cleric'):    (20, 20, 19, 25),
    ('Thief', 'Mage'):      (20, 21, 18, 25),
    ('Warrior', 'Thief'):   (25, 18, 20, 23),
    ('Warrior', 'Mage'):    (25, 19, 20, 22),
    ('Warrior', 'Cleric'):  (25, 18, 21, 22),
    ('Warrior', 'Druid'):   (25, 18, 21, 22),
    ('Mage', 'Thief'):      (18, 25, 22, 21),
    ('Mage', 'Warrior'):    (19, 25, 22, 20),
    ('Mage', 'Cleric'):     (18, 25, 23, 20),
    ('Mage', 'Druid'):      (18, 25, 23, 20),
    ('Cleric', 'Warrior'):  (21, 22, 25, 18),
    ('Cleric', 'Thief'):    (20, 22, 25, 19),
    ('Cleric', 'Mage'):     (20, 23, 25, 18),
    ('Cleric', 'Druid'):    (20, 22, 26, 18),
    ('Druid', 'Cleric'):    (20, 20, 26, 20),
    ('Druid', 'Mage'):      (20, 21, 25, 20),
    ('Druid', 'Warrior'):   (21, 20, 25, 20),
    ('Druid', 'Thief'):     (20, 20, 25, 20),
}
PRESTIGE_CAPS = {
    combo: {'str_b': s, 'int_b': i, 'wis_b': w, 'dex_b': d}
    for combo, (s, i, w, d) in _P.items()
}

# Single-class prestige upgrades: +1 to prime stat (26). eq class = base class.
SINGLE_PRESTIGE = {
    'Harbinger': 'Augurer', 'Buccaneer': 'Fathomer', 'Infernalist': 'Nephandi',
    'Knight': 'Paladin', 'Hunter': 'Ranger', 'Dread Vampire': 'Vampire',
}

# Stats we require at cap, and the free ones we ignore.
MUSTMAX_CAPPED = ['str_b', 'dex_b', 'int_b', 'wis_b']
BUFFED_STATS = ['str_b', 'dex_b', 'int_b', 'wis_b', 'con_b', 'cha_b']  # +2/+3 apply

ITEM_STATS = ['hr', 'dr', 'hp', 'mana',
              'str_b', 'dex_b', 'int_b', 'wis_b', 'con_b', 'cha_b', 'lck_b', 'move_b', 'ac']

GOALS = [
    ('balanced',  'Balanced — max primary stat, then CON'),
    ('max_hp',    'Maximum HP'),
    ('max_mana',  'Maximum Mana'),
    ('max_moves', 'Maximum Moves'),
    ('max_hr',    'Maximum Hit Roll'),
    ('max_dr',    'Maximum Dam Roll'),
    ('max_combat','Maximum HR + DR (combat)'),
    ('max_ac',    'Maximum AC (tank)'),
    ('max_con',   'Maximum CON (stacks past cap)'),
]
GOAL_KEYS = {k for k, _ in GOALS}


def _base_class(cls):
    """Base class name used for equipment eligibility and role lookup."""
    if not cls:
        return ''
    if cls.startswith('Prestige:'):
        return cls.split(':', 1)[1].strip().split('/')[0].strip()
    return SINGLE_PRESTIGE.get(cls, cls)


def resolve_class(char_class):
    """Return (caps, primary_stat, eq_class) for a character's class string.

    caps        — {stat: cap} for the 4 must-max stats
    primary_stat — the class's prime stat key (most important)
    eq_class    — base class name that governs equipment eligibility
    """
    cc = char_class or ''
    if cc.startswith('Prestige:'):
        parts = [p.strip() for p in cc.split(':', 1)[1].strip().split('/')]
        primary_cls = parts[0]
        sec_cls = parts[1] if len(parts) > 1 else None
        caps = PRESTIGE_CAPS.get((primary_cls, sec_cls)) or _base_caps(primary_cls)
        primary_stat = BASE_CLASS_STATS.get(primary_cls, {}).get('primary')
        return dict(caps), primary_stat, primary_cls

    base = SINGLE_PRESTIGE.get(cc, cc)
    caps = _base_caps(base)
    if cc in SINGLE_PRESTIGE:  # single-class prestige: +1 to prime → 26
        prime = BASE_CLASS_STATS.get(base, {}).get('primary')
        if prime in caps:
            caps[prime] = 26
    primary_stat = BASE_CLASS_STATS.get(base, {}).get('primary')
    return caps, primary_stat, base


def _base_caps(cls):
    roles = BASE_CLASS_STATS.get(cls, {})
    caps = {}
    for stat in MUSTMAX_CAPPED:
        if stat == roles.get('primary'):
            caps[stat] = 25
        elif stat == roles.get('secondary'):
            caps[stat] = 22
        elif stat == roles.get('deficient'):
            caps[stat] = 18
        else:
            caps[stat] = 20
    return caps


def buff_bonus(char):
    """Per-stat bonus from the character's saved buff toggles."""
    bonus = 0
    if char.get('buff_leveling'):
        bonus += 2
    if char.get('buff_thoric'):
        bonus += 3
    return {s: bonus for s in BUFFED_STATS}


# ── Eligibility ───────────────────────────────────────────────────────────────

def is_eligible(item, ctx):
    """ctx: dict with level, eq_class, align_anti, sex, race."""
    lmin = item.get('level_min') or 0
    if lmin and ctx['level'] and lmin > ctx['level']:
        return False
    antis = (item.get('antis') or '').lower()
    if ctx['eq_class'] and ('anti-' + ctx['eq_class'].lower()) in antis:
        return False
    if ctx['align_anti'] and ('anti-' + ctx['align_anti'].lower()) in antis:
        return False
    if ctx['sex'] and ('anti-' + ctx['sex'].lower()) in antis:
        return False
    if item.get('is_oog') or item.get('is_pkill'):
        return False
    races = (item.get('races') or '').strip()
    if races and ctx['race'] and (' ' + ctx['race'] + ' ') not in (' ' + races + ' '):
        return False
    return True


# ── Scoring ───────────────────────────────────────────────────────────────────
_W_PRIMARY = 1200.0   # per point of headroom on the primary stat
_W_CAP     = 1000.0   # per point of headroom on other must-max stats
_W_CON_BAL = 700.0    # CON per point in Balanced mode
_W_CON_GOAL = 150.0   # CON per point in goal modes (kept, not prioritized)
_W_GOAL    = 900.0    # goal stat per point (below caps, above CON) in goal modes
_NEG_PEN   = 1100.0   # penalty per point an item drains a must-max stat
_BASELINE  = {'hp': 0.5, 'mana': 0.5, 'hr': 0.3, 'dr': 0.3}  # generic usefulness


def _goal_value(item, goal):
    if goal == 'max_hp':     return item.get('hp') or 0
    if goal == 'max_mana':   return item.get('mana') or 0
    if goal == 'max_moves':  return item.get('move_b') or 0
    if goal == 'max_hr':     return item.get('hr') or 0
    if goal == 'max_dr':     return item.get('dr') or 0
    if goal == 'max_combat': return (item.get('hr') or 0) + (item.get('dr') or 0)
    if goal == 'max_ac':     return -(item.get('ac') or 0)  # lower AC = better armor
    return 0


def score_item(item, caps, effective, primary_stat, goal):
    """effective = base+buffs+gear-so-far per stat (headroom = cap - effective)."""
    s = 0.0
    for stat in MUSTMAX_CAPPED:
        v = item.get(stat) or 0
        if v > 0:
            head = max(0, caps.get(stat, 20) - effective.get(stat, 0))
            w = _W_PRIMARY if stat == primary_stat else _W_CAP
            s += w * min(v, head)
        elif v < 0:
            s += _NEG_PEN * v  # draining a needed stat is bad

    con = item.get('con_b') or 0
    if goal == 'max_con':
        s += _W_GOAL * con
    else:
        s += (_W_CON_BAL if goal == 'balanced' else _W_CON_GOAL) * con
        if goal != 'balanced':
            s += _W_GOAL * _goal_value(item, goal)

    for stat, w in _BASELINE.items():  # tie-break toward generally useful gear
        s += w * max(0, item.get(stat) or 0)
    return s


# ── Optimize ──────────────────────────────────────────────────────────────────

def _setup(char, align_anti):
    caps, primary_stat, eq_class = resolve_class(char.get('char_class'))
    bonus = buff_bonus(char)
    base = {s: (char.get('base_' + s[:-2]) or 0) + bonus.get(s, 0)
            for s in ['str_b', 'dex_b', 'int_b', 'wis_b', 'con_b', 'cha_b', 'lck_b']}
    ctx = {
        'level': char.get('level') or 0,
        'eq_class': eq_class,
        'align_anti': align_anti,
        'sex': char.get('sex') or '',
        'race': char.get('race') or '',
    }
    return ctx, caps, primary_stat, base


def _eligible_for_slot(items_by_slot, slot_key, layer_slot, ctx):
    items = [i for i in items_by_slot.get(slot_key, []) if is_eligible(i, ctx)]
    if layer_slot:
        items = [i for i in items if 'layerable' in (i.get('flags') or '').lower()]
    return items


def _greedy(items_by_slot, wear_slots, ctx, caps, primary_stat, base, goal):
    """Cap-aware greedy fill (used for the feasible Balanced base)."""
    gear = {s: 0 for s in ITEM_STATS}
    used_unique = set()
    result = {}
    for slot_key, _label, max_count in wear_slots:
        layer = max_count > 2
        items = _eligible_for_slot(items_by_slot, slot_key, layer, ctx)
        if not items:
            continue
        used_in_slot = {}
        for idx in range(max_count):
            effective = {s: base.get(s, 0) + gear.get(s, 0) for s in base}
            best, best_score = None, 0.0
            for it in items:
                iid = it['id']
                if 'unique' in (it.get('flags') or '').lower() and iid in used_unique:
                    continue
                if used_in_slot.get(iid, 0) >= (1 if layer else 2):
                    continue
                sc = score_item(it, caps, effective, primary_stat, goal)
                if sc > best_score:
                    best, best_score = it, sc
            if best is None or best_score <= 0:
                break
            result[f'{slot_key}_{idx}'] = best
            used_in_slot[best['id']] = used_in_slot.get(best['id'], 0) + 1
            if 'unique' in (best.get('flags') or '').lower():
                used_unique.add(best['id'])
            for s in ITEM_STATS:
                gear[s] += best.get(s) or 0
    return result


def _copies_ok(result, name, cand, layer):
    """Respect the unique flag globally and copy limits within a slot."""
    cid = cand['id']
    prefix = name.rsplit('_', 1)[0]
    if 'unique' in (cand.get('flags') or '').lower():
        if any(k != name and v['id'] == cid for k, v in result.items()):
            return False
    same_slot = sum(1 for k, v in result.items()
                    if k != name and k.rsplit('_', 1)[0] == prefix and v['id'] == cid)
    return same_slot < (1 if layer else 2)


def _improve_for_goal(result, items_by_slot, wear_slots, ctx, caps, base, goal):
    """Local search from a feasible base: swap/fill to raise the goal while
    never dropping a must-max stat that is currently at cap below its cap."""
    gear = {s: 0 for s in ITEM_STATS}
    for it in result.values():
        for s in ITEM_STATS:
            gear[s] += it.get(s) or 0

    def have(stat):
        return base.get(stat, 0) + gear[stat]

    def preserves_caps(current, cand):
        for stat in MUSTMAX_CAPPED:
            cap = caps.get(stat, 20)
            cur_total = have(stat)
            delta = (cand.get(stat) or 0) - ((current.get(stat) or 0) if current else 0)
            if cur_total >= cap and cur_total + delta < cap:
                return False  # would break an already-met cap
        return True

    for _pass in range(4):
        changed = False
        for slot_key, _label, max_count in wear_slots:
            layer = max_count > 2
            elig = _eligible_for_slot(items_by_slot, slot_key, layer, ctx)
            if not elig:
                continue
            for idx in range(max_count):
                name = f'{slot_key}_{idx}'
                current = result.get(name)
                best = None
                best_gv = _goal_value(current, goal) if current else 0
                for cand in elig:
                    if current is not None and cand['id'] == current['id']:
                        continue
                    gv = _goal_value(cand, goal)
                    if gv <= best_gv:
                        continue
                    if not preserves_caps(current, cand):
                        continue
                    if not _copies_ok(result, name, cand, layer):
                        continue
                    best, best_gv = cand, gv
                if best is not None:
                    for s in ITEM_STATS:
                        gear[s] += (best.get(s) or 0) - ((current.get(s) or 0) if current else 0)
                    result[name] = best
                    changed = True
        if not changed:
            break


def optimize(char, items_by_slot, wear_slots, goal, align_anti):
    """Return {slot_name: item} best-in-slot suggestion for the goal.

    Caps are a hard constraint: the Balanced base satisfies them (when the
    gear pool allows), then goal modes improve the goal without breaking any
    already-met cap.
    """
    if goal not in GOAL_KEYS:
        goal = 'balanced'
    ctx, caps, primary_stat, base = _setup(char, align_anti)
    result = _greedy(items_by_slot, wear_slots, ctx, caps, primary_stat, base, 'balanced')
    if goal != 'balanced':
        _improve_for_goal(result, items_by_slot, wear_slots, ctx, caps, base, goal)
    return result


def cap_report(char, result_totals_dict):
    """Per must-max stat: base+buffs+gear vs cap, and whether it's met.
    CON is reported as uncapped (always 'met' — more is better)."""
    caps, primary_stat, _ = resolve_class(char.get('char_class'))
    bonus = buff_bonus(char)
    rows = []
    for stat, label in [('str_b', 'STR'), ('dex_b', 'DEX'), ('int_b', 'INT'),
                        ('wis_b', 'WIS'), ('con_b', 'CON')]:
        base = (char.get('base_' + stat[:-2]) or 0) + bonus.get(stat, 0)
        have = base + (result_totals_dict.get(stat) or 0)
        cap = None if stat == 'con_b' else caps.get(stat)
        rows.append({
            'stat': stat, 'label': label, 'have': have, 'cap': cap,
            'met': (cap is None) or (have >= cap),
            'is_primary': stat == primary_stat,
            'over': cap is not None and have > cap,
        })
    return rows


def result_totals(result):
    totals = {s: 0 for s in ITEM_STATS}
    for item in result.values():
        for s in ITEM_STATS:
            totals[s] += item.get(s) or 0
    return totals
