#!/usr/bin/env bash
# Live poll runner — outputs new deals in alert format
set -euo pipefail
cd /home/ubuntu/projects/deal-resell-engine
source .venv/bin/activate
python scripts/live_poll.py --out alert 2>&1
