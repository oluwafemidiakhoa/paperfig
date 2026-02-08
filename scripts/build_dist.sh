#!/usr/bin/env bash
set -euo pipefail

python3 -m pip install --upgrade pip
python3 -m pip install build twine
python3 -m build
python3 -m twine check dist/*
