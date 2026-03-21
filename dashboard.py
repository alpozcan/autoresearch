"""
Live dashboard for autoresearch iOS optimization experiments.
Serves a self-contained HTML page with Plotly.js charts at http://localhost:8050.

Usage:
    python dashboard.py              # start dashboard
    python dashboard.py --port 8050  # custom port
"""

import os
import sys
import json
import time
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

AUTORESEARCH_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(AUTORESEARCH_DIR, "results")
BASELINE_COLD_LAUNCH = 558

MODELS = [
    {"short": "claude-opus", "color": "#7c3aed"},
    {"short": "claude-sonnet", "color": "#2563eb"},
    {"short": "gemini-pro", "color": "#059669"},
    {"short": "gpt-4.1", "color": "#d97706"},
    {"short": "deepseek-v3", "color": "#dc2626"},
]


def load_all_results():
    """Load history.json from all model result directories."""
    data = {}
    for model in MODELS:
        short = model["short"]
        path = os.path.join(RESULTS_DIR, short, "history.json")
        if os.path.exists(path):
            with open(path, "r") as f:
                data[short] = json.load(f)
        else:
            data[short] = []
    return data


def build_html():
    """Build the complete dashboard HTML with embedded data."""
    all_data = load_all_results()
    models_json = json.dumps(MODELS)
    data_json = json.dumps(all_data)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="10">
<title>autoresearch iOS Dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'SF Pro', system-ui, sans-serif;
         background: #0a0a0a; color: #e5e5e5; padding: 20px; }}
  h1 {{ font-size: 1.5rem; font-weight: 600; margin-bottom: 4px; }}
  .subtitle {{ color: #737373; font-size: 0.85rem; margin-bottom: 20px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }}
  .card {{ background: #171717; border: 1px solid #262626; border-radius: 12px; padding: 16px; }}
  .card-title {{ font-size: 0.8rem; color: #737373; text-transform: uppercase;
                 letter-spacing: 0.05em; margin-bottom: 8px; }}
  .full-width {{ grid-column: 1 / -1; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  th {{ text-align: left; padding: 8px 12px; color: #737373; border-bottom: 1px solid #262626;
        font-weight: 500; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #1a1a1a; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; }}
  .badge-keep {{ background: #052e16; color: #4ade80; }}
  .badge-discard {{ background: #1c1917; color: #a8a29e; }}
  .badge-crash {{ background: #450a0a; color: #f87171; }}
  .stat-value {{ font-size: 1.8rem; font-weight: 700; }}
  .stat-label {{ font-size: 0.75rem; color: #737373; }}
  .model-dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%;
                margin-right: 6px; }}
  #timeline {{ width: 100%; height: 350px; }}
  #comparison {{ width: 100%; height: 250px; }}
</style>
</head>
<body>
<h1>autoresearch iOS</h1>
<p class="subtitle">Cold launch optimization &middot; Multi-model comparison &middot;
   Auto-refreshes every 10s &middot; {datetime.now().strftime("%H:%M:%S")}</p>

<div class="grid" id="stats-grid"></div>

<div class="grid">
  <div class="card full-width">
    <div class="card-title">Score Timeline</div>
    <div id="timeline"></div>
  </div>
</div>

<div class="grid">
  <div class="card full-width">
    <div class="card-title">Best Cold Launch by Model</div>
    <div id="comparison"></div>
  </div>
</div>

<div class="grid">
  <div class="card full-width">
    <div class="card-title">Model Leaderboard</div>
    <table id="leaderboard">
      <thead>
        <tr>
          <th>Model</th>
          <th>Best (ms)</th>
          <th>Improvement</th>
          <th>Experiments</th>
          <th>Keep Rate</th>
          <th>Total Tokens</th>
          <th>Total Cost</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>
</div>

<div class="grid">
  <div class="card full-width">
    <div class="card-title">Recent Experiments</div>
    <table id="experiments">
      <thead>
        <tr>
          <th>Model</th>
          <th>#</th>
          <th>Launch (ms)</th>
          <th>Score</th>
          <th>Status</th>
          <th>Description</th>
          <th>Tokens</th>
          <th>Cost</th>
          <th>Time</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>
</div>

<script>
const MODELS = {models_json};
const DATA = {data_json};
const BASELINE = {BASELINE_COLD_LAUNCH};

// --- Stats cards ---
const statsGrid = document.getElementById('stats-grid');
let totalExperiments = 0;
let totalCost = 0;
let globalBest = BASELINE;
let globalBestModel = '';

MODELS.forEach(m => {{
  const history = DATA[m.short] || [];
  totalExperiments += history.length;
  history.forEach(h => {{
    totalCost += (h.cost_usd || 0);
    if (h.status === 'keep' && h.cold_launch_ms > 0 && h.cold_launch_ms < globalBest) {{
      globalBest = h.cold_launch_ms;
      globalBestModel = m.short;
    }}
  }});
}});

const improvement = ((BASELINE - globalBest) / BASELINE * 100).toFixed(1);
const stats = [
  {{ label: 'Total Experiments', value: totalExperiments }},
  {{ label: 'Best Cold Launch', value: globalBest + 'ms' }},
  {{ label: 'Improvement', value: improvement + '%' }},
  {{ label: 'Total Cost', value: '$' + totalCost.toFixed(2) }},
];
stats.forEach(s => {{
  const card = document.createElement('div');
  card.className = 'card';
  card.innerHTML = `<div class="stat-value">${{s.value}}</div><div class="stat-label">${{s.label}}</div>`;
  statsGrid.appendChild(card);
}});

// --- Timeline chart ---
const timelineTraces = [];
MODELS.forEach(m => {{
  const history = DATA[m.short] || [];
  if (history.length === 0) return;
  let runningBest = BASELINE;
  const x = [], y = [];
  history.forEach(h => {{
    if (h.status === 'keep' && h.cold_launch_ms > 0) {{
      runningBest = Math.min(runningBest, h.cold_launch_ms);
    }}
    x.push(h.num);
    y.push(runningBest);
  }});
  timelineTraces.push({{
    x, y, name: m.short, mode: 'lines+markers',
    line: {{ color: m.color, width: 2 }},
    marker: {{ size: 4 }},
  }});
}});

// Baseline line
timelineTraces.push({{
  x: [0, Math.max(...MODELS.flatMap(m => (DATA[m.short]||[]).map(h=>h.num)).concat([50]))],
  y: [BASELINE, BASELINE], name: 'Baseline', mode: 'lines',
  line: {{ color: '#525252', width: 1, dash: 'dash' }},
}});

Plotly.newPlot('timeline', timelineTraces, {{
  paper_bgcolor: '#171717', plot_bgcolor: '#171717',
  font: {{ color: '#a3a3a3', size: 11 }},
  xaxis: {{ title: 'Experiment #', gridcolor: '#262626' }},
  yaxis: {{ title: 'Best Cold Launch (ms)', gridcolor: '#262626' }},
  legend: {{ orientation: 'h', y: -0.2 }},
  margin: {{ t: 10, r: 20, b: 60, l: 60 }},
}}, {{ responsive: true }});

// --- Comparison bar chart ---
const compX = [], compY = [], compColors = [];
MODELS.forEach(m => {{
  const history = DATA[m.short] || [];
  const keeps = history.filter(h => h.status === 'keep' && h.cold_launch_ms > 0);
  const best = keeps.length > 0 ? Math.min(...keeps.map(h => h.cold_launch_ms)) : BASELINE;
  compX.push(m.short);
  compY.push(best);
  compColors.push(m.color);
}});

Plotly.newPlot('comparison', [{{
  x: compX, y: compY, type: 'bar',
  marker: {{ color: compColors, opacity: 0.85 }},
  text: compY.map(v => v + 'ms'), textposition: 'outside',
  textfont: {{ color: '#a3a3a3' }},
}}], {{
  paper_bgcolor: '#171717', plot_bgcolor: '#171717',
  font: {{ color: '#a3a3a3', size: 11 }},
  yaxis: {{ title: 'Cold Launch (ms)', gridcolor: '#262626' }},
  margin: {{ t: 10, r: 20, b: 40, l: 60 }},
  shapes: [{{
    type: 'line', x0: -0.5, x1: compX.length - 0.5,
    y0: BASELINE, y1: BASELINE,
    line: {{ color: '#525252', width: 1, dash: 'dash' }},
  }}],
}}, {{ responsive: true }});

// --- Leaderboard ---
const lbBody = document.querySelector('#leaderboard tbody');
const modelStats = MODELS.map(m => {{
  const history = DATA[m.short] || [];
  const keeps = history.filter(h => h.status === 'keep' && h.cold_launch_ms > 0);
  const best = keeps.length > 0 ? Math.min(...keeps.map(h => h.cold_launch_ms)) : BASELINE;
  const totalTokens = history.reduce((s, h) => s + (h.input_tokens||0) + (h.output_tokens||0), 0);
  const cost = history.reduce((s, h) => s + (h.cost_usd||0), 0);
  return {{ ...m, best, total: history.length, keeps: keeps.length, totalTokens, cost }};
}}).sort((a, b) => a.best - b.best);

modelStats.forEach(m => {{
  const imp = ((BASELINE - m.best) / BASELINE * 100).toFixed(1);
  const keepRate = m.total > 0 ? (m.keeps / m.total * 100).toFixed(0) : '0';
  const row = document.createElement('tr');
  row.innerHTML = `
    <td><span class="model-dot" style="background:${{m.color}}"></span>${{m.short}}</td>
    <td>${{m.best}}</td>
    <td>${{imp}}%</td>
    <td>${{m.total}}</td>
    <td>${{keepRate}}%</td>
    <td>${{m.totalTokens.toLocaleString()}}</td>
    <td>$${{m.cost.toFixed(2)}}</td>
  `;
  lbBody.appendChild(row);
}});

// --- Recent experiments ---
const expBody = document.querySelector('#experiments tbody');
const allExps = [];
MODELS.forEach(m => {{
  (DATA[m.short] || []).forEach(h => {{
    allExps.push({{ ...h, model: m.short, color: m.color }});
  }});
}});
allExps.sort((a, b) => (b.timestamp || '').localeCompare(a.timestamp || ''));
allExps.slice(0, 50).forEach(h => {{
  const badgeClass = h.status === 'keep' ? 'badge-keep' :
                     h.status === 'discard' ? 'badge-discard' : 'badge-crash';
  const tokens = (h.input_tokens||0) + (h.output_tokens||0);
  const row = document.createElement('tr');
  row.innerHTML = `
    <td><span class="model-dot" style="background:${{h.color}}"></span>${{h.model}}</td>
    <td>${{h.num || '-'}}</td>
    <td>${{h.cold_launch_ms || '-'}}</td>
    <td>${{h.composite_score ? h.composite_score.toFixed(4) : '-'}}</td>
    <td><span class="badge ${{badgeClass}}">${{h.status}}</span></td>
    <td>${{(h.description || '').substring(0, 60)}}</td>
    <td>${{tokens.toLocaleString()}}</td>
    <td>$${{(h.cost_usd||0).toFixed(4)}}</td>
    <td>${{h.timestamp ? new Date(h.timestamp).toLocaleTimeString() : '-'}}</td>
  `;
  expBody.appendChild(row);
}});
</script>
</body>
</html>""";


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        html = build_html()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass  # silence request logs


def main():
    parser = argparse.ArgumentParser(description="autoresearch live dashboard")
    parser.add_argument("--port", type=int, default=8050)
    args = parser.parse_args()

    server = HTTPServer(("0.0.0.0", args.port), DashboardHandler)
    print(f"Dashboard running at http://localhost:{args.port}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
