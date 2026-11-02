# UC4P2 Language Pilot — refactor, improvements, and API curls

Host: `https://datagems-dev.scayle.es`  
Demo: https://datagems-dev.scayle.es/language-pilot/tree  
Example question (v2 `query_id` `23`): *How was Odin portrayed in earlier records compared to today?*

Each protected curl embeds the Keycloak token fetch inline (same pattern as `API.md`).
Pipe JSON responses through `| jq` for pretty output (install with `brew install jq` if needed).
SSE stream curls stay without `| jq` (they are not a single JSON object).

## 1. Refactor (thin orchestrator)

| Change | Detail |
|--------|--------|
| Thin pilot | LangGraph shell only; portable NLP lives in shared services |
| Query disambiguation | Trust `POST …/query_disambiguation/language` (no local resolve overrides) |
| In-dataset-discovery | `extendKnowledge`, `decompose`, `nlgEvaluate` only |
| Cross-Dataset Discovery | `search/` + `corpus-analysis-search/` |
| Data ownership | Full v2 benchmark in language-pilot; IDD holds NLG gold only |
| Fallback | Local path if QD/IDD down; local gold if IDD unmatched |

**Step → service**

| Pilot step | Service |
|------------|---------|
| `route`, `generate_subquestions`, `synthesize`, `export_benchmark` | **Language pilot** (local) |
| `disambiguate` | **Query disambiguation** |
| `extend_knowledge`, `decompose`, `evaluate_answer` | **In-dataset-discovery** |
| `retrieve_slices`, `compute_features` | **Cross-Dataset Discovery** |

## 2. Improvements

| Area | What shipped |
|------|----------------|
| Demo / UX | `/tree` Evaluation tab, v2 question drawer (0–35), JSON downloads |
| LLMs | `llm_model` / `judge_llm_model` on requests; `GET /llm/options` |
| Evaluation | StudentQuiz-shaped `evaluation_report` with formula + `calculation.elements` per use-case |
| Metrics | BLEU, ROUGE, token F1, METEOR, LLM-as-judge; per-step / total / eval timings |
| Multi-run | `run_id`, `started_at`, `finished_at`, `execution` (models + ids) |

---

## A. Language pilot

Service: **UC4P2 Language Pilot** · base `https://datagems-dev.scayle.es/language-pilot`

### Catalog / public GETs

```bash
# Root
curl -sS https://datagems-dev.scayle.es/language-pilot/ | jq

# Health
curl -sS https://datagems-dev.scayle.es/language-pilot/health | jq

# Step catalog
curl -sS https://datagems-dev.scayle.es/language-pilot/steps | jq

# LLM options (pipeline + judge defaults)
curl -sS https://datagems-dev.scayle.es/language-pilot/llm/options | jq

# Evaluation measure catalog (StudentQuiz-shaped, empty observations)
curl -sS https://datagems-dev.scayle.es/language-pilot/evaluation/measures | jq

# Tree UI + helper GETs
curl -sS https://datagems-dev.scayle.es/language-pilot/tree
curl -sS https://datagems-dev.scayle.es/language-pilot/tree/token | jq
curl -sS https://datagems-dev.scayle.es/language-pilot/tree/questions | jq
```

### Full pipeline

```bash
# ThematicExploration (full run)
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/ThematicExploration \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query":"How was Odin portrayed in earlier records compared to today?","query_id":"23","k":5,"decompose_mode":"few-shot","llm_model":"qwen3","judge_llm_model":"glm-5.3-flash","refresh":true}' | jq
```

```bash
# Stream (SSE)
curl -sS -N -X POST https://datagems-dev.scayle.es/language-pilot/ThematicExploration/stream \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"query":"How was Odin portrayed in earlier records compared to today?","query_id":"23","k":5,"decompose_mode":"few-shot"}'
```

```bash
# Poll a streamed job (replace JOB_ID)
curl -sS "https://datagems-dev.scayle.es/language-pilot/ThematicExploration/runs/JOB_ID" \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')"
```

### Step APIs (run from start through that node)

These are **Language pilot** entry points (`/language-pilot/steps/…`). They are *not* the upstream tool APIs.
Several steps call a shared service under the hood:

| Pilot step URL | Upstream service API (actual tool) |
|----------------|--------------------------------------|
| `…/steps/disambiguate` | **Query disambiguation** `POST …/query_disambiguation/language` |
| `…/steps/extend-knowledge` | **In-dataset-discovery** `POST …/extendKnowledge` |
| `…/steps/decompose` | **In-dataset-discovery** `POST …/decompose` |
| `…/steps/retrieve` | **Cross-Dataset Discovery** `POST …/search/` |
| `…/steps/features` | **Cross-Dataset Discovery** `POST …/corpus-analysis-search/` |
| `…/steps/evaluate` | **In-dataset-discovery** `POST …/nlgEvaluate` (or local gold) |
| `…/steps/route`, `generate-subquestions`, `synthesize`, `export` | local in the pilot |

To call the IDD decompose tool **directly**, use section C (`/in-dataset-discovery/decompose`), not `/language-pilot/steps/decompose`.

```bash
# route (local)
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/steps/route \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query":"How was Odin portrayed in earlier records compared to today?","query_id":"23"}' | jq
```

```bash
# disambiguate → calls Query disambiguation
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/steps/disambiguate \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query":"How was Odin portrayed in earlier records compared to today?","query_id":"23"}' | jq
```

```bash
# extend-knowledge → calls In-dataset-discovery /extendKnowledge
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/steps/extend-knowledge \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query":"How was Odin portrayed in earlier records compared to today?","query_id":"23"}' | jq
```

```bash
# generate-subquestions (local, from extend payload)
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/steps/generate-subquestions \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query":"How was Odin portrayed in earlier records compared to today?","query_id":"23"}' | jq
```

```bash
# Pilot wrapper only — under the hood calls In-dataset-discovery POST /decompose
# (for the real IDD API curl, see section C)
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/steps/decompose \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query":"How was Odin portrayed in earlier records compared to today?","query_id":"23","decompose_mode":"few-shot"}' | jq
```

```bash
# retrieve → calls Cross-Dataset Discovery /search/
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/steps/retrieve \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query":"How was Odin portrayed in earlier records compared to today?","query_id":"23","k":5}' | jq
```

```bash
# features → calls Cross-Dataset Discovery /corpus-analysis-search/
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/steps/features \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query":"How was Odin portrayed in earlier records compared to today?","query_id":"23","k":5}' | jq
```

```bash
# synthesize (local LLM)
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/steps/synthesize \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query":"How was Odin portrayed in earlier records compared to today?","query_id":"23","k":5,"llm_model":"qwen3"}' | jq
```

```bash
# evaluate → calls In-dataset-discovery /nlgEvaluate (or local gold)
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/steps/evaluate \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query":"How was Odin portrayed in earlier records compared to today?","query_id":"23","k":5,"llm_model":"qwen3","judge_llm_model":"glm-5.3-flash"}' | jq
```

```bash
# export (local)
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/steps/export \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query":"How was Odin portrayed in earlier records compared to today?","query_id":"23","k":5}' | jq
```

---

## B. Query disambiguation

Service: **Query disambiguation** · base `https://datagems-dev.scayle.es/query-disambiguation`  
Used by pilot step `disambiguate`. UC4P2 uses **`/query_disambiguation/language` only**.

```bash
# Health
curl -sS https://datagems-dev.scayle.es/query-disambiguation/health | jq
```

```bash
# Language resolve (comparative / descriptive)
curl -sS -X POST https://datagems-dev.scayle.es/query-disambiguation/query_disambiguation/language \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query":"How was Odin portrayed in earlier records compared to today?"}' | jq
```

---

## C. In-dataset-discovery

Service: **In-dataset-discovery** · base `https://datagems-dev.scayle.es/in-dataset-discovery`  
Used by pilot steps `extend_knowledge`, `decompose`, `evaluate_answer`. UC4P2 uses **these three routes only**.

```bash
# Health
curl -sS https://datagems-dev.scayle.es/in-dataset-discovery/health | jq
```

```bash
# Extend knowledge
curl -sS -X POST https://datagems-dev.scayle.es/in-dataset-discovery/extendKnowledge \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"question":"How was Odin portrayed in earlier records compared to today?"}' | jq
```

```bash
# Decompose — this is the real In-dataset-discovery tool API
curl -sS -X POST https://datagems-dev.scayle.es/in-dataset-discovery/decompose \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"question":"How was Odin portrayed in earlier records compared to today?"}' | jq
```

```bash
# NLG evaluate
curl -sS -X POST https://datagems-dev.scayle.es/in-dataset-discovery/nlgEvaluate \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"hypothesis":"Earlier records often present Odin as a war and wisdom figure; modern portrayals emphasize myth and literature.","reference":"In earlier records Odin appears as a warlike and wise figure; today he is mainly known through myth and literature."}' | jq
```

```bash
# NLG evaluate — optional gold-file lookup by query_id (when no reference)
curl -sS -X POST https://datagems-dev.scayle.es/in-dataset-discovery/nlgEvaluate \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"hypothesis":"Earlier records often present Odin as a war and wisdom figure; modern portrayals emphasize myth and literature.","question":"How was Odin portrayed in earlier records compared to today?","query_id":"23"}' | jq
```

---

## D. Cross-Dataset Discovery (retrieval)

Service: **Cross-Dataset Discovery** · used by pilot `retrieve_slices` / `compute_features`  
Base from env `CROSS_DATASET_DISCOVERY_URL` (on Scayle typically under `https://datagems-dev.scayle.es/cross-dataset-discovery`).

```bash
# Health (if exposed)
curl -sS https://datagems-dev.scayle.es/cross-dataset-discovery/health | jq
```

```bash
# Search (example — body fields follow CDD contract; pilot builds this per slice)
curl -sS -X POST https://datagems-dev.scayle.es/cross-dataset-discovery/search/ \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query":"Odin Norse mythology historical portrayal","k":5,"dataset_id":"d84d1a2e-127d-4393-91d0-afb7e4fd9c68"}' | jq
```

```bash
# Corpus analysis
curl -sS -X POST https://datagems-dev.scayle.es/cross-dataset-discovery/corpus-analysis-search/ \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query":"Odin","dataset_id":"d84d1a2e-127d-4393-91d0-afb7e4fd9c68"}' | jq
```

---

## Quick index

| API | Service |
|-----|---------|
| `GET/POST /language-pilot/…` (incl. `/ThematicExploration`, `/steps/*`, `/tree`, `/llm/options`, `/evaluation/measures`) | **Language pilot** |
| `POST /query-disambiguation/query_disambiguation/language` | **Query disambiguation** |
| `POST /in-dataset-discovery/extendKnowledge` | **In-dataset-discovery** |
| `POST /in-dataset-discovery/decompose` | **In-dataset-discovery** |
| `POST /in-dataset-discovery/nlgEvaluate` | **In-dataset-discovery** |
| `POST /cross-dataset-discovery/search/` | **Cross-Dataset Discovery** |
| `POST /cross-dataset-discovery/corpus-analysis-search/` | **Cross-Dataset Discovery** |
