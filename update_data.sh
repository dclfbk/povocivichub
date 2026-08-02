#!/bin/bash
set -e

cd "$(dirname "$0")/python_pipeline"
pip install -r requirements.txt --break-system-packages

# osmnx caches every Overpass response to disk (cache/*.json) and replays it
# on identical queries indefinitely -- so OSM edits (e.g. tagging a PoI
# access=private) never reach the pipeline until this cache is cleared, no
# matter how many times update_data.sh runs. Wipe it here so every update
# fetches current OSM data.
rm -rf cache

python build_data.py
