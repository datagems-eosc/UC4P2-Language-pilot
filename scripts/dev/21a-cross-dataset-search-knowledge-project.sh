#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/_token.sh"
curl -sS -X POST https://datagems-dev.scayle.es/cross-dataset-discovery/search/ \
  -H "Authorization: Bearer ${access_token}" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the definition of a marriage in the 1800s? wedding nuptials matrimony", "k": 5, "search_mode": "hybrid", "dataset_ids": ["d84d1a2e-127d-4393-91d0-afb7e4fd9c68"]}'
