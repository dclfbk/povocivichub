#!/usr/bin/env python3
"""
Aggiorna solo gli eventi di TuttaPovo in public/data/povo_pois.json, senza
rieseguire tutta la pipeline (niente OSM, DTM, GTFS). Pensato per la GitHub
Action settimanale (.github/workflows/update-eventi.yml), dopo che
calendar_tuttapovo.py ha riscaricato il calendario in eventi_tuttapovo.csv.

    python update_eventi.py
"""
import json
import os

from eventi import EVENTI_INPUT, link_eventi, strip_emails

HERE = os.path.dirname(os.path.abspath(__file__))
POIS_PATH = os.path.join(HERE, "..", "public", "data", "povo_pois.json")


def main():
    if os.path.exists(EVENTI_INPUT):
        strip_emails(EVENTI_INPUT)
    with open(POIS_PATH, encoding='utf-8') as fh:
        data = json.load(fh)
    feats = data['features']
    per_poi, _ = link_eventi(f['properties']['id'] for f in feats)
    changed = 0
    for f in feats:
        p = f['properties']
        n, shown = per_poi.get(str(p['id']), (0, []))
        new = (n, shown if shown else '')
        if (p.get('eventi_n', 0), p.get('eventi', '')) != new:
            p['eventi_n'], p['eventi'] = new
            changed += 1
    if not changed:
        print("Nessun cambiamento negli eventi: povo_pois.json non riscritto.")
        return
    # One feature per line, like build_data.py's GeoJSON writer, so the diff
    # stays readable (spacing differs slightly from GDAL's the first time).
    with open(POIS_PATH, 'w', encoding='utf-8') as fh:
        fh.write('{\n"type": "FeatureCollection",\n')
        if 'name' in data:
            fh.write(f'"name": {json.dumps(data["name"])},\n')
        if 'crs' in data:
            fh.write(f'"crs": {json.dumps(data["crs"])},\n')
        fh.write('"features": [\n')
        fh.write(',\n'.join(json.dumps(f, ensure_ascii=False) for f in feats))
        fh.write('\n]\n}\n')
    print(f"PoI con eventi aggiornati: {changed}")


if __name__ == '__main__':
    main()
