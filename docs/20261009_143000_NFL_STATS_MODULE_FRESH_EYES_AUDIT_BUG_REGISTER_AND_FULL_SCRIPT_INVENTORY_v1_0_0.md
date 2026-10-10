# NFL Stats Module — Fresh-Eyes Audit: Bug Register + Full Script Inventory (v1.0.0)

**Date:** 2026-10-09 14:30 MST (21:30 UTC)
**Author:** Claude (GLM 5.3) — independent fresh-eyes review round (operator requested new-model perspectives on the build and session so far)
**Scope:** the complete NFL Stats module build — widget module (28-season in-browser stats lab), nflverse data pipeline, NFL Data Sentinel v1.0.1, both GitHub Actions workflows, proof harness, and the cloud-integration pitch state
**Method:** READ-ONLY. Full file reads, live gate re-runs, live network dry-run. **No code or data files were changed in this round.** All fixes below are documented and gated on operator approval.
**Companion docs:** `20261008_133000_..._MASTER_PITCH_...` (phases P0–P7, decisions D-1..D-6), `20261008_134000_LEGACY_..._AUDIT_...`, `20261008_112000_NFL_DATA_SENTINEL_v1_0_1.md`, session logs 2026-10-08/09.

---

## 1. Executive summary

- **4 confirmed bugs found** by fresh-eyes review: 1 **critical cloud blocker** (lockfile out of sync — cloud build will hard-fail), 1 **high** (sentinel staleness alarm is structurally dead on CI), 1 **medium** (games.parquet will freeze post-merge), 1 **low** (CUSUM advertised but never wired).
- **9 minor findings** + **2 new design decisions** (D-7 refresh cadence, D-8 CUSUM disposition) + **1 pitch amendment** (P2 must stage `package-lock.json`).
- **Everything else verified solid**: live gates re-run green today (25/25 data, 16/16 sentinel), and a live dry-run demonstrated the sentinel catching Friday's cuts on all 8 feeds with the bundle **22.3h stale vs remote** — the exact failure mode it was built to catch, caught on cue.
- **Full inventory delivered** (§6): ~14.0K first-party lines across 6 active lanes; plus 3,167 lines of dead legacy and 7,094 lines of unrelated superseded temp ancestors.

---

## 2. Live evidence (re-verified 2026-10-09, ~21:00–21:15 UTC)

| Check | Result |
|---|---|
| `verify_data.py` | **25/25 PASS** — 33 bundles strict-JSON-parseable; catalog 177 player / 151 team stats; 2026 weeks 1..4 contiguous; players_index 15,480; career leaders live-verified (Stafford 4,707 / Fitzpatrick 17,493 / Brady 89,216); inventory 150 nodes, 100.0% documented |
| `verify_sentinel.py` | **16/16 PASS** — 51 log events, 8 feeds covered, state last_check 2026-10-08T18:37:15Z |
| `sentinel --status` | 6 total checks recorded; all 8 feeds learned; 2026 bundle weeks 1..4 contiguous; baselines warming as designed (size n=2, no arrival windows yet — needs ≥4 same-weekday cuts / MIN_BASELINE_N=5) |
| `sentinel --check --dry-run` (live network) | **8/8 feeds NEW_CUT** (Friday cuts ~16:00Z: stats_player/stats_team/pbp 5.0h, rosters/weekly_rosters/depth_charts/injuries 6.8h, schedules 0.1h); **stale_vs_remote = 22.3h** (local bundle frozen at the Oct 8 manual refresh); `depth_charts z=+3.9` **correctly WITHHELD** (n=2 < MIN_BASELINE_N=5); 25-tag inventory intact |
| Baseline module suite (not re-run today; last full run 2026-10-07) | 173/173 assertions, 47 screenshots, 15/15 sentinel replay, 16/16 machine gates |

The dry-run is the system working as pitched: nflverse cut fresh data ~5h ago, and the sentinel instantly quantified exactly how far behind our frozen local bundle is. On cloud, this is the loop that runs daily against the Actions-refreshed bundles.

---

## 3. Bug register (confirmed; fixes gated on operator approval)

### B1 — CRITICAL — `package-lock.json` is missing `three` + `hyparquet` → cloud build hard-fails
- **Evidence:** `package.json` (modified, unstaged) adds `"hyparquet": "^1.31.2"` and `"three": "^0.186.1"`. The tracked `package-lock.json` has **zero entries** for `node_modules/three` / `node_modules/hyparquet` (verified by search). Both exist in local `node_modules` (installed without saving the lockfile). Local `vite build` works only because local `node_modules` is already populated.
- **Impact:** Vercel runs `npm ci` when a lockfile is present. `npm ci` **refuses to install anything that isn't in the lockfile** — the first cloud build fails with EUSAGE ("lock file does not satisfy package.json"). This blocks every pitch phase from P1 onward.
- **Fix (P0.5, minutes):**
  1. `npm install` (syncs lockfile; adds both packages' entries)
  2. Re-verify: `node node_modules\vite\bin\vite.js build` (never `npx vite` per worktree rules)
  3. **Amend pitch P2 staging list: stage BOTH `package.json` AND `package-lock.json`.** (The current pitch lists only `package.json` — that would ship the mismatch.)
- **Rollback:** `git checkout -- package-lock.json package.json` (restores pre-fix tracked state).

### B2 — HIGH — `check_bundles` staleness uses filesystem `mtime` → STALE_BUNDLES is structurally dead on CI
- **Location:** `scripts/monitor/nfl_data_sentinel.py:352-386` — `check_bundles()`; mtime captured at `:371` (`path.stat().st_mtime`), alarm at `:380-382` (`stale_h > STALE_HOURS`, `STALE_HOURS = 36.0` at `:86`).
- **Mechanism:** Git checkouts do not preserve mtimes — every file on a CI runner gets the checkout's timestamp. So on cloud, `stale_vs_remote` ≈ (checkout_time − remote_cut_time), which is ~0 or negative → **STALE_BUNDLES can never fire**, and the digest/status line is misleadingly "fresh" forever. This kills the sentinel's headline alarm (the class of catch that found the 46.7h freeze on Oct 8).
- **Fix (low risk):** derive bundle age from the **`generated_at` field** the exporter writes into every `season_*.json` (verified present in all bundles; catalog and players_index carry it too), with `mtime` as fallback:
  ```python
  # inside check_bundles, per bundle path:
  try:
      gen = json.loads(path.read_text(encoding="utf-8")).get("generated_at")
      stamp = parse_iso(gen) if gen else datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
  except Exception:
      stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
  ```
  Store the same ISO string in state exactly as today (state/`--status`/digest code unchanged).
- **Verification:** `--replay-test` (15 tests) + one local `--check --dry-run` before commit; cloud verification is the first daily workflow run.
- **Note:** with mtime semantics fixed, D-7 (below) becomes required, otherwise the Tue/Wed-only refresh schedule produces recurring expected alarms Fri–Mon.

### B3 — MEDIUM — `games.parquet` is consumed by the module but never refreshed by the workflow
- **Evidence:** `src/lib/nflParquet.js:46` `loadGames()` fetches `public/nfl-stats/parquet/games.parquet` (game lists; prop-distribution opponent sources). The refresh workflow's mirror copy list (`nfl-data-refresh.yml:39-43`) copies only: stats_player_week 2025/2026, stats_team_week 2025/2026, play_by_play_2026 — **no `games.parquet` line**. The exporter downloads it (schedules tag is in its endpoint set), but the mirror step never copies it.
- **Impact:** post-merge, the cloud copy of `games.parquet` freezes at whatever we ship in P2. Game lists go stale immediately; the prop-distribution opponent source degrades silently. (2025 mirrors being frozen is correct by design — 2025 is a completed season. `games.parquet` contains the live 2026 schedule + results, so it must refresh.)
- **Fix (one line, add after `nfl-data-refresh.yml:43`):**
  ```yaml
  cp .nfl-cache/github.com__nflverse__nflverse-data__releases__download__schedules__games.parquet public/nfl-stats/parquet/games.parquet
  ```
- **Verification:** local exporter run + the cp, then `verify_data.py` + module suite (game list / prop-distribution views show current-week opponents).
- **Sibling note:** `play_by_play_2025.parquet` is intentionally not re-copied (completed season, 19.39MB frozen in-repo) — correct, leave as is.

### B4 — LOW — `cusum_step` is defined, documented, and replay-tested — but never called
- **Evidence:** `nfl_data_sentinel.py:170` defines `cusum_step(s, x, mu, sigma, k=0.5, h=5.0)`; module docstring `:6` advertises "one-sided CUSUM"; replay tests exercise it; **no call site exists in the live check loop**, and state stores no cusum accumulators.
- **Impact:** doc/behavior mismatch — the advertised drift detector does not run in production; size-anomaly detection is EWMA-z only. No functional failure, but the docs oversell, and slow drift (the thing CUSUM exists for) goes undetected.
- **Options (→ D-8):**
  - **(a) Wire it:** per-feed `state["feeds"][f]["cusum_s"]`; in the per-feed size check, when `n ≥ MIN_BASELINE_N`, `s = cusum_step(prev, ln(bytes), mu, sqrt(var))`; on `s > h` raise `SIZE_ANOMALY` with `"cusum drift"` detail and reset `s = 0`. ~15 lines + state migration (default 0.0).
  - **(b) Make docs honest:** remove "one-sided CUSUM" from the docstring/sentinel doc and delete the dead function + its replay tests.
  - **Recommendation:** (a) is cheap and true to the design; (b) is fine if the operator prefers minimal surface.

---

## 4. Minor findings, design decisions, and pitch amendments

| # | Finding | Disposition |
|---|---|---|
| M1 | **Caption overclaim:** `stats_team_week` parquet mirrors are referenced in display captions ("parsed in-browser") but **no code path loads them** — `loadWeekly`/`loadGames`/`loadPlays` cover player weeks, games, pbp only. Team mirrors (2025/2026 copied each run; 26 older seasons frozen in-repo) are currently dead weight. | Either correct captions (factory facts, models source label, `NFLStatsWidget.jsx:478`) or keep mirrors for future team-features. Low priority; data is harmless. |
| M2 | **Persistent alarms repost daily:** TAG_MISSING/ERROR alarms whose `cut_key` resolves to `None` post the alarm marked `"?"`, so `posted` never matches next run → daily repost while the condition persists. | Acceptable for now (loud-on-purpose), or add a "persistent" dedupe key. Operator call. |
| M3 | `verify_sentinel.py` docstring still says "v1.0.0" (sentinel is v1.0.1). | Cosmetic; fix with B2 commit. |
| M4 | **Year-boundary tripwires:** `verify_data.py` expects `catalog["seasons"] == list(range(1999, 2027))`; capture suite expects "28 seasons" in the selector. Both trip when the exporter adds season_2027 (Aug 2027). | Note in runbook; change on 2027 export debut. Not a today-problem. |
| M5 | Workflows push without `git pull --rebase origin <branch>` first → a user push between checkout and bot push fails that run (retryable, no corruption). | Add rebase step in P6 hardening if desired. |
| M6 | Pitch D-4 secret command pipes the webhook via stdin (`"..." | gh secret set`). Works, but `gh secret set DISCORD_WEBHOOK_NFL --body "$env:DISCORD_WEBHOOK_NFL" --repo ...` avoids quoting/pipeline pitfalls. | Amend pitch command at execution time. |
| M7 | `load_state` silently resets on corrupt/missing state (fresh baselines) — correct for bootstrap, but a corrupt state file mid-flight would quietly disarm thresholds for ~5 cuts and could re-storm alarms. | Acceptable (documented behavior); optional: log a loud `STATE_RESET` event line when it happens. |
| M8 | `sentinel_log.jsonl` grows unbounded (~2-3 KB/day ≈ 1 MB/year). | Fine for years; rotate when it matters. |
| M9 | `git` prints "unable to find all commit-graph files" on every command (stale commit-graph in this worktree). | Benign; `git commit-graph write --reachable` silences it. Cosmetic. |
| M10 | `build_stat_docs.py` is not in the refresh workflow; `stat_docs.json` is static. If nflverse ships new stat columns, new catalog keys would lack formula docs (UI falls back to a generic caption — graceful). | Optionally add `python scripts/publish/build_stat_docs.py` after augment in the workflow. Low. |
| M11 | **MLB has no refresh automation** (no MLB workflow; `mlb_stats_export.py` exists, unused in CI). 602.2 MB / 291 files frozen in-repo. | Acceptable for ship (2026 MLB season over); future decision for parity. |
| M12 | **Seed state carry-over:** P2 will commit local `scripts/monitor/state/` containing today's dry-run `posted_cuts` markers (Friday's cuts). Harmless — by deploy time newer cuts exist, and suppression is per-cut — and the baselines warm the cloud start. Alternative: reset state to minimal seed before commit. | Recommend: commit current state (warmer start); no action needed. |

### New design decisions (extend pitch D-1..D-6)

- **D-7 — Refresh cadence (required once B2 is fixed):** current cron `0 14 * * 2,3` (Tue/Wed 14:00Z) means the bundle goes >36h stale vs weekend cuts → with honest staleness semantics the sentinel posts STALE_BUNDLES ~2-3× every week (Fri–Mon), which reads as failure noise.
  - **Recommend:** `'0 14 * * 0,1,2,3,5'` (Sun/Mon/Tue/Wed/Fri) — Sunday run pre-loads weekend gameday data, Monday captures Sunday-night cuts, Tue/Wed capture the weekly stats cuts + corrections, Friday captures midweek cuts like today's. Under this cadence the bundle never crosses the 36h threshold in normal operation → STALE_BUNDLES returns to meaning "something is actually broken."
  - Alternative: keep 2,3 and accept ~2-3 expected alarms/week as a heartbeat (operator may actually like receipts; but recurring "expected" alarms erode signal).
  - Cost: +3 runs/week × ~3-5 min public-repo Actions; the big item per run is the ~493MB pbp redownload (unchanged per run).
- **D-8 — CUSUM disposition:** wire `cusum_step` into the live loop (option a) or remove it + fix docs (option b). See B4.

### Pitch amendment (P2 staging list)

Add **`package-lock.json`** (after the B1 `npm install` sync) to the P2 staging list alongside `package.json`. Everything else in the pitch's staging inventory stands as written.

---

## 5. Verified-solid (fresh-eyes confirmed-good)

- **Module:** 173/173 assertions (Oct 7 full run), 47 screenshots, deep links, 390px responsive gates, export cards, hamburger nav; week-5-safe by construction (frozen 2025 fixtures + auto-growing 2026 checks; only M4-class year-boundary trips in Aug 2027).
- **Pipeline:** exporter refresh mode (2025-2026 only; 1999-2024 bundles frozen in-repo — 28-season continuity audit closed), one API call for all 25 tags, merge + catalog + players_index rebuild, `generated_at` stamps everywhere; augment step mandatory (its omission was the retired workflow's silent-qualifier-wipe bug — now documented in the workflow header); career leaders read same-origin mirrors; strict-JSON gate + week gate before any commit; bot commit scoped to `public/nfl-stats/{data,parquet}` with `git diff --cached --quiet` no-op guard.
- **Sentinel:** UTC-correct everywhere; 8 feeds / 9 alarm types; EWMA α=0.25 with MIN_BASELINE_N=5 trust gate (demonstrated live today: z=+3.9 correctly withheld at n=2); robust MAD arrival windows; per-cut suppression (published_at is stale by years on nflverse — RE-UPLOAD is the signal; cut_key = max asset `updated_at`); digest + alarm separation; state committed by CI; 15/15 replay tests.
- **Workflows:** both have `permissions: contents: write`, concurrency groups, path-scoped adds, no-op commit guards, env-only webhook usage (RULE 13 compliant — nothing hardcoded, nothing printed); receipt path proven live (http 204, message id 1557825575366955029, Oct 7).
- **Repo hygiene:** only the 2 intended workflows exist on disk (old one retired with backup at `E:\abet\.cache\tmp\opencode\pre-consolidation\`); `dist/` ignored; backup/`.backup` files under `src/` identified and excluded from the P2 staging plan; `package-lock.json` tracked (which is exactly why B1 matters).

---

## 6. Full script inventory (line counts, fresh-measured 2026-10-09)

### Lane A — Module UI (worktree `src/`) — 8,727 lines

**`src/nflstats/` — 49 files, 5,330 lines**

| charts (18 files, 936) | lines | | core (4 files, 552) | lines |
|---|---|---|---|---|
| RadarChart.jsx | 166 | | useWidgetEngine.js | 472 |
| CareerChart.jsx | 74 | | registry.js | 37 |
| DriverTrendChart.jsx | 69 | | constants.js | 21 |
| scales.js | 68 | | urlState.js | 22 |
| BumpChart.jsx | 61 | | | |
| hover.js | 57 | | | |
| FeatureScatter.jsx | 50 | | | |
| LineChart.jsx | 48 | | | |
| GameTimeline.jsx | 45 | | | |
| PropHistogram.jsx | 44 | | | |
| CorrMatrix.jsx | 43 | | | |
| ModelMarketScatter.jsx | 37 | | | |
| R2BarChart.jsx | 31 | | | |
| ConvergenceChart.jsx | 30 | | | |
| WxepaQuadrant.jsx | 63 | | | |
| ChartAxes.jsx | 20 | | | |
| index.js | 16 | | | |
| modelTheme.js | 14 | | | |

| features (21 files, 3,635) | lines | | features (cont.) | lines |
|---|---|---|---|---|
| models/index.jsx | 784 | | factory/index.jsx | 300 |
| quadrant3d/index.jsx | 702 | | factory/WidgetMap.jsx | 240 |
| betting/index.jsx | 363 | | records/index.jsx | 210 |
| career/index.jsx | 175 | | plays/index.jsx | 243 |
| playerCard/index.jsx | 157 | | progression (CompareCell+PlotStage) | 57 |
| career/AllTimeLeaders.jsx | 150 | | radar/RadarPills.jsx | 29 |
| career/CareerTable.jsx | 56 | | betting/defs.js | 5 |
| models/defs.js | 31 | | plays/defs.js | 12 |
| table/index.jsx | 103 | | records/defaults.js | 18 |

| ui (8 files, 207) | lines |
|---|---|
| CatalogModal.jsx | 54 |
| StatDocCard.jsx | 42 |
| Legend.jsx | 32 |
| MiniHist.jsx | 24 |
| Tooltip.jsx | 24 |
| Face.jsx / InfoDot.jsx / index.js | 12/12/7 |

**`src/lib/` NFL lane — 1,644 lines:** `nflModels.js` 832, `nflParquet.js` 479, `nflStats.js` 235, `chartExport.js` 98

**Widget wrappers — 1,753 lines:** `NFLStatsWidget.jsx` 511, `NFLStatsWidget.css` 943, `StatsEmbedWidget.jsx` 160, `StatsEmbedWidget.css` 139

### Lane B — Publish pipeline (`scripts/publish/`) — 2,113 lines

| Script | Lines | Role |
|---|---|---|
| nfl_stats_export.py | 653 | nflverse → season bundles + mirrors + catalog + players_index (refresh mode for live seasons) |
| mlb_stats_export.py | 667 | MLB counterpart (no CI wiring yet — M11) |
| build_stat_docs.py | 286 | formula docs (static; optional workflow add — M10) |
| build_widget_inventory.py | 177 | widget-coverage inventory (workflow gate: 150 nodes, 100%) |
| build_career_leaders.py | 152 | all-time leaders from same-origin parquet mirrors |
| augment_catalog.py | 117 | schedules/pbp/pfr stat augmentation + qualifiers rebuild (mandatory step) |
| check_module_sizes.py | 61 | dev-only bundle-size check |

### Lane C — Monitor (`scripts/monitor/`) — 892 lines

| Script | Lines | Role |
|---|---|---|
| nfl_data_sentinel.py | 670 | 8 feeds, 9 alarms, EWMA/MAD/(CUSUM), suppression, digest, CLI (check/status/replay-test) |
| build_sentinel_proof.py | 222 | renders sentinel proof HTML for the proof suite |

(+ runtime artifacts `state/sentinel_state.json` 22,237 B, `state/sentinel_log.jsonl` 17,360 B — committed by cloud CI; monitor `.gitignore` = `__pycache__/` only)

### Lane D — CI / orchestration — 178 lines

| File | Lines | Role |
|---|---|---|
| .github/workflows/nfl-data-refresh.yml | 102 | Tue/Wed 14:00Z refresh: export → 5 mirrors → augment → career → inventory → strict-JSON gate → week gate → bot commit → optional receipt |
| .github/workflows/nfl-data-sentinel.yml | 61 | daily 16:00Z sentinel: --check --digest, --replay-test, state commit with no-op guard, artifact upload |
| refresh-nfl-data.bat | 15 | local predecessor (retire candidate — pitch D-5) |

### Lane E — Proof harness (`D:\nfl-progression\proof\`) — 1,788 lines

| Script | Lines | Role |
|---|---|---|
| capture_module.py | 832 | 173-assertion Playwright capture suite (47 screenshots, network/console/error capture) |
| build_proof_html.py | 321 | evidence renderer |
| build_module_proof.py | 259 | suite orchestrator (build + serve 8611 + capture + verify) |
| verify_data.py | 130 | 25-check data gate (strict JSON, catalog, weeks, leaders, inventory) |
| verify_sentinel.py | 118 | 16-check sentinel state/log gate |
| export_proof_data.py | 128 | proof data exporter |

### Lane F — Discord poster (`E:\abet\abet-scraper-scripts\scripts\`) — 225 lines

`abet_discord_embed.py` 94, `abet_discord_channels.py` 76, `abet_discord_post.py` 55 (RULE 13: webhook from `E:\abet\.env` by name, never printed)

### Lane G — Legacy pipelines (`E:\abet\scripts\pipelines\`) — 3,167 lines — DEAD (retirement gated by pitch D-5)

`data_loader.py` 745, `automated_sync_orchestrator.py` 695, `orchestrator.py` 693, `nba_stats_sync.py` 525, `nflverse_sync.py` 509 — all ABET_* tasks Disabled, hardcoded webhooks predate RULE 13, DuckDB target no longer used; full audit in `20261008_134000_LEGACY_...`.

### Lane H — Temp ancestors (`E:\abet\.cache\tmp\opencode\`) — 7,094 lines — superseded, unrelated

`nfl_monitor_gh.py` 3,446, `nfl_monitor_verify.py` 1,841, `nfl_monitor_raw.py` 1,807 — these are **odds-monitor lineage** (9-key API rotation, SQLite, chart posting), not NFL-stats ancestors; superseded by the odds platform. Keep for archaeology or purge at will; ~90 smaller inspect/patch scripts from past sessions live alongside.

### First-party active-build total: **≈14,023 lines** (Lanes A–F)

### Data assets (not code, for completeness)

- `public/nfl-stats/` — 98.7 MB: 33 season bundles (1999-2026, strict-gated) + parquet mirrors (pbp_2025 19.39 MB, pbp_2026, player/team week mirrors, games.parquet) + catalog + players_index + stat_docs + inventory
- `public/mlb-stats/` — **602.2 MB / 291 files** (largest `season_2021.json` 11.13 MB) — frozen, no CI refresh (M11)

---

## 7. Recommended next actions

1. **P0.5 fix batch (on approval, ~30 min):** B1 lockfile sync (`npm install` + build verify + stage both files) → B3 one-line workflow addition → B2 `generated_at` staleness fix + M3 docstring → B4 per D-8 choice. Each fix backed up per RULE 2 (`*_backup_YYYYMMDD_HHMM_BEFORE_*`), gates re-run after (verify_data 25/25, verify_sentinel 16/16, replay 15/15, one local `--check --dry-run`, `vite build`).
2. **Fold M5/M6/M10 + seed-state choice (M12) into the P2/P6 execution steps.**
3. **Answer D-7 (cadence — recommend `0 14 * * 0,1,2,3,5`) alongside pitch decisions D-1..D-6, plus D-8.**
4. Then execute the pitch phases P0–P7 as written (with the P2 lockfile amendment).

**Rollback for this round:** none needed — this round changed no code or data. Local sentinel state updates from gate runs/dry-run are runtime artifacts (untracked), self-healing on next runs.

*Written by Claude (GLM 5.3) fresh-eyes review round, 2026-10-09 14:30 MST. No mutations; all fixes herein are proposals awaiting operator approval.*
