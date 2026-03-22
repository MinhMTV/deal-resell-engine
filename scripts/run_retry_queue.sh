#!/usr/bin/env bash
# Retry queue processor — run via systemd timer or manually
set -euo pipefail
cd /home/ubuntu/projects/deal-resell-engine
source .venv/bin/activate
python scripts/retry_queue.py --out text 2>&1
