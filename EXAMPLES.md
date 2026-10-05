# ThematicExploration examples

Questions 2–5 come from `data/pilot2_benchmark_english.v1.json`.

---

## 1. Marriage, 1800s vs now

```bash
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/ThematicExploration \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query": "How did a marriage look like in the 1800s compared to now?", "until": "retrieve_slices"}'
```

## 2. Dresden nicknames across time

```bash
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/ThematicExploration \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query": "How do historical descriptions of the Dresden'\''s cultural nicknames and the reasons given for them vary across time?", "until": "retrieve_slices"}'
```

## 3. Galileo origin and family

```bash
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/ThematicExploration \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query": "How do historical accounts differ in reporting Galileo origin and family?", "until": "retrieve_slices"}'
```

## 4. Valid marriage over time

```bash
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/ThematicExploration \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query": "How does the definition of a valid marriage shift over time in the Western hemisphere?", "until": "retrieve_slices"}'
```

## 5. Odin, earlier records vs today

```bash
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/ThematicExploration \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query": "How was Odin portrayed in earlier records compared to today?", "until": "retrieve_slices"}'
```
