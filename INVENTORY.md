# abet-stats — Script Inventory

**Synced:** 2026-10-10 (machine clock corrected — stamps now real) from `D:\abet_dev\claude_dashboard_pills_20260925` (worktree) + `D:\nfl-progression\proof`. P0.5 fix batch applied: sentinel → v1.0.2 (B2 + B4); refresh-workflow snapshot gained the games.parquet mirror (B3).
**Verification:** line counts re-measured 2026-10-10; see `docs/20261009_143000_…FRESH_EYES_AUDIT….md` (bug register B1–B4) and `docs/20261010_150000_…P0_5_FIX_BATCH….md` (fixes + gate proofs). Secret scan (webhook URLs, gh tokens, service keys): **zero hits** — RULE 13 clean.

## nfl/publish — 1,446 lines

| Script | Lines | Role |
|---|---|---|
| nfl_stats_export.py | 653 | nflverse → season bundles + mirrors + catalog + players_index (one API call, 25 tags; refresh mode for live seasons) |
| build_stat_docs.py | 286 | formula docs for every catalog stat |
| build_widget_inventory.py | 177 | widget-coverage inventory (workflow gate: 150 nodes, 100%) |
| build_career_leaders.py | 152 | all-time leaders from same-origin parquet mirrors |
| augment_catalog.py | 117 | schedules/pbp/pfr stat augmentation + qualifiers rebuild (mandatory step) |
| check_module_sizes.py | 61 | dev-only bundle-size check |

## nfl/monitor — 927 lines

| Script | Lines | Role |
|---|---|---|
| nfl_data_sentinel.py | 702 | NFL Data Sentinel v1.0.2 — 8 feeds, 9 alarm types, EWMA α=0.25 (trusted n≥5), MAD arrival windows, per-cut suppression, digest + alarms, CLI (check/status/replay-test); v1.0.2: bundle staleness from generated_at with mtime fallback (B2), one-sided CUSUM wired live (B4) |
| build_sentinel_proof.py | 225 | renders the sentinel proof page (v1.0.2: bundles table gained generated_at + ts source columns) |

## nfl/workflows — 171 lines (reference snapshots, +3-line banner each)

| File | Lines | Role |
|---|---|---|
| nfl-data-refresh.yml | 107 | SNAPSHOT of live refresh workflow (export → mirrors + games.parquet → augment → career → inventory → gates → bot commit → optional receipt; Tue/Wed 14:00Z) |
| nfl-data-sentinel.yml | 64 | SNAPSHOT of live sentinel workflow (daily 16:00Z --check --digest, --replay-test, state commit) |

## mlb/publish — 667 lines

| Script | Lines | Role |
|---|---|---|
| mlb_stats_export.py | 667 | MLB stats exporter (no CI wiring yet — frozen 602.2 MB in-repo assets) |

## proof — 1,788 lines

| Script | Lines | Role |
|---|---|---|
| capture_module.py | 832 | 173-assertion Playwright capture suite (47 screenshots, console/network/error capture) |
| build_proof_html.py | 321 | evidence renderer (self-contained proof page) |
| build_module_proof.py | 259 | suite orchestrator (build + serve 127.0.0.1:8611 + capture + verify) |
| verify_data.py | 130 | 25-check data gate (strict JSON, catalog, weeks, leaders, inventory) |
| verify_sentinel.py | 118 | 16-check sentinel state/log gate |
| export_proof_data.py | 128 | proof data exporter |

## Totals

| Lane | Lines |
|---|---|
| nfl (publish + monitor + workflows) | 2,544 |
| mlb | 667 |
| proof harness | 1,788 |
| **Scripts in this repo** | **4,999** |
| docs (5 files) | — |

For context, the full NFL Stats build these scripts serve is ~14.0K first-party lines (module UI 8,727 + these scripts + Discord poster 225) — see the fresh-eyes audit for the complete breakdown.

## Not carried over (deliberately)

- `refresh-nfl-data.bat` (15 lines) — local predecessor, retire candidate (pitch D-5).
- Legacy pipelines `E:\abet\scripts\pipelines\` (3,167 lines: data_loader 745, automated_sync_orchestrator 695, orchestrator 693, nba_stats_sync 525, nflverse_sync 509) — dead (all ABET_* tasks Disabled), documented for retirement in the fresh-eyes audit.
- Discord poster trio (`abet-scraper-scripts`: abet_discord_post 55, embed 94, channels 76) — cross-cutting infra, stays in `abet-scraper-scripts`.
- Sentinel runtime state + data bundles — live in the dashboard repo by design.
