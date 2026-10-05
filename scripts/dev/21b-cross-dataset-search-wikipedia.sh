#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/_token.sh"
curl -sS -X POST https://datagems-dev.scayle.es/cross-dataset-discovery/search/ \
  -H "Authorization: Bearer ${access_token}" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the definition of a marriage in the present? wedding marriage union", "k": 5, "search_mode": "hybrid", "dataset_ids": ["1f6fba0c-9aea-4345-b5a3-457c924f9e0c"]}'
