"""HTML tree view of a ThematicExploration JSON payload, pipeline first → last."""

from __future__ import annotations

import html
import json
from typing import Any

from fastapi.responses import HTMLResponse

_OVERVIEW_KEYS = (
    "service",
    "query_id",
    "question",
    "status",
    "last_step",
    "decompose_mode",
    "concept",
    "comparison_type",
    "clarification",
    "constraint_errors",
)

_END_KEYS = ("synthesized_answer", "grounded_citations")


def presentation_tree(payload: Any) -> Any:
    """Reorder a run so the user reads overview → pipeline (1…n) → answer."""
    if not isinstance(payload, dict):
        return payload
    pipeline = payload.get("pipeline")
    if not isinstance(pipeline, list):
        return payload
    ordered: dict[str, Any] = {}
    for key in _OVERVIEW_KEYS:
        value = payload.get(key)
        if value not in (None, "", []):
            ordered[key] = value
    ordered["pipeline"] = pipeline
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
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<span class="num">{html.escape(str(value))}</span>'
    text = str(value)
    klass = "str long" if len(text) > 80 or "\n" in text else "str"
    return f'<span class="{klass}">{html.escape(text)}</span>'


def _label(key: str, value: Any) -> str:
    if isinstance(value, dict):
        n = len(value)
        hint = "empty" if n == 0 else f"{{ {n} }}"
        return f"{html.escape(key)} <em>{hint}</em>"
    if isinstance(value, list):
        n = len(value)
        hint = "empty" if n == 0 else f"[ {n} ]"
        return f"{html.escape(key)} <em>{hint}</em>"
    return html.escape(key)


def _node_html(key: str, value: Any, *, open_node: bool = False) -> str:
    opened = " open" if open_node else ""
    if not isinstance(value, (dict, list)):
        return (
            f'<div class="leaf"><span class="key">{html.escape(key)}</span>'
            f'<span class="colon">:</span> {_leaf(value)}</div>'
        )
    if isinstance(value, list):
        if value and all(not isinstance(item, (dict, list)) for item in value):
            items = "".join(f"<li>{_leaf(item)}</li>" for item in value)
            return (
                f"<details{opened}><summary>{_label(key, value)}</summary>"
                f'<ol class="scalars">{items}</ol></details>'
            )
        children = "".join(
            _node_html(str(index), item, open_node=False)
            for index, item in enumerate(value, start=1)
        )
        return (
            f"<details{opened}><summary>{_label(key, value)}</summary>"
            f'<div class="kids">{children}</div></details>'
        )
    children = "".join(
        _node_html(child_key, child_val, open_node=False)
        for child_key, child_val in value.items()
    )
    extra = ""
    if key.isdigit() and "name" in value and "title" in value:
        outcome = html.escape(str(value.get("outcome") or ""))
        title = html.escape(str(value.get("title") or value.get("name") or key))
        name = html.escape(str(value.get("name") or ""))
        extra = f' class="step {outcome}"'
        summary = (
            f'<span class="badge">{html.escape(key)}</span> {title} '
            f'<code>{name}</code> <span class="outcome {outcome}">{outcome}</span>'
        )
        if value.get("summary"):
            summary += f'<span class="hint">{html.escape(str(value["summary"]))}</span>'
        return (
            f"<details{opened}{extra}><summary>{summary}</summary>"
            f'<div class="kids">{children}</div></details>'
        )
    return (
        f"<details{opened}><summary>{_label(key, value)}</summary>"
        f'<div class="kids">{children}</div></details>'
    )


def tree_markup(payload: Any) -> str:
    ordered = presentation_tree(payload)
    if isinstance(ordered, dict):
        parts = []
        for key, value in ordered.items():
            open_node = key in {"pipeline", "question", "status", "synthesized_answer"}
            parts.append(_node_html(key, value, open_node=open_node))
        return f'<div class="tree">{"".join(parts)}</div>'
    return f'<div class="tree">{_leaf(ordered)}</div>'


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
    .tree details.step.failed, .tree details.step.halted { border-left-color: var(--fail); }
    summary { cursor: pointer; padding: 4px 0; }
    summary .badge {
      display: inline-block; min-width: 1.6em; text-align: center;
      background: var(--accent); color: #fff; border-radius: 4px;
      font-size: .75rem; padding: 1px 5px; margin-right: 6px;
    }
    summary code { font-size: .8rem; color: var(--muted); }
    .outcome { font-size: .75rem; font-weight: 700; text-transform: uppercase; margin-left: 6px; }
    .outcome.ok { color: var(--ok); }
    .hint { display: block; color: var(--muted); font-size: .85rem; font-weight: 400; margin: 2px 0 0 2.1em; }
    .key { color: var(--accent); font-weight: 600; }
    .colon { color: var(--muted); margin: 0 6px 0 2px; }
    .str { color: #0f172a; white-space: pre-wrap; word-break: break-word; }
    .str.long { display: block; margin: 4px 0 8px 1em; }
    .num { color: #9a3412; }
    .bool { color: #6d28d9; }
    .null { color: var(--muted); }
    em { color: var(--muted); font-style: normal; font-size: .8rem; }
    .leaf { padding: 2px 0 2px 4px; }
    .kids { padding-bottom: 6px; }
    ol.scalars { margin: 4px 0 8px 1.2em; padding: 0; }
    ol.scalars li { margin: 2px 0; }
  </style>
</head>
<body>
  <header>
    <h1>ThematicExploration</h1>
    <p>Pipeline tree from the first step to the last. Open a saved JSON run, or ask a question.</p>
    <form class="bar" id="run-form">
      <input type="text" name="query" id="query" placeholder="How did a marriage look like in the 1800s compared to now?" required/>
      <input type="password" name="token" id="token" placeholder="Bearer access token" autocomplete="off"/>
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
    const OVERVIEW = ["service","query_id","question","status","last_step","decompose_mode","concept","comparison_type","clarification","constraint_errors"];
    const ENDING = ["synthesized_answer","grounded_citations"];

    function presentationTree(payload) {
      if (!payload || typeof payload !== "object" || Array.isArray(payload) || !Array.isArray(payload.pipeline)) {
        return payload;
      }
      const ordered = {};
      for (const key of OVERVIEW) {
        const value = payload[key];
        if (value !== null && value !== undefined && value !== "" && !(Array.isArray(value) && value.length === 0)) {
          ordered[key] = value;
        }
      }
      ordered.pipeline = payload.pipeline;
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
        const children = value.map((item, index) => nodeHtml(String(index + 1), item, false)).join("");
        return "<details" + opened + "><summary>" + label(key, value) + "</summary><div class=\\"kids\\">" + children + "</div></details>";
      }
      if (/^\\d+$/.test(key) && value.name && value.title) {
        const outcome = escapeHtml(value.outcome || "");
        const title = escapeHtml(value.title || value.name || key);
        const name = escapeHtml(value.name || "");
        let summary = '<span class="badge">' + escapeHtml(key) + "</span> " + title + " <code>" + name + "</code> <span class=\\"outcome " + outcome + "\\">" + outcome + "</span>";
        if (value.summary) summary += '<span class="hint">' + escapeHtml(value.summary) + "</span>";
        const children = Object.keys(value).map(child => nodeHtml(child, value[child], false)).join("");
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
      const openKeys = new Set(["pipeline", "question", "status", "synthesized_answer"]);
      view.innerHTML = '<div class="tree">' + Object.keys(ordered).map(key => nodeHtml(key, ordered[key], openKeys.has(key))).join("") + "</div>";
    }
    window.renderPayload = renderPayload;

    document.getElementById("file").addEventListener("change", async (event) => {
      const file = event.target.files && event.target.files[0];
      if (!file) return;
      renderPayload(JSON.parse(await file.text()));
    });

    document.getElementById("run-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const view = document.getElementById("view");
      view.innerHTML = "<p class=\\"empty\\">Running pipeline…</p>";
      const token = document.getElementById("token").value.trim();
      if (token) sessionStorage.setItem("dg_access_token", token);
      const headers = { "Content-Type": "application/json" };
      const stored = token || sessionStorage.getItem("dg_access_token") || "";
      if (stored) headers["Authorization"] = "Bearer " + stored;
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
        view.innerHTML = '<p class="error">' + escapeHtml(JSON.stringify(payload)) + "</p>";
        return;
      }
      renderPayload(payload);
    });

    if (EMBEDDED) renderPayload(EMBEDDED);
    const saved = sessionStorage.getItem("dg_access_token");
    if (saved) document.getElementById("token").value = saved;
  </script>
</body>
</html>
"""
