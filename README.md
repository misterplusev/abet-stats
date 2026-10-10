# abet-stats

**Canonical scripts home for all ABET league stats pipelines — NFL, MLB, and future leagues.**

[![](https://img.shields.io/badge/status-library--first-blue)]() [![](https://img.shields.io/badge/actions--usage-zero-brightgreen)]() [![](https://img.shields.io/badge/secrets--none-RULE_13-brightgreen)]()

## Mission

Every league-stats script in the ABET system has exactly one canonical home: **this repo**. The dashboards consume these scripts; the data they produce lives with the dashboard (see "Consumption model"). No workflows run here — this is a library, not a runner.

## Layout

```
abet-stats/
├── nfl/
│   ├── publish/          # nflverse exporter, catalog augmentation, career leaders,
│   │                     # stat docs, widget inventory, module size check
│   ├── monitor/          # NFL Data Sentinel v1.0.1 + sentinel proof builder
│   └── workflows/        # REFERENCE SNAPSHOTS of the live workflows (labeled, do not run)
├── mlb/
│   └── publish/          # MLB stats exporter
├── proof/                # 173-assertion Playwright capture suite + data/sentinel gates
│                         # + proof builders (the module verification harness)
├── docs/                 # architecture bible, sentinel doc, cloud-integration pitch,
│                         # fresh-eyes audit
├── INVENTORY.md          # full line-count inventory
└── README.md
```

New leagues follow the same pattern: `nba/publish/`, `nhl/publish/`, … — one folder per league, `publish/` (build data) and `monitor/` (watch upstream) subfolders as needed.

## What does NOT live here

- **Data bundles & parquet mirrors** (`public/nfl-stats/`, 98.7 MB) — committed to the dashboard repo so Vercel serves them in-repo.
- **Sentinel runtime state** (`sentinel_state.json`, `sentinel_log.jsonl`) — committed to the dashboard repo by the sentinel workflow.
- **Live workflows** — `.github/workflows/` in `misterplusev/abet-mlb-monitor-widgets` runs the schedules and commits data in place. This repo **deliberately has no `.github/workflows/`** — zero GitHub Actions minutes are ever consumed here. The copies under `nfl/workflows/` are labeled reference snapshots only.
- **Legacy pipelines** (`E:\abet\scripts\pipelines\`) — dead code (all ABET_* tasks Disabled), documented in the fresh-eyes audit; deliberately not carried over.
- **Secrets** — none, by RULE 13: all webhooks/tokens are read from environment variables by the callers, never stored in code.

## Consumption model (library-first)

The dashboard repo's workflows check this repo out and run the scripts from it, while writing data/state back into the dashboard repo checkout:

```yaml
# inside abet-mlb-monitor-widgets/.github/workflows/nfl-data-refresh.yml
- uses: actions/checkout@v4           # dashboard repo (default)
- uses: actions/checkout@v4
  with:
    repository: misterplusev/abet-stats   # public repo -> no PAT/token needed
    path: abet-stats

# then, instead of: python scripts/publish/nfl_stats_export.py ...
- run: python abet-stats/nfl/publish/nfl_stats_export.py --seasons 2025-2026 --refresh --cache .nfl-cache
```

Being public is what makes this zero-friction: cross-repo checkout needs no `token:`. It also burns nothing — Actions usage is counted where workflows RUN (the dashboard repo), not where code is checked out from.

## Sync discipline

- **Edit scripts here first.** This repo is the source of truth.
- The dashboard worktree (`D:\abet_dev\claude_dashboard_pills_20260925`) keeps working copies for local dev runs, the proof harness, and the module suite. After editing here, copy the changed file(s) to the worktree path and re-run the gates.
- The pending dashboard commit wires its workflows to checkout this repo (see `docs/…MASTER_PITCH…` + fresh-eyes audit for the P-series plan and the B1–B4 bug register that must land first).

## Pipeline order (NFL, mandatory)

`export → mirror copies → augment_catalog → build_career_leaders → build_widget_inventory → strict-JSON gate → week gate → bot commit → optional Discord receipt`

The augment step is load-bearing: skipping it silently wipes catalog qualifiers/stat_sources (the exact regression that retired the predecessor workflow — documented in the workflow header and the architecture bible).

## References

- Dashboard repo (private): `misterplusev/abet-mlb-monitor-widgets` — Vercel project `abet-dashboard`, production alias https://abet-dashboard.vercel.app
- `INVENTORY.md` — every script with fresh line counts
- `docs/20261002_141343_NFL_STATS_MODULE_ARCHITECTURE_OPERATIONS_AND_DATA_BIBLE_v1_0_0.md` — the bible
- `docs/20261008_112000_NFL_DATA_SENTINEL_v1_0_1.md` — sentinel design
- `docs/20261008_133000_…MASTER_PITCH….md` — cloud integration plan (P0–P7, decisions D-1..D-6)
- `docs/20261009_143000_…FRESH_EYES_AUDIT….md` — bug register (B1–B4) + full inventory
