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
curl -s -X POST "http://localhost:8080/compare" \
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

The response includes `search_queries`, per-slice `passages` (from Cross-Dataset Discovery), `retrieval_errors`, `synthesized_answer`, and `grounded_citations`.

Dev cluster (after deploy):

```text
https://datagems-dev.scayle.es/language-pilot/health
https://datagems-dev.scayle.es/language-pilot/swagger
```

```bash
curl -s -X POST "https://datagems-dev.scayle.es/language-pilot/compare" \
  -H "Content-Type: application/json" \
  -d '{"query": "How did a marriage look like in the 1800s compared to now?"}'
```

Kubernetes manifests: [`UC4P2-Language-pilot-deployment-dev`](../UC4P2-Language-pilot-deployment-dev).

## Retrieval

Each comparison slice issues `POST /search/` on Cross-Dataset Discovery. The search string is the decomposed sub-question for that slice plus lexical variants. Auth uses a Keycloak password-grant token (`DG_USERNAME` / `DG_PASSWORD`) unless `CROSS_DATASET_DISCOVERY_TOKEN` is set.

## Tests

```bash
PYTHONPATH=. pytest
```

Notebook for the API and retrieval: [`notebooks/compare_api.ipynb`](notebooks/compare_api.ipynb). Open it from the repo root kernel (`PYTHONPATH` is set in the first cell).
