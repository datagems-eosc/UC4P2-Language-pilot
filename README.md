# UC4P2 Language Pilot

Historical comparative QA for the DataGEMS language use case (Thematic Search). The pipeline disambiguates a question, expands knowledge, decomposes it, retrieves passages from [Cross-Dataset Discovery](https://datagems-eosc.github.io/cross-dataset-discovery-docs/latest/api-overview/), and returns a grounded comparison.

## HTTP API

```bash
pip install -r requirements.txt
cp .env.example .env   # fill DG_USERNAME / DG_PASSWORD and optional Scayle credentials
PYTHONPATH=. python -m uvicorn src.app.main:app --host 0.0.0.0 --port 8080
```

- API: http://localhost:8080
- Swagger: http://localhost:8080/swagger
- Health: http://localhost:8080/health

```bash
curl -s -X POST "http://localhost:8080/ThematicExploration" \
  -H "Content-Type: application/json" \
  -d '{"query": "How did a marriage look like in the 1800s compared to now?"}'
```

`POST /compare` is an alias of the same operation.

Each pipeline node also has its own endpoint. It runs from the start through that node and returns that node as `result`, with the prefix in `pipeline`.

| Method | Path | Stops after |
|--------|------|-------------|
| GET | `/steps` | Catalog of step APIs |
| POST | `/steps/route` | `route` |
| POST | `/steps/disambiguate` | `disambiguate` |
| POST | `/steps/extend-knowledge` | `extend_knowledge` |
| POST | `/steps/decompose` | `decompose` |
| POST | `/steps/retrieve` | `retrieve_slices` |
| POST | `/steps/features` | `compute_features` |
| POST | `/steps/synthesize` | `synthesize` |
| POST | `/steps/export` | `export_benchmark` (same as `/ThematicExploration`) |

```bash
curl -s -X POST "http://localhost:8080/steps/disambiguate" \
  -H "Content-Type: application/json" \
  -d '{"query": "How did a marriage look like in the 1800s compared to now?"}'
```

Optional fields:

| Field | Meaning |
|-------|---------|
| `query_id` | Stable id in the response / benchmark record |
| `until` | Stop after a LangGraph node (`disambiguate`, `retrieve_slices`, …) |
| `k` | Passages per slice (default 5) |
| `include_trace` | Include every node update |

The response `pipeline` list is the audit trail: one object per step with `step`, `name`, `title`, `outcome`, `summary`, and `output`. Convenience fields (`synthesized_answer`, `passages`, …) still sit at the top level. Set `include_trace` if you also need the raw LangGraph updates as `raw_trace`.

Dev cluster (after deploy):

```text
https://datagems-dev.scayle.es/language-pilot/health
https://datagems-dev.scayle.es/language-pilot/swagger
```

```bash
curl -s -X POST "https://datagems-dev.scayle.es/language-pilot/ThematicExploration" \
  -H "Content-Type: application/json" \
  -d '{"query": "How did a marriage look like in the 1800s compared to now?"}'
```

Kubernetes manifests: [`UC4P2-Language-pilot-deployment-dev`](../UC4P2-Language-pilot-deployment-dev).

## Retrieval

Each comparison slice issues `POST /search/` (and `POST /corpus-analysis-search/`) on Cross-Dataset Discovery, restricted to the language corpora:

| Key | Name | Language / era | UUID |
|-----|------|----------------|------|
| Encyc | EncycNet | German, historical | `07382b91-5bc5-42f9-8391-33adc2460c19` |
| Kp | 19th C. Knowledge Project (Britannica) | English, historical | `d84d1a2e-127d-4393-91d0-afb7e4fd9c68` |
| Diderot | Encyclopédie | French, historical | `d5c34990-9acf-4349-91d4-924f58565922` |
| Wiki | Wikipedia | present-day | `1f6fba0c-9aea-4345-b5a3-457c924f9e0c` |

The search string is the decomposed sub-question for that slice plus lexical variants. Auth uses a Keycloak password-grant token (`DG_USERNAME` / `DG_PASSWORD`) unless `CROSS_DATASET_DISCOVERY_TOKEN` is set.

`compute_features` then calls `POST /corpus-analysis-search/` on the same service (UC4P1-style features live in the result `metadata`). Local KWIC/collocations stay on the retrieved passages as a fallback if that call fails.

The final answer is synthesized only from `passages`. Each `[ref_N]` in `synthesized_answer` maps to `grounded_citations` (`slice_id`, `dataset_id`, `source_document`, `text_snippet`) so you can open the matching retrieval hit.

## Tests

```bash
PYTHONPATH=. pytest
```

Notebook for the API and retrieval: [`notebooks/compare_api.ipynb`](notebooks/compare_api.ipynb). Open it from the repo root kernel (`PYTHONPATH` is set in the first cell).
