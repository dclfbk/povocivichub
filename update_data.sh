#!/bin/bash
set -e

cd "$(dirname "$0")/python_pipeline"
pip install -r requirements.txt --break-system-packages
python build_data.py
