"""HTML tree view of a ThematicExploration JSON payload, pipeline first → last."""

from __future__ import annotations

import html
import json
from typing import Any

from fastapi.responses import HTMLResponse

from src.retrieval.corpora import corpus_name_for_id

_OVERVIEW_KEYS = (
    "service",
    "query_id",
    "question",
    "status",
    "last_step",
    "failed_step",
    "error",
    "decompose_mode",
    "concept",
    "comparison_type",
    "clarification",
    "constraint_errors",
    "slices",
)

_END_KEYS = ("synthesized_answer", "nlg_evaluation", "grounded_citations")

_TEXT_LIMIT = 600


def _truncate(text: Any, limit: int = _TEXT_LIMIT) -> str:
    value = str(text or "")
    if len(value) <= limit:
        return value
    return value[:limit] + "…"


def _slice_labels(slices: list[Any] | None) -> dict[str, str]:
    labels: dict[str, str] = {}
    for item in slices or []:
        if not isinstance(item, dict):
            continue
        slice_id = str(item.get("slice_id") or "")
        label = str(item.get("label") or slice_id)
        corpus = corpus_name_for_id(str(item.get("corpus_id") or ""))
        labels[slice_id] = f"{label} · {corpus}" if corpus else label
    return labels


def _enrich_passages(
    passages: Any,
    slice_labels: dict[str, str],
) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(passages, dict):
        return {}
    enriched: dict[str, list[dict[str, Any]]] = {}
    for slice_id, items in passages.items():
        heading = slice_labels.get(str(slice_id), str(slice_id))
        rows: list[dict[str, Any]] = []
        for index, item in enumerate(items or [], start=1):
            if not isinstance(item, dict):
                continue
            dataset_id = str(item.get("dataset_id") or "")
            rows.append(
                {
                    "rank": index,
                    "corpus": corpus_name_for_id(dataset_id) or dataset_id,
                    "dataset_id": dataset_id,
                    "doc_id": item.get("doc_id"),
                    "similarity": item.get("similarity"),
                    "text": _truncate(item.get("text") or item.get("text_snippet")),
                }
            )
        enriched[heading] = rows
    return enriched


def _enrich_step(step: dict[str, Any], slice_labels: dict[str, str]) -> dict[str, Any]:
    """Promote step outputs so decomposed questions / passages are one click away."""
    output = step.get("output") if isinstance(step.get("output"), dict) else {}
    name = str(step.get("name") or "")
    display: dict[str, Any] = {
        "step": step.get("step"),
        "name": step.get("name"),
        "title": step.get("title"),
        "outcome": step.get("outcome"),
        "summary": step.get("summary"),
    }
    if name == "route":
        display["route"] = output.get("route") or output
    elif name == "disambiguate":
        display["slices"] = output.get("slices")
        display["comparison_type"] = output.get("comparison_type")
        display["disambiguation_source"] = output.get("disambiguation_source")
        if output.get("clarification"):
            display["clarification"] = output.get("clarification")
    elif name == "extend_knowledge":
        display["expansion"] = output.get("expansion")
    elif name == "generate_subquestions":
        display["generated_subquestions"] = output.get("generated_subquestions")
    elif name == "decompose":
        display["decomposed_questions"] = output.get("qdmr")
        display["decompose_mode"] = output.get("decompose_mode")
    elif name == "retrieve_slices":
        display["search_queries"] = output.get("search_queries")
        display["retrieved_passages"] = _enrich_passages(output.get("passages"), slice_labels)
        errors = output.get("retrieval_errors") or {}
        if errors:
            display["retrieval_errors"] = errors
    elif name == "compute_features":
        metrics = output.get("feature_metrics") or {}
        compact: dict[str, Any] = {}
        for slice_id, block in metrics.items() if isinstance(metrics, dict) else []:
            if not isinstance(block, dict):
                continue
            ca = block.get("corpus_analysis") if isinstance(block.get("corpus_analysis"), dict) else {}
            compact[slice_labels.get(str(slice_id), str(slice_id))] = {
                "passage_count": block.get("passage_count"),
                "corpus_analysis_hits": ca.get("hit_count"),
                "corpus_analysis_error": ca.get("error"),
                "corpus_analysis_source": ca.get("source"),
            }
        display["feature_metrics"] = compact
    elif name == "synthesize":
        display["answer"] = output.get("synthesized_answer")
        citations = []
        for item in output.get("grounded_citations") or []:
            if not isinstance(item, dict):
                continue
            citations.append(
                {
                    "citation_id": item.get("citation_id"),
                    "slice": slice_labels.get(str(item.get("slice_id") or ""), item.get("slice_label")),
                    "corpus": item.get("corpus_name")
                    or corpus_name_for_id(str(item.get("dataset_id") or "")),
                    "similarity": item.get("similarity"),
                    "used_in_answer": item.get("used_in_answer"),
                    "text": _truncate(item.get("text_snippet") or item.get("text"), 360),
                }
            )
        display["citations"] = citations
    elif name == "evaluate_answer":
        display["nlg_evaluation"] = output.get("nlg_evaluation")
    elif name == "export_benchmark":
        record = output.get("benchmark") if isinstance(output.get("benchmark"), dict) else {}
        display["benchmark"] = {
            "query_id": record.get("query_id"),
            "question": record.get("question"),
            "concept": record.get("concept"),
        }
    if step.get("outcome") in {"timeout", "failed"} and output.get("error"):
        display["error"] = output.get("error")
        display["completed_steps"] = output.get("completed_steps")
    return display


def presentation_tree(payload: Any) -> Any:
    """Reorder a run so the user reads overview → pipeline (1…n) → answer."""
    if not isinstance(payload, dict):
        return payload
    pipeline = payload.get("pipeline")
    if not isinstance(pipeline, list):
        return payload
    slice_labels = _slice_labels(payload.get("slices") if isinstance(payload.get("slices"), list) else [])
    ordered: dict[str, Any] = {}
    for key in _OVERVIEW_KEYS:
        value = payload.get(key)
        if value not in (None, "", []):
            ordered[key] = value
    ordered["pipeline"] = [
        _enrich_step(step, slice_labels) if isinstance(step, dict) else step for step in pipeline
    ]
    for key in _END_KEYS:
        value = payload.get(key)
        if value not in (None, "", []):
            ordered[key] = value
    return ordered


def _leaf(value: Any) -> str:
    if value is None:
        return '<span class="null">null</span>'
    if isinstance(value, bool):
        return f'<span class="bool">{str(value).lower()}</span>'
    if isinstance(value, (int, float)):
        return f'<span class="num">{html.escape(str(value))}</span>'
    text = str(value)
    klass = "str long" if len(text) > 80 or "\n" in text else "str"
    return f'<span class="{klass}">{html.escape(text)}</span>'


def _label(key: str, value: Any) -> str:
    if isinstance(value, dict):
        n = len(value)
        return f"{html.escape(key)} <em>{'{ ' + str(n) + ' }' if n else 'empty'}</em>"
    if isinstance(value, list):
        n = len(value)
        return f"{html.escape(key)} <em>{'[ ' + str(n) + ' ]' if n else 'empty'}</em>"
    return html.escape(key)


def _node_html(key: str, value: Any, *, open_node: bool = False) -> str:
    opened = " open" if open_node else ""
    if value is None or isinstance(value, (str, int, float, bool)):
        return (
            f'<div class="leaf"><span class="key">{html.escape(key)}</span>'
            f'<span class="colon">:</span> {_leaf(value)}</div>'
        )
    if isinstance(value, list):
        if value and all(item is None or not isinstance(item, (dict, list)) for item in value):
            items = "".join(f"<li>{_leaf(item)}</li>" for item in value)
            return (
                f"<details{opened}><summary>{_label(key, value)}</summary>"
                f'<ol class="scalars">{items}</ol></details>'
            )
        is_pipeline = bool(value and isinstance(value[0], dict) and value[0].get("name") and value[0].get("title"))
        children = "".join(
            _node_html(str(index), item, open_node=is_pipeline) for index, item in enumerate(value, start=1)
        )
        return (
            f"<details{opened}><summary>{_label(key, value)}</summary>"
            f'<div class="kids">{children}</div></details>'
        )
    if key.isdigit() and isinstance(value, dict) and value.get("name") and value.get("title"):
        outcome = html.escape(str(value.get("outcome") or ""))
        title = html.escape(str(value.get("title") or value.get("name") or key))
        name = html.escape(str(value.get("name") or ""))
        summary = (
            f'<span class="badge">{html.escape(key)}</span> {title} '
            f"<code>{name}</code> <span class=\"outcome {outcome}\">{outcome}</span>"
        )
        if value.get("summary"):
            summary += f'<span class="hint">{html.escape(str(value["summary"]))}</span>'
        skip = {"step", "name", "title", "outcome", "summary"}
        open_children = {
            "decomposed_questions",
            "generated_subquestions",
            "retrieved_passages",
            "search_queries",
            "slices",
            "expansion",
            "answer",
            "citations",
            "nlg_evaluation",
            "route",
            "error",
        }
        children = "".join(
            _node_html(child, value[child], open_node=child in open_children)
            for child in value
            if child not in skip
        )
        return (
            f"<details{opened} class=\"step {outcome}\"><summary>{summary}</summary>"
            f'<div class="kids">{children}</div></details>'
        )
    children = "".join(_node_html(child, value[child]) for child in value)
    return (
        f"<details{opened}><summary>{_label(key, value)}</summary>"
        f'<div class="kids">{children}</div></details>'
    )


def tree_markup(payload: Any) -> str:
    ordered = presentation_tree(payload)
    if not isinstance(ordered, dict):
        return f'<div class="tree">{_leaf(ordered)}</div>'
    open_keys = {"pipeline", "question", "status", "synthesized_answer", "slices"}
    parts = [
        _node_html(key, value, open_node=key in open_keys)
        for key, value in ordered.items()
    ]
    return f'<div class="tree">{"".join(parts)}</div>'


def tree_page(payload: Any | None = None, *, error: str = "") -> str:
    body = tree_markup(payload) if payload is not None else '<p class="empty">Open a ThematicExploration JSON file, or run a question.</p>'
    err = f'<p class="error">{html.escape(error)}</p>' if error else ""
    embedded = "null"
    if payload is not None:
        embedded = json.dumps(payload, ensure_ascii=False, default=str).replace("<", "\\u003c")
    return _PAGE.replace("__TREE__", body).replace("__ERROR__", err).replace("__EMBEDDED__", embedded)


def html_response(payload: Any | None = None, *, error: str = "", status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(tree_page(payload, error=error), status_code=status_code)


_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>ThematicExploration tree</title>
  <style>
    :root {
      --ink: #1c1917;
      --muted: #57534e;
      --line: #e7e5e4;
      --bg: #fafaf9;
      --card: #ffffff;
      --ok: #166534;
      --ok-bg: #dcfce7;
      --partial: #92400e;
      --fail: #991b1b;
      --accent: #1e3a5f;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font: 15px/1.45 "Source Sans 3", "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--bg);
    }
    header {
      position: sticky; top: 0; z-index: 2;
      background: var(--accent); color: #fff;
      padding: 14px 20px 16px;
      display: grid; gap: 10px;
    }
    header h1 { margin: 0; font-size: 1.15rem; font-weight: 650; }
    header p { margin: 0; opacity: .85; font-size: .9rem; }
    .bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .bar input[type=text], .bar textarea {
      flex: 1 1 280px; min-width: 0; padding: 8px 10px;
      border: 0; border-radius: 6px; font: inherit;
    }
    .bar button, .bar label.file {
      background: #fff; color: var(--accent); border: 0;
      border-radius: 6px; padding: 8px 12px; cursor: pointer; font: inherit; font-weight: 600;
    }
    .bar label.file input { display: none; }
    main { max-width: 1100px; margin: 0 auto; padding: 18px 16px 64px; }
    .empty, .error { padding: 16px; background: var(--card); border: 1px solid var(--line); border-radius: 8px; }
    .error { color: var(--fail); }
    .tree details {
      border-left: 1px solid var(--line);
      margin-left: 8px; padding-left: 10px;
    }
    .tree details.step { border-left-width: 3px; margin: 8px 0 8px 4px; padding: 4px 0 4px 10px; background: var(--card); border-radius: 0 8px 8px 0; }
    .tree details.step.ok { border-left-color: var(--ok); }
    .tree details.step.partial { border-left-color: var(--partial); }
    .tree details.step.failed, .tree details.step.halted, .tree details.step.timeout { border-left-color: var(--fail); }
    summary { cursor: pointer; padding: 4px 0; }
    summary .badge {
      display: inline-block; min-width: 1.6em; text-align: center;
      background: var(--accent); color: #fff; border-radius: 4px;
      font-size: .75rem; padding: 1px 5px; margin-right: 6px;
    }
    summary code { font-size: .8rem; color: var(--muted); }
    .outcome { font-size: .75rem; font-weight: 700; text-transform: uppercase; margin-left: 6px; }
    .outcome.ok { color: var(--ok); }
    .outcome.partial { color: var(--partial); }
    .outcome.failed, .outcome.halted, .outcome.timeout { color: var(--fail); }
    .hint { display: block; color: var(--muted); font-size: .9rem; margin: 2px 0 0 2.1em; }
    .leaf { padding: 2px 0; }
    .key { font-weight: 600; }
    .colon { color: var(--muted); }
    .str.long { white-space: pre-wrap; display: inline-block; max-width: 100%; }
    .num, .bool { color: #1d4ed8; }
    .null { color: var(--muted); font-style: italic; }
    em { color: var(--muted); font-style: normal; font-size: .85rem; }
    ol.scalars { margin: 4px 0 8px 1.2em; }
  </style>
</head>
<body>
  <header>
    <h1>ThematicExploration</h1>
    <p>Pipeline tree from the first step to the last. Open a saved JSON run, or ask a question.</p>
    <form class="bar" id="run-form">
      <input type="text" name="query" id="query" placeholder="How did a marriage look like in the 1800s compared to now?" required/>
      <input type="password" name="token" id="token" placeholder="Bearer token (auto if empty)" autocomplete="off"/>
      <select id="decompose_mode" title="decompose_mode">
        <option value="few-shot">few-shot</option>
        <option value="predict">predict</option>
        <option value="cot">cot</option>
      </select>
      <button type="submit">Run</button>
      <label class="file">Open JSON<input type="file" id="file" accept=".json,application/json"/></label>
    </form>
  </header>
  <main>
    __ERROR__
    <div id="view">__TREE__</div>
  </main>
  <script>
    const EMBEDDED = __EMBEDDED__;
    const OVERVIEW = ["service","query_id","question","status","last_step","failed_step","error","decompose_mode","concept","comparison_type","clarification","constraint_errors","slices"];
    const ENDING = ["synthesized_answer","nlg_evaluation","grounded_citations"];
    const CORPUS = {
      "07382b91-5bc5-42f9-8391-33adc2460c19": "EncycNet",
      "d84d1a2e-127d-4393-91d0-afb7e4fd9c68": "19th C. Knowledge Project (Britannica)",
      "d5c34990-9acf-4349-91d4-924f58565922": "Encyclopédie (Diderot)",
      "1f6fba0c-9aea-4345-b5a3-457c924f9e0c": "Wikipedia"
    };
    const TEXT_LIMIT = 600;
    const OPEN_STEP_KEYS = new Set([
      "decomposed_questions","generated_subquestions","retrieved_passages","search_queries",
      "slices","expansion","answer","citations","nlg_evaluation","route","error"
    ]);

    function truncate(text, limit) {
      const value = String(text || "");
      return value.length <= limit ? value : value.slice(0, limit) + "…";
    }

    function sliceLabels(slices) {
      const labels = {};
      for (const item of slices || []) {
        if (!item || typeof item !== "object") continue;
        const id = String(item.slice_id || "");
        const label = String(item.label || id);
        const corpus = CORPUS[item.corpus_id] || item.corpus_id || "";
        labels[id] = corpus ? (label + " · " + corpus) : label;
      }
      return labels;
    }

    function enrichPassages(passages, labels) {
      const enriched = {};
      for (const [sliceId, items] of Object.entries(passages || {})) {
        const heading = labels[sliceId] || sliceId;
        enriched[heading] = (items || []).map((item, index) => ({
          rank: index + 1,
          corpus: CORPUS[item.dataset_id] || item.dataset_id || "",
          dataset_id: item.dataset_id,
          doc_id: item.doc_id,
          similarity: item.similarity,
          text: truncate(item.text || item.text_snippet, TEXT_LIMIT)
        }));
      }
      return enriched;
    }

    function enrichStep(step, labels) {
      const output = (step && step.output && typeof step.output === "object") ? step.output : {};
      const name = String((step && step.name) || "");
      const display = {
        step: step.step,
        name: step.name,
        title: step.title,
        outcome: step.outcome,
        summary: step.summary
      };
      if (name === "route") display.route = output.route || output;
      if (name === "disambiguate") {
        display.slices = output.slices;
        display.comparison_type = output.comparison_type;
        display.disambiguation_source = output.disambiguation_source;
        if (output.clarification) display.clarification = output.clarification;
      }
      if (name === "extend_knowledge") display.expansion = output.expansion;
      if (name === "generate_subquestions") display.generated_subquestions = output.generated_subquestions;
      if (name === "decompose") {
        display.decomposed_questions = output.qdmr;
        display.decompose_mode = output.decompose_mode;
      }
      if (name === "retrieve_slices") {
        display.search_queries = output.search_queries;
        display.retrieved_passages = enrichPassages(output.passages, labels);
        if (output.retrieval_errors && Object.keys(output.retrieval_errors).length) {
          display.retrieval_errors = output.retrieval_errors;
        }
      }
      if (name === "compute_features") {
        const compact = {};
        for (const [sliceId, block] of Object.entries(output.feature_metrics || {})) {
          const ca = (block && block.corpus_analysis) || {};
          compact[labels[sliceId] || sliceId] = {
            passage_count: block && block.passage_count,
            corpus_analysis_hits: ca.hit_count,
            corpus_analysis_error: ca.error,
            corpus_analysis_source: ca.source
          };
        }
        display.feature_metrics = compact;
      }
      if (name === "synthesize") {
        display.answer = output.synthesized_answer;
        display.citations = (output.grounded_citations || []).map(item => ({
          citation_id: item.citation_id,
          slice: labels[item.slice_id] || item.slice_label,
          corpus: item.corpus_name || CORPUS[item.dataset_id] || item.dataset_id,
          similarity: item.similarity,
          used_in_answer: item.used_in_answer,
          text: truncate(item.text_snippet || item.text, 360)
        }));
      }
      if (name === "evaluate_answer") display.nlg_evaluation = output.nlg_evaluation;
      if (name === "export_benchmark") {
        const record = output.benchmark || {};
        display.benchmark = {
          query_id: record.query_id,
          question: record.question,
          concept: record.concept
        };
      }
      if ((step.outcome === "timeout" || step.outcome === "failed") && output.error) {
        display.error = output.error;
        display.completed_steps = output.completed_steps;
      }
      return display;
    }

    function presentationTree(payload) {
      if (!payload || typeof payload !== "object" || Array.isArray(payload) || !Array.isArray(payload.pipeline)) {
        return payload;
      }
      const labels = sliceLabels(payload.slices);
      const ordered = {};
      for (const key of OVERVIEW) {
        const value = payload[key];
        if (value !== null && value !== undefined && value !== "" && !(Array.isArray(value) && value.length === 0)) {
          ordered[key] = value;
        }
      }
      ordered.pipeline = payload.pipeline.map(step => enrichStep(step, labels));
      for (const key of ENDING) {
        const value = payload[key];
        if (value !== null && value !== undefined && value !== "" && !(Array.isArray(value) && value.length === 0)) {
          ordered[key] = value;
        }
      }
      return ordered;
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    function leaf(value) {
      if (value === null) return '<span class="null">null</span>';
      if (typeof value === "boolean") return '<span class="bool">' + value + '</span>';
      if (typeof value === "number") return '<span class="num">' + escapeHtml(value) + '</span>';
      const text = String(value);
      const klass = text.length > 80 || text.includes("\\n") ? "str long" : "str";
      return '<span class="' + klass + '">' + escapeHtml(text) + '</span>';
    }

    function label(key, value) {
      if (value && typeof value === "object" && !Array.isArray(value)) {
        const n = Object.keys(value).length;
        return escapeHtml(key) + " <em>" + (n ? "{ " + n + " }" : "empty") + "</em>";
      }
      if (Array.isArray(value)) {
        const n = value.length;
        return escapeHtml(key) + " <em>" + (n ? "[ " + n + " ]" : "empty") + "</em>";
      }
      return escapeHtml(key);
    }

    function nodeHtml(key, value, openNode) {
      const opened = openNode ? " open" : "";
      if (value === null || typeof value !== "object") {
        return '<div class="leaf"><span class="key">' + escapeHtml(key) + '</span><span class="colon">:</span> ' + leaf(value) + '</div>';
      }
      if (Array.isArray(value)) {
        const primitive = value.length && value.every(item => item === null || typeof item !== "object");
        if (primitive) {
          const items = value.map(item => "<li>" + leaf(item) + "</li>").join("");
          return "<details" + opened + "><summary>" + label(key, value) + "</summary><ol class=\\"scalars\\">" + items + "</ol></details>";
        }
        const isPipeline = value.length && value[0] && value[0].name && value[0].title;
        const children = value.map((item, index) => nodeHtml(String(index + 1), item, !!isPipeline)).join("");
        return "<details" + opened + "><summary>" + label(key, value) + "</summary><div class=\\"kids\\">" + children + "</div></details>";
      }
      if (/^\\d+$/.test(key) && value.name && value.title) {
        const outcome = escapeHtml(value.outcome || "");
        const title = escapeHtml(value.title || value.name || key);
        const name = escapeHtml(value.name || "");
        let summary = '<span class="badge">' + escapeHtml(key) + "</span> " + title + " <code>" + name + "</code> <span class=\\"outcome " + outcome + "\\">" + outcome + "</span>";
        if (value.summary) summary += '<span class="hint">' + escapeHtml(value.summary) + "</span>";
        const skip = new Set(["step", "name", "title", "outcome", "summary"]);
        const children = Object.keys(value)
          .filter(child => !skip.has(child))
          .map(child => nodeHtml(child, value[child], OPEN_STEP_KEYS.has(child)))
          .join("");
        return "<details" + opened + ' class="step ' + outcome + '"><summary>' + summary + "</summary><div class=\\"kids\\">" + children + "</div></details>";
      }
      const children = Object.keys(value).map(child => nodeHtml(child, value[child], false)).join("");
      return "<details" + opened + "><summary>" + label(key, value) + "</summary><div class=\\"kids\\">" + children + "</div></details>";
    }

    function renderPayload(payload) {
      const ordered = presentationTree(payload);
      const view = document.getElementById("view");
      if (!ordered || typeof ordered !== "object") {
        view.innerHTML = "<p class=\\"empty\\">Nothing to show.</p>";
        return;
      }
      const openKeys = new Set(["pipeline", "question", "status", "synthesized_answer", "slices"]);
      view.innerHTML = '<div class="tree">' + Object.keys(ordered).map(key => nodeHtml(key, ordered[key], openKeys.has(key))).join("") + "</div>";
    }
    window.renderPayload = renderPayload;

    document.getElementById("file").addEventListener("change", async (event) => {
      const file = event.target.files && event.target.files[0];
      if (!file) return;
      renderPayload(JSON.parse(await file.text()));
    });

    const TOKEN_ENDPOINTS = [
      "tree/token",
      "/language-pilot/tree/token",
      "https://datagems-dev.scayle.es/language-pilot/tree/token"
    ];

    async function fetchDefaultToken() {
      let lastError = "token endpoint unavailable";
      for (const url of TOKEN_ENDPOINTS) {
        try {
          const response = await fetch(url, { headers: { Accept: "application/json" } });
          if (!response.ok) {
            lastError = "HTTP " + response.status + " from " + url;
            continue;
          }
          const payload = await response.json();
          const token = payload && payload.access_token;
          if (token) return String(token);
          lastError = "no access_token in response from " + url;
        } catch (error) {
          lastError = String(error && error.message ? error.message : error);
        }
      }
      throw new Error(lastError);
    }

    async function ensureAccessToken() {
      const field = document.getElementById("token");
      const typed = field.value.trim();
      if (typed) {
        sessionStorage.setItem("dg_access_token", typed);
        return typed;
      }
      const saved = sessionStorage.getItem("dg_access_token") || "";
      if (saved) {
        field.value = saved;
        return saved;
      }
      const token = await fetchDefaultToken();
      field.value = token;
      sessionStorage.setItem("dg_access_token", token);
      return token;
    }

    document.getElementById("run-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const view = document.getElementById("view");
      view.innerHTML = "<p class=\\"empty\\">Running pipeline…</p>";
      let token = "";
      try {
        token = await ensureAccessToken();
      } catch (error) {
        view.innerHTML = '<p class="error">Could not get a default Bearer token. Paste one manually. ' +
          escapeHtml(String(error && error.message ? error.message : error)) + "</p>";
        return;
      }
      const headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + token,
      };
      const response = await fetch("ThematicExploration", {
        method: "POST",
        headers,
        body: JSON.stringify({
          query: document.getElementById("query").value,
          decompose_mode: document.getElementById("decompose_mode").value,
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        if (response.status === 401) sessionStorage.removeItem("dg_access_token");
        view.innerHTML = '<p class="error">' + escapeHtml(JSON.stringify(payload)) + '</p>';
        return;
      }
      renderPayload(payload);
    });

    if (EMBEDDED) renderPayload(EMBEDDED);
    ensureAccessToken().catch(() => {
      /* leave the field empty; Run will surface the error */
    });
  </script>
</body>
</html>
"""
