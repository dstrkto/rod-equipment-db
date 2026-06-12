#!/usr/bin/env python3
"""
Bulk-import items from the Order of Dragonslayer wiki dump into rod.db.

Walks reference/orderwiki/pages/*.wiki, extracts every identify block,
parses each with the same importer used by the paste-import page, and
inserts items that aren't already in the database (matched by name,
case-insensitive).

Imported rows get editor='OrderWiki' so they're easy to find (or purge):
    sqlite3 rod.db "SELECT COUNT(*) FROM items WHERE editor='OrderWiki'"

Usage:
    python3 scripts/import_orderwiki.py            # dry run — report only
    python3 scripts/import_orderwiki.py --commit   # actually insert
"""

import argparse
import json
import os
import re
import sqlite3
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from importer import parse_identify  # noqa: E402

PAGES_DIR = os.path.join(REPO_ROOT, 'reference', 'orderwiki', 'pages')
DB_PATH = os.path.join(REPO_ROOT, 'rod.db')

_TAG_RE = re.compile(r'</?(?:pre|nowiki|code)>', re.IGNORECASE)
_CATEGORY_RE = re.compile(r'\[\[Category:([^\]|]+)')
_OBJECT_RE = re.compile(r"Object '", re.IGNORECASE)
# Wiki pages often truncate the object line: "Object 'a band of quicksilver'..."
# The parser's name regex needs "Object 'X' is", so rewrite to canonical form.
_NAME_TRUNC_RE = re.compile(r"^Object '(.+)'(?:\.{2,}|…)\s*$", re.IGNORECASE)
# Container weights confuse the type line: "weight 2 (all: 1)."
_ALL_WEIGHT_RE = re.compile(r'(,\s*weight \d+)\s*\(all:\s*\d+\)\.', re.IGNORECASE)


def identify_blocks(text):
    """Split page wikitext into chunks, one per identify block."""
    text = _TAG_RE.sub('', text)
    blocks = []
    current = None
    for line in text.splitlines():
        stripped = line.strip()
        if _OBJECT_RE.match(stripped):
            if current:
                blocks.append('\n'.join(current))
            m = _NAME_TRUNC_RE.match(stripped)
            if m:
                stripped = f"Object '{m.group(1)}' is an object..."
            current = [stripped]
        elif current is not None:
            current.append(_ALL_WEIGHT_RE.sub(r'\1.', line))
    if current:
        blocks.append('\n'.join(current))
    return blocks


def page_categories(text):
    """Category names on the page, minus the generic 'Items'."""
    cats = [c.strip() for c in _CATEGORY_RE.findall(text)]
    return [c for c in cats if c.lower() != 'items']


def main():
    ap = argparse.ArgumentParser(description='Import order wiki items into rod.db')
    ap.add_argument('--commit', action='store_true',
                    help='insert into the database (default is a dry-run report)')
    ap.add_argument('--pages', default=PAGES_DIR)
    ap.add_argument('--db', default=DB_PATH)
    args = ap.parse_args()

    index_path = os.path.join(args.pages, '_index.json')
    with open(index_path) as f:
        index = json.load(f)

    db = sqlite3.connect(args.db)
    existing = {row[0].lower().strip()
                for row in db.execute('SELECT name FROM items')}

    stats = {'pages': 0, 'blocks': 0, 'parsed': 0,
             'new': 0, 'dup_db': 0, 'dup_wiki': 0, 'unparsed': 0}
    seen_this_run = set()
    new_items = []
    dup_db_names = []

    for title, meta in sorted(index.items()):
        path = os.path.join(args.pages, meta['file'])
        if not os.path.exists(path):
            continue
        with open(path, encoding='utf-8') as f:
            text = f.read()
        blocks = identify_blocks(text)
        if not blocks:
            continue
        stats['pages'] += 1
        cats = page_categories(text)
        wiki_date = (meta.get('timestamp') or '')[:10]

        for block in blocks:
            stats['blocks'] += 1
            item = parse_identify(block)
            # require a type line too, so stray "Object '...'" prose doesn't
            # produce empty husks
            if not item or not item['item_type']:
                stats['unparsed'] += 1
                continue
            stats['parsed'] += 1

            # Normalize styled weapon types ("stabbing weapon") to the DB's
            # plain 'weapon', keeping the style as a note in other
            if item['item_type'].endswith(' weapon'):
                style = item['item_type'][:-len(' weapon')]
                item['item_type'] = 'weapon'
                tag = f'[{style}]'
                if tag not in item['other']:
                    item['other'] = (tag + ' ' + item['other']).strip()

            key = item['name'].lower().strip()
            if key in existing:
                stats['dup_db'] += 1
                dup_db_names.append(item['name'])
                continue
            if key in seen_this_run:
                stats['dup_wiki'] += 1
                continue
            seen_this_run.add(key)

            item['editor'] = 'OrderWiki'
            item['date_mod'] = wiki_date
            if cats:
                hint = '(wiki: ' + ', '.join(cats) + ')'
                item['other'] = (item['other'] + ' ' + hint).strip()
            new_items.append((title, item))
            stats['new'] += 1

    print(f"Pages with identify blocks: {stats['pages']}")
    print(f"Identify blocks found:      {stats['blocks']}")
    print(f"  parsed as items:          {stats['parsed']}")
    print(f"  unparsable/partial:       {stats['unparsed']}")
    print(f"  already in DB:            {stats['dup_db']}")
    print(f"  duplicated within wiki:   {stats['dup_wiki']}")
    print(f"  NEW items to import:      {stats['new']}")

    if not args.commit:
        print('\nDry run — nothing written. Sample of new items:')
        for title, item in new_items[:15]:
            print(f"  lv{item['level']:>3} {item['item_type']:<10} "
                  f"{item['wear_loc']:<8} {item['name']}")
        print('\nRe-run with --commit to insert.')
        db.close()
        return

    cols = ['name', 'item_type', 'wear_loc', 'level', 'level_min', 'level_max',
            'weight', 'ac', 'd1', 'd2', 'hr', 'dr', 'hp', 'mana',
            'str_b', 'dex_b', 'int_b', 'wis_b', 'con_b', 'cha_b', 'lck_b',
            'move_b', 'item_value', 'gold', 'flags', 'antis', 'races', 'other',
            'mob_source', 'area', 'date_mod', 'editor',
            'is_oog', 'is_pkill', 'is_gloried']
    sql = f"INSERT INTO items ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})"
    for _title, item in new_items:
        db.execute(sql, [item[c] for c in cols])
    db.commit()
    db.close()
    print(f"\nInserted {stats['new']} items (editor='OrderWiki').")


if __name__ == '__main__':
    main()
