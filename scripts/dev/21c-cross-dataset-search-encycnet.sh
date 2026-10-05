#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/_token.sh"
curl -sS -X POST https://datagems-dev.scayle.es/cross-dataset-discovery/search/ \
  -H "Authorization: Bearer ${access_token}" \
  -H "Content-Type: application/json" \
  -d '{"query": "Ehe Hochzeit", "k": 5, "search_mode": "hybrid", "dataset_ids": ["07382b91-5bc5-42f9-8391-33adc2460c19"]}'
