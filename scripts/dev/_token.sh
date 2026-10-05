#!/usr/bin/env bash
# Source this file: sets access_token from Keycloak (openid datagems offline_access).
access_token="$(
  curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
    --header 'Content-Type: application/x-www-form-urlencoded' \
    --data-urlencode 'grant_type=password' \
    --data-urlencode 'client_id=swagger-client' \
    --data-urlencode 'username=dg-user-1' \
    --data-urlencode 'password=dg-user-1' \
    --data-urlencode 'scope=openid datagems offline_access' \
    | jq -r '.access_token'
)"
