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
  -d '{"query": "What is the definition of a marriage in the 1800s? wedding nuptials matrimony", "k": 5, "search_mode": "hybrid", "dataset_ids": ["d84d1a2e-127d-4393-91d0-afb7e4fd9c68"]}'
