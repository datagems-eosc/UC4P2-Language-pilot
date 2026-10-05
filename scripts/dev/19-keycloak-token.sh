#!/usr/bin/env bash
set -euo pipefail
curl -sS -X POST https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "client_id=swagger-client" \
  -d "username=dg-user-1" \
  -d "password=dg-user-1" \
  -d "scope=openid datagems offline_access"
