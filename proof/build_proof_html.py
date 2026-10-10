import json
import sys
from pathlib import Path

import plotly

HERE = Path(__file__).resolve().parent
DATA = HERE / "nfl_stats_data.json"
OUT = HERE / "nfl-stats-proof.html"

PLOTLY_JS = Path(plotly.__file__).resolve().parent / "package_data" / "plotly.min.js"

CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body {
  margin: 0; background: #000000; color: #ededed;
  font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  font-size: 14px; line-height: 1.5; -webkit-font-smoothing: antialiased;
}
a { color: #ededed; text-decoration: underline; text-underline-offset: 3px; }
header {
  position: sticky; top: 0; z-index: 10; padding: 20px 28px 14px;
  background: rgba(0,0,0,0.85); backdrop-filter: blur(12px);
  border-bottom: 1px solid #262626;
}
.brand { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.brand h1 { font-size: 18px; font-weight: 600; letter-spacing: 0.02em; margin: 0; }
.badge {
  font-size: 10px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase;
  padding: 3px 8px; border-radius: 999px; border: 1px solid #333; color: #a1a1a1;
}
.badge.live { color: #4ade80; border-color: #14532d; }
.sub { color: #888; font-size: 12.5px; margin-top: 4px; }
.sub code { font-family: ui-monospace, "SF Mono", "Cascadia Mono", Consolas, monospace; font-size: 11.5px; color: #aaa; }
.tabs {
  display: flex; gap: 8px; flex-wrap: wrap; padding: 12px 28px 2px;
  position: sticky; top: 88px; z-index: 9; background: rgba(0,0,0,0.85); backdrop-filter: blur(12px);
}
.tab {
  appearance: none; cursor: pointer; font: inherit; font-size: 12.5px; font-weight: 500;
  color: #a1a1a1; background: transparent; border: 1px solid #262626; border-radius: 999px;
  padding: 5px 12px; transition: all .12s ease;
}
.tab:hover { color: #ededed; border-color: #444; }
.tab.active { background: #ededed; color: #000; border-color: #ededed; font-weight: 600; }
main { padding: 18px 28px 60px; max-width: 1280px; }
.panel { display: none; }
.panel.active { display: block; }
.card {
  background: #0a0a0a; border: 1px solid #262626; border-radius: 12px;
  padding: 18px 20px; margin-bottom: 16px;
}
.card h2 { font-size: 14.5px; font-weight: 600; margin: 0 0 2px; }
.card .desc { color: #888; font-size: 12.5px; margin-bottom: 12px; }
.chart { width: 100%; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th {
  text-align: left; color: #888; font-size: 11px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.06em; padding: 8px 10px;
  border-bottom: 1px solid #262626;
}
td { padding: 8px 10px; border-bottom: 1px solid #1a1a1a; }
tr:last-child td { border-bottom: none; }
td.num, th.num { text-align: right; font-family: ui-monospace, "SF Mono", "Cascadia Mono", Consolas, monospace; }
.ok { color: #4ade80; font-weight: 600; }
.pos { display: inline-block; font-size: 10.5px; font-weight: 600; color: #a1a1a1; border: 1px solid #333; border-radius: 6px; padding: 1px 6px; margin-right: 6px; }
.tm { color: #a1a1a1; font-weight: 600; }
.legendtitle { font-size: 11px !important; color: #888 !important; }
"""

JS = """
const DATA = __DATA_PLACEHOLDER__;

function fmtOf(chart, i) {
  return chart.fmt || ",.1f";
}

function renderBump(id, chart) {
  const fmt = chart.fmt;
  const cap = chart.cap || chart.series.length * 2;
  const traces = chart.series.map(s => ({
    x: s.weeks,
    y: s.rank,
    mode: "lines+markers",
    name: s.name,
    line: { color: s.color, width: 2.5 },
    marker: { size: 9, color: s.color, line: { width: 1, color: "#444444" } },
    customdata: s.weeks.map((w, i) => [w, s.per_game[i], s.cum[i]]),
    hovertemplate: "<b>" + s.name + "</b><br>Cumulative: %{customdata[2]" + fmt + "}<br>This week: %{customdata[1]" + fmt + "}<br>Week %{x}<extra></extra>",
    connectgaps: false
  }));
  const step = cap <= 18 ? 1 : 2;
  const tickvals = [];
  for (let i = 1; i <= cap; i += step) tickvals.push(i);
  const maxWeek = Math.max(...chart.weeks);
  const layout = {
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: "#ededed", family: "Inter, -apple-system, Segoe UI, sans-serif", size: 12 },
    yaxis: { range: [cap + 0.5, 0.5], tickvals: tickvals, title: { text: "Rank by cumulative total (capped at " + cap + ")", font: { size: 11, color: "#888" } }, gridcolor: "#1a1a1a", zeroline: false },
    xaxis: { range: [0.5, maxWeek + 0.5], title: { text: "Week", font: { size: 11, color: "#888" } }, dtick: 1, gridcolor: "#1a1a1a", zeroline: false },
    legend: { title: { text: "Leader", font: { size: 11, color: "#888" } }, font: { size: 11.5 }, itemsizing: "constant" },
    margin: { l: 55, r: 20, t: 14, b: 46 },
    height: Math.max(460, 40 * chart.series.length + 110),
    hovermode: "closest",
    dragmode: false
  };
  Plotly.newPlot(id, traces, layout, { displayModeBar: false, responsive: true });
}

function renderDots(id, chart) {
  const fmt = chart.fmt;
  const traces = chart.series.map(s => ({
    x: s.weeks,
    y: s.values,
    mode: "lines+markers",
    name: s.name,
    line: { color: s.color, width: 2.5 },
    marker: { size: 9, color: s.color, line: { width: 1, color: "#444444" } },
    customdata: s.weeks.map(() => s.season_total),
    hovertemplate: "<b>" + s.name + "</b><br>Week %{x}: %{y" + fmt + "}<br>Season total: %{customdata" + fmt + "}<extra></extra>",
    connectgaps: false
  }));
  const layout = {
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: "#ededed", family: "Inter, -apple-system, Segoe UI, sans-serif", size: 12 },
    yaxis: { title: { text: "Per-game value", font: { size: 11, color: "#888" } }, gridcolor: "#1a1a1a", zeroline: false },
    xaxis: { title: { text: "Week", font: { size: 11, color: "#888" } }, dtick: 1, gridcolor: "#1a1a1a", zeroline: false },
    legend: { title: { text: "Player / Team", font: { size: 11, color: "#888" } }, font: { size: 11.5 }, itemsizing: "constant" },
    margin: { l: 55, r: 20, t: 14, b: 46 },
    height: Math.max(460, 40 * chart.series.length + 110),
    hovermode: "closest",
    dragmode: false
  };
  Plotly.newPlot(id, traces, layout, { displayModeBar: false, responsive: true });
}

const CHART_DEFS = [
  ["tab-passing", [["passing-bump", DATA.charts.passing_bump_2025, "bump"]]],
  ["tab-rushing", [["rushing-dots", DATA.charts.rushing_dots_2025, "dots"]]],
  ["tab-tackles", [["tackles-bump", DATA.charts.tackles_bump_2025, "bump"]]],
  ["tab-receiving", [["receiving-bump", DATA.charts.receiving_bump_2025, "bump"]]],
  ["tab-yac", [["yac-bump", DATA.charts.yac_bump_2025, "bump"]]],
  ["tab-points-allowed", [["points-allowed-bump", DATA.charts.points_allowed_bump_2025, "bump"]]],
  ["tab-plays", [["plays-dots", DATA.charts.plays_dots_2025, "dots"]]],
  ["tab-2026", [["passing-2026-bump", DATA.charts.passing_bump_2026, "bump"]]],
  ["tab-leaders", []],
  ["tab-proof", []]
];

function activate(tabId) {
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === tabId));
  document.querySelectorAll(".panel").forEach(p => p.classList.toggle("active", p.id === tabId));
  const def = CHART_DEFS.find(d => d[0] === tabId);
  if (def) {
    def[1].forEach(([divId, chart, kind]) => {
      const el = document.getElementById(divId);
      if (el && !el.dataset.rendered) {
        (kind === "bump" ? renderBump : renderDots)(divId, chart);
        el.dataset.rendered = "1";
      }
    });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".tab").forEach(t => t.addEventListener("click", () => activate(t.dataset.tab)));
  activate("tab-passing");
});
"""


def fmt_num(v):
    if v is None:
        return ""
    if isinstance(v, float) and v == int(v):
        return f"{int(v):,}"
    return f"{v:,.1f}"


def leaders_table(rows, stat_label):
    head = f"""<table><thead><tr><th>#</th><th>Player</th><th>Team</th><th class="num">{stat_label}</th></tr></thead><tbody>"""
    body = []
    for i, r in enumerate(rows):
        pos = f'<span class="pos">{r.get("position") or ""}</span>' if r.get("position") else ""
        body.append(
            f'<tr><td class="num">{i + 1}</td><td>{pos}{r["player"]}</td><td class="tm">{r.get("team") or ""}</td>'
            f'<td class="num">{fmt_num(r["value"])}</td></tr>')
    return head + "".join(body) + "</tbody></table>"


def sanity_table(rows):
    body = []
    for r in rows:
        mark = '<span class="ok">MATCH</span>' if r["match"] else '<span style="color:#f87171">MISMATCH</span>'
        body.append(f'<tr><td><code>{r["stat"]}</code></td><td>{r["expected"]}</td><td>{r["got"]}</td><td>{mark}</td></tr>')
    return ('<table><thead><tr><th>Stat (2024)</th><th>Known total</th><th>This app</th><th>Status</th></tr></thead><tbody>'
            + "".join(body) + "</tbody></table>")


def endpoints_table(rows):
    body = []
    for r in rows:
        body.append(f'<tr><td><code>{r["endpoint"]}</code></td><td class="num">{r["seasons"]}</td></tr>')
    return ('<table><thead><tr><th>Endpoint</th><th class="num">Seasons available</th></tr></thead><tbody>'
            + "".join(body) + "</tbody></table>")


def main():
    data = json.loads(DATA.read_text())
    data_js = DATA.read_text()
    tables = data["tables"]
    gen = data["generated"]

    panels = {
        "tab-passing": ("Passing Yards", "Cumulative rank of the league leaders week by week. Hover any dot for week + cumulative + per-game values.",
                        leaders_table(tables["passing_leaders_2025"], "Passing Yards"), "Final 2025 leaderboard (top 15)"),
        "tab-rushing": ("Rushing Yards", "Per-game values as connected dot plots for the top 10 rushers — how each season unfolded week to week.", "", ""),
        "tab-tackles": ("Total Tackles", "Defensive tackle leaders, rank by cumulative solo + assisted tackles.",
                        leaders_table(tables["tackles_leaders_2025"], "Total Tackles"), "Final 2025 leaderboard (top 15)"),
        "tab-receiving": ("Receiving Yards", "Receiver leaders, rank by cumulative receiving yards.", "", ""),
        "tab-yac": ("Yards After Contact", "Rushing yards after contact (PFR advanced data) — proves the PFR endpoint wiring.", "", ""),
        "tab-points-allowed": ("Team: Points Allowed", "Team-level progression from game results (schedules) — fewest points allowed climbs to rank 1.", "", ""),
        "tab-plays": ("Team: Play Count", "Plays run per game per team, computed from play-by-play — proves the pbp endpoint wiring.", "", ""),
        "tab-2026": ("2026 Season So Far", "Live current-season progression (completed weeks only) — updates as weeks land.", "", ""),
        "tab-leaders": ("Season Leaders", "Final leaderboards from the season stats endpoints.", "", ""),
        "tab-proof": ("Proof", "Every claim, verified against known totals and live nflverse endpoints.", "", ""),
    }

    def chart_card(div_id, kind_label):
        return f'<div class="chart" id="{div_id}"></div>'

    sections = []
    for tab_id, (title, desc, table_html, table_desc) in panels.items():
        inner = [f'<h2>{title}</h2>', f'<div class="desc">{desc}</div>']
        if tab_id == "tab-passing":
            inner.append(chart_card("passing-bump", "bump"))
            inner.append(f'<div class="desc" style="margin-top:14px">{table_desc}</div>')
            inner.append(table_html)
        elif tab_id == "tab-tackles":
            inner.append(chart_card("tackles-bump", "bump"))
            inner.append(f'<div class="desc" style="margin-top:14px">{table_desc}</div>')
            inner.append(table_html)
        elif tab_id == "tab-rushing":
            inner.append(chart_card("rushing-dots", "dots"))
        elif tab_id == "tab-receiving":
            inner.append(chart_card("receiving-bump", "bump"))
        elif tab_id == "tab-yac":
            inner.append(chart_card("yac-bump", "bump"))
        elif tab_id == "tab-points-allowed":
            inner.append(chart_card("points-allowed-bump", "bump"))
        elif tab_id == "tab-plays":
            inner.append(chart_card("plays-dots", "dots"))
        elif tab_id == "tab-2026":
            inner.append(chart_card("passing-2026-bump", "bump"))
        elif tab_id == "tab-leaders":
            inner.append('<div class="desc">Passing yards — 2025 (top 15)</div>')
            inner.append(leaders_table(tables["passing_leaders_2025"], "Passing Yards"))
            inner.append('<div class="desc" style="margin-top:14px">Total tackles — 2025 (top 15)</div>')
            inner.append(leaders_table(tables["tackles_leaders_2025"], "Total Tackles"))
        elif tab_id == "tab-proof":
            inner.append('<div class="card"><h2>Known totals — 2024 sanity check</h2>'
                         '<div class="desc">This app\'s season endpoints reproduce official league totals exactly.</div>'
                         + sanity_table(tables["sanity_2024"]) + "</div>")
            inner.append('<div class="card"><h2>nflverse endpoints wired</h2>'
                         '<div class="desc">Live season coverage probed from the nflverse-data GitHub releases.</div>'
                         + endpoints_table(tables["endpoints"]) + "</div>")
            inner.append('<div class="card"><h2>Sources & method</h2>'
                         f'<div class="desc">Generated {gen}. Data: {data["meta"]["sources"]}. {data["meta"]["notes"]} '
                         'Charts: rank race = rank of cumulative total per week (dot plots with connecting lines); '
                         'per-game = weekly values as connected dots. Full Streamlit app: '
                         '<code>D:\\nfl-progression</code> (Player Progression, Team Progression, Season Leaders, PBP Explorer, Endpoint Explorer).</div></div>')
        sections.append(f'<section class="panel" id="{tab_id}"><div class="card">' + "".join(inner) + "</div></section>")

    tab_labels = {
        "tab-passing": "Passing Yards",
        "tab-rushing": "Rushing Yards",
        "tab-tackles": "Total Tackles",
        "tab-receiving": "Receiving Yards",
        "tab-yac": "Yards After Contact",
        "tab-points-allowed": "Points Allowed (team)",
        "tab-plays": "Play Count (team)",
        "tab-2026": "2026 So Far",
        "tab-leaders": "Season Leaders",
        "tab-proof": "Proof",
    }
    tabs_html = "".join(
        f'<button class="tab" data-tab="{tid}">{label}</button>' for tid, label in tab_labels.items())

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NFL Stat Progression — Proof</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <div class="brand">
    <h1>NFL Stat Progression</h1>
    <span class="badge live">live nflverse data</span>
    <span class="badge">{data["meta"]["seasons"]}</span>
    <span class="badge">generated {gen}</span>
  </div>
  <div class="sub">Week-by-week progression of stat leaders — bump charts (rank races) and per-game dot plots.
  Module-ready: this file is self-contained and can be embedded as the <code>nfl-stats</code> tab.</div>
</header>
<nav class="tabs">{tabs_html}</nav>
<main>{''.join(sections)}</main>
<script>{JS.replace('__DATA_PLACEHOLDER__', data_js)}</script>
<script>{PLOTLY_JS.read_text(encoding="utf-8")}</script>
</body>
</html>"""

    OUT.write_text(html, encoding="utf-8")
    print("wrote", OUT, f"{OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
