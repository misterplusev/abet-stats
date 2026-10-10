# NFL Stats Module — Exhaustive Documentation

Everything about the NFL Stat Progression module: architecture, every file, every script,
data schemas, algorithms, exact formulas, the proof system, and operations.
Written so a new agent (or human) can operate, extend, debug, and re-verify the whole
system with zero missing context. Last updated: 2026-09-28 (session build).

---

## 1. What this is

A fully client-side NFL analytics module embedded in the ABET dashboard
(`?section=stats&tab=nfl-stats`). It renders week-by-week stat-leader progression charts
(bump/rank races, cumulative pace, per-game dots), team radars, records/streaks/milestones,
career stitching across eras, full-universe "all players" analysis parsed from raw nflverse
parquet **in the browser**, sortable data tables, player drill-down cards, stat definitions
with exact formulas, deep-linkable URLs — with a Playwright proof pipeline that regenerates a
self-contained evidence HTML on demand.

No backend. No API keys. Data comes from public nflverse GitHub releases; heavy data
(weekly parquet, ~20.5 MB) is shipped same-origin so the browser can parse it without CORS.

---

## 2. Repo map (exact paths)

Dashboard worktree (Vercel project `abet-dashboard`, repo `misterplusev/abet-mlb-monitor-widgets`):
- `D:\abet_dev\claude_dashboard_pills_20260925\`

```
src/
  widgets/
    NFLStatsWidget.jsx        # the entire module UI + chart engines (1948 lines)
    NFLStatsWidget.css        # all module styling, prefix nsw- (689 lines)
    StatsEmbedWidget.jsx      # dispatcher: sportTab==='nfl-stats' -> NFLStatsWidget (156)
    index.js                  # widget exports incl. NFLStatsWidget (68)
  lib/
    nflStats.js               # catalog/season/docs loading, rank+chart math, colors (233)
    nflParquet.js             # browser parquet: full pools, careers, radar, records (383)
scripts/publish/
  nfl_stats_export.py         # standalone cloud exporter: nflverse -> JSON bundles (653)
  augment_catalog.py          # adds stat_sources + qualifiers, builds players_index.json (117)
  build_stat_docs.py          # builds stat_docs.json: descriptions/formulas/variables (248)
.github/workflows/
  refresh-nfl-stats-data.yml  # PARKED scheduled data refresh (not pushed yet) (62)
refresh-nfl-data.bat          # local one-click data refresh + rebuild (15)
public/nfl-stats/
  data/                       # 31 files: season bundles, catalog, players_index, stat_docs
  parquet/                    # 28 weekly player parquet files (1999-2026, 20.5 MB)
docs/
  20261002_141343_NFL_STATS_MODULE_ARCHITECTURE_OPERATIONS_AND_DATA_BIBLE_v1_0_0.md         # this document
```

Proof bundle (outside repo, D: drive):
```
D:\nfl-progression\
  proof/
    capture_module.py         # Playwright proof suite (~76 assertions) (474)
    verify_data.py            # 20 data-integrity checks (113)
    build_module_proof.py     # builds self-contained proof HTML (229)
    nfl-dashboard-module-proof.html   # the deliverable proof page (~10 MB)
    dashboard-module/         # screenshots (module_*.png), evidence.json, verify_data.json, build.log
    OPEN-PROOF.bat            # opens proof HTML + serves proof dir on :8612
    SERVE-DASHBOARD.bat       # runs vite preview on :8611 + opens browser
    START-LOCAL-SERVERS.bat   # starts both servers + opens both pages (use this one)
  scripts/
    export_dashboard_data.py  # legacy Streamlit-coupled exporter (superseded; kept for ref)
```

---

## 3. Architecture / data flow

```
nflverse-data GitHub releases (public)
  stats_player/stats_player_week_{season}.parquet     (1999-2026)
  stats_team/stats_team_week_{season}.parquet
  pfr_advstats/advstats_week_{rush,pass,rec,def}_{season}.parquet   (2018+)
  pbp/play_by_play_{season}.parquet                   (team efficiency, 2024+ bundles)
  schedules/games.parquet                             (points, wins, lines)
  teams/teams_colors_logos.parquet                    (colors, ESPN logos)
  players/players.parquet                             (pfr_id crosswalk, headshots)
        |
        |  scripts/publish/nfl_stats_export.py  (downloads, computes, writes)
        v
public/nfl-stats/data/            public/nfl-stats/parquet/
  season_{1999..2026}.json          stats_player_week_{season}.parquet  (copied once)
  catalog.json                      |
  players_index.json                |  parsed IN BROWSER by hyparquet (same-origin)
  stat_docs.json                    v
        |                       NFLStatsWidget.jsx + nflParquet.js
        +--------------------->  (bundles = instant charts; parquet = full universe,
                                 careers, records, player cards, tables)
        v
Playwright proof: capture_module.py -> evidence.json -> build_module_proof.py -> HTML
```

Two data lanes:
1. **Bundles (JSON)** — precomputed top-40 pools per stat with weekly values `v`, cumulative
   league ranks `r`, weekly league ranks `wr`. Instant loads, all 28 seasons.
2. **Parquet (same-origin copies of nflverse weekly player files)** — full universe computed
   on demand in-browser: "All players" pools, careers, records scans, player radar/game logs.

---

## 4. Data products & schemas

### 4.1 `data/season_{season}.json` (885 KB modern, 384 KB partial 2026)
```json
{
  "season": 2025,
  "generated_at": "2026-09-28T21:57:04Z",
  "source": "nflverse-data releases (...)",
  "top_n": 15,                       // per-stat pool hint (superseded by catalog.top_n=40)
  "weeks": [1..18],                  // REG season weeks present
  "players": { "<player_id>": ["Name","TEAM","POS","headshot_url","position_group"] },
  "player_stats": { "<statKey>": [ { "id": "...", "v": [..], "r": [..], "wr": [..] }, ... ] },
  "team_stats":   { "<statKey>": [ { "id": "SEA",  "v": [..], "r": [..], "wr": [..] }, ... ] },
  "team_ids": ["ARI", ...]
}
```
- `v` weekly values (null = no game), `r` cumulative league rank per week (min-method, all
  entities league-wide, null before first game), `wr` weekly (single-game) league rank.
- Pool selection per stat: **top 30 overall + top 6 per position group, capped at 40**,
  ordered by final total desc. Teams: all ≤32.
- PFR stat ids are prefixed `pfr:` (e.g. `pfr:TaylJo02`); players map carries their
  crosswalked position + headshot.

### 4.2 `data/catalog.json`
```json
{
  "generated_at": "...", "top_n": 40,
  "seasons": [1999..2026],
  "season_weeks": {"2025": 18, ...},
  "player_groups": [{ "group": "Passing", "stats": [{ "key":"passing_yards","label":"Passing yards","agg":"sum","fmt":"i0" }]}],
  "team_groups":   [ ... same shape ... ],
  "player_stat_count": 177, "team_stat_count": 151,
  "team_meta": { "SEA": ["Seattle Seahawks","#002244","#69BE28","https://a.espncdn.com/i/teamlogos/nfl/500/sea.png"] },
  "stat_sources": { "player": {"passing_yards":"stats_player/stats_player_week_{season}.parquet", ...},
                    "team":   {"plays":"pbp/play_by_play_{season}.parquet", ...} },
  "qualifiers": { "passing_cpoe": {"by":"attempts","min":100}, ... }
}
```
- `agg`: `sum` (counting) or `mean` (rates). `fmt`: `i0` integer / `f2` two decimals.
- 177 player + 151 team = union of stat keys across all seasons. Early seasons have fewer
  (PFR adds ~40 keys from 2018; pbp-derived team keys from 2024 bundles).

### 4.3 `data/players_index.json` (2.5 MB, 15,423 players)
`{ "<player_id>": {"n":name,"p":position,"g":position_group,"h":headshot,"f":firstSeason,"l":lastSeason,"t":lastTeam} }`

### 4.4 `data/stat_docs.json` (128 KB, 328 entries + `variables` glossary)
Per stat: `{label, group, agg, fmt, source, qualifier, desc, formula, vars{sym:meaning}, notes, auto?}`.
Curated entries in `build_stat_docs.py` (CPOE, WOPR, PACR, RACR, EPA, success rate, fantasy,
tackles composite, passer-rating-allowed, YAC, team metrics…); the rest template-generated
(sum/mean + source + era notes). Variables glossary shared at `docs.variables`.

### 4.5 `parquet/` — same-origin mirrors (all parsed in-browser by hyparquet)
```
stats_player_week_{1999..2026}.parquet   # weekly player stats (full universe, careers, records)
play_by_play_2025.parquet                # 19.4 MB — Game Center (2025 season)
play_by_play_2026.parquet                # 3.4 MB  — Game Center (current season)
games.parquet                            # 0.5 MB  — game index (scores, weather, roof)
```
Column-pruned on load (`PLAY_COLUMNS` / `GAME_COLUMNS` in nflParquet.js). Older pbp seasons
will load through the planned Cloudflare Worker proxy. Used for: full pools, careers, records
scans, player radar, game logs, play-by-play browser, WP/EPA timelines.

---

## 5. Module internals (`NFLStatsWidget.jsx`)

### 5.1 Component inventory
| Component | Role |
|---|---|
| `NFLStatsWidget` | Root: catalog/season/docs loading, all state, controls, renders modes |
| `BumpChart` | Rank race (or cumulative values when Y=same rank↔values toggle) SVG engine |
| `LineChart` | Season-pace (cumulative) and per-game dot lines |
| `RadarChart` | Team/player percentile radar (rings, axes, polygons, `note` caption) |
| `TableView` | Sortable stats table + source path |
| `CareerPanel` / `CareerChart` / `CareerTable` | Player search, career overlay, era toggle, sortable table |
| `RecordsPanel` | Single-game / streaks / milestones finder over parquet |
| `PlaysPanel` + `GameTimeline` | Game Center: game picker, WP timeline + cumulative EPA, filterable/sortable play table |
| `ModelsPanel` + `ModelMarketScatter` | Models: win drivers, team Elo table, Elo-vs-market scorecards + divergence log |
| `BettingPanel` + `PropHistogram` | Betting: Prop Lab distributions vs a line; Team Lines ATS/O-U vs closing lines |
| `PlayerCard` | Drawer: percentile radar, game log, career chart |
| `CompareCell` | One season cell in compare mode with its own hover tooltip |
| `Tooltip`, `Legend`, `Face` | Shared popup (headshot/logo + ranks), chips, avatar w/ fallback |
| `StatDocCard`, `CatalogModal` | Definitions/formulas panel; searchable 328-stat browser |

### 5.2 State model (root)
`catalog, seasonData, status/error` (bundle lane) · `season, level, category, statKey` ·
`mode` (`rank|pace|game|table|career|records|radar`) · `rankYMode` (`rank|value`), `ySide` ·
`posFilter`, `topN` · `pinnedIds[]` (multi-select compare) · `hoverId` ·
`fullMode/fullData/fullStatus/fullVolumes` (parquet lane) · `qualify/qualMin` ·
`compareMode/compareSeasons/compareLayout/compareData` · `docs/showDoc/catalogLevel` ·
`playerCard` · `radarWeek` · URL-synced via `readUrlState()` + replaceState effect.

### 5.3 URL state (deep links)
Params: `stat, level, season, mode, pos, top, cmp, cmpseasons, cmplayout, full, players`.
Example: `?section=stats&tab=nfl-stats&stat=rushing_yards&season=2005&top=15`.
URL stat resolution happens once at catalog load (do NOT add a second category↔stat
reconciler — that caused a 300 renders/sec ping-pong loop; the validation effect is the single
owner).

### 5.4 Chart math (`nflStats.js`)
- `computeChart(seasonData, catalog, level, statKey, topN, posFilter, qualifier)`:
  raw pool → position filter → qualifier filter (`volumes.get(id) >= min`) → slice topN →
  per entity: running sum or mean (`runningAccumulate`), true ranks from bundle `r`/`wr`.
  Returns `poolSize = filtered.length` (filtered!), `rawPoolSize`, `availableGroups`.
- `rankScaleOf(chart)`: display cap = min(max(2×series,12),40); clipped ranks; step 1/2.
- `valueScaleOf(chart, kind)`: min/max scale + nice ticks (`niceTicks` 1/2/2.5/5/10 steps).
- Colors (`resolveColors`): per team — primary color if luminance ≥ 0.42 else brightened
  toward white; **if the resolved color collides with an already-used one, try the team's
  secondary color** (this is why Seahawks = action green: SEA and NE share #002244); palette
  fallback only as last resort. Player teams resolved the same way.
- `computeRadar(seasonData, catalog, statKeys, uptoWeek)`: team percentile axes, `LOWER_BETTER`
  set inverts; used by team radar and (via parquet variant) player radar.
- `formatValue/formatCompact`: `i0` → thousands-separated ints; `f2` → 2 decimals.

### 5.5 Parquet lane (`nflParquet.js`)
- `loadWeekly(season)` — fetch same-origin parquet → `parquetReadObjects` (cached per session).
- `buildStatSeason(rows, statKey, agg)` — bundle-shaped object for ONE stat, full universe;
  computes cumulative arrays + cum ranks + weekly ranks in JS (competition rank, ties share).
- `loadFullPool(season, statKey, agg)` — cached pool used by "All players" mode.
- `computePlayerRadar(season, playerId, group, statKeys, metaByKey)` — percentile vs position
  peers; skips axes with <3 peers; `LOWER_KEYS` invert.
- `playerGameLog(season, playerId, statKey, agg)` — weekly rows desc with cum/wrank/srank + team/opp.
- `collectPlayerGames` (internal) — per (player, week) aggregation across any season range.
- `scanSingleGameRecords(statKey, seasons)` — top 50 games sorted desc.
- `scanStreaks(statKey, seasons, threshold)` — runs of consecutive *player games* ≥ threshold
  (spans seasons); returns 50 longest with start/end season+week.
- `scanMilestones(statKey, seasons, threshold)` — first crossing per player (season+week+at),
  final in-era career total, games. **Totals cover the 1999+ weekly era only.**
- `buildCareer(playerIds, statKey, agg, seasons)` — per-season totals/games/team per player +
  `leagueTotals` (sum of all league values per season) for era adjustment.

### 5.6 Era adjustment (exact math)
For sum stats only: adjusted = raw × (leagueTotal[baselineSeason] / leagueTotal[season]),
baseline = latest season in the career range. Displayed tooltip shows adjusted and raw.

### 5.7 Qualifiers (exact semantics)
Catalog `qualifiers[key] = {by, min}` for rate stats. Effective volume = the `by` stat's
season final (sum or mean per its agg). Applied after position filter, before top-N slice.
Default mins: passing→attempts 100 · rushing→carries 50 · receiving→targets 25 · coverage→
def_targets 25 · YAC/att→carries 50. UI: On/Off + numeric input; caption shows `≥N label`.

### 5.8 Records algorithms (exact)
- Single game: aggregate stat by (player_id, week) per season → collect all → sort desc → 50.
- Streaks: per player, all games ordered by (season, week); run where value ≥ threshold;
  flush on miss; sort by length desc; UI filters `length >= minLen` (default 3).
- Milestones: per player chronological cumulative sum; record first week total ≥ threshold;
  sort by crossing (season, week).

### 5.9 Player card
Entry: click any name button in Table view (`onOpenPlayer`). Contents: header (face, name,
pos·team, seasons-in-data), percentile radar vs position peers for the CURRENT season (up to
12 category stats), game log for the season (wk/team/opp/value/wk rank/cum/rank), career chart
(parquet, raw). Auto-loads (parquet cached after first open).

### 5.10 Stat info + catalog
ⓘ button next to the Stat selector toggles `StatDocCard` for the current stat (desc, formula
in monospace, variables list, notes, source path, qualify rule, agg semantics). Header badges
("177 player stats" / "151 team stats") open `CatalogModal`: search all stats, click a row for
its full doc, "Chart this stat" switches level/category/stat.

### 5.11 Models (`src/lib/nflModels.js` + `ModelsPanel`)
Three sub-views, all client-side:
- **Win drivers**: `buildTeamGames(seasons)` joins `team_week_{season}.parquet` with
  `games.parquet` into team-game rows (features + win as 1/0.5/0). `pearson()` per feature;
  `lmCluster()` fits a linear probability model `win = α + β·home + Σ βᵢ·z(featureᵢ)`
  (features standardized) and computes **cluster-robust (sandwich) SEs** clustered by
  team-season: Σ_g (X_g'u_g)(X_g'u_g)'. Verified 1999–2026: n=14,007, 894 clusters,
  turnover margin r=+0.474, R²=0.350.
- **Team Elo**: `computeElo(games)` — strictly sequential (each probability uses only prior
  games): P(home) = 1/(1+10^(−((R_h+55)−R_a)/400)), K=20, 75% mean reversion between seasons.
  `endOfSeasonRatings()` snapshots ratings + W-L-T per season end. No lookahead by construction.
- **Elo vs Market**: `marketHomeProb()` = no-vig moneyline (American→prob, normalized) with
  spread fallback P = Φ(margin/13.86). Scorecards: straight-up accuracy + Brier for both,
  calibration scatter (market x, Elo y, colored by result), and the top-25 divergence log.
  These are the convergence/divergence monitors requested in the original roadmap, v1.
- **Bottom-up EPA model** (`buildEpaRatings`, `buildEpaRatingsByWeek`, `epaHomeProb`):
  play-level aggregation with opponent adjustment. Model: `epa_per_play(team,game) ≈
  off[team] + def[opp]` solved by iterative fixed point (SRS-style, 12 passes, re-centered each
  pass); per-team SE from residual variance/√games. Matchup: `net = off − def` (def > 0 =
  allows more EPA = weaker), `margin = (net_home − net_away) × 62 plays + 2.0` HFA,
  `P(home) = Φ(margin / 13.86)`. `buildEpaRatingsByWeek` re-solves ratings before EVERY week
  (point-in-time, no lookahead) and is cached per season.
- **Convergence monitor** (Models → Convergence): joins both independent models per game
  (Elo as of kickoff; EPA ratings as of that week), reports games compared, corr(Elo, EPA),
  average |Δ|, each model's straight-up accuracy, a by-week disagreement line chart, the
  final EPA ratings table (off/def/net/GP), and the top-25 divergence log with outcomes and
  which model was closer. Verified on 2025: 256 games, corr 0.600, avg Δ 18.7 pts,
  Elo 62.9% vs EPA 57.4% straight-up.

### 5.12 Betting (`BettingPanel`, helpers in `nflModels.js` / `nflParquet.js`)
- **Prop Lab**: `buildPropDistribution(playerId, statKey, seasons)` collects the player's
  per-game values across seasons from `stats_player_week_*.parquet` (games without a box-score
  row excluded; joined to `games.parquet` for opponent/home-away). Outputs n, P(over) =
  count(v > line)/n, P(push) = count(v = line)/n (integer lines only), P(under), mean, median,
  σ, a 24-bucket histogram with the line drawn, and the last-25 game log with OVER/under flags.
- **Team Lines**: for each REG game, team spread = `spread_line` (home) or its negation (away);
  ATS = margin + line → W/L/P; total vs `total_line` → O/U/P. Table per team for the season
  (ATS W–L–P, O/U, avg line/margin/total) sorted by ATS net, click-through game log. League
  aggregate cover rate is the published market-efficiency sanity check (~50%).
- Live prop lines: the Line input is manual today; wiring the existing odds pipeline
  (TheOddsAPI / Supabase props) into that field is the next integration step.

---

## 6. Exporter (`scripts/publish/nfl_stats_export.py`)

CLI: `python nfl_stats_export.py --seasons 1999-2026 --out public/nfl-stats/data --cache <dir> [--refresh]`
1. Downloads each source parquet (cached by URL-derived filename).
2. Player weekly: REG weeks; all numeric columns minus meta; derived `def_tackles_total =
   solo + tackle_assists`, `total_yards`, `off_plays`, `total_tds`.
3. PFR rush/pass/rec/def: prefixed ids, crosswalked positions/headshots from players.parquet.
4. Team weekly + schedules (points_for/against, point_diff, wins) + pbp-derived metrics for
   2024-2026 bundles (plays, EPA/play, success rate, pass rate, yards/play, explosive,
   turnovers, sacks allowed, 3rd/4th down rates; EPA/success null pre-2006).
5. `pack_panel`: pivot (entity×week), `sum` → `fillna(0).cumsum`; `mean` → expanding mean
   (transpose trick for pandas 3); ranks via `rank(axis=0)` (NOT axis=1); weekly ranks via
   pivot rank; pool = top30 + top6/position, cap 40; values rounded, non-finite → null;
   `allow_nan=False` hard gate.
6. Writes `season_{season}.json`; then rebuilds `catalog.json` (merging all existing season
   files) and `players_index.json`.
`augment_catalog.py` adds `stat_sources` + `qualifiers` (rerun after catalog rebuilds from
existing files). `build_stat_docs.py` regenerates `stat_docs.json`.

Data freshness reality: nflverse publishes after games (stats/team/pbp ~evening ET; PFR
advstats typically Tuesday). Re-run the exporter to refresh; 28-season full run ≈ 25-30 min
cached, single-season ≈ 30-60 s.

---

## 7. Proof & verification system

- `proof/verify_data.py` — 20 checks: strict JSON parse of all 29 bundles (rejects
  NaN/Infinity), catalog coverage 1999-2026, known-total spot checks (Stafford 4,707; Burrow
  4,918; Barkley 2,005; Brooks 180; JSN 1,793; YAC Taylor 759; Beuerlein 4,436; Rams 518 PF;
  DAL 511 PA; 2026 = 3 weeks…), rank ordering sanity, no non-finite values.
- `proof/capture_module.py` — Playwright suite (~76 assertions) against `vite preview` on
  127.0.0.1:8611: chart rendering, position filter, full-universe parquet (474 receivers),
  compare + tooltips, qualifiers (38→24 CPOE), stat docs, catalog (177 rows), tables +
  sorting, player card (radar/game log/career), records (Megatron 329 / 8-game streak /
  Harrison first 10k), deep links, hamburger navigation, team radar + weekly radar, multi-
  select, tooltip weekly/season ranks, colors, 1999+2026+2025 seasons. Writes
  `dashboard-module/evidence.json`; exits non-zero on any failure.
- `proof/build_module_proof.py` — inlines 25 screenshots as base64 + evidence tables into
  `nfl-dashboard-module-proof.html` (self-contained, opens via file://).
- Run everything:
  ```
  cd D:\abet_dev\claude_dashboard_pills_20260925
  node node_modules\vite\bin\vite.js build
  start preview (8611):  D:\nfl-progression\proof\START-LOCAL-SERVERS.bat
  python D:\nfl-progression\proof\capture_module.py     (env: PLAYWRIGHT_BROWSERS_PATH=D:\nfl-progression\.cache\pw-browsers, venv python)
  python D:\nfl-progression\proof\verify_data.py
  python D:\nfl-progression\proof\build_module_proof.py
  ```

---

## 8. Automation & operations

- `refresh-nfl-data.bat` (repo root): re-exports 2026 via the standalone exporter (`--refresh`)
  then `vite build`. Local, one double-click.
- `.github/workflows/refresh-nfl-stats-data.yml` (PARKED — not pushed): Mondays 03:30 UTC +
  Tuesdays 12:30 UTC + manual; installs pandas/pyarrow/requests; exports current season;
  strict-JSON gate; commits `public/nfl-stats/data` only if changed → Vercel redeploys.
  Requires `scripts/publish/*` + data committed to the repo first. Repo has **no other
  workflows**; enabling is additive.
- Servers: dashboard preview `:8611` (vite preview of dist), proof files `:8612`
  (python http.server). They die when the assistant session ends — use the bats.
- Vercel: worktree is linked to project `abet-dashboard` (org team_ku5o9x7AzL9wQqEj6IbL20u0);
  `vercel --prod` from the worktree or push the branch. Not deployed by assistant without ask.
- Backups: `src/widgets/StatsEmbedWidget.jsx.backup_20260926_pre_nfl_module` (pre-module).

---

## 9. Constraints, gotchas, lessons

1. **1999+ only** — nflverse weekly era. Milestones/careers count in-era production only
   (labeled in UI).
2. **PFR stats 2018+** — availability differences by season are natural, not bugs.
3. **Rank semantics** — `r`/`wr` are true league-wide ranks computed at export time; the
   client never re-ranks from a truncated pool.
4. **Pool vs filtered pool** — `poolSize` reported is post-filter (position/qualifier);
   `rawPoolSize` is the unfiltered count.
5. **Full mode only carries the selected stat** (+ its qualifier volume) in memory; stat
   switches trigger a cached rebuild. The slider max reads the raw full-pool length.
6. **Single reconciler rule** — category↔stat validity is owned by ONE effect; adding a second
   reconciler caused an infinite render loop (300+/s) that detached DOM nodes. Don't.
7. **hyparquet needs ArrayBuffer** (not Node Buffer). Browser fetch is fine.
8. **CORS** — direct browser fetches to github release assets are blocked (no ACAO); that's why
   parquet is mirrored same-origin under `public/nfl-stats/parquet/`. A Cloudflare Worker
   proxy is the planned alternative for on-demand seasons (PBP explorer).
9. **Headshots/logos** — hotlinked (nfl.com static, ESPN CDN) with colored-dot fallback via
   `Face` onError. No local mirror yet.
10. **Data sizes** — bundles ≈ 47 MB total; parquet ≈ 20.5 MB; proof HTML ≈ 10 MB. `vite build`
    copies all of `public/` into `dist/` (build ~30 s, occasionally ~3 min on cold FS).
11. **npm** — install with `npm install --no-audit --no-fund`; esbuild postinstall may be
    blocked by allowScripts but builds work. Use `node node_modules\vite\bin\vite.js build`
    directly (npx tries the network and can fail with ECOMPROMISED lock checks).

---

## 10. Change log (this build arc)

1. v1: Streamlit explorer (D:\nfl-progression) → dashboard module (bump/pace/dot, 1999-2026,
   player+team, position filters, tooltips, team colors, proof pipeline).
2. Y labels left/right · Rank↔Values toggle · season-pace crash fix (format string called as
   function) · headshots/team logos + secondary-color collision fallback.
3. Deeper pools (top30+6/group, cap 40) · position chips · weekly+season ranks in tooltip
   (export `wr`) · multi-select pins · team radar + weekly radar ("through week N").
4. Full universe via same-origin parquet (hyparquet) · compare-season layouts (side/stacked/
   grid) · sortable tables + source paths · career stitching + season tables · player card.
5. Records/streaks/milestones finder · qualifiers (rate-stat volume gates) · era-adjusted
   careers (league-total indexing) · stat docs with exact formulas + variables · catalog
   browser · compare-cell tooltips · deep-link URL state.
6. Game Center v1 (season/week/game picker, WP timeline with scoring markers, cumulative EPA,
   filterable/sortable play table) on shipped 2025+2026 play-by-play parquet · college logo fix
   (ESPN 761-team id table, no more mascot-slug garbage; Alabama State ≠ Alabama).
7. Models v1: win-driver correlations + cluster-robust LPM, point-in-time team Elo
   (all seasons from schedules), Elo-vs-market scorecards + calibration scatter + divergence
   log. Shipped `team_week_{1999..2026}.parquet` (3.2 MB) and play-by-play/games mirrors.
8. Betting v1: Prop Lab (player distributions vs any line, splits, histogram) + Team Lines
   (ATS/O/U records vs closing spreads/totals for all teams, click-through logs). Verified
   league ATS cover = 50.0% and Kelce-vs-65.5 = 53.0% over since 2019.
9. Models v2: bottom-up opponent-adjusted EPA ratings (iterative fixed point with SEs,
   point-in-time by week) + the Convergence monitor (top-down Elo vs bottom-up EPA: scorecard,
   weekly disagreement chart, divergence log with which model was closer). Verified 2025:
   corr 0.600, avg Δ 18.7 pts, 256 games.
10. UX/fix pass: pill-shaped horizontally-scrollable view switches + mobile media queries ·
    starfield backdrop · THE canonical ABET chip loader (AbetChipLoader) replaces generic
    spinners · records position pills now actually filter the parquet scans · radar overhaul
    ("Radar Charts": all teams drawn faint, division-grouped team pills covering all 32,
    bigger canvas/labels, hover titles with percentile + raw, Chargers-disappearing bug fixed
    by decoupling pills from the top-N single-stat pool) · team logos in the Elo table ·
    driver-influence-by-season trend chart (r per feature per season, 1999–2026).
11. Radar interactivity pass: drag-to-rotate + wheel zoom; hover cards with league-distribution
    mini-histogram, percentile, raw value, league n and team logo; popup clamped + flips at the
    right edge; labels at 24px; division pills carry team logos; LA/LAC division-map bug fixed.
12. Faces-everywhere pass: team logos in the Game Center header + every play row, Team Lines,
    EPA ratings, radar pills and tooltip; player headshots in all Records tables (loads
    players_index); tooltip max-width guards (min(340px, 90vw)).
13. 3D Lab (three.js): pick any three team stats as axes; quadrant-tinted coordinate planes at
    each median (the "infinite planes" idea — every stat pair defines a plane, third stat is
    depth); orbit/zoom/pan; raycast hover cards with raw + percentile; plus admin-free server
    autostart (Startup folder) and the agent-onboarding docs (20261002_141343_NFL_STATS_MODULE_AGENT_INSPECTION_AND_BUG_SWEEP_GUIDE_v1_0_0.md +
    repo-root AGENTS.md).
14. Bug-closure + suite refresh round: E10 decided and implemented (compare mode is
    preset-pools only; pool toggle hidden while comparing; caption says so; full loader gated) ·
    radar vertex hover verified reliable and now permanently asserted (popup containment, team
    logo, league histogram) · faces sweep asserted (play rows, records rows, radar pills) ·
    3D Lab asserted (WebGL canvas, live context, three axis pickers) · suite now **116/116
    assertions**, 20/20 data checks, **32 proof screenshots**, 0 page errors. See
    `20261002_143500_NFL_STATS_MODULE_BUG_LEDGER_CLOSURE_AND_SUITE_REFRESH_v1_0_0.md`.
15. F16 advanced metrics BUILT: wXEPA (leverage-weighted expected EPA, w = 4*wp*(1-wp), garbage
    time excluded by default) for offense + wXEPA allowed for defense, Eckel Rate
    (success x explosiveness, explicit variant contract), raw EPA reference columns, a
    BTB-style offense/defense QUADRANT chart with team logos at league medians, and two
    definition cards carrying the exact formulas + code paths. New Models sub-tab
    "Team Metrics". Verified: 120/120 suite assertions, 20/20 data checks, 33 proof
    screenshots, 0 page errors.
16. Factor-dynamics + Monte Carlo round: factor hover-highlighting across the module (rows and
    trend lines dim/highlight together) · 6x6 factor matrix (correlation/covariance toggle,
    hover-highlight, tooltips) · R²-by-season fit chart · comprehensive factor inventory
    (11 factors incl. referee/weather/roof marked planned) · statistical-term info buttons
    (mean/median/SD/skew/kurtosis/correlation/R²/Monte Carlo) with exact formulas and code
    paths · Monte Carlo season simulator (5,000 sims, point-in-time Elo, p10/mean/p90 per
    team, histogram) · chart label text raised to 15px/13px module-wide. Verified: 128/128
    suite assertions, 20/20 data checks, 35 proof screenshots, 0 page errors.
17. Model expansion + inference round: win model grows 6 -> 11 factors (rest advantage,
    division game, dome, outdoor temperature, outdoor wind — DOME-AWARE: weather terms are
    zeroed under a dome dummy; outdoor missing values baselined at 60F / 5mph) · RMSE reported
    (least-squares objective) with a geometric-calculus term card (residual = orthogonal
    projection; gradient -2X'(y-Xb)=0) · Bayesian linear regression (conjugate Gaussian prior
    N(0,1) on standardized coefficients) with 95% credible intervals and a "credibly != 0"
    verdict column · Pythagorean expectation (k=2.37) as Pyth W next to actual wins in Team
    Metrics · factor matrix now 11x11, inventory 13 rows, descriptives 11 rows. Verified:
    131/131 suite assertions, 20/20 data checks.
18. Factory view (F17): three.js digital twin of the pipeline — stations for source, parquet
    mirror, bundle factory, model works, UI, proof line and agent docs, with glowing agents
    traveling conveyor curves (run/pause + speed); click any station or chip for its role,
    live volumes and docs. Plus the functionality map + documentation audit doc
    (20261002_160000_...FUNCTIONALITY_MAP_AND_DOCUMENTATION_AUDIT) incl. the weather-widget
    reconnaissance and F18 (weather intelligence via E:\weather-widget's hourly Supabase).
    Verified: 135/135 suite assertions.
20. 3D Lab shipped (F12): team LOGO sprites replace colored dots — canvas-textured circular
    badges with team-color rings and abbr fallback (CORS-safe: texture drawn immediately,
    upgraded in place when the CDN image loads); hover scales the sprite and shows raw +
    percentile on all three axes; the scene lives in a rounded panel with a
    Panel/Theatre toggle (theatre = fixed overlay at 94vh with ResizeObserver-driven
    renderer resize). Badge styling superseded by #21 (bare logos, no rings).
    Verified: 138/138 suite assertions (sprites >= 30, theatre overlay,
    theatre canvas > 80% viewport), 37 proof screenshots.
19. Decomposition plan + S0: full widget-decomposition plan published
    (20261002_163000_..._WIDGET_DECOMPOSITION_PLAN) with the 3,725-line inventory, the one-way
    import silo architecture (core/ui/charts/features), the 8-step extraction order (S0-S7),
    per-module error boundaries + suite tags driving Factory station badges, and F19/F17b/F20
    registrations. S0 executed: src/nflstats tree created and core/registry.js added
    (13 modules, extraction status, frozen proof baseline 135/20/36) - zero behavior change,
    build green.
33. NFL Data Sentinel v1.0.1 + refresh consolidation + post-corrections data refresh (2026-10-07/08):
    continuity audit (season_1999-2026 ALL contiguous; 1999-2020 = 17 weeks, 2021-2025 = 18, 2026 =
    4; parquet mirrors 1999-2026 player/team + pbp 2025/2026; careers 138 stats full history) then
    built scripts/monitor/nfl_data_sentinel.py (stdlib-only smart monitor: ONE API call discovers all
    25 nflverse release tags, JSONL audit log scripts/monitor/state/sentinel_log.jsonl, EWMA size
    baselines, median+/-3*MAD arrival windows (prior -> learned after 4 same-weekday cuts), one-sided
    CUSUM drift, alarms NEW_CUT/LATE/SIZE_ANOMALY/ASSET_MISSING/TAG_MISSING/STALE_BUNDLES/
    WEEKS_NOT_CONTIGUOUS, suppression = max one post per alarm per cut, chatty gate for schedules) +
    build_sentinel_proof.py (nfl-data-sentinel-proof.html, 7 sections) + verify_sentinel.py (16
    machine checks) + nfl-data-sentinel.yml (daily 16:00 UTC, state committed for cloud memory) +
    consolidated nfl-data-refresh.yml (strict-JSON gate + concurrency + fixed invalid secrets-in-if;
    retired refresh-nfl-stats-data.yml after backup - it skipped augment_catalog.py and would have
    wiped catalog qualifiers) - KEY DISCOVERY: nflverse re-cuts tags by RE-UPLOADING assets, so
    published_at is stale by YEARS; the true cut = max(asset.updated_at); real tag names are
    schedules/rosters/weekly_rosters; pt_spread does NOT exist in nflverse (feed removed) - Discord:
    first digest posted to the NFL channel 2026-10-07 22:10Z (http 204) + claudecode receipt -
    sentinel caught all 8 feeds re-cut overnight and our bundle 46.7h behind; full refresh chain
    executed 2026-10-08 (2026 now 2,601 players +59, players_index 15,480, week 4 contiguous, stale
    -1.3h; inventory 150 nodes, coverage 100.0%) - gates after refresh: 173/173 suite, 25/25 data
    checks, 47 proof images, 15/15 replay, 16/16 sentinel checks - docs: 20261008_112000_NFL_DATA_
    SENTINEL_v1_0_1.md + handoff addendum + session log 2026-10-08; activation pending push approval.
32. Week-4 data refresh + pipeline-order fix + Predictive Value lab + automation + Discord recon
    + documentation mandate: refreshed 2026 to week 4 via nfl_stats_export.py --seasons 2026
    --refresh (4 weeks, 2,542 players), copied mirrors (player/team/pbp 2026), regenerated
    career_leaders (Rodgers 67,266 now) - and the SUITE CAUGHT the pipeline-order regression that
    the raw exporter wipes catalog qualifiers/stat_sources (Qualify control vanished); fix is
    running augment_catalog.py (7 qualifiers restored) - documented as mandatory order and added
    to the new CI workflow · verify_data week check made auto-growing (contiguous from 1) so it
    never needs manual edits as the season accrues · NEW Predictive Value lab: nflModels gains
    univariateFit (OLS + residual sigma), grangerDeltaR2 (AR vs AR+x on consecutive team weeks,
    ΔR² vs TSS + F) and predictiveTable (all 11 drivers); charts/FeatureScatter.jsx renders the
    scatter with OLS line + dashed ±1σ/±2σ residual bands; Models sub-tab "Predictive Value" with
    on-demand R² table (click a row to re-aim), margin mean ±1σ/±2σ sidebar. First result:
    turnover margin r=0.530/R²=0.281 same-game but Granger ΔR²≈0.000 (F=0.6) - contemporaneous,
    not predictive · NEW automation: .github/workflows/nfl-data-refresh.yml (Tue+Wed 14:00 UTC:
    export 2025-2026 refresh -> mirrors -> augment -> career leaders -> inventory -> week gate ->
    commit/push -> Vercel redeploy -> optional Discord receipt via repo secret per RULE 13) ·
    Discord monitor inspection: E:\abet\scripts\pipelines\{nflverse_sync,automated_sync_orchestrator}.py
    exist (hourly 'nfl' change-detection webhook -> DuckDB) but are NOT operating (all ABET_*
    scheduled tasks Disabled, no recent logs/sync output, hardcoded webhooks predating RULE 13) -
    recommendation: own receipts via secret, deliberate decision needed on the old orchestrator ·
    Documentation mandate met: docs/20261005_150000_..._SESSION_HANDOFF_FULL_STATE (read-first
    source of truth: paths, engine, runbooks, lessons, queue) + docs/20261005_150500_..._LIVE_PBP_
    AND_GAME_SIMILARITY_ROADMAP (M1-M5 spec for similar-games live engine). Registry now
    173/25/47. Verified: 173/173 suite assertions, 25/25 data checks, 47 proof screenshots
    (new: module_47_predictive_value), 0 page errors.
31. 3D Lab per-plane truth round + ABET integration plan: audited the 3D labelling and found two
    genuine bugs - the Y(depth)/Z(height) axis names were swapped in the scene, and the 3D
    quadrant arrows sat on the floor plane while naming the height stat. Fixed: axis names now
    match the world mapping (x=dev(kx), y=dev(kz), z=dev(ky)), and every one of the three 2D
    planes is labelled as what it is - X×Y (floor), X×Z (front), Y×Z (wall) - with gold pair
    captions at each plane's outer corner. Real stat values are now ticked on ALL THREE axes
    (5 per axis = 15 ticks, e.g. points scored 27->101, points allowed, differential -52->48)
    and each axis gets a dashed gold MEAN PLANE at its true mean deviation (3 refs). The old
    mislabelled floor arrows were removed. Sliders (sprite/label/plane-opacity) apply to the
    new elements automatically. Suite +3 assertions (ticks=15, refs=3, labels>=11 in 3D).
    Also published the exhaustive integration plan for piping the module into the working
    abet-dashboard: docs/20261005_131500_NFL_STATS_MODULE_ABET_DASHBOARD_INTEGRATION_PLAN_v1_0_0.md
    (manifest, dependency delta, batch commit/PR commands, Vercel preview checklist, VM port
    per RULE 11, verification matrix, risks, rollback tag pre-nfl-module-20261005). Registry
    SUITE_BASELINE now 170/25/46. Verified: 170/170 suite assertions, 25/25 data checks,
    46 proof screenshots, 0 page errors.
30. Decomposition S3 executed (engine extraction - the finale): the shell's entire logic
    segment (355 lines: catalog/season/docs loading, chart state, category<->stat reconciler,
    URL sync, compare/radar/full-pool lanes, chart/radar/compare selectors, hover + pin
    handlers - 92 bindings) moved verbatim into src/nflstats/core/useWidgetEngine.js; the
    widget keeps only JSX (511 lines) and destructures the engine in one statement. Provider
    ordering and hook rules are preserved because the engine IS the single React subtree hook;
    converting it to DataContext/ChartContext providers later is a mechanical wrap. Code map:
    146 nodes, 2 inline (header + shell JSX) / 144 extracted, 15 silos, coverage 100.0%.
    Freeze gate held first try: 167/167 suite assertions, 25/25 data checks, 46 proof
    screenshots, 0 page errors. Decomposition arc totals: NFLStatsWidget.jsx 4,069 -> 511
    lines (-87%), everything else lives in core (constants/urlState/engine/registry), ui (8),
    charts (17) and 11 feature silos.
29. Decomposition S6 slice executed (labs + stages + core seeds): Quadrant3D ->
    features/quadrant3d/, FactoryView + WidgetMap -> features/factory/ (old widget files
    removed); CompareCell -> features/progression/; MODES/POS_ORDER/DIVISIONS ->
    core/constants.js and readUrlState -> core/urlState.js (named export); new
    features/progression/PlotStage.jsx (radar/rank/pace/game plot engine + tooltip) and
    features/radar/RadarPills.jsx replace inline shell JSX - DOM structure unchanged. One
    runtime-only miss the build could not catch (CompareCell's RefreshCw import) was caught by
    the suite and fixed; lesson: build validates module resolution, the suite validates
    identifiers. Monolith: 850 -> 771 lines - the ONLY inline pieces left are the
    NFLStatsWidget shell and the imports header (145 nodes, 2 inline / 143 extracted, 15
    silos, coverage 100.0%). Freeze gate held: 167/167 suite assertions, 25/25 data checks,
    46 proof screenshots, 0 page errors. Remaining S3 finale: lift the shell's state/effects
    into DataContext/ChartContext so the shell becomes a ~150-line provider; the props for the
    stages are already in place.
28. Decomposition S5 executed (plays/betting/models) - via a mechanical splitter: instead of
    hand-transcribing, a script split the monolith's top-level chunks by declaration boundaries
    and emitted them verbatim with computed imports (verified by dependency scan + the build
    as parser). The monolith collapses 2,562 -> 850 lines: PlaysPanel + PLAY_TYPE_LABELS ->
    features/plays/, ModelsPanel (+ FACTOR_DEFS/STAT_TERMS defs) -> features/models/,
    BettingPanel (+ PROP_STATS defs) -> features/betting/, and the support charts ->
    charts/ (GameTimeline, DriverTrendChart + modelTheme DRIVER_COLORS, ConvergenceChart,
    CorrMatrix, R2BarChart, WxepaQuadrant, ModelMarketScatter, PropHistogram; barrel extended).
    Silo rules intact: models/betting panels import charts | ui | lib only. Code map now
    143 nodes, 7 inline / 136 extracted, coverage 100.0% - the only inline pieces left are the
    shell (NFLStatsWidget), CompareCell, MODES/POS_ORDER/DIVISIONS, readUrlState and the
    imports header. One suite assertion updated (the code-map split check assumed 20+ inline
    pieces and now verifies 1..60 so it tracks decomposition progress honestly). Freeze gate
    held: 167/167 suite assertions, 25/25 data checks, 46 proof screenshots, 0 page errors.
27. Decomposition S4 executed (leaf feature panels): the monolith falls 3,469 -> 2,562 lines as
    TableView -> src/nflstats/features/table/, CareerTable + CareerPanel + AllTimeLeaders ->
    features/career/, PlayerCard -> features/playerCard/, RecordsPanel + threshold/milestone
    defaults -> features/records/ (CareerChart moved to charts/ as a pure chart so playerCard
    never imports another feature - silo rule intact). CareerPanel consumes the charts + ui
    silos through relative imports; root now imports the four feature barrels only. Code map:
    143 nodes, 23 inline / 120 extracted, monolith coverage 100.0% (the imports/header block is
    now an explicit tracked node), 0 unmapped. Freeze gate held: 167/167 suite assertions,
    25/25 data checks, 46 proof screenshots, 0 page errors. Remaining monolith: NFLStatsWidget
    shell 735 + ModelsPanel 706 + BettingPanel 353 + PlaysPanel 236 + GameTimeline/PLAY_TYPE_
    LABELS + models support charts + DIVISIONS/MODES/readUrlState (S3/S5/S6 queue).
26. Decomposition S2 executed (charts silo): the monolith drops 3,873 -> 3,469 lines as the
    chart engine moves verbatim into src/nflstats/charts/ - scales.js (W/H/TOP/BOTTOM,
    frameFor, niceStep, niceTicks, rankScaleOf, valueScaleOf), hover.js (useContainerSize +
    buildTip), ChartAxes.jsx, BumpChart.jsx, LineChart.jsx, RadarChart.jsx + barrel index.js
    (one-way imports: charts -> lib scales; charts -> ui primitives only) - CompareCell and the
    root hover handler now consume the silo through the barrel; zero behavior change. Code map
    inventory: 142 nodes, 31 inline / 111 extracted (was 46/96), monolith coverage 99.0%,
    0 unmapped. Freeze gate held: 167/167 suite assertions, 25/25 data checks, 46 proof
    screenshots, 0 page errors on the identical baseline. Remaining monolith is dominated by
    NFLStatsWidget shell 735 / ModelsPanel 706 / BettingPanel 353 / PlaysPanel 236 /
    RecordsPanel 204 / CareerPanel 167 / PlayerCard 150 / AllTimeLeaders 145 (S3-S6 queue).
25. Third-plane verification + plane opacity round: audited the 3D wiring end-to-end - sprites
    are placed by deviation on all three stats (x=dev(kx), y=dev(kz), z=dev(ky)), the three
    median planes exist (4 tinted quadrant tiles each + new LineLoop outlines at 0.35 opacity
    so the structure is legible at any fill level), and the depth axis is measurably populated
    (data-depth-split readout: 16/16 teams on each side of the depth median for the default
    axes) · NEW PLANE OPACITY slider (0.02-0.35, default 0.10) live-updates every quadrant
    tile's material via planeMatsRef - no scene rebuild - so the user can crank the three
    planes visible to prove the third comparison; wired as data-plane-opacity (+ data-planes
    1/3, data-depth-split) · suite now asserts 3 planes in 3D / 1 plane in 2D, both-sides
    population of the depth plane, live opacity change, and orbits the camera by mouse drag
    for the new proof shot. Registry SUITE_BASELINE now 167/25/46. Verified: 167/167 suite
    assertions, 25/25 data checks, 46 proof screenshots (new: module_46_3d_three_planes.png),
    0 page errors.
24. Label-size slider + decomposition begins (S1) + Code map round: 3D Lab gains a LABEL SIZE
    slider (0.5-1.5, default 0.85) rescaling every in-scene text sprite live (axis names,
    median/mean flags, quadrant corners, value ticks) through labelSpritesRef - no scene
    rebuild; wired as data-label-size/data-label-range · S1 of the decomposition plan EXECUTED:
    the 4,069-line monolith dropped to 3,873 lines as Face, Tooltip, Legend, MiniHist, InfoDot,
    StatDocCard and CatalogModal moved verbatim into src/nflstats/ui/ (barrel index.js, one-way
    imports; zero behavior change - full suite green on the same assertions) · NEW
    build_widget_inventory.py parses every top-level declaration of the monolith + every
    extracted module, maps each to its decomposition silo, and gates line coverage (99.1%,
    0 unmapped) - verified in verify_data.py · NEW Factory "Code map" scene (WidgetMap.jsx,
    three.js): every declaration is a bar (height = LOC) grouped into silo clusters; bright =
    extracted, dim = inline; hover = name/file/span/silo/status; 142 nodes · 14 silos ·
    46 inline / 96 extracted today, so each future S-step visibly moves bars. Registry
    SUITE_BASELINE now 163/25/45. Verified: 163/163 suite assertions (code map renders with
    node/silo/inline/extracted counts, label slider 0.85->1.30 live), 25/25 data checks
    (inventory coverage + mapping gates), 45 proof screenshots (new: module_45_widget_code_map),
    0 page errors.
23. 3D Lab player mode + sprite-size slider round: the quadrant engine gets a Teams | Players
    level switch - player mode charts any PLAYER stats (default receiving yards x receiving
    TDs x receptions) with bare headshot sprites from the season bundle (players map carries
    name/team/pos/headshot_url), a Top 10 / Top 15 / All population control (players carrying
    every charted stat, ranked by the X axis; 2D requires 2 axes, 3D requires all 3), player
    tooltips (name + team/pos) and a supporting player table (headshot, pos, team, raw value +
    percentile per axis) · new HEADSHOT SIZE / LOGO SIZE slider (0.14-0.65, step 0.03, default
    0.34) rescales every sprite live via the spritesRef pass-through (no scene rebuild; hover
    scale follows baseScale) · export card now names level + sprite kind; Quadrant3D grew a
    unified makeSprite (text-initials/abbr fallback, CORS-safe in-place upgrade) and split
    buildTeamPoints / buildPlayerPoints with shared normalization (median/mean/maxDev, dev +
    percentile). Verified: 158/158 suite assertions (player mode sprites >= 8, player table
    8-40 rows with percentile, slider 0.34->0.56 rescale, back to teams), 23/23 data checks,
    44 proof screenshots (new: module_44_3d_players_sized.png), 0 page errors.
22. Quadrant polish + career leaders + export round: 2D quadrant gets real stat values ticked
    along both axes (median ± maxDev at 5 points, e.g. points scored 27/45.5/64/82.5/101),
    dashed gold MEAN reference lines at the actual mean deviation with labels (solid cross =
    median), quadrant labels tucked inside at ±0.88 so they never cover the tick row, roomier
    2D mount (1140x600) - and a sortable supporting table below the chart (team logo, raw
    value + percentile per axis, 31/32 rows by league era) · NEW career_leaders.json artifact
    (scripts/publish/build_career_leaders.py): precomputed all-time career leaderboards for
    138 player stats from the same-origin weekly parquet mirror (REG only; per-season sum or
    pooled weekly mean; rate stats gated >= 48 weeks + catalog qualifiers; derived
    total_yards/total_tds/def_tackles_total/off_plays mirrored from the exporter) - sanity:
    rec yds Fitzgerald 17,493 / pass yds Brady 89,216 / rec TDs Moss 139 / rush yds Gore
    16,000 / CPOE Romo 6.01 · Career mode gains the All-Time Leaders panel: top 10/25 career
    trajectories on the shared career chart (hover = name+season+value), sortable table
    (rank, headshot, teams, span, career total/mean, best season) and one-click '+ compare'
    staging into the compare chart (any of 15,423 indexed players vs any other, e.g. Jerry
    Rice vs JSN) · NEW shared export pipeline (src/lib/chartExport.js): composeCard frames
    WebGL canvases or rasterized SVG clones (inline-styled, logos stripped for CORS) into a
    1200x675 social card with title/subtitle/provenance footer; wired to the main progression
    chart, the career/compare chart, the leaders chart and the 3D Lab quadrant - all four
    downloads asserted live in the suite. Registry SUITE_BASELINE now 153/23/43. Verified:
    153/153 suite assertions (ticks=10, mean refs=2, quadrant table full league, top10->top25
    redraw 25 paths, Rice+JSN compare = 2 lines, 4 PNG downloads), 23/23 data checks
    (3 new career-leader checks), 43 proof screenshots (5 new: leaders, compare, 3 export
    cards), 0 page errors.
21. 3D Lab visual-language + 2D quadrant round: sprites restyled as bare team logos (no
    circles/rings; abbr fallback, CORS-safe in-place texture upgrade) - supersedes the badge
    styling of #20 · in-scene text sprites for axis names, 'median' flags and all four quadrant
    corners (↑/↓ per axis, gold), force-rendered on top (renderOrder=2) so logos never hide
    them · gold control labels via .nsw-label-gold · NEW 2D plane mode = the X×Y quadrant chart
    (X+Y cross lines at the medians, depth selector hidden, 8 in-scene labels) with a 2D/3D
    toggle; 3D keeps three planes + box edges · panel-mode 2D composition tuned: camera z=3.05
    (plane ≈ 70% of mount height), 2D-only mount 920×560 centered, corner labels placed outside
    the plane at ±1.06 where only true double-extremes reach, label type scaled per role
    (axis 54·1.4, median 40·0.85, quadrant 38·0.95). Registry SUITE_BASELINE bumped to
    141/20/38. Verified: 141/141 suite assertions (labels >= 8, data-dims="2d", selects=2 in 2D,
    theatre overlay + canvas > 80%), 20/20 data checks, 38 proof screenshots (new:
    module_38_3d_2d_plane.png), 0 page errors.

Roadmap (queued): (4) PBP explorer + game center with Cloudflare Worker proxy; (5) EP/WP
model rebuild + win regressions (point-in-time discipline like Barlowe Analytics' talent
ratings, incl. uncertainty); (6) prop lines vs historical distributions with the live-odds
pipeline.

---

## 11. Quick "where do I change X"

| Want | File |
|---|---|
| Chart rendering/interactions | `src/widgets/NFLStatsWidget.jsx` (Bump/Line/Radar/Table) |
| Filtering/ranking math | `src/lib/nflStats.js` (`computeChart`, scales, colors) |
| Parquet scans/records/careers | `src/lib/nflParquet.js` |
| Models (Elo, regressions, market) | `src/lib/nflModels.js` |
| Betting (ATS/O-U math, devig) | `src/lib/nflModels.js` + `buildPropDistribution` in nflParquet |
| Pool depth / new stat sources | `scripts/publish/nfl_stats_export.py` |
| Qualifier rules / sources tags | `scripts/publish/augment_catalog.py` |
| Formulas / descriptions | `scripts/publish/build_stat_docs.py` |
| Proof assertions | `D:\nfl-progression\proof\capture_module.py` |
| Data integrity checks | `D:\nfl-progression\proof\verify_data.py` |
| Scheduled refresh | `.github/workflows/refresh-nfl-stats-data.yml` (parked) |
| 3D Lab (three.js) | `src/widgets/Quadrant3D.jsx` |
| Agent onboarding / bug sweep | `docs/20261002_141343_NFL_STATS_MODULE_AGENT_INSPECTION_AND_BUG_SWEEP_GUIDE_v1_0_0.md` (read first) |
