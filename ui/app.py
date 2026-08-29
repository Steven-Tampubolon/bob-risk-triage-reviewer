"""
ui/app.py

Minimal Flask dashboard for the PR Risk Triage Reviewer.

Reads output/explained_priority_queue.json and renders a priority-sorted HTML
table with colour-coded priority labels and merge-blocker guardrail indicators.

Run:
    flask --app ui.app run            (from project root)
    python -m flask --app ui.app run  (alternative)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Flask, render_template_string

app = Flask(__name__)

# Resolve path relative to project root, not the ui/ package directory
_QUEUE_PATH = Path(__file__).resolve().parent.parent / "output" / "explained_priority_queue.json"

# ---------------------------------------------------------------------------
# Colour palette for priority labels
# ---------------------------------------------------------------------------

_LABEL_STYLES: dict[str, dict[str, str]] = {
    "Critical": {"bg": "#dc2626", "fg": "#ffffff"},   # red
    "High":     {"bg": "#ea580c", "fg": "#ffffff"},   # orange
    "Medium":   {"bg": "#ca8a04", "fg": "#ffffff"},   # yellow-dark (readable)
    "Low":      {"bg": "#16a34a", "fg": "#ffffff"},   # green
}
_FALLBACK_STYLE = {"bg": "#6b7280", "fg": "#ffffff"}

# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

_TEMPLATE = """\
<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>PR Risk Triage — Priority Queue</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, "Segoe UI", system-ui, sans-serif;
      font-size: 14px;
      line-height: 1.5;
      color: #1f2328;
      background: #f6f8fa;
      padding: 24px 20px 48px;
    }
    h1 {
      font-size: 20px;
      font-weight: 600;
      margin-bottom: 4px;
    }
    .subtitle {
      color: #57606a;
      font-size: 13px;
      margin-bottom: 20px;
    }
    .table-wrap {
      overflow-x: auto;
      background: #ffffff;
      border: 1px solid #d0d7de;
      border-radius: 6px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }
    colgroup col.col-pr     { width: 80px; }
    colgroup col.col-br     { width: 130px; }
    colgroup col.col-score  { width: 80px; }
    colgroup col.col-label  { width: 100px; }
    colgroup col.col-exp    { width: auto; }
    thead th {
      background: #f6f8fa;
      border-bottom: 1px solid #d0d7de;
      padding: 8px 12px;
      text-align: left;
      font-size: 12px;
      font-weight: 600;
      color: #57606a;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      white-space: nowrap;
    }
    tbody tr { border-bottom: 1px solid #e5e7eb; }
    tbody tr:last-child { border-bottom: none; }
    tbody tr.blocker { background: #fff8f0; }
    tbody tr:hover { background: #f0f6ff; }
    tbody tr.blocker:hover { background: #fef0e0; }
    td {
      padding: 10px 12px;
      vertical-align: top;
    }
    .pr-num {
      font-family: ui-monospace, "SFMono-Regular", monospace;
      font-size: 13px;
      color: #0969da;
      font-weight: 500;
    }
    .br-badge {
      display: inline-block;
      padding: 1px 7px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: 600;
      background: #e5e7eb;
      color: #374151;
      white-space: nowrap;
    }
    .br-badge.multi { background: #dbeafe; color: #1d4ed8; }
    .score {
      font-weight: 700;
      font-size: 15px;
      color: #1f2328;
    }
    .label-badge {
      display: inline-block;
      padding: 2px 10px;
      border-radius: 12px;
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }
    .guardrail {
      display: inline-block;
      margin-left: 6px;
      padding: 1px 6px;
      border-radius: 4px;
      font-size: 10px;
      font-weight: 700;
      background: #fef9c3;
      color: #854d0e;
      border: 1px solid #fde047;
      vertical-align: middle;
      white-space: nowrap;
    }
    .reviewer {
      font-size: 11px;
      color: #57606a;
      margin-top: 3px;
    }
    .explanation {
      font-size: 13px;
      line-height: 1.6;
      color: #1f2328;
      word-break: break-word;
    }
    .count { color: #57606a; font-size: 13px; margin-bottom: 12px; }
  </style>
</head>
<body>
  <h1>PR Risk Triage — Priority Queue</h1>
  <p class="subtitle">Sorted by priority score (highest first) &middot; {{ rows|length }} pull requests</p>
  <p class="count">
    <strong>{{ critical_count }}</strong> Critical &nbsp;
    <strong>{{ high_count }}</strong> High &nbsp;
    <strong>{{ medium_count }}</strong> Medium &nbsp;
    <strong>{{ low_count }}</strong> Low &nbsp;
    &nbsp;|&nbsp; <strong>{{ blocker_count }}</strong> merge-blocker guardrails active
  </p>
  <div class="table-wrap">
    <table>
      <colgroup>
        <col class="col-pr" />
        <col class="col-br" />
        <col class="col-score" />
        <col class="col-label" />
        <col class="col-exp" />
      </colgroup>
      <thead>
        <tr>
          <th>PR #</th>
          <th>Blast Radius</th>
          <th>Score</th>
          <th>Label</th>
          <th>Explanation</th>
        </tr>
      </thead>
      <tbody>
        {% for row in rows %}
        <tr{% if row.merge_blocker %} class="blocker"{% endif %}>
          <td class="pr-num">#{{ row.pr_number }}</td>
          <td>
            <span class="br-badge{% if row.blast_radius_label == 'multi_module' %} multi{% endif %}">
              {{ row.blast_radius_label | replace('_', ' ') }}
            </span>
          </td>
          <td><span class="score">{{ row.priority_score }}</span></td>
          <td>
            <span class="label-badge"
              style="background:{{ row.label_bg }};color:{{ row.label_fg }}">
              {{ row.priority_label }}
            </span>
            {% if row.merge_blocker %}
            <span class="guardrail" title="Merge is blocked — mandatory review required">⛔ guardrail</span>
            {% endif %}
            {% if row.required_reviewer %}
            <div class="reviewer">👤 {{ row.required_reviewer }}</div>
            {% endif %}
          </td>
          <td><p class="explanation">{{ row.explanation }}</p></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    with open(_QUEUE_PATH, encoding="utf-8") as fh:
        raw: list[dict] = json.load(fh)

    # Ensure sorted by priority_score descending (file should already be, but guarantee it)
    raw.sort(key=lambda r: r.get("priority_score", 0), reverse=True)

    rows = []
    for entry in raw:
        label = entry.get("priority_label", "")
        style = _LABEL_STYLES.get(label, _FALLBACK_STYLE)
        rows.append({
            **entry,
            "label_bg": style["bg"],
            "label_fg": style["fg"],
        })

    counts = {lbl: sum(1 for r in rows if r.get("priority_label") == lbl)
              for lbl in ("Critical", "High", "Medium", "Low")}
    blocker_count = sum(1 for r in rows if r.get("merge_blocker"))

    return render_template_string(
        _TEMPLATE,
        rows=rows,
        critical_count=counts["Critical"],
        high_count=counts["High"],
        medium_count=counts["Medium"],
        low_count=counts["Low"],
        blocker_count=blocker_count,
    )
