#!/usr/bin/env bash
set -euo pipefail

python3 -m unittest discover -s tests -v
bash ./scripts/check_docs_drift.sh
