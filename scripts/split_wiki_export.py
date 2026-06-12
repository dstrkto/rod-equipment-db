#!/usr/bin/env python3
"""
Split a MediaWiki Special:Export XML dump into per-page wikitext files.

Produces the same layout as scrape_rodpedia.py: one <title>.wiki file per
page plus an _index.json mapping titles to files.

Usage:
    python3 scripts/split_wiki_export.py <export.xml> [--out DIR]
"""

import argparse
import hashlib
import json
import os
import sys
import urllib.parse
import xml.etree.ElementTree as ET


def safe_filename(title, index):
    name = urllib.parse.quote(title.replace(' ', '_'), safe="_()'!,-.~")
    taken = {v['file'].lower() for t, v in index.items() if t != title}
    candidate = name + '.wiki'
    if candidate.lower() in taken:
        suffix = hashlib.sha1(title.encode('utf-8')).hexdigest()[:6]
        candidate = f'{name}-{suffix}.wiki'
    return candidate


def local(tag):
    """Strip the xmlns prefix ElementTree includes in tag names."""
    return tag.rsplit('}', 1)[-1]


def split(xml_path, outdir):
    os.makedirs(outdir, exist_ok=True)
    index_path = os.path.join(outdir, '_index.json')
    index = {}
    if os.path.exists(index_path):
        with open(index_path) as f:
            index = json.load(f)

    count = 0
    # iterparse keeps memory flat regardless of dump size
    for _event, elem in ET.iterparse(xml_path, events=('end',)):
        if local(elem.tag) != 'page':
            continue
        title = ns = text = timestamp = None
        for child in elem.iter():
            tag = local(child.tag)
            if tag == 'title':
                title = child.text
            elif tag == 'ns':
                ns = int(child.text or 0)
            elif tag == 'text':
                text = child.text or ''
            elif tag == 'timestamp':
                timestamp = child.text or ''
        if title is None:
            elem.clear()
            continue
        fname = (index.get(title) or {}).get('file') or safe_filename(title, index)
        with open(os.path.join(outdir, fname), 'w', encoding='utf-8') as f:
            f.write(text or '')
        index[title] = {'file': fname, 'ns': ns or 0, 'timestamp': timestamp or ''}
        count += 1
        elem.clear()

    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=1, sort_keys=True)
    print(f'{count} pages written to {outdir}')


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument('xml', help='Special:Export XML dump')
    ap.add_argument('--out', help='output directory (default: alongside the dump)')
    args = ap.parse_args()
    outdir = args.out or os.path.join(os.path.dirname(os.path.abspath(args.xml)), 'pages')
    if not os.path.exists(args.xml):
        sys.exit(f'No such file: {args.xml}')
    split(args.xml, outdir)


if __name__ == '__main__':
    main()
