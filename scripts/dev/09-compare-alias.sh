#!/usr/bin/env bash
set -euo pipefail
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/compare \
  -H "Content-Type: application/json" \
  -d '{"query": "How did a marriage look like in the 1800s compared to now?", "query_id": "curl-alias", "k": 5, "decompose_mode": "few-shot"}'
