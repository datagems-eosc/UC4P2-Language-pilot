"""HTML tree view of a ThematicExploration JSON payload, pipeline first → last."""

from __future__ import annotations

import html
import json
import re
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
    "use_extension_questions",
    "llm_model",
    "judge_llm_model",
    "concept",
    "comparison_type",
    "clarification",
    "constraint_errors",
    "slices",
    "memory",
)

_END_KEYS = ("synthesized_answer", "grounded_citations")

_TEXT_LIMIT = 600
_REF = re.compile(r"\[(ref_\d+)\]")
_TONES = 6


def _tone(citation_id: str) -> str:
    digits = "".join(char for char in str(citation_id or "") if char.isdigit())
    number = int(digits) if digits else 1
    return f"t{((number - 1) % _TONES) + 1}"


def _normalize_citation(item: dict[str, Any], slice_labels: dict[str, str] | None = None) -> dict[str, Any]:
    labels = slice_labels or {}
    dataset_id = str(item.get("dataset_id") or "")
    return {
        "citation_id": item.get("citation_id"),
        "slice": labels.get(str(item.get("slice_id") or ""), item.get("slice_label") or item.get("slice")),
        "corpus": item.get("corpus_name")
        or item.get("corpus")
        or corpus_name_for_id(dataset_id)
        or dataset_id,
        "similarity": item.get("similarity"),
        "used_in_answer": item.get("used_in_answer", True),
        "text": _truncate(item.get("text_snippet") or item.get("text"), 360),
        "source_document": item.get("source_document") or item.get("doc_id"),
    }


def _link_refs(text: str, known: set[str]) -> str:
    parts: list[str] = []
    cursor = 0
    for match in _REF.finditer(text):
        parts.append(html.escape(text[cursor : match.start()]))
        citation_id = match.group(1)
        missing = " missing" if known and citation_id not in known else ""
        parts.append(
            f'<a class="ref {_tone(citation_id)}{missing}" href="#cite-{html.escape(citation_id)}" '
            f'data-ref="{html.escape(citation_id)}">{html.escape(match.group(0))}</a>'
        )
        cursor = match.end()
    parts.append(html.escape(text[cursor:]))
    return "".join(parts)


def _answer_block(key: str, text: str, citations: list[Any] | None = None) -> str:
    known = {
        str(item.get("citation_id"))
        for item in (citations or [])
        if isinstance(item, dict) and item.get("citation_id")
    }
    return (
        f'<div class="answer-block"><span class="key">{html.escape(key)}</span>'
        f'<div class="answer">{_link_refs(text, known)}</div></div>'
    )


def _citation_card(item: dict[str, Any], *, anchor: bool = True) -> str:
    citation_id = str(item.get("citation_id") or "")
    used = item.get("used_in_answer", True)
    unused = "" if used else " unused"
    meta = " · ".join(
        str(part)
        for part in (item.get("corpus"), item.get("slice"), item.get("source_document"))
        if part
    )
    similarity = item.get("similarity")
    if similarity not in (None, ""):
        meta = f"{meta} · sim {similarity}" if meta else f"sim {similarity}"
    meta_html = f'<span class="cite-meta">{html.escape(meta)}</span>' if meta else ""
    identity = f' id="cite-{html.escape(citation_id)}"' if anchor and citation_id else ""
    flag = "" if used else '<span class="cite-flag">not cited in the answer</span>'
    return (
        f'<article class="cite {_tone(citation_id)}{unused}"{identity} '
        f'data-ref="{html.escape(citation_id)}">'
        f'<header><span class="ref-chip {_tone(citation_id)}">{html.escape(citation_id or "citation")}</span>'
        f"{flag}{meta_html}</header>"
        f'<p>{html.escape(str(item.get("text") or ""))}</p></article>'
    )


def _ref_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    citation_id = str(item.get("citation_id") or "")
    digits = "".join(char for char in citation_id if char.isdigit())
    return (int(digits) if digits else 10**9, citation_id)


def _prepare_citations(citations: list[Any]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for item in citations:
        if not isinstance(item, dict):
            continue
        prepared.append(item if "text" in item else _normalize_citation(item))
    prepared.sort(key=_ref_sort_key)
    return prepared


def _citations_block(
    key: str,
    citations: list[Any],
    *,
    open_node: bool = True,
    anchors: bool = True,
) -> str:
    prepared = _prepare_citations(citations)
    used = sum(1 for item in prepared if item.get("used_in_answer", True))
    unused = len(prepared) - used
    cards = "".join(_citation_card(item, anchor=anchors) for item in prepared)
    opened = " open" if open_node else ""
    title = (
        f"{html.escape(key)} <em>[ {used} cited · {unused} not cited · shown as ref_1… ]</em>"
        if unused
        else _label(key, prepared)
    )
    return (
        f"<details{opened} class=\"cites\"><summary>{title}</summary>"
        f'<div class="cite-list">{cards}</div></details>'
    )


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
        "duration_s": step.get("duration_s"),
        "duration_ms": step.get("duration_ms"),
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
        display["citations"] = [
            _normalize_citation(item, slice_labels)
            for item in output.get("grounded_citations") or []
            if isinstance(item, dict)
        ]
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
            if key == "grounded_citations" and isinstance(value, list):
                ordered[key] = [
                    _normalize_citation(item, slice_labels)
                    for item in value
                    if isinstance(item, dict)
                ]
            else:
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


def _node_html(key: str, value: Any, *, open_node: bool = False, citations: list[Any] | None = None) -> str:
    opened = " open" if open_node else ""
    if key in {"synthesized_answer", "answer"} and isinstance(value, str):
        return _answer_block(key, value, citations)
    if key in {"grounded_citations", "citations"} and isinstance(value, list):
        return _citations_block(key, value, open_node=True, anchors=key == "grounded_citations")
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
            _node_html(str(index), item, open_node=is_pipeline, citations=citations)
            for index, item in enumerate(value, start=1)
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
        if value.get("duration_s") is not None:
            summary += f'<span class="hint">{html.escape(str(value["duration_s"]))}s</span>'
        if value.get("summary"):
            summary += f'<span class="hint">{html.escape(str(value["summary"]))}</span>'
        skip = {"step", "name", "title", "outcome", "summary", "duration_s", "duration_ms"}
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
        step_citations = value.get("citations") if isinstance(value.get("citations"), list) else citations
        children = "".join(
            _node_html(child, value[child], open_node=child in open_children, citations=step_citations)
            for child in value
            if child not in skip
        )
        return (
            f"<details{opened} class=\"step {outcome}\"><summary>{summary}</summary>"
            f'<div class="kids">{children}</div></details>'
        )
    children = "".join(_node_html(child, value[child], citations=citations) for child in value)
    return (
        f"<details{opened}><summary>{_label(key, value)}</summary>"
        f'<div class="kids">{children}</div></details>'
    )


def tree_markup(payload: Any) -> str:
    ordered = presentation_tree(payload)
    if not isinstance(ordered, dict):
        return f'<div class="tree">{_leaf(ordered)}</div>'
    citations = ordered.get("grounded_citations") if isinstance(ordered.get("grounded_citations"), list) else []
    open_keys = {"pipeline", "question", "status", "synthesized_answer", "slices", "grounded_citations"}
    parts = [
        _node_html(key, value, open_node=key in open_keys, citations=citations)
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
    return HTMLResponse(
        tree_page(payload, error=error),
        status_code=status_code,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )


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
      position: sticky; top: 0; z-index: 4;
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
    .shell { display: flex; align-items: stretch; min-height: calc(100vh - 120px); }
    aside.drawer {
      flex: 0 0 320px; width: 320px; background: var(--card);
      border-right: 1px solid var(--line); display: flex; flex-direction: column;
      max-height: calc(100vh - 120px); position: sticky; top: 0;
    }
    aside.drawer.closed { display: none; }
    .drawer-head { padding: 12px 12px 8px; border-bottom: 1px solid var(--line); }
    .drawer-head h2 { margin: 0 0 8px; font-size: .95rem; }
    .drawer-head input {
      width: 100%; padding: 8px 10px; border: 1px solid var(--line);
      border-radius: 6px; font: inherit;
    }
    .drawer-list { overflow: auto; padding: 8px 8px 24px; }
    .drawer-concept { margin: 10px 4px 4px; font-size: .75rem; font-weight: 700;
      text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
    .drawer-q {
      display: block; width: 100%; text-align: left; border: 0; background: transparent;
      padding: 8px 8px; border-radius: 6px; cursor: pointer; font: inherit; color: inherit;
    }
    .drawer-q:hover, .drawer-q.selected { background: #eff6ff; }
    .drawer-q .qid { display: inline-block; min-width: 1.6em; margin-right: 6px;
      background: var(--accent); color: #fff; border-radius: 4px; font-size: .7rem;
      padding: 1px 5px; text-align: center; vertical-align: top; }
    .drawer-q.child { padding-left: 18px; }
    .drawer-q.child .qid { background: #64748b; }
    .drawer-q .qtext { font-size: .9rem; }
    .drawer-q.child .qtext { font-size: .85rem; color: #334155; }
    .drawer-empty { padding: 12px; color: var(--muted); }
    main { flex: 1; min-width: 0; max-width: 1100px; margin: 0 auto; padding: 18px 16px 64px; }
    @media (max-width: 840px) {
      aside.drawer {
        position: fixed; z-index: 3; left: 0; top: 0; bottom: 0; max-height: none;
        box-shadow: 8px 0 24px rgba(0,0,0,.18);
      }
    }
    .empty, .error, .progress { padding: 16px; background: var(--card); border: 1px solid var(--line); border-radius: 8px; }
    .error { color: var(--fail); }
    .progress { background: #eff6ff; border-color: #bfdbfe; color: var(--accent); margin-bottom: 12px; }
    .progress.done { background: var(--ok-bg); border-color: #bbf7d0; color: var(--ok); }
    .progress.fail { background: #fee2e2; border-color: #fecaca; color: var(--fail); }
    .result-tabs {
      display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
      margin: 0 0 12px; padding-bottom: 10px; border-bottom: 1px solid var(--line);
    }
    .result-tabs .tab {
      background: transparent; border: 1px solid var(--line); color: var(--muted);
      border-radius: 6px; padding: 6px 12px; cursor: pointer; font: inherit; font-weight: 600;
    }
    .result-tabs .tab.active { background: var(--accent); color: #fff; border-color: var(--accent); }
    .result-tabs .tab:disabled { opacity: .45; cursor: not-allowed; }
    .result-tabs .download {
      margin-left: auto; background: var(--card); border: 1px solid var(--line);
      border-radius: 6px; padding: 6px 12px; cursor: pointer; font: inherit; font-weight: 600;
      color: var(--accent);
    }
    .result-tabs .download:disabled { opacity: .45; cursor: not-allowed; }
    .tab-panel[hidden] { display: none !important; }
    .eval-card {
      background: var(--card); border: 1px solid var(--line); border-radius: 8px;
      padding: 14px 16px; margin: 0 0 12px;
    }
    .eval-card h3 { margin: 0 0 8px; font-size: 1rem; }
    .eval-meta { display: flex; flex-wrap: wrap; gap: 8px 14px; margin: 0 0 10px; font-size: .9rem; color: var(--muted); }
    .eval-meta strong { color: var(--ink); font-weight: 650; }
    .eval-gt { white-space: pre-wrap; background: #f8fafc; border-radius: 6px; padding: 10px 12px; margin: 8px 0; }
    .eval-pair { display: grid; gap: 10px; margin: 8px 0 14px; }
    @media (min-width: 900px) { .eval-pair { grid-template-columns: 1fr 1fr; } }
    .eval-pair h4 { margin: 0 0 6px; font-size: .85rem; color: var(--muted); font-weight: 650; }
    .eval-measure {
      border: 1px solid var(--line); border-radius: 8px; background: var(--card);
      margin: 0 0 10px; overflow: hidden;
    }
    .eval-measure > summary {
      list-style: none; cursor: pointer; display: flex; flex-wrap: wrap; gap: 8px 14px;
      align-items: baseline; padding: 10px 12px; background: #f8fafc;
    }
    .eval-measure > summary::-webkit-details-marker { display: none; }
    .eval-measure-name { font-weight: 700; color: var(--ink); }
    .eval-measure-family {
      font-size: .72rem; text-transform: uppercase; letter-spacing: .04em;
      color: var(--muted); font-weight: 700;
    }
    .eval-measure-value {
      margin-left: auto; font-variant-numeric: tabular-nums; font-weight: 750;
      color: #1d4ed8; font-size: 1.05rem;
    }
    .eval-measure-body { padding: 10px 12px 12px; border-top: 1px solid var(--line); }
    .eval-desc { margin: 0 0 8px; color: var(--muted); font-size: .88rem; }
    .eval-formula {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .82rem;
      color: #334155; background: #f1f5f9; border-radius: 6px; padding: 8px 10px; margin: 0 0 10px;
      white-space: pre-wrap; word-break: break-word;
    }
    .eval-elements-table { width: 100%; border-collapse: collapse; font-size: .85rem; }
    .eval-elements-table th, .eval-elements-table td {
      text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); vertical-align: top;
    }
    .eval-elements-table th { color: var(--muted); font-weight: 650; width: 32%; }
    .eval-elements-table td { white-space: pre-wrap; word-break: break-word; font-variant-numeric: tabular-nums; }
    .eval-obs-title { margin: 12px 0 6px; font-size: .9rem; font-weight: 650; }
    .eval-metrics { width: 100%; border-collapse: collapse; font-size: .9rem; }
    .eval-metrics th, .eval-metrics td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }
    .eval-metrics th { color: var(--muted); font-weight: 600; }
    .eval-metrics td.num { font-variant-numeric: tabular-nums; color: #1d4ed8; }
    .answer-block {
      background: var(--card); border: 1px solid var(--line); border-radius: 8px;
      padding: 12px 14px; margin: 10px 0;
    }
    .answer-block .key { display: block; margin-bottom: 6px; color: var(--muted); font-size: .85rem; }
    .answer { white-space: pre-wrap; }
    a.ref, .ref-chip {
      display: inline; border-radius: 4px; padding: 0 5px; font-weight: 700;
      text-decoration: none; font-size: .85em; cursor: pointer;
    }
    a.ref.missing { background: #fee2e2; color: #991b1b; }
    .t1, .t1 .ref-chip { background: #fef3c7; color: #92400e; }
    .t2, .t2 .ref-chip { background: #dbeafe; color: #1e3a8a; }
    .t3, .t3 .ref-chip { background: #dcfce7; color: #166534; }
    .t4, .t4 .ref-chip { background: #fce7f3; color: #9d174d; }
    .t5, .t5 .ref-chip { background: #e0e7ff; color: #3730a3; }
    .t6, .t6 .ref-chip { background: #ffedd5; color: #9a3412; }
    .cite-list { display: grid; gap: 8px; margin: 8px 0 12px; }
    .cite {
      border: 1px solid var(--line); border-left-width: 4px; border-radius: 8px;
      padding: 10px 12px; background: var(--card);
    }
    .cite.t1 { border-left-color: #d97706; }
    .cite.t2 { border-left-color: #2563eb; }
    .cite.t3 { border-left-color: #16a34a; }
    .cite.t4 { border-left-color: #db2777; }
    .cite.t5 { border-left-color: #4f46e5; }
    .cite.t6 { border-left-color: #ea580c; }
    .cite header { display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline; margin-bottom: 4px; }
    .cite-meta { color: var(--muted); font-size: .85rem; }
    .cite p { margin: 0; white-space: pre-wrap; }
    .cite.unused { opacity: .7; }
    .cite-flag { color: var(--muted); font-size: .78rem; font-weight: 650; }
    .cite.lit, a.ref.lit, .cite.hover, a.ref.hover, .cite:target { box-shadow: 0 0 0 2px currentColor; }
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
    <p>Pipeline tree from the first step to the last. Run mints a Bearer token, then streams each step.</p>
    <form class="bar" id="run-form">
      <button type="button" id="toggle-drawer" title="Benchmark questions">Questions</button>
      <input type="text" name="query" id="query" placeholder="How did a marriage look like in the 1800s compared to now?" required/>
      <input type="hidden" name="query_id" id="query_id" value=""/>
      <select id="decompose_mode" title="decompose_mode">
        <option value="few-shot">few-shot</option>
        <option value="predict">predict</option>
        <option value="cot">cot</option>
      </select>
      <select id="llm_model" title="Pipeline Scayle LLM (llm_model)">
        <option value="qwen3">pipeline: qwen3</option>
      </select>
      <select id="judge_llm_model" title="Judge Scayle LLM (judge_llm_model)">
        <option value="glm-5.3-flash">judge: glm-5.3-flash</option>
      </select>
      <label class="file" title="Decompose, retrieve, and answer from every knowledge-extension question">
        <input type="checkbox" id="use_extension_questions" style="display:inline;margin-right:6px"/>KE questions
      </label>
      <label class="file" title="Re-run the pipeline even if this question is already stored">
        <input type="checkbox" id="refresh" style="display:inline;margin-right:6px"/>Refresh
      </label>
      <button type="submit">Run</button>
      <label class="file">Open JSON<input type="file" id="file" accept=".json,application/json"/></label>
    </form>
  </header>
  <div class="shell">
    <aside class="drawer" id="drawer">
      <div class="drawer-head">
        <h2>Benchmark questions</h2>
        <input type="search" id="question-filter" placeholder="Filter by id, concept, or text" autocomplete="off"/>
      </div>
      <div class="drawer-list" id="question-list"><p class="drawer-empty">Loading questions…</p></div>
    </aside>
    <main>
      __ERROR__
      <p id="progress" class="progress" hidden></p>
      <div class="result-tabs" id="result-tabs" role="tablist">
        <button type="button" class="tab active" data-tab="pipeline" role="tab" aria-selected="true">Pipeline</button>
        <button type="button" class="tab" data-tab="evaluation" id="tab-evaluation" role="tab" aria-selected="false" disabled>Evaluation</button>
        <button type="button" class="download" id="download-eval" disabled title="Download StudentQuiz-compatible evaluation JSON">Download evaluation</button>
        <button type="button" class="download" id="download-run" disabled title="Download full ThematicExploration JSON">Download full run</button>
      </div>
      <div id="panel-pipeline" class="tab-panel" role="tabpanel">
        <div id="view">__TREE__</div>
      </div>
      <div id="panel-evaluation" class="tab-panel" role="tabpanel" hidden>
        <div id="eval-view"><p class="empty">Evaluation appears here after the evaluate step finishes.</p></div>
      </div>
    </main>
  </div>
  <script>
    const EMBEDDED = __EMBEDDED__;
    let latestPayload = null;
    const OVERVIEW = ["service","run_id","job_id","started_at","finished_at","execution","query_id","question","status","last_step","failed_step","error","memory","decompose_mode","use_extension_questions","llm_model","judge_llm_model","execution_time_s","evaluation_time_s","step_timings","concept","comparison_type","clarification","constraint_errors","slices"];
    const ENDING = ["synthesized_answer","grounded_citations"];
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

    function tone(citationId) {
      const digits = String(citationId || "").replace(/\\D/g, "");
      const number = parseInt(digits || "1", 10);
      return "t" + ((((number - 1) % 6) + 6) % 6 + 1);
    }

    function normalizeCitation(item, labels) {
      labels = labels || {};
      return {
        citation_id: item.citation_id,
        slice: labels[item.slice_id] || item.slice_label || item.slice,
        corpus: item.corpus_name || item.corpus || CORPUS[item.dataset_id] || item.dataset_id || "",
        similarity: item.similarity,
        used_in_answer: item.used_in_answer !== false,
        text: truncate(item.text_snippet || item.text, 360),
        source_document: item.source_document || item.doc_id
      };
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
        display.citations = (output.grounded_citations || []).map(item => normalizeCitation(item, labels));
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
          ordered[key] = (key === "grounded_citations" && Array.isArray(value))
            ? value.filter(item => item && typeof item === "object").map(item => normalizeCitation(item, labels))
            : value;
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

    function linkRefs(text, known) {
      const source = String(text || "");
      const pattern = /\\[(ref_\\d+)\\]/g;
      let out = "";
      let cursor = 0;
      let match;
      while ((match = pattern.exec(source))) {
        out += escapeHtml(source.slice(cursor, match.index));
        const citationId = match[1];
        const missing = known && known.size && !known.has(citationId) ? " missing" : "";
        out += '<a class="ref ' + tone(citationId) + missing + '" href="#cite-' + escapeHtml(citationId) +
          '" data-ref="' + escapeHtml(citationId) + '">' + escapeHtml(match[0]) + "</a>";
        cursor = match.index + match[0].length;
      }
      return out + escapeHtml(source.slice(cursor));
    }

    function answerBlock(key, text, citations) {
      const known = new Set((citations || []).map(item => item && item.citation_id).filter(Boolean));
      return '<div class="answer-block"><span class="key">' + escapeHtml(key) +
        '</span><div class="answer">' + linkRefs(text, known) + "</div></div>";
    }

    function citationCard(item, anchors) {
      const citationId = String((item && item.citation_id) || "");
      const unused = item && item.used_in_answer === false ? " unused" : "";
      const bits = [item.corpus, item.slice, item.source_document].filter(Boolean);
      if (item.similarity !== null && item.similarity !== undefined && item.similarity !== "") {
        bits.push("sim " + item.similarity);
      }
      const meta = bits.join(" · ");
      const identity = anchors && citationId ? ' id="cite-' + escapeHtml(citationId) + '"' : "";
      const flag = unused ? '<span class="cite-flag">not cited in the answer</span>' : "";
      return '<article class="cite ' + tone(citationId) + unused + '"' + identity +
        ' data-ref="' + escapeHtml(citationId) + '"><header><span class="ref-chip ' + tone(citationId) + '">' +
        escapeHtml(citationId || "citation") + "</span>" + flag +
        (meta ? '<span class="cite-meta">' + escapeHtml(meta) + "</span>" : "") +
        "</header><p>" + escapeHtml((item && item.text) || "") + "</p></article>";
    }

    function refSortKey(item) {
      const citationId = String((item && item.citation_id) || "");
      const digits = citationId.replace(/\\D/g, "");
      return [digits ? parseInt(digits, 10) : 1e9, citationId];
    }

    function citationsBlock(key, items, anchors) {
      const prepared = (items || []).map(item => item && item.text !== undefined ? item : normalizeCitation(item || {}));
      prepared.sort((left, right) => {
        const a = refSortKey(left);
        const b = refSortKey(right);
        return a[0] - b[0] || String(a[1]).localeCompare(String(b[1]));
      });
      const used = prepared.filter(item => item.used_in_answer !== false).length;
      const unused = prepared.length - used;
      const cards = prepared.map(item => citationCard(item, !!anchors)).join("");
      let title = label(key, prepared);
      if (unused) {
        title = escapeHtml(key) + " <em>[ " + used + " cited · " + unused + " not cited · shown as ref_1… ]</em>";
      }
      return '<details open class="cites"><summary>' + title +
        '</summary><div class="cite-list">' + cards + "</div></details>";
    }

    function nodeHtml(key, value, openNode, citations) {
      const opened = openNode ? " open" : "";
      if ((key === "synthesized_answer" || key === "answer") && typeof value === "string") {
        return answerBlock(key, value, citations);
      }
      if ((key === "grounded_citations" || key === "citations") && Array.isArray(value)) {
        return citationsBlock(key, value, key === "grounded_citations");
      }
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
        const children = value.map((item, index) => nodeHtml(String(index + 1), item, !!isPipeline, citations)).join("");
        return "<details" + opened + "><summary>" + label(key, value) + "</summary><div class=\\"kids\\">" + children + "</div></details>";
      }
      if (/^\\d+$/.test(key) && value.name && value.title) {
        const outcome = escapeHtml(value.outcome || "");
        const title = escapeHtml(value.title || value.name || key);
        const name = escapeHtml(value.name || "");
        let summary = '<span class="badge">' + escapeHtml(key) + "</span> " + title + " <code>" + name + "</code> <span class=\\"outcome " + outcome + "\\">" + outcome + "</span>";
        if (value.duration_s !== null && value.duration_s !== undefined) {
          summary += '<span class="hint">' + escapeHtml(value.duration_s) + "s</span>";
        }
        if (value.summary) summary += '<span class="hint">' + escapeHtml(value.summary) + "</span>";
        const skip = new Set(["step", "name", "title", "outcome", "summary", "duration_s", "duration_ms"]);
        const stepCitations = Array.isArray(value.citations) ? value.citations : citations;
        const children = Object.keys(value)
          .filter(child => !skip.has(child))
          .map(child => nodeHtml(child, value[child], OPEN_STEP_KEYS.has(child), stepCitations))
          .join("");
        return "<details" + opened + ' class="step ' + outcome + '"><summary>' + summary + "</summary><div class=\\"kids\\">" + children + "</div></details>";
      }
      const children = Object.keys(value).map(child => nodeHtml(child, value[child], false, citations)).join("");
      return "<details" + opened + "><summary>" + label(key, value) + "</summary><div class=\\"kids\\">" + children + "</div></details>";
    }

    function downloadJson(filename, data) {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    }

    function evaluationBundle(payload) {
      const nlg = payload && payload.nlg_evaluation;
      if (!nlg || typeof nlg !== "object") return null;
      if (nlg.evaluation_report && typeof nlg.evaluation_report === "object") {
        return nlg.evaluation_report;
      }
      return {
        schemaVersion: "1.0",
        evaluation: {
          id: "uc4p2-language-pilot",
          projectId: "uc4p2_language_pilot",
          label: "UC4P2 Language Pilot",
          provenance: {
            note: "Fallback bundle without calculation elements (older run).",
            run: {
              query_id: payload.query_id || nlg.question_id || "",
              question: payload.question || "",
              matched: !!nlg.matched,
            },
          },
        },
        measures: [],
        nlg_evaluation: nlg,
      };
    }

    function formatElementValue(value) {
      if (value === null || value === undefined) return "–";
      if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
        return String(value);
      }
      try { return JSON.stringify(value, null, 2); } catch (_) { return String(value); }
    }

    function elementsTable(elements) {
      if (!elements || !elements.length) {
        return '<p class="empty">No calculation elements for this observation.</p>';
      }
      const rows = elements.map(el => {
        const label = el.label || el.id || "element";
        const unit = el.unit ? ' <em>(' + escapeHtml(el.unit) + ")</em>" : "";
        return "<tr><th>" + escapeHtml(label) +
          (el.id ? ' <code>' + escapeHtml(el.id) + "</code>" : "") +
          "</th><td>" + escapeHtml(formatElementValue(el.value)) + unit + "</td></tr>";
      }).join("");
      return '<table class="eval-elements-table"><thead><tr><th>Element</th><th>Value for this use-case</th></tr></thead><tbody>' +
        rows + "</tbody></table>";
    }

    function observationBlock(obs, index, total) {
      const calc = (obs && obs.calculation) || {};
      const formula = calc.formula
        ? '<div class="eval-formula"><strong>Formula:</strong> ' + escapeHtml(calc.formula) + "</div>"
        : "";
      const dims = obs && obs.dimensions ? obs.dimensions : {};
      const dimBits = Object.keys(dims).map(key =>
        "<span><strong>" + escapeHtml(key) + "</strong> " + escapeHtml(dims[key]) + "</span>"
      ).join("");
      const title = total > 1
        ? '<div class="eval-obs-title">Observation ' + (index + 1) +
          (dims.operator ? " · " + escapeHtml(dims.operator) : "") +
          " → <span class=\\"num\\">" + escapeHtml(obs.value == null ? "–" : obs.value) + "</span></div>"
        : "";
      return title +
        (dimBits ? '<div class="eval-meta">' + dimBits + "</div>" : "") +
        formula +
        elementsTable(calc.elements || []);
    }

    function measureCards(report) {
      const measures = report && Array.isArray(report.measures) ? report.measures : [];
      if (!measures.length) return "<p class=\\"empty\\">No measures in evaluation report.</p>";
      return measures.map(measure => {
        const observations = Array.isArray(measure.observations) ? measure.observations : [];
        const primary = observations[0] || {};
        const value = observations.length === 1
          ? primary.value
          : (observations.length ? observations.length + " observations" : "–");
        const body = observations.length
          ? observations.map((obs, index) => observationBlock(obs, index, observations.length)).join("")
          : '<p class="empty">No observation for this use-case yet.</p>';
        const desc = measure.description
          ? '<p class="eval-desc">' + escapeHtml(measure.description) + "</p>"
          : "";
        return '<details class="eval-measure">' +
          "<summary><span class=\\"eval-measure-family\\">" + escapeHtml(measure.family || "") +
          "</span><span class=\\"eval-measure-name\\">" + escapeHtml(measure.label || measure.id) +
          "</span><span class=\\"eval-measure-value\\">" + escapeHtml(value == null ? "–" : value) +
          "</span></summary><div class=\\"eval-measure-body\\">" + desc + body +
          "</div></details>";
      }).join("");
    }

    function metricRows(metrics) {
      if (!metrics || typeof metrics !== "object") return "";
      const keys = Object.keys(metrics);
      if (!keys.length) return "<p class=\\"empty\\">No numeric metrics.</p>";
      const rows = keys.map(key => {
        const value = metrics[key];
        const cell = typeof value === "number"
          ? '<td class="num">' + escapeHtml(value) + "</td>"
          : "<td>" + escapeHtml(value) + "</td>";
        return "<tr><th>" + escapeHtml(key) + "</th>" + cell + "</tr>";
      }).join("");
      return '<table class="eval-metrics"><tbody>' + rows + "</tbody></table>";
    }

    function judgeBlock(judge) {
      if (!judge || typeof judge !== "object") return "";
      if (!judge.available) {
        return '<div class="eval-card"><h3>LLM-as-judge</h3><p class="empty">' +
          escapeHtml(judge.reason || "Not available.") + "</p></div>";
      }
      const bits = [
        ["score", judge.score],
        ["faithfulness", judge.faithfulness],
        ["coverage", judge.coverage],
        ["verdict", judge.verdict],
        ["judge_lm", judge.judge_lm],
        ["pipeline_lm", judge.pipeline_lm],
      ].filter(pair => pair[1] !== null && pair[1] !== undefined && pair[1] !== "");
      const meta = bits.map(pair => "<span><strong>" + escapeHtml(pair[0]) + "</strong> " +
        escapeHtml(pair[1]) + "</span>").join("");
      const rationale = judge.rationale
        ? '<p class="eval-gt">' + escapeHtml(judge.rationale) + "</p>"
        : "";
      return '<div class="eval-card"><h3>LLM-as-judge</h3><div class="eval-meta">' + meta +
        "</div>" + rationale + "</div>";
    }

    function renderEvaluation(payload) {
      const evalView = document.getElementById("eval-view");
      const tab = document.getElementById("tab-evaluation");
      const downloadEval = document.getElementById("download-eval");
      const downloadRun = document.getElementById("download-run");
      const bundle = evaluationBundle(payload);
      if (downloadRun) downloadRun.disabled = !(payload && typeof payload === "object");
      if (!bundle) {
        if (tab) tab.disabled = true;
        if (downloadEval) downloadEval.disabled = true;
        evalView.innerHTML = '<p class="empty">Evaluation appears here after the evaluate step finishes.</p>';
        return;
      }
      if (tab) tab.disabled = false;
      if (downloadEval) downloadEval.disabled = false;
      const nlg = (payload && payload.nlg_evaluation) || {};
      const run = (bundle.evaluation && bundle.evaluation.provenance && bundle.evaluation.provenance.run) || {};
      const matched = !!(nlg.matched || run.matched);
      const execution = (payload && payload.execution) || nlg.execution || {};
      const meta = [
        ["run_id", run.run_id || execution.run_id || payload.run_id || nlg.run_id || "–"],
        ["started_at", run.started_at || execution.started_at || payload.started_at || "–"],
        ["finished_at", run.finished_at || execution.finished_at || payload.finished_at || "–"],
        ["llm_model", run.llm_model || execution.llm_model || payload.llm_model || "–"],
        ["judge_llm_model", run.judge_llm_model || execution.judge_llm_model || payload.judge_llm_model || "–"],
        ["matched", matched ? "yes" : "no"],
        ["question_id", run.query_id || nlg.question_id || payload.query_id || "–"],
        ["match", nlg.match || "–"],
        ["gold_source", run.gold_source || nlg.gold_source || "–"],
        ["source", run.source || nlg.source || "local"],
        ["schema", bundle.schemaVersion || "1.0"],
        ["evaluation_time_s", run.evaluation_time_s ?? nlg.execution_time_s ?? payload.evaluation_time_s ?? "–"],
        ["pipeline_time_s", run.execution_time_s ?? nlg.pipeline_execution_time_s ?? payload.execution_time_s ?? "–"],
      ].map(pair => "<span><strong>" + escapeHtml(pair[0]) + "</strong> " + escapeHtml(pair[1]) + "</span>").join("");
      const gtText = (bundle.measures && bundle.measures[0] && bundle.measures[0].provenance && bundle.measures[0].provenance.ground_truth)
        || nlg.ground_truth || "";
      const answerText = (bundle.measures && bundle.measures[0] && bundle.measures[0].provenance && bundle.measures[0].provenance.synthesized_answer)
        || (payload && payload.synthesized_answer) || "";
      const pair = '<div class="eval-pair">' +
        '<div><h4>System answer (this use-case)</h4><div class="eval-gt">' +
        escapeHtml(answerText || "–") + "</div></div>" +
        "<div><h4>Ground truth</h4><div class=\\"eval-gt\\">" +
        escapeHtml(gtText || "No ground_truth matched for this question / query_id.") +
        "</div></div></div>";
      const summary = nlg.summary
        ? '<p class="eval-meta">' + escapeHtml(nlg.summary) + "</p>"
        : "";
      const metricsHtml = Array.isArray(bundle.measures) && bundle.measures.length
        ? measureCards(bundle)
        : metricRows(nlg.metrics);
      evalView.innerHTML =
        '<div class="eval-card"><h3>NLG evaluation for this use-case</h3><div class="eval-meta">' + meta +
        "</div>" + summary + pair +
        "<h3>Measures — score, formula, and element values</h3>" +
        '<p class="eval-desc">Open a measure to see exactly how the score was computed for this run ' +
        "(hypothesis tokens, reference tokens, overlaps, P/R/F1, timings, …). " +
        "<strong>Download evaluation</strong> exports the same StudentQuiz JSON with full " +
        "<code>calculation.elements</code>.</p>" +
        metricsHtml + "</div>" +
        judgeBlock(nlg.llm_judge);
      if (matched && payload && payload.status !== "running") {
        selectTab("evaluation");
      }
    }

    function selectTab(name) {
      const tabs = document.querySelectorAll(".result-tabs .tab");
      tabs.forEach(button => {
        const active = button.getAttribute("data-tab") === name;
        button.classList.toggle("active", active);
        button.setAttribute("aria-selected", active ? "true" : "false");
      });
      document.getElementById("panel-pipeline").hidden = name !== "pipeline";
      document.getElementById("panel-evaluation").hidden = name !== "evaluation";
    }

    function renderPayload(payload) {
      latestPayload = payload;
      const ordered = presentationTree(payload);
      const view = document.getElementById("view");
      if (!ordered || typeof ordered !== "object") {
        view.innerHTML = "<p class=\\"empty\\">Nothing to show.</p>";
        renderEvaluation(payload);
        return;
      }
      const citations = Array.isArray(ordered.grounded_citations) ? ordered.grounded_citations : [];
      const openKeys = new Set(["pipeline", "question", "status", "synthesized_answer", "slices", "grounded_citations"]);
      view.innerHTML = '<div class="tree">' + Object.keys(ordered).map(key => nodeHtml(key, ordered[key], openKeys.has(key), citations)).join("") + "</div>";
      renderEvaluation(payload);
    }
    window.renderPayload = renderPayload;

    document.getElementById("result-tabs").addEventListener("click", (event) => {
      const tab = event.target.closest(".tab");
      if (tab && !tab.disabled) {
        selectTab(tab.getAttribute("data-tab"));
        return;
      }
      if (event.target.id === "download-eval" && latestPayload) {
        const bundle = evaluationBundle(latestPayload);
        if (!bundle) return;
        const run = bundle.evaluation && bundle.evaluation.provenance && bundle.evaluation.provenance.run;
        const qid = String(
          (run && run.query_id) || latestPayload.query_id || "run"
        ).replace(/[^\\w.-]+/g, "_");
        const rid = String(
          (run && run.run_id) || latestPayload.run_id || "exec"
        ).replace(/[^\\w.-]+/g, "_").slice(0, 12);
        downloadJson("uc4p2-evaluation-" + qid + "-" + rid + ".json", bundle);
      }
      if (event.target.id === "download-run" && latestPayload) {
        const qid = String(latestPayload.query_id || "run").replace(/[^\\w.-]+/g, "_");
        const rid = String(latestPayload.run_id || "exec").replace(/[^\\w.-]+/g, "_").slice(0, 12);
        downloadJson("uc4p2-thematic-exploration-" + qid + "-" + rid + ".json", latestPayload);
      }
    });

    const view = document.getElementById("view");
    view.addEventListener("click", (event) => {
      const el = event.target.closest("[data-ref]");
      if (!el) return;
      const citationId = el.getAttribute("data-ref");
      if (el.tagName === "A") event.preventDefault();
      view.querySelectorAll(".lit").forEach(node => node.classList.remove("lit"));
      view.querySelectorAll('[data-ref="' + citationId + '"]').forEach(node => node.classList.add("lit"));
      const target = document.getElementById("cite-" + citationId);
      if (target) {
        const details = target.closest("details");
        if (details) details.open = true;
        target.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    });
    view.addEventListener("mouseover", (event) => {
      const el = event.target.closest("[data-ref]");
      if (!el) return;
      view.querySelectorAll('[data-ref="' + el.getAttribute("data-ref") + '"]').forEach(node => node.classList.add("hover"));
    });
    view.addEventListener("mouseout", (event) => {
      const el = event.target.closest("[data-ref]");
      if (!el) return;
      view.querySelectorAll('[data-ref="' + el.getAttribute("data-ref") + '"]').forEach(node => node.classList.remove("hover"));
    });

    document.getElementById("file").addEventListener("change", async (event) => {
      const file = event.target.files && event.target.files[0];
      if (!file) return;
      renderPayload(JSON.parse(await file.text()));
    });

    function apiUrl(suffix) {
      const base = location.pathname.replace(/\\/tree\\/?$/, "/");
      const prefix = base.endsWith("/") ? base : base + "/";
      return prefix + String(suffix || "").replace(/^\\//, "");
    }

    function absoluteUrl(suffix) {
      return new URL(apiUrl(suffix), location.href).href;
    }

    async function mintAccessToken() {
      const url = absoluteUrl("tree/token");
      let lastError = null;
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          const response = await fetch(url, {
            headers: { Accept: "application/json" },
            cache: "no-store",
            credentials: "same-origin",
          });
          if (!response.ok) {
            const payload = await response.json().catch(() => ({}));
            const detail = payload && payload.detail ? String(payload.detail) : ("HTTP " + response.status);
            throw new Error(detail + " from " + url);
          }
          const payload = await response.json();
          const token = payload && payload.access_token;
          if (!token) throw new Error("no access_token from " + url);
          return String(token);
        } catch (error) {
          lastError = error;
        }
      }
      const message = String(lastError && lastError.message ? lastError.message : lastError);
      if (/failed to fetch|networkerror|load failed/i.test(message)) {
        throw new Error(
          "The browser could not reach " + url +
          ". Hard-refresh this page, check the DataGEMS VPN, then open that URL in this same tab."
        );
      }
      throw lastError;
    }
    const STREAM_URL = apiUrl("ThematicExploration/stream");
    const FALLBACK_URL = apiUrl("ThematicExploration");

    function setProgress(text, kind) {
      const progress = document.getElementById("progress");
      if (!text) {
        progress.hidden = true;
        progress.textContent = "";
        progress.className = "progress";
        return;
      }
      progress.hidden = false;
      progress.className = "progress" + (kind ? " " + kind : "");
      progress.textContent = text;
    }

    function progressFromPayload(payload) {
      const steps = (payload && payload.pipeline) || [];
      const last = steps[steps.length - 1] || {};
      const title = last.title || last.name || "";
      if (payload && payload.status === "running") {
        setProgress("Running pipeline… " + steps.length + " step(s) done" + (title ? " — " + title : ""), "");
        return;
      }
      if (payload && payload.memory && payload.memory.hit) {
        setProgress("Done — reused stored result (memory hit).", "done");
        return;
      }
      if (payload && (payload.status === "timeout" || payload.status === "error")) {
        setProgress(payload.error || ("Stopped: " + payload.status), "fail");
        return;
      }
      setProgress("Done — " + (payload && payload.status ? payload.status : "ok") + ".", "done");
    }

    function parseSseChunk(chunk) {
      let event = "message";
      const dataLines = [];
      let commentJob = "";
      for (const raw of chunk.split("\\n")) {
        const line = raw.replace(/\\r$/, "");
        if (!line) continue;
        if (line.startsWith(":")) {
          const note = line.slice(1).trim();
          if (note.startsWith("job ")) commentJob = note.slice(4).trim();
          continue;
        }
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
      }
      if (!dataLines.length) {
        return commentJob ? { event: "job", payload: { job_id: commentJob, status: "running" } } : null;
      }
      return { event, payload: JSON.parse(dataLines.join("\\n")) };
    }

    async function readSse(response, onEvent) {
      if (!response.body || !response.body.getReader) {
        const text = await response.text();
        for (const chunk of text.split("\\n\\n")) {
          const parsed = parseSseChunk(chunk);
          if (parsed) onEvent(parsed.event, parsed.payload);
        }
        return;
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buffer.indexOf("\\n\\n")) >= 0) {
          const chunk = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          const parsed = parseSseChunk(chunk);
          if (parsed) onEvent(parsed.event, parsed.payload);
        }
      }
      if (buffer.trim()) {
        const parsed = parseSseChunk(buffer);
        if (parsed) onEvent(parsed.event, parsed.payload);
      }
    }

    async function postUrl(url, headers, body) {
      return fetch(url, { method: "POST", headers, body });
    }

    function jobIdFrom(payload, fallback) {
      return String((payload && payload.job_id) || fallback || "");
    }

    async function pollJob(accessToken, jobId) {
      setProgress("Stream dropped — still running, updating from the server…", "");
      for (let attempt = 0; attempt < 180; attempt++) {
        let token = accessToken;
        let response = await fetch(apiUrl("ThematicExploration/runs/" + jobId), {
          headers: { Accept: "application/json", Authorization: "Bearer " + token },
          cache: "no-store",
        });
        if (response.status === 401) {
          token = await mintAccessToken();
          response = await fetch(apiUrl("ThematicExploration/runs/" + jobId), {
            headers: { Accept: "application/json", Authorization: "Bearer " + token },
            cache: "no-store",
          });
          accessToken = token;
        }
        if (response.status === 404) {
          throw new Error("Run snapshot expired before the pipeline finished.");
        }
        if (!response.ok) {
          throw new Error("HTTP " + response.status + " from run snapshot");
        }
        const payload = await response.json();
        progressFromPayload(payload);
        renderPayload(payload);
        if (payload && payload.status !== "running") return payload;
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      throw new Error("Timed out waiting for the run to finish.");
    }

    async function finishWithoutStream(accessToken, requestBody) {
      setProgress("Stream dropped — finishing the pipeline…", "");
      const headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": "Bearer " + accessToken,
      };
      let response = await postUrl(FALLBACK_URL, headers, requestBody);
      if (response.status === 401) {
        accessToken = await mintAccessToken();
        headers.Authorization = "Bearer " + accessToken;
        response = await postUrl(FALLBACK_URL, headers, requestBody);
      }
      if (!response.ok) {
        const payload = await response.json().catch(() => ({ detail: "HTTP " + response.status }));
        throw new Error(payload.detail ? String(payload.detail) : JSON.stringify(payload));
      }
      const payload = await response.json();
      progressFromPayload(payload);
      renderPayload(payload);
      return payload;
    }

    async function recoverRun(accessToken, jobId, requestBody) {
      if (jobId) {
        try {
          return await pollJob(accessToken, jobId);
        } catch (_error) {
          setProgress("Run snapshot unavailable — finishing the pipeline…", "");
        }
      }
      return finishWithoutStream(accessToken, requestBody);
    }

    document.getElementById("run-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const view = document.getElementById("view");
      const runButton = event.submitter || document.querySelector("#run-form button[type=submit]");
      view.innerHTML = "";
      document.getElementById("eval-view").innerHTML =
        '<p class="empty">Evaluation appears here after the evaluate step finishes.</p>';
      document.getElementById("tab-evaluation").disabled = true;
      document.getElementById("download-eval").disabled = true;
      document.getElementById("download-run").disabled = true;
      selectTab("pipeline");
      latestPayload = null;
      setProgress("Getting access token…", "");
      if (runButton) runButton.disabled = true;
      let token = "";
      try {
        token = await mintAccessToken();
      } catch (error) {
        setProgress("", "");
        view.innerHTML = '<p class="error">Could not create a Bearer token. ' +
          escapeHtml(String(error && error.message ? error.message : error)) + "</p>";
        if (runButton) runButton.disabled = false;
        return;
      }
      setProgress("Running pipeline…", "");
      const selectedId = document.getElementById("query_id").value.trim();
      const body = JSON.stringify({
        query: document.getElementById("query").value,
        query_id: selectedId || undefined,
        decompose_mode: document.getElementById("decompose_mode").value,
        llm_model: document.getElementById("llm_model").value || undefined,
        judge_llm_model: document.getElementById("judge_llm_model").value || undefined,
        use_extension_questions: !!document.getElementById("use_extension_questions").checked,
        use_memory: true,
        refresh: !!document.getElementById("refresh").checked,
      });

      async function postPipeline(accessToken, url) {
        const headers = {
          "Content-Type": "application/json",
          "Accept": "text/event-stream, application/json",
          "Authorization": "Bearer " + accessToken,
        };
        return postUrl(url, headers, body);
      }

      try {
        let response = await postPipeline(token, STREAM_URL);
        if (response.status === 401) {
          setProgress("Access token expired — getting a new one…", "");
          token = await mintAccessToken();
          response = await postPipeline(token, STREAM_URL);
        }
        if (!response.ok || !(String(response.headers.get("content-type") || "").includes("text/event-stream"))) {
          if (!response.ok && response.status !== 401) {
            response = await postPipeline(token, FALLBACK_URL);
          }
          if (!response.ok) {
            const payload = await response.json().catch(() => ({ detail: "HTTP " + response.status }));
            setProgress("", "");
            view.innerHTML = '<p class="error">' + escapeHtml(JSON.stringify(payload)) + "</p>";
            return;
          }
          const payload = await response.json();
          progressFromPayload(payload);
          renderPayload(payload);
          return;
        }
        let lastPayload = null;
        let jobId = response.headers.get("X-Run-Id") || response.headers.get("x-run-id") || "";
        try {
          await readSse(response, (event, payload) => {
            jobId = jobIdFrom(payload, jobId);
            if (event === "job") return;
            lastPayload = payload;
            progressFromPayload(payload);
            renderPayload(payload);
          });
        } catch (error) {
          jobId = jobIdFrom(lastPayload, jobId);
          lastPayload = await recoverRun(token, jobId, body);
          return;
        }
        if (lastPayload && lastPayload.status === "running") {
          lastPayload = await recoverRun(token, jobIdFrom(lastPayload, jobId), body);
        }
      } catch (error) {
        setProgress("", "");
        view.innerHTML = '<p class="error">' + escapeHtml(String(error && error.message ? error.message : error)) + "</p>";
      } finally {
        if (runButton) runButton.disabled = false;
      }
    });

    if (EMBEDDED) renderPayload(EMBEDDED);

    let catalog = [];

    function renderQuestionList(items) {
      const root = document.getElementById("question-list");
      const selected = document.getElementById("query_id").value;
      if (!items.length) {
        root.innerHTML = '<p class="drawer-empty">No matching questions.</p>';
        return;
      }
      const groups = {};
      for (const item of items) {
        const concept = item.concept || "Other";
        (groups[concept] || (groups[concept] = [])).push(item);
      }
      root.innerHTML = Object.keys(groups).map(concept => {
        const rows = groups[concept].map(item => {
          const base = item.parent ? "drawer-q" : "drawer-q child";
          const klass = item.query_id === selected ? base + " selected" : base;
          return '<button type="button" class="' + klass + '" data-id="' + escapeHtml(item.query_id) + '">' +
            '<span class="qid">' + escapeHtml(item.query_id || "–") + "</span>" +
            '<span class="qtext">' + escapeHtml(item.question) + "</span></button>";
        }).join("");
        return '<div class="drawer-concept">' + escapeHtml(concept) + "</div>" + rows;
      }).join("");
    }

    function applyQuestionFilter() {
      const needle = document.getElementById("question-filter").value.trim().toLowerCase();
      const filtered = catalog.filter(item => {
        if (!needle) return true;
        return String(item.query_id).toLowerCase().includes(needle) ||
          String(item.concept || "").toLowerCase().includes(needle) ||
          String(item.question || "").toLowerCase().includes(needle);
      });
      renderQuestionList(filtered);
    }

    document.getElementById("toggle-drawer").addEventListener("click", () => {
      document.getElementById("drawer").classList.toggle("closed");
    });
    document.getElementById("question-filter").addEventListener("input", applyQuestionFilter);
    document.getElementById("question-list").addEventListener("click", (event) => {
      const button = event.target.closest(".drawer-q");
      if (!button) return;
      const item = catalog.find(row => row.query_id === button.getAttribute("data-id"));
      if (!item) return;
      document.getElementById("query").value = item.question;
      document.getElementById("query_id").value = item.query_id || "";
      applyQuestionFilter();
      document.getElementById("query").focus();
    });
    document.getElementById("query").addEventListener("input", () => {
      const typed = document.getElementById("query").value.trim();
      const match = catalog.find(item => item.question === typed);
      document.getElementById("query_id").value = match ? match.query_id : "";
      applyQuestionFilter();
    });

    function fillModelSelect(selectId, models, selected) {
      const select = document.getElementById(selectId);
      if (!select) return;
      const choices = (models && models.length) ? models : [selected || "qwen3"];
      const current = selected || choices[0];
      select.innerHTML = choices.map(name => {
        const mark = name === current ? " selected" : "";
        return '<option value="' + escapeHtml(name) + '"' + mark + ">" + escapeHtml(name) + "</option>";
      }).join("");
    }

    (async () => {
      const root = document.getElementById("question-list");
      try {
        const [questionsResponse, llmResponse] = await Promise.all([
          fetch(apiUrl("tree/questions"), { headers: { Accept: "application/json" } }),
          fetch(apiUrl("llm/options"), { headers: { Accept: "application/json" } }),
        ]);
        if (!questionsResponse.ok) throw new Error("HTTP " + questionsResponse.status);
        const payload = await questionsResponse.json();
        catalog = Array.isArray(payload.questions) ? payload.questions : [];
        applyQuestionFilter();
        if (llmResponse.ok) {
          const llm = await llmResponse.json();
          fillModelSelect("llm_model", llm.models, llm.default_llm_model);
          fillModelSelect("judge_llm_model", llm.models, llm.default_judge_llm_model);
        }
      } catch (error) {
        root.innerHTML = '<p class="drawer-empty">' +
          escapeHtml(String(error && error.message ? error.message : error)) + "</p>";
      }
    })();
  </script>
</body>
</html>
"""
