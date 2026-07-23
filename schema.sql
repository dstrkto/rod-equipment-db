CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_type TEXT NOT NULL DEFAULT '',
    wear_loc  TEXT NOT NULL DEFAULT '',
    name      TEXT NOT NULL,
    level     TEXT DEFAULT '',   -- stored as text; may be range "X-Y"
    level_min INTEGER DEFAULT 0,
    level_max INTEGER DEFAULT 0,
    weight    TEXT DEFAULT '',
    ac        INTEGER DEFAULT 0, -- AC apply (negative = better for player)
    d1        TEXT DEFAULT '',   -- weapon ndice (may be range)
    d2        TEXT DEFAULT '',   -- weapon max_dam (may be range)
    hr        INTEGER DEFAULT 0,
    dr        INTEGER DEFAULT 0,
    hp        INTEGER DEFAULT 0,
    mana      INTEGER DEFAULT 0,
    str_b     INTEGER DEFAULT 0,
    dex_b     INTEGER DEFAULT 0,
    int_b     INTEGER DEFAULT 0,
    wis_b     INTEGER DEFAULT 0,
    con_b     INTEGER DEFAULT 0,
    cha_b     INTEGER DEFAULT 0,
    lck_b     INTEGER DEFAULT 0,
    move_b    INTEGER DEFAULT 0,
    item_value INTEGER DEFAULT 0, -- AC value for armor; weight for weapons
    gold      INTEGER DEFAULT 0,
    flags     TEXT DEFAULT '',
    antis     TEXT DEFAULT '',
    races     TEXT DEFAULT '',
    other     TEXT DEFAULT '',   -- special affects / other notes
    mob_source TEXT DEFAULT '',
    area      TEXT DEFAULT '',
    date_mod  TEXT DEFAULT '',
    editor    TEXT DEFAULT '',
    is_oog    INTEGER DEFAULT 0, -- not_in_game flag
    is_pkill  INTEGER DEFAULT 0,
    is_gloried INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_items_name      ON items(name);
CREATE INDEX IF NOT EXISTS idx_items_type      ON items(item_type);
CREATE INDEX IF NOT EXISTS idx_items_wear_loc  ON items(wear_loc);
CREATE INDEX IF NOT EXISTS idx_items_level_min ON items(level_min);
CREATE INDEX IF NOT EXISTS idx_items_area      ON items(area);

CREATE TABLE IF NOT EXISTS characters (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT UNIQUE NOT NULL,
    char_class TEXT DEFAULT '',
    race       TEXT DEFAULT '',
    sex        TEXT DEFAULT '',
    level      INTEGER DEFAULT 50,
    base_str   INTEGER DEFAULT 0,
    base_dex   INTEGER DEFAULT 0,
    base_int   INTEGER DEFAULT 0,
    base_wis   INTEGER DEFAULT 0,
    base_con   INTEGER DEFAULT 0,
    base_cha   INTEGER DEFAULT 0,
    base_lck   INTEGER DEFAULT 0,
    base_hp    INTEGER DEFAULT 0,
    base_mana  INTEGER DEFAULT 0,
    base_move  INTEGER DEFAULT 0,
    alignment  TEXT DEFAULT 'Neutral',   -- Good / Neutral / Evil
    -- Stat-preview buff toggles (persist across devices); see character_detail
    buff_leveling INTEGER DEFAULT 0,      -- leveling spells: +2 to 6 stats
    buff_thoric   INTEGER DEFAULT 0       -- Thoric's Blessing (<=lvl 20): +3
);

-- One row per slot per character; is_wanted=0 → current equip, is_wanted=1 → wanted equip
CREATE TABLE IF NOT EXISTS char_slots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id    INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    slot_name  TEXT NOT NULL,   -- e.g. "about_0", "finger_1", "wield_0"
    item_id    INTEGER REFERENCES items(id) ON DELETE SET NULL,
    is_wanted  INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_slots_char ON char_slots(char_id, is_wanted);
