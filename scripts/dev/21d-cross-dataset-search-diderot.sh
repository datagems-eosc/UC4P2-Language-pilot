#!/usr/bin/env bash
set -euo pipefail
access_token="$(
  curl -sS -X POST https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "grant_type=password" \
    -d "client_id=swagger-client" \
    -d "username=dg-user-1" \
    -d "password=dg-user-1" \
    -d "scope=openid datagems offline_access" \
    | python3 -c "import json,sys; print(json.load(sys.stdin)[\"access_token\"])"
)"
curl -sS -X POST https://datagems-dev.scayle.es/cross-dataset-discovery/search/ \
  -H "Authorization: Bearer ${access_token}" \
  -H "Content-Type: application/json" \
  -d '{"query": "mariage", "k": 5, "search_mode": "hybrid", "dataset_ids": ["d5c34990-9acf-4349-91d4-924f58565922"]}'
