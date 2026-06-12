#!/usr/bin/env python3
"""
Scrape RoDpedia (a MediaWiki wiki) into local wikitext files.

Uses the MediaWiki API (not HTML crawling): pages are fetched in batches
of 50 as raw wikitext, politely rate-limited, with resume support.

Usage:
    python3 scripts/scrape_rodpedia.py              # scrape main namespace
    python3 scripts/scrape_rodpedia.py --wait       # poll until wiki is up, then scrape
    python3 scripts/scrape_rodpedia.py --namespaces 0,14   # also grab Category pages
    python3 scripts/scrape_rodpedia.py --force      # re-download existing files

Output: reference/rodpedia/<title>.wiki plus _index.json mapping
titles to files. Re-running skips files that already exist, so an
interrupted scrape picks up where it left off.
"""

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = 'https://rodpedia.realmsofdespair.info'
USER_AGENT = 'rod-db-scraper/1.0 (personal gear database; contact: chris@diaz.ink)'
BATCH_LIMIT = 50          # API max for content queries by normal users
RETRIES = 5


class _Done(Exception):
    """Raised internally to stop after --max-pages."""


def api_get(api_url, params, timeout=30):
    """One API call with retries, maxlag etiquette, and error handling."""
    params = dict(params, format='json', formatversion='2', maxlag='5')
    url = api_url + '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            if 'error' in data:
                if data['error'].get('code') == 'maxlag':
                    # server is busy — back off and retry
                    time.sleep(5 * attempt)
                    last_err = RuntimeError('maxlag')
                    continue
                raise RuntimeError(f"API error: {data['error']}")
            return data
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            last_err = e
            if attempt < RETRIES:
                time.sleep(5 * attempt)
    raise last_err


def find_api(base):
    """Locate api.php (root and /w/ are the common layouts)."""
    for path in ('/api.php', '/w/api.php'):
        url = base.rstrip('/') + path
        try:
            data = api_get(url, {
                'action': 'query', 'meta': 'siteinfo',
                'siprop': 'general|statistics',
            })
            general = data['query']['general']
            stats = data['query']['statistics']
            print(f"API found: {url}")
            print(f"  Site: {general.get('sitename')} — {general.get('generator')}")
            print(f"  Articles: {stats.get('articles')}  Total pages: {stats.get('pages')}")
            return url
        except Exception:
            continue
    return None


def safe_filename(title, index):
    """Filesystem-safe, mostly-readable filename; collision-proofed via index."""
    name = urllib.parse.quote(title.replace(' ', '_'), safe="_()'!,-.~")
    # APFS is case-insensitive: "A bag" and "A Bag" are distinct wiki pages
    # but would be the same file — disambiguate with a short hash.
    taken = {v['file'].lower(): t for t, v in index.items() if t != title}
    candidate = name + '.wiki'
    if candidate.lower() in taken:
        suffix = hashlib.sha1(title.encode('utf-8')).hexdigest()[:6]
        candidate = f'{name}-{suffix}.wiki'
    return candidate


def scrape(api_url, outdir, namespaces, delay, max_pages, force):
    os.makedirs(outdir, exist_ok=True)
    index_path = os.path.join(outdir, '_index.json')
    index = {}
    if os.path.exists(index_path):
        with open(index_path) as f:
            index = json.load(f)

    counts = {'total': 0, 'saved': 0, 'skipped': 0}
    try:
        for ns in namespaces.split(','):
            cont = {}
            while True:
                params = {
                    'action': 'query',
                    'generator': 'allpages',
                    'gapnamespace': ns.strip(),
                    'gaplimit': str(BATCH_LIMIT),
                    'prop': 'revisions',
                    'rvprop': 'content|timestamp',
                    'rvslots': 'main',
                }
                params.update(cont)
                data = api_get(api_url, params)
                for page in data.get('query', {}).get('pages', []):
                    revs = page.get('revisions')
                    if not revs:
                        continue  # content arrives in a later continuation batch
                    title = page['title']
                    fname = (index.get(title) or {}).get('file') or safe_filename(title, index)
                    path = os.path.join(outdir, fname)
                    counts['total'] += 1
                    if os.path.exists(path) and not force:
                        counts['skipped'] += 1
                    else:
                        with open(path, 'w', encoding='utf-8') as f:
                            f.write(revs[0]['slots']['main']['content'])
                        counts['saved'] += 1
                    index[title] = {
                        'file': fname,
                        'ns': int(ns),
                        'timestamp': revs[0].get('timestamp', ''),
                    }
                    if max_pages and counts['total'] >= max_pages:
                        raise _Done
                print(f"  ...{counts['total']} pages "
                      f"({counts['saved']} saved, {counts['skipped']} already had)")
                if 'continue' not in data:
                    break
                cont = data['continue']
                time.sleep(delay)
    except _Done:
        pass
    except KeyboardInterrupt:
        print('\nInterrupted — progress is saved; re-run to resume.')
    finally:
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=1, sort_keys=True)

    print(f"Done: {counts['total']} pages seen, {counts['saved']} written, "
          f"{counts['skipped']} skipped → {outdir}")


def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description='Scrape RoDpedia into local wikitext files.')
    ap.add_argument('--base', default=DEFAULT_BASE, help='wiki base URL')
    ap.add_argument('--out', default=os.path.join(repo_root, 'reference', 'rodpedia'))
    ap.add_argument('--namespaces', default='0',
                    help='comma-separated namespace ids (0=articles, 14=categories)')
    ap.add_argument('--delay', type=float, default=1.5,
                    help='seconds between API batches (be polite)')
    ap.add_argument('--max-pages', type=int, help='stop after N pages (for testing)')
    ap.add_argument('--force', action='store_true', help='overwrite existing files')
    ap.add_argument('--wait', action='store_true',
                    help='poll every 10 minutes until the wiki responds, then scrape')
    args = ap.parse_args()

    api_url = find_api(args.base)
    while api_url is None and args.wait:
        print(f'{args.base} not responding; retrying in 10 minutes...')
        time.sleep(600)
        api_url = find_api(args.base)
    if api_url is None:
        sys.exit(f'No MediaWiki API found at {args.base} — is the site up?')

    scrape(api_url, args.out, args.namespaces, args.delay, args.max_pages, args.force)


if __name__ == '__main__':
    main()
