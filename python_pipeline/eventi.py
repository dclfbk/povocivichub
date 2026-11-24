"""
Eventi di TuttaPovo collegati ai punti della mappa (2026-11-24).

Events scraped from tuttapovo.it/appuntamenti.asp by calendar_tuttapovo.py
(one row per event *date*; event_id groups them). Their free-text location is
linked to a PoI through raw_data/eventi_luoghi.csv: ordered regexes, grouped
so that within a group the first (most specific) match wins ("Casa Sociale -
Sala Agorà" -> Agorà, not the generic Casa Sociale), while an event held in
several places ("Teatro Concordia e piazzale oratorio") links to each.

Each PoI gets eventi_n (distinct events) and up to EVENTI_MAX_POPUP events for
the popup: upcoming first, then the latest. Posters are re-hosted as
thumbnails (permission from TuttaPovo / the associations, 2026-11-24); PDFs
are only linked. Organisers' e-mails are never exported.

Deliberately light on dependencies (stdlib + requests + Pillow): it's shared
by build_data.py and by update_eventi.py, which a weekly GitHub Action runs
without the heavy geo stack.
"""
import csv
import datetime
import os
import re

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
EVENTI_INPUT = os.path.join(HERE, "eventi_tuttapovo.csv")
EVENTI_LUOGHI_INPUT = os.path.join(HERE, "..", "raw_data", "eventi_luoghi.csv")
LOCANDINE_CACHE_DIR = os.path.join(HERE, "cache", "locandine")
LOCANDINE_OUTPUT_DIR = os.path.join(HERE, "..", "public", "data", "locandine")
LOCANDINE_PUBLIC_PREFIX = "./data/locandine/"
LOCANDINE_MAX_PX = 480
EVENTI_MAX_POPUP = 4
HEADERS = {'User-Agent': 'PovoCivicHub/1.0 (https://github.com/povocivichub; data pipeline)'}
_MESI = {m: i for i, m in enumerate(['gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno', 'luglio',
                                     'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre'], start=1)}


def parse_data_evento(text):
    """First 'giorno mese anno' in a free-text date ('sabato 6 gennaio 2024 ore 15:30')."""
    m = re.search(r'(\d{1,2})\s+(' + '|'.join(_MESI) + r')\s+(\d{4})', text or '', re.I)
    if not m:
        return None
    try:
        return datetime.date(int(m.group(3)), _MESI[m.group(2).lower()], int(m.group(1)))
    except ValueError:
        return None


def locandina_thumb(event_id, url, name):
    """Thumbnail of an image poster in public/data/locandine/, '' for PDFs/failures."""
    from io import BytesIO  # noqa: F401  (Pillow reads from the cached file)
    from PIL import Image

    ext = os.path.splitext(name or '')[1].lower()
    if not url or ext not in ('.jpg', '.jpeg', '.png', '.webp'):
        return ''
    fname = f"ev_{event_id}.jpg"
    out_path = os.path.join(LOCANDINE_OUTPUT_DIR, fname)
    if os.path.exists(out_path):
        return LOCANDINE_PUBLIC_PREFIX + fname
    cache_path = os.path.join(LOCANDINE_CACHE_DIR, f"{event_id}{ext}")
    try:
        if not os.path.exists(cache_path):
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            os.makedirs(LOCANDINE_CACHE_DIR, exist_ok=True)
            with open(cache_path, 'wb') as fh:
                fh.write(resp.content)
        img = Image.open(cache_path).convert('RGB')
        img.thumbnail((LOCANDINE_MAX_PX, LOCANDINE_MAX_PX))
        os.makedirs(LOCANDINE_OUTPUT_DIR, exist_ok=True)
        img.save(out_path, 'JPEG', quality=80, optimize=True)
    except Exception as e:
        print(f"    Warning: poster for event {event_id} not available: {e}")
        return ''
    return LOCANDINE_PUBLIC_PREFIX + fname


def strip_emails(path=EVENTI_INPUT):
    """Drop the organisers' e-mail column from the scraped CSV (it's committed to a public repo)."""
    with open(path, encoding='utf-8-sig') as fh:
        rows = list(csv.DictReader(fh, delimiter=';'))
    if not rows or 'email' not in rows[0]:
        return
    fields = [f for f in rows[0] if f != 'email']
    with open(path, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fields, delimiter=';', extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def link_eventi(poi_ids, today=None):
    """
    ({poi_id: (eventi_n, [event dicts for the popup])}, stats) for the PoIs in
    poi_ids. Returns ({}, stats) if the events CSV or the place dictionary is missing.
    """
    stats = {'eventi': 0, 'abbinati': 0, 'non_abbinati': [], 'locandine': 0}
    if not (os.path.exists(EVENTI_INPUT) and os.path.exists(EVENTI_LUOGHI_INPUT)):
        print("    Events or place dictionary missing, skipped.")
        return {}, stats
    with open(EVENTI_LUOGHI_INPUT, encoding='utf-8') as fh:
        rules = [(r['gruppo'], re.compile(r['regex'], re.I), r['id']) for r in csv.DictReader(fh)]
    with open(EVENTI_INPUT, encoding='utf-8-sig') as fh:
        rows = list(csv.DictReader(fh, delimiter=';'))
    events = {}
    for r in rows:
        e = events.setdefault(r['event_id'], {'row': r, 'dates': set()})
        d = parse_data_evento(r['date_text'])
        if d:
            e['dates'].add(d)
    stats['eventi'] = len(events)
    today = today or datetime.date.today()
    poi_ids = {str(p) for p in poi_ids}
    per_poi = {}
    for eid, e in events.items():
        loc = e['row']['location']
        hit = {}
        for gruppo, rx, pid in rules:
            if gruppo not in hit and rx.search(loc):
                hit[gruppo] = pid
        pids = [p for p in dict.fromkeys(hit.values()) if p in poi_ids]
        if not pids:
            stats['non_abbinati'].append(loc.strip()[:80])
            continue
        stats['abbinati'] += 1
        future = sorted(d for d in e['dates'] if d >= today)
        when = future[0] if future else (max(e['dates']) if e['dates'] else None)
        for pid in pids:
            per_poi.setdefault(pid, []).append((eid, e, when, bool(future)))
    result = {}
    for pid, evs in per_poi.items():
        upcoming = sorted([x for x in evs if x[3]], key=lambda x: x[2])
        past = sorted([x for x in evs if not x[3] and x[2]], key=lambda x: x[2], reverse=True)
        shown = []
        for eid, e, when, is_future in (upcoming + past)[:EVENTI_MAX_POPUP]:
            r = e['row']
            img = locandina_thumb(eid, r.get('attachment_url'), r.get('attachment_name'))
            stats['locandine'] += bool(img)
            is_pdf = (r.get('attachment_name') or '').lower().endswith('.pdf')
            shown.append({
                'titolo': r['title'].strip(), 'data': when.isoformat() if when else '',
                'prossimo': is_future, 'organizzatore': r['organisation'].strip(),
                'url': r['detail_url'], 'locandina': img,
                'locandina_pdf': r['attachment_url'] if is_pdf else '',
            })
        result[pid] = (len(evs), shown)
    print(f"    {stats['abbinati']} of {stats['eventi']} events linked to {len(result)} PoIs; "
          f"{stats['locandine']} poster thumbnails; {len(stats['non_abbinati'])} events without a known place.")
    return result, stats
