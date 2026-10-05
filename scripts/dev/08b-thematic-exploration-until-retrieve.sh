#!/usr/bin/env bash
set -euo pipefail
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/ThematicExploration \
  -H "Content-Type: application/json" \
  -d '{"query": "How did a marriage look like in the 1800s compared to now?", "until": "retrieve_slices"}'
