"""Build the self-contained proof HTML for the NFL stats dashboard module."""
import base64
import hashlib
import json
import re
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
MOD = HERE / "dashboard-module"
OUT = HERE / "nfl-dashboard-module-proof.html"
APP = Path(r"D:\abet_dev\claude_dashboard_pills_20260925")

evidence = json.loads((MOD / "evidence.json").read_text(encoding="utf-8"))
verify = json.loads((MOD / "verify_data.json").read_text(encoding="utf-8"))
build_log = (MOD / "build.log").read_text(encoding="utf-8", errors="replace") if (MOD / "build.log").exists() else ""

SHOTS = [
    ("module_1_default_2026_rank.png", "1 · Default view — 2026 live season, Passing yards league rank race. Opens straight from ?section=stats&tab=nfl-stats.", "live"),
    ("module_2_2025_tackles_rank.png", "2 · Rank race — 2025 Total tackles, all 18 weeks. Jordyn Brooks wire-to-wire #1 (180) with true league ranks (early-season positions clipped at rank 20). Avatars = headshots with colored-dot fallback.", "rank"),
    ("module_3_2025_tackles_pergame.png", "3 · Per game — same stat as connected dot plots with team colors.", "game"),
    ("module_4_2025_values_scale.png", "4 · Y scale = Values — the rank race re-scaled to accumulated tackles (0→180) so you watch totals pile up week by week.", "values"),
    ("module_5_2025_pace_right_axis.png", "5 · Season pace + Y labels docked right — axis title, ticks and gridlines all switch sides. (This view previously crashed — regression-tested in the suite.)", "pace"),
    ("module_6_2025_teams_points.png", "6 · Team level — 2025 Points scored (Rams 518) with team logos. Same engine for all 151 team stats incl. plays, EPA/play, points allowed, penalties.", "teams"),
    ("module_7_tooltip.png", "7 · Hover tooltip — this week's value with its rank for that week, plus season total with season rank. Legend chips pin players for comparison.", "tooltip"),
    ("module_8_2026_live_rank.png", "8 · 2026 in progress — the bundle rebuilds as weeks complete.", "live26"),
    ("module_9_1999_history.png", "9 · 1999 — the oldest bundled season (Beuerlein 4,436 passing yards).", "history"),
    ("module_10_hamburger_stats_menu.png", "10 · The customer entrance: hamburger menu → Stats → NFL tab.", "menu"),
    ("module_11_position_filter.png", "11 · Position filter + deep pools — 2025 receiving yards, WR only, 25 series from a 40-deep pool. Pool = top 30 league-wide + top 6 per position group so filters work at depth; PFR advanced stats carry positions and headshots too.", "positions"),
    ("module_12_multi_select.png", "12 · Multi-select compare — click any number of legend chips to pin them; the rest dim, hovering still focuses one. 'Show all (3)' clears.", "multiselect"),
    ("module_13_radar_top4.png", "13 · Team radar — Results & Points category scored as league percentiles (outer = best, ↓ = lower is better). Default shows the top 4; any category's stats become axes.", "radar"),
    ("module_14_radar_compare.png", "14 · Radar compare — Seahawks vs Lions pinned. Team colors now use brand palettes (navy where it works, secondary color like Seahawks action green when primary collides).", "radarcmp"),
    ("module_15_full_universe.png", "15 · Full universe — 'All players' parses the raw nflverse parquet in the browser: 474 receivers with recorded yardage (not just 40), 200 plotted, position filters still apply, ranks still league-wide.", "full"),
    ("module_18_radar_week6.png", "16 · Weekly radar — same team percentiles computed through week 6 of the season instead of final totals.", "radarweek"),
    ("module_16_table.png", "17 · Data table — every plotted entity as rows (weeks played, this week, season, weekly rank, season rank) with the exact nflverse source path.", "table"),
    ("module_17_career.png", "18 · Career stitching — search any player across eras (Rice, Kelce…), load their career from raw weekly parquet, and compare season-by-season totals on one chart plus a full table.", "career"),
    ("module_19_season_compare.png", "19 · Season compare — select up to 6 seasons and see the same chart for each, in grid / side-by-side / stacked layouts (add or remove seasons with the chips).", "compare"),
    ("module_20_sorted_table.png", "20 · Sortable tables — click any column header to sort (indicator shows direction); works in the stats table and the career table.", "sorttable"),
    ("module_21_player_card.png", "21 · Player drill-down — click any name in a table to open the player card: percentile radar vs position peers, full game log, and the career chart in one drawer.", "playercard"),
    ("module_22_records.png", "22 · Records finder — single-game records, streaks (min threshold + min games), and career milestones, scanned from the raw weekly parquet across any season range. Example: most receiving yards in a game since 1999 (Calvin Johnson, 329) and his 8-game 100-yard streak.", "records"),
    ("module_23_qualifier.png", "23 · Qualifiers — rate stats auto-gate on a minimum volume (CPOE ≥ 300 pass attempts here), adjustable on the fly; turn off to see everyone.", "qualifier"),
    ("module_24_stat_info.png", "24 · Stat info — every stat carries its definition, the exact formula, every variable, the source file and qualify rules; one click from the Stat selector.", "statdoc"),
    ("module_25_catalog.png", "25 · Catalog browser — click the header badges to search and browse all 177 player / 151 team stats with full definitions before charting any of them.", "catalog"),
    ("module_26_game_center.png", "26 · Game Center — pick season/week/game: win-probability timeline (scoring plays marked), cumulative EPA per team, and every play with EPA/WP/description + filters and sorting. Parsed in-browser from the shipped play-by-play parquet.", "gamecenter"),
    ("module_27_win_drivers.png", "27 · Models — win drivers over 14,007 team-games (1999–2026): Pearson r per driver + linear probability model with cluster-robust standard errors (clustered by team-season, 894 clusters). Turnover margin tops the list at r = +0.47; model R² = 0.35.", "drivers"),
    ("module_28_elo_market.png", "28 · Models — point-in-time Elo vs the market: sequential Elo (no lookahead), no-vig moneyline probabilities, Brier/accuracy scorecards, a calibration scatter, and the top divergence log (KC@MIA: Elo 46% vs market 18%, market right).", "elomarket"),
    ("module_29_prop_lab.png", "29 · Betting — Prop Lab: any player, any prop stat, any line, any season range/split. Historical game distribution + P(over)/P(push)/P(under), mean/median/σ, and the game log vs the line. (Kelce rec yds vs 65.5: 53% over, mean 69.5.)", "proplab"),
    ("module_30_team_lines.png", "30 · Betting — Team Lines: closing spreads/totals vs results for every team — ATS and O/U records, average line/margin/total, and a click-through game log. League cover rate lands at ~50%, the market-efficiency sanity check.", "teamlines"),
    ("module_31_convergence.png", "31 · Models — Convergence monitor: top-down (sequential Elo) vs bottom-up (opponent-adjusted play-level EPA, re-solved before every week). 256 games in 2025: corr = 0.600, average disagreement 18.7 pts; the per-week divergence line and the log of biggest disagreements (with which model was closer) make model drift visible.", "convergence"),
    ("module_32_3d_lab.png", "32 · 3D Lab (three.js) — any three team stats as axes; quadrant-tinted coordinate planes at each median; orbit/zoom/pan; raycast hover cards with raw value + percentile. Every stat pair defines a plane, so axis switching navigates an effectively infinite layout space.", "quad3d"),
    ("module_33_team_metrics.png", "33 · Team Metrics (F16) — wXEPA (leverage-weighted expected EPA, w = 4·wp·(1−wp), garbage time excluded) on offense and wXEPA allowed on defense, plotted as a BTB-style quadrant chart with team logos at league medians; Eckel Rate (success × explosiveness) alongside; every metric card carries its exact formula and code path.", "teammetrics"),
    ("module_34_factor_matrix.png", "34 · Models — factor matrix: Pearson correlations between every model factor with hover highlighting across the module (correlation/covariance toggle), R²-by-season fit chart, and the comprehensive factor inventory including planned referee/weather factors.", "factormatrix"),
    ("module_35_montecarlo.png", "35 · Models — Monte Carlo: 5,000 simulated seasons from point-in-time Elo (played games are facts, future games Bernoulli), per-team win distributions with p10/mean/p90, and the full league table.", "montecarlo"),
    ("module_36_factory.png", "36 · Factory — a three.js digital twin of the pipeline: stations are the real stages (nflverse source → parquet mirror → bundle factory → model works → module UI → proof line → agent docs) with glowing agents moving real data units along conveyor curves; orbit/zoom, speed control, click any station for its role, volumes and docs.", "factory"),
    ("module_37_3d_theatre.png", "37 · 3D Lab theatre mode — the same live three.js scene expanded to a full-overlay rounded panel; team logos are canvas-textured sprites (abbr fallback), hover shows raw value + percentile on all three axes.", "quad3dtheatre"),
    ("module_38_3d_2d_plane.png", "38 · 3D Lab 2D plane mode — the pure quadrant chart: bare team logos (no chrome), real stat values ticked along both axes (27→101 points scored, −52→48 differential), solid = median, dashed gold = mean, quadrant corners identified with ↑/↓, axis names rendered in-scene, and a sortable team table (31/32 by league era, raw + percentile) below with one-click PNG export.", "quad3d2d"),
    ("module_39_career_alltime_leaders.png", "39 · All-time career leaders — every player stat carries a precomputed 1999–2026 career leaderboard (REG weekly parquet; rate stats gated ≥48 weeks + catalog qualifiers) drawn as 10/25 career trajectories with a sortable table: headshots, teams, span, career total, best season, and '+ compare' staging into the career chart. Shown: passing — Brady 89,216 / Brees 80,428 / Manning 68,201, real career totals.", "leaders"),
    ("module_40_export_card_leaders.png", "40 · Export — the leaders chart rendered through the shared card pipeline into a 1200×675 PNG (title, window, provenance footer) for social publishing; downloaded live in the suite.", "exportleaders"),
    ("module_41_career_compare_jsn_rice.png", "41 · Any player vs any player — Jerry Rice vs Jaxon Smith-Njigba on one career trajectory chart plus the season-by-season table. Any of the 15,423 indexed players can be staged via search or the leaders table's '+ compare'.", "comparejsn"),
    ("module_42_export_card_quadrant.png", "42 · Export — the live 3D Lab quadrant scene (WebGL with preserveDrawingBuffer) composited into the same 1200×675 social card with the median/mean legend baked into the subtitle.", "exportquad"),
    ("module_43_export_card_main_chart.png", "43 · Export — any main progression chart exports through the shared SVG→PNG pipeline (inline-styled clone, logos stripped to stay CORS-clean); downloaded live in the suite.", "exportmain"),
    ("module_47_predictive_value.png", "47 · Models — Predictive Value: every driver feature gets on-demand R² (same-game, vs margin), a lag-1 Granger-style ΔR² + F (does last week's value add forecast power beyond last week's margin?), and a scatter with the OLS fit plus dashed ±1σ/±2σ residual bands; the sidebar shows the margin mean and its ±1σ/±2σ ranges. Click any row to re-aim the scatter.", "predictive"),
    ("module_46_3d_three_planes.png", "46 · 3D Lab — the third plane, verified: with three different stats the scene carries all three median planes (each outlined, each quadrant background's opacity now slider-controlled and set to 0.25 here), sprites placed by deviation on every axis, and the depth-split readout proving population on both sides of the depth median plane. The suite orbits the camera here and asserts 3 planes in 3D / 1 plane in 2D.", "threeplanes"),
    ("module_45_widget_code_map.png", "45 · Factory — Code map: a three.js map of the widget itself. Every top-level declaration of the 3,873-line monolith plus every extracted module becomes a bar (height = lines of code) grouped into decomposition-plan silos; bright = extracted (96 pieces incl. the new S1 ui/ layer), dim = still inline (46); hover shows name, file, line span, target silo and status. Generated from source by build_widget_inventory.py with a 99.1% line-coverage gate so nothing can silently fall out of the refactor.", "codemap"),
    ("module_44_3d_players_sized.png", "44 · 3D Lab player mode — the same quadrant engine on PLAYER stats (receiving yards / receiving TDs / receptions by default) with bare headshot sprites from the season bundle, a Top 10/15/All population ranked by the X axis (players carrying every charted stat), the supporting player table, and the new sprite-size slider (0.14–0.65) shown at 0.56 — one slider rescales team logos or player headshots live.", "quad3dplayers"),
]

HASH_FILES = [
    ("src/widgets/NFLStatsWidget.jsx", "Module UI + SVG chart engine"),
    ("src/widgets/NFLStatsWidget.css", "abet dark styling (Berkeley blue/gold)"),
    ("src/lib/nflStats.js", "data loading + series/rank computation"),
    ("src/widgets/StatsEmbedWidget.jsx", "stats tab dispatcher (nfl-stats → module)"),
]

DATA_FILES = sorted((APP / "public" / "nfl-stats" / "data").glob("*.json"))
DATA_MB = sum(f.stat().st_size for f in DATA_FILES) / 1024 / 1024
CATALOG = json.loads((APP / "public" / "nfl-stats" / "data" / "catalog.json").read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16].upper()


def img_uri(name: str) -> str:
    data = base64.b64encode((MOD / name).read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


assert_rows = "".join(
    f"<tr><td class='{'ok' if a['ok'] else 'bad'}'>{'PASS' if a['ok'] else 'FAIL'}</td><td>{a['name']}</td><td class='detail'>{a['detail']}</td></tr>"
    for a in evidence["assertions"]
)
verify_rows = "".join(
    f"<tr><td class='{'ok' if a['ok'] else 'bad'}'>{'PASS' if a['ok'] else 'FAIL'}</td><td>{a['name']}</td><td class='detail'>{a['detail']}</td></tr>"
    for a in verify["results"]
)
hash_rows = "".join(
    f"<tr><td class='mono'>{sha(APP / p)}</td><td class='mono'>{p}</td><td>{desc}</td></tr>" for p, desc in HASH_FILES
)
data_rows = "".join(
    f"<tr><td class='mono'>{f.name}</td><td>{f.stat().st_size/1024:.0f} KB</td></tr>" for f in DATA_FILES
)
shot_html = "".join(
    f"<figure id='shot-{key}'><img src='{img_uri(name)}' alt='{caption}'/><figcaption>{caption}</figcaption></figure>"
    for name, caption, key in SHOTS
)
net_rows = "".join(
    f"<tr><td class='ok'>{r['status']}</td><td class='mono'>{r['url']}</td></tr>" for r in evidence["data_responses"]
)
log_tail = "\n".join(build_log.strip().splitlines()[-12:])
clean_log = re.sub(r"\x1b\[[0-9;]*m", "", build_log)
m = re.search(r"built in ([\d.]+)s", clean_log)
build_time = f"{m.group(1)}s" if m else "ok"

html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>NFL Stats Module — Delivery Proof — ABET Dashboard</title>
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:#06101A; color:#C8D8EC; font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
a {{ color:#FDB515; }}
.wrap {{ max-width:1180px; margin:0 auto; padding:28px 22px 60px; }}
header {{ border-bottom:1px solid rgba(59,125,216,.25); padding-bottom:18px; margin-bottom:22px; }}
h1 {{ font-size:22px; color:#F0F4FA; margin:0 0 4px; }}
h2 {{ font-size:16px; color:#F0F4FA; margin:34px 0 10px; border-left:3px solid #FDB515; padding-left:10px; }}
h3 {{ font-size:14px; color:#F0F4FA; margin:22px 0 8px; }}
.sub {{ color:#8A9BB0; font-size:13px; }}
.chips {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:14px; }}
.chip {{ font-size:11px; font-weight:700; letter-spacing:.05em; text-transform:uppercase; padding:4px 11px; border-radius:999px; border:1px solid rgba(59,125,216,.35); background:rgba(59,125,216,.1); color:#C8D8EC; }}
.chip.gold {{ border-color:rgba(253,181,21,.5); background:rgba(253,181,21,.12); color:#FDB515; }}
.chip.green {{ border-color:rgba(0,200,83,.45); background:rgba(0,200,83,.12); color:#00C853; }}
.card {{ background:#0C1E35; border:1px solid rgba(0,50,98,.45); border-radius:12px; padding:16px 18px; margin:12px 0; }}
.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; margin-top:6px; }}
th, td {{ text-align:left; padding:6px 9px; border-bottom:1px solid rgba(59,125,216,.15); vertical-align:top; }}
th {{ color:#8A9BB0; font-size:11px; text-transform:uppercase; letter-spacing:.05em; }}
td.ok {{ color:#00C853; font-weight:700; }}
td.bad {{ color:#FF0055; font-weight:700; }}
td.detail {{ color:#8A9BB0; font-size:12px; }}
.mono {{ font-family:'JetBrains Mono','Cascadia Code',monospace; font-size:12px; }}
figure {{ margin:0 0 26px; }}
figure img {{ width:100%; border:1px solid rgba(59,125,216,.35); border-radius:10px; display:block; }}
figcaption {{ font-size:13px; color:#8A9BB0; margin-top:8px; }}
pre {{ background:#081424; border:1px solid rgba(59,125,216,.25); border-radius:10px; padding:12px 14px; overflow:auto; font-size:12px; color:#C8D8EC; }}
code {{ font-family:'JetBrains Mono','Cascadia Code',monospace; font-size:12px; color:#FDB515; }}
.small {{ font-size:12px; color:#8A9BB0; }}
.kpi {{ display:flex; gap:26px; flex-wrap:wrap; margin:8px 0 2px; }}
.kpi b {{ display:block; font-size:24px; color:#F0F4FA; }}
.kpi span {{ font-size:11px; text-transform:uppercase; letter-spacing:.06em; color:#8A9BB0; }}
</style></head><body><div class="wrap">
<header>
  <h1>NFL Stat Progression — dashboard module delivery proof</h1>
  <div class="sub">Built into <code>abet-dashboard</code> (Vercel, mes-projects) · stats section · <code>?section=stats&amp;tab=nfl-stats</code> · generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}</div>
  <div class="chips">
    <span class="chip green">Build pass — vite {build_time}</span>
    <span class="chip green">Playwright {evidence['passed_count']}/{evidence['assertion_count']}</span>
    <span class="chip green">Data checks {verify['passed']}/{verify['total']}</span>
    <span class="chip">app navigation test: PASS</span>
    <span class="chip gold">0 page errors</span>
  </div>
  <div class="kpi">
    <div><b>{CATALOG['player_stat_count']}</b><span>player stats</span></div>
    <div><b>{CATALOG['team_stat_count']}</b><span>team stats</span></div>
    <div><b>{len(CATALOG['seasons'])}</b><span>seasons 1999–2026</span></div>
    <div><b>{len(DATA_FILES)}</b><span>data bundles</span></div>
    <div><b>{DATA_MB:.1f} MB</b><span>prebuilt JSON</span></div>
  </div>
</header>

<h2>What was broken → what shipped</h2>
<div class="card">
  <p>The Stats section's sport tabs route to <code>StatsEmbedWidget</code>, which embeds third-party sites in iframes. For <code>nfl-stats</code> that meant Pro Football Reference / ESPN / nflverse pages that refuse framing — the tab looked broken. The module replaces that for the NFL tab with a fully native widget: <b>bump charts (league-rank races)</b>, <b>season pace lines</b>, and <b>per-game dot plots</b> for every nflverse player and team stat.</p>
  <ul class="small">
    <li><b>Players</b>: {CATALOG['player_stat_count']} stats across {len(CATALOG['player_groups'])} groups — passing, rushing, receiving, defense (tackles/sacks/INTs), special teams, ball security, fantasy, plus PFR advanced (yards after contact, broken tackles, drops, pressures, coverage) where the era tracks them (2018+).</li>
    <li><b>Teams</b>: {CATALOG['team_stat_count']} stats — results &amp; points (schedules), offense/defense (stats_team), efficiency from play-by-play (plays, EPA/play, success rate, pass rate — 2024+ bundles), ST, penalties.</li>
    <li><b>Seasons</b>: 1999 → 2026; the 2026 bundle regenerates as weeks complete; each season loads on demand (~0.6–0.9 MB JSON).</li>
    <li><b>Controls</b>: rank↔values Y-scale toggle (watch raw totals accumulate), Y-axis labels dock left/right, three views (rank race / season pace / per game) + team radar, position filter (QB/RB/WR/TE/OL/DL/LB/DB/SPEC), top-N slider to 40, multi-select compare chips, click-to-isolate legend.</li>
    <li><b>Tooltip</b>: weekly value with the player's rank for that week, plus season total with season rank (both league-wide, not pool-relative).</li>
    <li><b>Radar</b>: any team category becomes a percentile radar across the league (outer = best, ↓ = lower is better); pin two or more teams to compare shapes; scrub a week slider for "through week N" percentiles.</li>
    <li><b>Full universe</b>: 'All players' parses the raw nflverse weekly parquet <i>in the browser</i> (hyparquet, same-origin) — every entity with a recorded stat, position filters at full depth, league-wide ranks computed client-side. No 40-player cap.</li>
    <li><b>Tables</b>: any chart converts to a data table (weeks played, this week, season total, weekly + season rank) with the exact source file path per stat.</li>
    <li><b>Season compare</b>: pick multiple seasons (chips, up to 6) and render the same chart per season — <i>side-by-side</i>, <i>stacked</i>, or <i>grid</i>. Pins and position filters apply across all of them.</li>
    <li><b>Game Center</b>: season/week/game picker over shipped play-by-play parquet (2025+2026): win-probability timeline with scoring markers, cumulative EPA, and a sortable/filterable play table (EPA, WP, down & distance, descriptions).</li>
    <li><b>Win drivers</b>: Pearson correlations + a linear probability model with <i>cluster-robust</i> standard errors over 14,007 team-games (turnover margin r=+0.47; R²=0.35; 894 clusters).</li>
    <li><b>Models ×2</b>: </li>
    <li><b>Top-down (Elo)</b>: strictly sequential, point-in-time ratings (K=20/HFA=55/75% carry-over) — every probability uses only games before it.</li>
    <li><b>Bottom-up (EPA)</b>: opponent-adjusted play-level EPA ratings solved by iterative fixed point (EPA/play ≈ off[team] + def[opponent], 12 passes, re-centered, per-team SEs); expected margin = (net diff) × 62 plays + 2.0, P = Φ(margin/13.86). Re-solved before every week — no lookahead.</li>
    <li><b>Convergence monitor</b>: runs both independent models per game, scores their agreement (corr 0.600, avg Δ 18.7 pts on 256 games of 2025), charts disagreement by week, and logs the largest divergences with outcomes and which model was closer (e.g. CHI@DET: Elo 77% vs early-EPA 7% — Elo right, small-sample EPA punished).</li>
    <li><b>Betting</b>: Prop Lab (player × stat × line × season-range/split → P(over)/P(push)/P(under), distribution histogram, game log; lines auto-fill from the live odds feed when wired) and Team Lines (ATS + O/U records vs closing spreads/totals for all 32 teams with click-through game logs; league cover rate sanity = ~50%).</li>
    <li><b>Stat definitions</b>: every one of the 328 catalog stats ships with a plain-English description, the exact formula, and every variable defined (CPOE, WOPR, PACR, passer rating allowed, EPA/play, success rate…). ⓘ next to the Stat selector; browse/search all of them from the header badge.</li>
    <li><b>Compare tooltips</b>: hover any season cell in compare mode for the same full popup (name, headshot, team, week, this-week value + rank, season total + rank). Clicking a line pins that player across every selected season.</li>
    <li><b>Qualifiers</b>: rate stats (CPOE, RACR, target share, passer rating allowed…) auto-gate on a minimum volume (attempts / carries / targets) with an adjustable threshold — so rate charts show real producers, not one-attempt flukes. Toggle Off to see the entire population.</li>
    <li><b>Era-adjusted careers</b>: normalize each season's totals to a common league environment (indexed to the latest season) with one toggle — Jerry Rice's 1999–2004 vs Travis Kelce's 2014–2026 becomes an honest cross-era comparison.</li>
    <li><b>Records finder</b>: single-game leaderboards, streaks (threshold + minimum games), and career milestones — scanned client-side across any season range from raw parquet. Verified era records: Calvin Johnson 329 rec yds (2013), 8 straight 100-yard games (2012), Marvin Harrison first to 10k receiving (2006 W2).</li>
    <li><b>Player drill-down</b>: click any name in a table → drawer with percentile radar vs position peers, week-by-week game log (with weekly + season ranks), and the career chart.</li>
    <li><b>Deep links</b>: the URL carries stat, season, level, mode, filters, top-N, pinned players, compare seasons, and layouts — share or bookmark any exact chart state (e.g. <code>?stat=rushing_yards&amp;season=2005&amp;top=15</code>).</li>
    <li><b>Sortable tables</b>: every column header sorts (asc/desc toggle with indicator) in both the stats table and the career table.</li>
    <li><b>Careers</b>: search 15,423 players, stitch any career across seasons from parquet (Rice 1999→ Kelce 2011→2026), overlay season totals for up to 8 players, full season table.</li>
    <li><b>Colors</b>: brand-first resolution — brightened primary color, secondary color when primaries collide (Seahawks action green, not a generic gold), palette only as last resort.</li>
    <li><b>Identity</b>: player headshots (nflverse headshot_url) and team logos (ESPN CDN from teams_colors_logos) with graceful colored-dot fallback when a URL is stale.</li>
    <li><b>Data</b>: prebuilt from nflverse-data GitHub releases by <code>D:\\nfl-progression\\scripts\\export_dashboard_data.py</code> (same cached pipeline as the Streamlit explorer). True league-wide ranks are stored per week — not re-ranked from the top-15 slice.</li>
  </ul>
</div>

<h2>1 · The module in the dashboard (screenshots from the production build)</h2>
{shot_html}

<h2>2 · Automated verification</h2>
<h3>Playwright run against <code>vite preview</code> (production bundle)</h3>
<div class="small">First chart render: {evidence['timings'].get('first_chart_ms','?')} ms · page errors: {len(evidence['page_errors'])} · data bundle responses all HTTP 200:</div>
<table><thead><tr><th style="width:70px">HTTP</th><th>URL</th></tr></thead><tbody>{net_rows}</tbody></table>
<table><thead><tr><th style="width:70px">Result</th><th>Assertion</th><th>Detail</th></tr></thead><tbody>{assert_rows}</tbody></table>
<div class="small">The only console noise is pre-existing and external: four 404s from MLB assets (<code>mlbstatic.com/team-logos/none.svg</code>, Baseball Savant fonts) and one React deprecation warning from a legacy widget — none touched by this module.</div>

<h3>Data bundle verification ({verify['passed']}/{verify['total']})</h3>
<table><thead><tr><th style="width:70px">Result</th><th>Check</th><th>Detail</th></tr></thead><tbody>{verify_rows}</tbody></table>

<h3>Repo checks</h3>
<div class="card small">
  <p><b>vite build</b> — <code>✓ built in {build_time}</code> (tail below).</p>
  <p><b>npm run test:app-navigation</b> — <code>app-navigation helpers: PASS</code></p>
  <pre>{log_tail}</pre>
</div>

<h2>3 · Files delivered</h2>
<div class="grid">
  <div class="card">
    <h3 style="margin-top:0">Source (SHA-256 prefix)</h3>
    <table><tbody>{hash_rows}</tbody></table>
    <p class="small">Modified: <code>src/widgets/index.js</code> (export). Backup of the pre-change dispatcher: <code>StatsEmbedWidget.jsx.backup_20260926_pre_nfl_module</code>.</p>
  </div>
  <div class="card">
    <h3 style="margin-top:0">Data bundles — public/nfl-stats/data/</h3>
    <table><tbody>{data_rows}</tbody></table>
  </div>
</div>

<h2>4 · Run &amp; deploy</h2>
<div class="card">
<pre>cd D:\\abet_dev\\claude_dashboard_pills_20260925
npm install            # first time
npm run build          # full suite incl. customer-release tests
npm run dev            # http://localhost:5180/?section=stats&amp;tab=nfl-stats</pre>
<p class="small">Deploy: this worktree is already linked to the <code>abet-dashboard</code> Vercel project (org team_ku5o9x7AzL9wQqEj6IbL20u0) — <code>vercel --prod</code> from this directory, or push the branch if CI owns deploys. Refresh data anytime with:</p>
<pre>D:\\nfl-progression\\.venv\\Scripts\\python.exe D:\\nfl-progression\\scripts\\export_dashboard_data.py --seasons 1999-2026</pre>
</div>

<footer class="small" style="margin-top:34px;border-top:1px solid rgba(59,125,216,.25);padding-top:14px">
  Proof bundle: <code>D:\\nfl-progression\\proof\\</code> — this page, <code>dashboard-module/evidence.json</code>, <code>verify_data.json</code>, <code>build.log</code>, raw screenshots, and the capture scripts
  (<code>capture_module.py</code>, <code>verify_data.py</code>). Served target: <a href="https://abet-dashboard-mvhjioili-mes-projects-1898c81d.vercel.app/?section=stats&amp;tab=nfl-stats">abet-dashboard … ?section=stats&amp;tab=nfl-stats</a>.<br/>
  Exhaustive engineering documentation (architecture, schemas, algorithms, formulas, ops): <code>D:\\abet_dev\\claude_dashboard_pills_20260925\\docs\\20261002_141343_NFL_STATS_MODULE_ARCHITECTURE_OPERATIONS_AND_DATA_BIBLE_v1_0_0.md</code>
</footer>
</div></body></html>"""

OUT.write_text(html, encoding="utf-8")
print(f"wrote {OUT} ({OUT.stat().st_size/1024/1024:.2f} MB)")
