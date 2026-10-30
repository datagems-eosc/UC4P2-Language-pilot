# API calls on datagems-dev

Host is always `https://datagems-dev.scayle.es`. Matching scripts: `scripts/dev/`.
Step → service diagram: [`ARCHITECTURE.md`](ARCHITECTURE.md).

**Access token.** Protected POSTs require a DataGEMS AAI JWT, same as [dg-app-api](https://github.com/datagems-eosc/dg-app-api). Each standard curl below fetches the token inline with `jq`. Scope is `openid datagems offline_access` (not `cross-dataset-discovery-api`). Health and catalog GETs stay public.

**Current upstream calls (pilot → shared services).** Only these remote paths are on the live language path:

| Pilot step | Upstream API |
|------------|--------------|
| `disambiguate` | `POST /query-disambiguation/query_disambiguation/language` (section F) |
| `extend_knowledge` | `POST /in-dataset-discovery/extendKnowledge` (section G) |
| `decompose` | `POST /in-dataset-discovery/decompose` (section G) |
| `evaluate_answer` | `POST /in-dataset-discovery/nlgEvaluate` (section G) |
| `retrieve_slices` | Cross-Dataset Discovery `POST /search/` (section E) |
| `compute_features` | Cross-Dataset Discovery `POST /corpus-analysis-search/` (section E) |

`route`, `generate_subquestions`, `synthesize`, and `export_benchmark` stay local in the pilot. Env: `QUERY_DISAMBIGUATION_URL`, `USE_IN_DATASET_DISCOVERY=1`, `IN_DATASET_DISCOVERY_URL`, `CROSS_DATASET_DISCOVERY_URL`. On QD/IDD outage the pilot keeps a local fallback.

**Not used by the pilot (do not call these for UC4P2):**

| Call | Why |
|------|-----|
| `POST /language-pilot/compare` | Deprecated alias of `/ThematicExploration` (still mounted, do not use) |
| `POST /query-disambiguation/query_disambiguation` (and `/openai`, `/scayle`, `/query_disambiguation4ap`) | General / AP QD APIs — pilot uses **`/query_disambiguation/language` only** |
| IDD `/explore`, `/text2sql`, `/text2geo`, `/linguisticFeatures`, … | Other IDD products — pilot uses **`/extendKnowledge`**, **`/decompose`**, **`/nlgEvaluate` only** |

**Example question (v2 parent `Question_ID` `9`):** `How does the definition of a valid marriage shift over time in the Western hemisphere?`

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
| `query` | Required question text. A single named period (for example Berlin’s climate in the 19th century) is a descriptive one-slice run; “compared to now” / “vary across time” still uses two slices. |
| `query_id` | Optional stable id (also used for gold / NLG match when it equals `Question_ID`) |
| `k` | Passages per slice, 1–20, default 5 |
| `decompose_mode` | `predict`, `cot`, or `few-shot` (default) |
| `use_extension_questions` | Default `false`. If `true`, each knowledge-extension question is retrieved as its own search. Decomposition still uses the original question |
| `include_trace` | `true` adds `raw_trace` |
| `until` | Stop after a node (full run only): `route`, `disambiguate`, `extend_knowledge`, `generate_subquestions`, `decompose`, `retrieve_slices`, `compute_features`, `synthesize`, `evaluate_answer`, `export_benchmark` |
| `use_memory` | Default `true`. Reuse a stored result for the same question + options instead of re-running |
| `refresh` | Default `false`. If `true`, ignore stored memory, run again, and overwrite storage (consistency check) |

**Response highlights**

| Field | Details |
|-------|---------|
| `status` | `ok`, `running` (SSE only), `clarification`, `partial`, `timeout`, or `error` |
| `pipeline[]` | Ordered steps with `outcome`, `summary`, and `output` (decomposed questions, passages, etc.) |
| `memory` | `{ hit, key, stored_at, path }` — `hit: true` when served from run memory |
| `failed_step` / `error` | Set when a step times out or fails; earlier `pipeline[]` results are kept |
| `synthesized_answer`, `grounded_citations`, `nlg_evaluation` | Answer, citations, NLG + LLM-as-judge |

Live version: **`0.1.28`**.

---

## A. Language pilot — catalog

Service info, docs, and HTML tree. No JSON body.

### A1. Root

**Details**

- Method / URL: `GET https://datagems-dev.scayle.es/language-pilot/`
- Returns: service name, version (`0.1.28`), docs path, `tree` / `tree_token` / stream, step list
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

### A7. HTML tree (viewer)

**Details**

- Method / URL: `GET https://datagems-dev.scayle.es/language-pilot/tree`
- Returns: HTML page to open a JSON file or run a question
- Auth: none for the page. **Run** calls `GET /tree/token` first (demo Keycloak user), then streams the pipeline. No Bearer field; a new token is minted on every click.
- UI: left **Questions** drawer lists every row from `data/pilot2_benchmark_english.v2.json` (`Question_ID` / `Subquestion_ID` `0`–`35`; nested children indented). Click one to fill the question field and `query_id`. Check **KE questions** to retrieve each knowledge-extension question as its own search (off = one search per slice). Banner shows “Getting access token…” then “Running pipeline…”; `[ref_N]` jumps to the matching card. `grounded_citations` is only the passages used in the answer (`ref_1`…); other hits stay in the retrieve step.
- Prefer a browser: https://datagems-dev.scayle.es/language-pilot/tree
- Script: `scripts/dev/07-language-pilot-tree.sh`

**Standard curl**

```bash
curl -sS https://datagems-dev.scayle.es/language-pilot/tree
```

### A8. Tree default Bearer token

**Details**

- Method / URL: `GET https://datagems-dev.scayle.es/language-pilot/tree/token`
- Auth: none
- Returns: `{"access_token":"…","token_type":"Bearer","expires_in":…}` (uses `DG_USERNAME` / `DG_PASSWORD`, else demo `dg-user-1`). The `/tree` **Run** button calls this on every click so the pipeline never reuses a leftover JWT.
- Disable with `TREE_AUTO_TOKEN=false`

**Standard curl**

```bash
curl -sS https://datagems-dev.scayle.es/language-pilot/tree/token
```

### A9. Tree question catalog

**Details**

- Method / URL: `GET https://datagems-dev.scayle.es/language-pilot/tree/questions`
- Auth: none
- Returns: `{ count, questions: [{ query_id, question, concept, source, parent, parent_id }] }` — all **36** v2 rows (`0`–`35`); `parent: false` + `parent_id` for nested subquestions

**Standard curl**

```bash
curl -sS https://datagems-dev.scayle.es/language-pilot/tree/questions
```

---

## B. Language pilot — full ThematicExploration

Runs the whole pipeline (or stops at `until`). Response includes `pipeline[]`, `passages`, `synthesized_answer`, `grounded_citations`, `nlg_evaluation`, and `memory`.

### B1. ThematicExploration

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/language-pilot/ThematicExploration`
- Auth: `Authorization: Bearer …` (Keycloak, category D)
- Body: `query`, optional `query_id`, `k`, `decompose_mode`, `use_extension_questions` (default `false`), `until`, `include_trace`, `use_memory` (default `true`), `refresh` (default `false`)
- Script: `scripts/dev/08-thematic-exploration.sh`
- Until-retrieve script: `scripts/dev/08b-thematic-exploration-until-retrieve.sh`
- Run memory: same question + `query_id` + `k` + `decompose_mode` + `use_extension_questions` + `until` returns the stored result (`memory.hit=true`) instead of re-running. Storage is JSON files under `RUN_MEMORY_DIR` (default `runs/memory/` locally, `/app/runs/memory/` in the pod). Pod disk is ephemeral unless a volume is mounted. Set `"refresh": true` to force a new pipeline run and overwrite storage. Set `"use_memory": false` to never read/write.
- Timeouts / step failures: HTTP 200 with `status` `timeout` or `error`, plus `failed_step`, `error`, and `pipeline[]` for every step completed before the failure. Soft-failed CDD corpus-analysis stays inside `compute_features` and does not abort the run.

**Standard curl** (first run stores; second run is a memory hit)

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
  -d '{"query": "How does the definition of a valid marriage shift over time in the Western hemisphere?", "query_id": "9", "k": 5, "decompose_mode": "few-shot"}'
```

Force a fresh run (consistency check):

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
  -d '{"query": "How does the definition of a valid marriage shift over time in the Western hemisphere?", "query_id": "9", "k": 5, "decompose_mode": "few-shot", "refresh": true}'
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
  -d '{"query": "How does the definition of a valid marriage shift over time in the Western hemisphere?", "until": "retrieve_slices"}'
```

### B1b. ThematicExploration stream (SSE)

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/language-pilot/ThematicExploration/stream`
- Auth: same Bearer JWT as B1
- Body: same as B1
- Returns: `text/event-stream`. First `event: job` has `job_id`. Each finished node is `event: step` with `status: "running"` and a growing `pipeline[]`. The last `event: done` is the same JSON as POST `/ThematicExploration` (including `memory`). Comment keepalives are sent while a step is still running.
- The pipeline keeps running in a background job if the SSE connection drops. Poll B1c with `job_id` (also in `X-Run-Id`).
- The `/tree` UI streams live, then polls B1c if the stream drops. If the job snapshot is missing it finishes with a normal POST `/ThematicExploration` instead of stopping on a network error.
- Memory hits emit `event: job` then a single `event: done`.

**Standard curl**

```bash
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
  -d '{"query": "How does the definition of a valid marriage shift over time in the Western hemisphere?", "query_id": "9", "k": 5, "decompose_mode": "few-shot"}'
```

### B1c. ThematicExploration run snapshot

**Details**

- Method / URL: `GET https://datagems-dev.scayle.es/language-pilot/ThematicExploration/runs/{job_id}`
- Auth: same Bearer JWT as B1
- Returns: the latest streamed payload for that `job_id` (`status` stays `running` until the background job finishes)

**Standard curl**

```bash
curl -sS https://datagems-dev.scayle.es/language-pilot/ThematicExploration/runs/JOB_ID \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')"
```

### B2. HTML tree from a saved JSON

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/language-pilot/tree`
- Auth: Bearer JWT
- Body: a ThematicExploration JSON document (large payloads may hit ingress `413`; prefer GET `/tree` + **Open JSON** in the browser)
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
{"query": "How does the definition of a valid marriage shift over time in the Western hemisphere?", "query_id": "9", "k": 5, "decompose_mode": "few-shot"}
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
  -d '{"query": "How does the definition of a valid marriage shift over time in the Western hemisphere?", "query_id": "9", "k": 5, "decompose_mode": "few-shot"}'
```

### C2. Disambiguate

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/language-pilot/steps/disambiguate`
- Stops after: `disambiguate`
- Upstream: query-disambiguation `POST /query_disambiguation/language` (section F). Summary includes `Source: query-disambiguation-api` when remote succeeds.
- Look at: `comparison_type` (`temporal` / `cross_lingual` / `descriptive`), `concept`, `slices` (corpus ids + years). Descriptive one-period questions keep a single slice.
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
  -d '{"query": "How does the definition of a valid marriage shift over time in the Western hemisphere?", "query_id": "9", "k": 5, "decompose_mode": "few-shot"}'
```

### C3. Extend knowledge

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/language-pilot/steps/extend-knowledge`
- Stops after: `extend_knowledge`
- Upstream: in-dataset-discovery `POST /extendKnowledge` when `USE_IN_DATASET_DISCOVERY=1` (section G). Concept is extracted on IDD (LLM-first); the pilot does not pass a local concept override.
- Look at: facets, feature lenses, per-slice lemmas (`slice_1`, `slice_2`), updated `concept`
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
  -d '{"query": "How does the definition of a valid marriage shift over time in the Western hemisphere?", "query_id": "9", "k": 5, "decompose_mode": "few-shot"}'
```

### C3b. Generate sub-questions from facets and lemmas

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/language-pilot/steps/generate-subquestions`
- Stops after: `generate_subquestions`
- Look at: `generated_subquestions` — one question per thematic facet and lemma, per slice, plus a contrast question
- These stay out of QDMR. With `use_extension_questions`, retrieve searches each one as a single query
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
  -d '{"query": "How does the definition of a valid marriage shift over time in the Western hemisphere?", "query_id": "9", "k": 5, "decompose_mode": "few-shot"}'
```

### C4. Decompose

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/language-pilot/steps/decompose`
- Stops after: `decompose`
- Upstream: in-dataset-discovery `POST /decompose` when `USE_IN_DATASET_DISCOVERY=1` (section G). Local QDMR (`decompose_mode`) is the fallback.
- Look at: `qdmr` sub-questions; `decompose_mode` (`idd` when remote)
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
  -d '{"query": "How does the definition of a valid marriage shift over time in the Western hemisphere?", "query_id": "9", "k": 5, "decompose_mode": "few-shot"}'
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
  -d '{"query": "How does the definition of a valid marriage shift over time in the Western hemisphere?", "query_id": "9", "k": 5, "decompose_mode": "few-shot"}'
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
  -d '{"query": "How does the definition of a valid marriage shift over time in the Western hemisphere?", "query_id": "9", "k": 5, "decompose_mode": "few-shot"}'
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
  -d '{"query": "How does the definition of a valid marriage shift over time in the Western hemisphere?", "query_id": "9", "k": 5, "decompose_mode": "few-shot"}'
```

### C7b. Evaluate against ground truth

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/language-pilot/steps/evaluate`
- Stops after: `evaluate_answer`
- Upstream: in-dataset-discovery `POST /nlgEvaluate` when `USE_IN_DATASET_DISCOVERY=1` (section G). Gold match is **exact** `Question_ID` or question text only (no fuzzy overlap).
- Look at: `nlg_evaluation.metrics` (BLEU, ROUGE, token F1, METEOR) and `nlg_evaluation.llm_judge` (separate LLM, not the synthesizer)
- Gold match for this walkthrough: `query_id` **`9`** (v2 parent). Judge stays on Scayle but uses another model (`JUDGE_LLM_MODEL`, default `glm-5.3-flash` vs pipeline `qwen3`)
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
  -d '{"query": "How does the definition of a valid marriage shift over time in the Western hemisphere?", "query_id": "9", "k": 5, "decompose_mode": "few-shot"}'
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
  -d '{"query": "How does the definition of a valid marriage shift over time in the Western hemisphere?", "query_id": "9", "k": 5, "decompose_mode": "few-shot"}'
```

---

## D. Keycloak (access token)

The nested `$(curl … | jq -r '.access_token')` in categories B, C, E, F, and G is this call. Language-pilot also forwards that JWT to Cross-Dataset Discovery, query-disambiguation, and in-dataset-discovery.

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

## F. Query-disambiguation (language only)

Used by language-pilot `disambiguate`. Live image **`v0.1.14`** (language gate parity: descriptive, default temporal pair, `corpus_id`, rich concepts). On the cluster the pod calls the in-namespace service; from a laptop use the public ingress. If unreachable, the pilot falls back to local slice parsing.

**UC4P2 uses only** `POST /query_disambiguation/language`. Do not use `/query_disambiguation`, `/query_disambiguation/openai`, `/query_disambiguation/scayle`, or `/query_disambiguation4ap` from the language pilot path.

### F1. Language disambiguation

**Details**

- Method / URL: `POST https://datagems-dev.scayle.es/query-disambiguation/query_disambiguation/language`
- Auth: `Authorization: Bearer …`
- Body: `{ "query": "…" }` (optional `use_llm`, `llm_model`)
- Returns: `proceed`, `comparison_type`, `target_concepts`, `slices[]` (`label`, years, `language`, `corpus_id`), optional `clarification` / `constraint_errors`
- Script: `scripts/dev/23-query-disambiguation-language.sh`
- Health: `GET https://datagems-dev.scayle.es/query-disambiguation/health`

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
  -d '{"query": "How does the definition of a valid marriage shift over time in the Western hemisphere?"}'
```

Descriptive (single period):

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
  -d '{"query": "How can the climate of Berlin in the 19th century be described?"}'
```

---

## G. In-dataset-discovery (question tools used by UC4P2)

Used by language-pilot `extend_knowledge`, `decompose`, and `evaluate_answer` when `USE_IN_DATASET_DISCOVERY=1`. Tools live under `src/agents/tools/` in [in-dataset-discovery](https://github.com/datagems-eosc/in-dataset-discovery); router: `src/app/routers/language.py`.

**UC4P2 uses only** the three routes below. Ignore other IDD paths (`/explore`, `/text2sql`, `/text2geo`, `/linguisticFeatures`, …) for this pilot.

| Method / path | Pilot step | Body |
|---------------|------------|------|
| `POST /extendKnowledge` | `extend_knowledge` | `question`, optional `concept`, `slices` |
| `POST /decompose` | `decompose` | `question`, optional `concept`, `slices` |
| `POST /nlgEvaluate` | `evaluate_answer` | `question`, `answer`, optional `query_id`, `ground_truth` |

Parent gold for remote NLG: IDD `data/nlg/pilot2_nlg_gold.v2.json` (not the full pilot benchmark). Base: `https://datagems-dev.scayle.es/in-dataset-discovery`. Health: `GET …/health`. Auth: Bearer (same Keycloak token as the pilot).

### G1. Decompose

```bash
curl -sS -X POST https://datagems-dev.scayle.es/in-dataset-discovery/decompose \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"question": "How does the definition of a valid marriage shift over time in the Western hemisphere?"}'
```

### G2. Extend knowledge

```bash
curl -sS -X POST https://datagems-dev.scayle.es/in-dataset-discovery/extendKnowledge \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"question": "How does the definition of a valid marriage shift over time in the Western hemisphere?"}'
```

### G3. NLG evaluate

```bash
curl -sS -X POST https://datagems-dev.scayle.es/in-dataset-discovery/nlgEvaluate \
  -H "Authorization: Bearer $(curl -sS --location 'https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token' \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=password' \
        --data-urlencode 'client_id=swagger-client' \
        --data-urlencode 'username=dg-user-1' \
        --data-urlencode 'password=dg-user-1' \
        --data-urlencode 'scope=openid datagems offline_access' | jq -r '.access_token')" \
  -H "Content-Type: application/json" \
  -d '{"question": "How does the definition of a valid marriage shift over time in the Western hemisphere?", "answer": "…", "query_id": "9"}'
```

Parent gold rows in IDD are under `data/nlg/pilot2_nlg_gold.v2.json` (`0`, `4`, `9`, `15`, `19`, `23`, `27`, `31`). Nested subquestion ids live only in the language-pilot benchmark file.
---
