#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/_token.sh"
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/steps/disambiguate \
  -H "Authorization: Bearer ${access_token}" \
  -H "Content-Type: application/json" \
  -d '{"query": "How did a marriage look like in the 1800s compared to now?", "query_id": "curl-steps", "k": 5, "decompose_mode": "few-shot"}'
