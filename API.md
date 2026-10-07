# API calls on datagems-dev

Host is always `https://datagems-dev.scayle.es`. Matching scripts: `scripts/dev/`.

**Access token.** Protected POSTs require a DataGEMS AAI JWT, same as [dg-app-api](https://github.com/datagems-eosc/dg-app-api). Each standard curl below fetches the token inline with `jq`. Scope is `openid datagems offline_access` (not `cross-dataset-discovery-api`). Health and catalog GETs stay public.

**Example question:** `How did a marriage look like in the 1800s compared to now?`

**Language corpora**

| Corpus | Era / language | Dataset id |
|--------|----------------|------------|
| EncycNet | German, historical | `07382b91-5bc5-42f9-8391-33adc2460c19` |
| 19th C. Knowledge Project | English, 1800s | `d84d1a2e-127d-4393-91d0-afb7e4fd9c68` |
| Encyclopédie (Diderot) | French, historical | `d5c34990-9acf-4349-91d4-924f58565922` |
| Wikipedia | present | `1f6fba0c-9aea-4345-b5a3-457c924f9e0c` |

**POST body fields (language-pilot)**

| Field | Details |
|-------|---------|
| `query` | Required question text |
| `query_id` | Optional stable id |
| `k` | Passages per slice, 1–20, default 5 |
| `decompose_mode` | `predict`, `cot`, or `few-shot` (default) |
| `include_trace` | `true` adds `raw_trace` |
| `until` | Stop after a node (full run only): `route`, `disambiguate`, `extend_knowledge`, `generate_subquestions`, `decompose`, `retrieve_slices`, `compute_features`, `synthesize`, `evaluate_answer`, `export_benchmark` |

---

## A. Language pilot — catalog

Service info, docs, and HTML tree. No JSON body.

### A1. Root

**Details**

- Method / URL: `GET https://datagems-dev.scayle.es/language-pilot/`
- Returns: service name, version (`0.1.10`), docs path, step list
- Script: `scripts/dev/01-language-pilot-root.sh`

**Standard curl**

```bash
curl -sS https://datagems-dev.scayle.es/language-pilot/
```

### A2. Health

**Details**

- Method / URL: `GET https://datagems-dev.scayle.es/language-pilot/health`
- Returns: `{"status": "healthy"}`
- Script: `scripts/dev/02-language-pilot-health.sh`

**Standard curl**

```bash
curl -sS https://datagems-dev.scayle.es/language-pilot/health
```

### A3. Swagger UI

**Details**

- Method / URL: `GET https://datagems-dev.scayle.es/language-pilot/swagger`
- Returns: HTML. Prefer a browser.
- Script: `scripts/dev/03-language-pilot-swagger.sh`

**Standard curl**

```bash
curl -sS https://datagems-dev.scayle.es/language-pilot/swagger
```

### A4. OpenAPI schema

**Details**

- Method / URL: `GET https://datagems-dev.scayle.es/language-pilot/openapi.json`
- Returns: OpenAPI JSON
- Script: `scripts/dev/04-language-pilot-openapi.sh`

**Standard curl**

```bash
curl -sS https://datagems-dev.scayle.es/language-pilot/openapi.json
```

### A5. ReDoc

**Details**

- Method / URL: `GET https://datagems-dev.scayle.es/language-pilot/redoc`
- Returns: HTML
- Script: `scripts/dev/05-language-pilot-redoc.sh`

**Standard curl**

```bash
curl -sS https://datagems-dev.scayle.es/language-pilot/redoc
```

### A6. Step catalog

**Details**

- Method / URL: `GET https://datagems-dev.scayle.es/language-pilot/steps`
- Returns: list of `POST /steps/...` APIs (name, path, title, summary)
- Script: `scripts/dev/06-language-pilot-steps.sh`

**Standard curl**

```bash
curl -sS https://datagems-dev.scayle.es/language-pilot/steps
```

### A7. HTML tree (empty viewer)

**Details**

- Method / URL: `GET https://datagems-dev.scayle.es/language-pilot/tree`
- Returns: HTML page to open a JSON file or run a question
- Script: `scripts/dev/07-language-pilot-tree.sh`

**Standard curl**

```bash
curl -sS https://datagems-dev.scayle.es/language-pilot/tree
```

---

## B. Language pilot — full ThematicExploration

Runs the whole pipeline (or stops at `until`). Response includes `pipeline[]`, `passages`, `synthesized_answer`, `grounded_citations`.

### B1. ThematicExploration

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/language-pilot/ThematicExploration`
- Auth: `Authorization: Bearer …` (Keycloak, category D)
- Body: `query`, optional `query_id`, `k`, `decompose_mode`, `until`, `include_trace`
- Script: `scripts/dev/08-thematic-exploration.sh`
- Until-retrieve script: `scripts/dev/08b-thematic-exploration-until-retrieve.sh`
- Timeouts / step failures: HTTP 200 with `status` `timeout` or `error`, plus `failed_step`, `error`, and `pipeline[]` for every step completed before the failure (intermediate fields such as `slices`, `qdmr`, `passages` are kept). Soft-failed CDD corpus-analysis stays inside `compute_features` and does not abort the run.

**Standard curl**

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
  -d '{"query": "How did a marriage look like in the 1800s compared to now?", "query_id": "curl-full", "k": 5, "decompose_mode": "few-shot"}'
```

Stop after retrieve:

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

### B2. Compare (deprecated alias)

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/language-pilot/compare`
- Same body and response as ThematicExploration
- Script: `scripts/dev/09-compare-alias.sh`

**Standard curl**

```bash
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/compare \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query": "How did a marriage look like in the 1800s compared to now?", "query_id": "curl-alias", "k": 5, "decompose_mode": "few-shot"}'
```

### B3. HTML tree from a saved JSON

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/language-pilot/tree`
- Body: a ThematicExploration JSON document
- Script: `scripts/dev/10-tree-from-json.sh` (reads `runs/thematic_exploration_marriage_v014.json`)

**Standard curl**

```bash
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/tree \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  --data-binary @runs/thematic_exploration_marriage_v014.json \
  -o thematic-tree.html
```

---

## C. Language pilot — one HTTP call per pipeline step

Each POST **restarts from the start** and stops at that node. The stopped node is `result`; everything up to there is `pipeline[]`. Auth is fetched inline in the curl.

Shared body:

```json
{"query": "How did a marriage look like in the 1800s compared to now?", "query_id": "curl-steps", "k": 5, "decompose_mode": "few-shot"}
```

### C1. Route

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/language-pilot/steps/route`
- Stops after: `route`
- Look at: `result.output.route.concept`
- Script: `scripts/dev/11-steps-route.sh`

**Standard curl**

```bash
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/steps/route \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query": "How did a marriage look like in the 1800s compared to now?", "query_id": "curl-steps", "k": 5, "decompose_mode": "few-shot"}'
```

### C2. Disambiguate

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/language-pilot/steps/disambiguate`
- Stops after: `disambiguate`
- Look at: `slices` — 1800s (Knowledge Project) vs present (Wikipedia)
- Script: `scripts/dev/12-steps-disambiguate.sh`

**Standard curl**

```bash
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/steps/disambiguate \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query": "How did a marriage look like in the 1800s compared to now?", "query_id": "curl-steps", "k": 5, "decompose_mode": "few-shot"}'
```

### C3. Extend knowledge

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/language-pilot/steps/extend-knowledge`
- Stops after: `extend_knowledge`
- Look at: facets, feature lenses, per-slice lemmas (`slice_1`, `slice_2`)
- Script: `scripts/dev/13-steps-extend-knowledge.sh`

**Standard curl**

```bash
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/steps/extend-knowledge \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query": "How did a marriage look like in the 1800s compared to now?", "query_id": "curl-steps", "k": 5, "decompose_mode": "few-shot"}'
```

### C3b. Generate sub-questions from facets and lemmas

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/language-pilot/steps/generate-subquestions`
- Stops after: `generate_subquestions`
- Look at: `generated_subquestions` — one question per thematic facet and lemma, per slice, plus a contrast question
- Retrieve later uses these questions together with QDMR
- Script: `scripts/dev/13b-steps-generate-subquestions.sh`

**Standard curl**

```bash
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/steps/generate-subquestions \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query": "How did a marriage look like in the 1800s compared to now?", "query_id": "curl-steps", "k": 5, "decompose_mode": "few-shot"}'
```

### C4. Decompose

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/language-pilot/steps/decompose`
- Stops after: `decompose`
- Look at: `qdmr` sub-questions; `decompose_mode`
- Script: `scripts/dev/14-steps-decompose.sh`

**Standard curl**

```bash
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/steps/decompose \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query": "How did a marriage look like in the 1800s compared to now?", "query_id": "curl-steps", "k": 5, "decompose_mode": "few-shot"}'
```

### C5. Retrieve

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/language-pilot/steps/retrieve`
- Stops after: `retrieve_slices`
- Calls Cross-Dataset Discovery `POST /search/` once per slice on the **dev** ingress
- Look at: `passages.slice_1` (Knowledge Project, usually hits) and **`passages.slice_2` (Wikipedia, often `[]`)** — that empty list is why `synthesized_answer` only cites the 1800s
- Also: `search_queries`, `retrieval_errors`
- Script: `scripts/dev/15-steps-retrieve.sh`

**Standard curl**

```bash
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/steps/retrieve \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query": "How did a marriage look like in the 1800s compared to now?", "query_id": "curl-steps", "k": 5, "decompose_mode": "few-shot"}'
```

### C6. Features

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/language-pilot/steps/features`
- Stops after: `compute_features`
- Calls Cross-Dataset Discovery `POST /corpus-analysis-search/` per slice
- Look at: `feature_metrics.slice_*.corpus_analysis.hit_count` (present often 0)
- Script: `scripts/dev/16-steps-features.sh`

**Standard curl**

```bash
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/steps/features \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query": "How did a marriage look like in the 1800s compared to now?", "query_id": "curl-steps", "k": 5, "decompose_mode": "few-shot"}'
```

### C7. Synthesize

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/language-pilot/steps/synthesize`
- Stops after: `synthesize`
- Grounded only on `passages`. No Wikipedia hits → no `[ref_N]` for present
- Look at: `synthesized_answer`, `grounded_citations`
- Script: `scripts/dev/17-steps-synthesize.sh`

**Standard curl**

```bash
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/steps/synthesize \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query": "How did a marriage look like in the 1800s compared to now?", "query_id": "curl-steps", "k": 5, "decompose_mode": "few-shot"}'
```

### C7b. Evaluate against ground truth

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/language-pilot/steps/evaluate`
- Stops after: `evaluate_answer`
- Looks up `Ground_Truth` in `data/*.json` (Pilot 2: `pilot2_benchmark_english.v1.json`) by `Question_ID`, exact question, concept (parent row for comparative queries), or overlap
- Look at: `nlg_evaluation.metrics` (BLEU, ROUGE, token F1, METEOR) and `nlg_evaluation.llm_judge` (separate LLM, not the synthesizer)
- The marriage walkthrough matches Question_ID `9`. Judge stays on Scayle but uses another model (`JUDGE_LLM_MODEL`, default `glm-5.3-flash` vs pipeline `qwen3`)
- Script: `scripts/dev/17b-steps-evaluate.sh`

**Standard curl**

```bash
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/steps/evaluate \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query": "How did a marriage look like in the 1800s compared to now?", "query_id": "curl-steps", "k": 5, "decompose_mode": "few-shot"}'
```

### C8. Export

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/language-pilot/steps/export`
- Stops after: `export_benchmark` (same coverage as a full ThematicExploration)
- Look at: `benchmark`
- Script: `scripts/dev/18-steps-export.sh`

**Standard curl**

```bash
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/steps/export \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query": "How did a marriage look like in the 1800s compared to now?", "query_id": "curl-steps", "k": 5, "decompose_mode": "few-shot"}'
```

---

## D. Keycloak (access token)

The nested `$(curl … | jq -r '.access_token')` in categories B, C, E, and F is this call. Language-pilot also forwards that JWT to Cross-Dataset Discovery.

### D1. Password grant

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token`
- Content-Type: `application/x-www-form-urlencoded`
- Fields: `grant_type=password`, `client_id=swagger-client`, `username`, `password`, `scope=openid datagems offline_access`
- Returns: JSON with `access_token`
- Script: `scripts/dev/19-keycloak-token.sh`
- Search scripts in category E fetch this token themselves

**Standard curl**

```bash
curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=password' \
  --data-urlencode 'client_id=swagger-client' \
  --data-urlencode 'username=dg-user-1' \
  --data-urlencode 'password=dg-user-1' \
  --data-urlencode 'scope=openid datagems offline_access'
```

---

## E. Cross-Dataset Discovery (dev ingress)

Public service at `https://datagems-dev.scayle.es/cross-dataset-discovery`. Not an in-cluster pod. Used by retrieve (`/search/`) and features (`/corpus-analysis-search/`).

### E1. Health

**Details**

- Method / URL: `GET https://datagems-dev.scayle.es/cross-dataset-discovery/health`
- Auth: none
- Script: `scripts/dev/20-cross-dataset-health.sh`

**Standard curl**

```bash
curl -sS https://datagems-dev.scayle.es/cross-dataset-discovery/health
```

### E2. Search — 1800s, Knowledge Project

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/cross-dataset-discovery/search/`
- Auth: `Authorization: Bearer …`
- Body: `query`, `k`, `search_mode` (`hybrid`), `dataset_ids`
- Dataset: `d84d1a2e-127d-4393-91d0-afb7e4fd9c68`
- Usually returns hits for this marriage query
- Script: `scripts/dev/21a-cross-dataset-search-knowledge-project.sh`

**Standard curl**

```bash
curl -sS -X POST https://datagems-dev.scayle.es/cross-dataset-discovery/search/ \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the definition of a marriage in the 1800s? wedding nuptials matrimony", "k": 5, "search_mode": "hybrid", "dataset_ids": ["d84d1a2e-127d-4393-91d0-afb7e4fd9c68"]}'
```

### E3. Search — present, Wikipedia (often empty)

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/cross-dataset-discovery/search/`
- Dataset: `1f6fba0c-9aea-4345-b5a3-457c924f9e0c`
- Often **0 hits** — this is the empty second period in ThematicExploration
- Script: `scripts/dev/21b-cross-dataset-search-wikipedia.sh`

**Standard curl**

```bash
curl -sS -X POST https://datagems-dev.scayle.es/cross-dataset-discovery/search/ \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the definition of a marriage in the present? wedding marriage union", "k": 5, "search_mode": "hybrid", "dataset_ids": ["1f6fba0c-9aea-4345-b5a3-457c924f9e0c"]}'
```

### E4. Search — German EncycNet

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/cross-dataset-discovery/search/`
- Dataset: `07382b91-5bc5-42f9-8391-33adc2460c19`
- Script: `scripts/dev/21c-cross-dataset-search-encycnet.sh`

**Standard curl**

```bash
curl -sS -X POST https://datagems-dev.scayle.es/cross-dataset-discovery/search/ \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query": "Ehe Hochzeit", "k": 5, "search_mode": "hybrid", "dataset_ids": ["07382b91-5bc5-42f9-8391-33adc2460c19"]}'
```

### E5. Search — French Diderot

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/cross-dataset-discovery/search/`
- Dataset: `d5c34990-9acf-4349-91d4-924f58565922`
- Script: `scripts/dev/21d-cross-dataset-search-diderot.sh`

**Standard curl**

```bash
curl -sS -X POST https://datagems-dev.scayle.es/cross-dataset-discovery/search/ \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query": "mariage", "k": 5, "search_mode": "hybrid", "dataset_ids": ["d5c34990-9acf-4349-91d4-924f58565922"]}'
```

### E6. Corpus-analysis-search

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/cross-dataset-discovery/corpus-analysis-search/`
- Body: **`query` and `dataset_ids` only** (no `k`, no `search_mode`)
- Used by language-pilot `compute_features`
- Script: `scripts/dev/22-cross-dataset-corpus-analysis.sh`

**Standard curl**

```bash
curl -sS -X POST https://datagems-dev.scayle.es/cross-dataset-discovery/corpus-analysis-search/ \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the definition of a marriage in the 1800s?", "dataset_ids": ["d84d1a2e-127d-4393-91d0-afb7e4fd9c68"]}'
```

---

## F. Query-disambiguation

Used by language-pilot `disambiguate`. On the cluster the pod calls the in-namespace service; from a laptop use the public ingress. If this 404s, the pilot falls back to local slice parsing.

### F1. Language disambiguation

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/query-disambiguation/query_disambiguation/language`
- Auth: `Authorization: Bearer …`
- Body: `query`
- Script: `scripts/dev/23-query-disambiguation-language.sh`

**Standard curl**

```bash
curl -sS -X POST https://datagems-dev.scayle.es/query-disambiguation/query_disambiguation/language \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query": "How did a marriage look like in the 1800s compared to now?"}'
```

---

## G. Britannica vs Wikipedia (same search, two corpora)

Same `POST /search/`, token, `k`, and `hybrid`. Only `query` and `dataset_ids` change. Language-pilot retrieve uses this pair: slice_1 → Knowledge Project, slice_2 → Wikipedia (often empty).

### G1. 19th C. Knowledge Project (Britannica)

Dataset `d84d1a2e-127d-4393-91d0-afb7e4fd9c68`. Usually returns hits.

```bash
curl -sS -X POST https://datagems-dev.scayle.es/cross-dataset-discovery/search/ \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the definition of a marriage in the 1800s? wedding nuptials matrimony", "k": 5, "search_mode": "hybrid", "dataset_ids": ["d84d1a2e-127d-4393-91d0-afb7e4fd9c68"]}'
```

### G2. Wikipedia (present, often empty)

Dataset `1f6fba0c-9aea-4345-b5a3-457c924f9e0c`. Often `results: []`.

```bash
curl -sS -X POST https://datagems-dev.scayle.es/cross-dataset-discovery/search/ \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the definition of a marriage in the present? wedding marriage union", "k": 5, "search_mode": "hybrid", "dataset_ids": ["1f6fba0c-9aea-4345-b5a3-457c924f9e0c"]}'
```
