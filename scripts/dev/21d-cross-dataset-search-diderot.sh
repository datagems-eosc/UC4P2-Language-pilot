#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/_token.sh"
curl -sS -X POST https://datagems-dev.scayle.es/cross-dataset-discovery/search/ \
  -H "Authorization: Bearer ${access_token}" \
  -H "Content-Type: application/json" \
  -d '{"query": "mariage", "k": 5, "search_mode": "hybrid", "dataset_ids": ["d5c34990-9acf-4349-91d4-924f58565922"]}'
