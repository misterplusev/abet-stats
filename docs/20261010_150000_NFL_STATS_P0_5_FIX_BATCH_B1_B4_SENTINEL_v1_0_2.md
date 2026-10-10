# NFL Stats — P0.5 Fix Batch (B1–B4) — Sentinel v1.0.2

**Date:** 2026-10-10 (machine clock corrected ~14:20 local — stamps in this doc are real)
**Scope:** the four blocker bugs from the fresh-eyes audit — the gate that must be green before the cloud-integration pitch (P0–P7) executes. Dev-only per RULE 2 (`E:\abet` untouched); the dashboard repo remains uncommitted pending pitch decisions D-1..D-6.
**abet-stats commits:** `31ed907` (banner fix), `a2fe06b` (B3 snapshot sync), + this batch (sentinel v1.0.2 + proof builder + docs).

## Fixes

### B1 — lockfile drift (three/hyparquet absent from package-lock.json) — FIXED
- **Root cause (discovered this batch):** user-level `~/.npmrc` contains `package-lock=false`, so every `npm install` on this machine silently skips lockfile writes. (Secondary find: stale `vite preview` processes from Oct 8 held `@rollup/rollup-win32-x64-msvc` → EBUSY.)
- **Fix:** project-level `.npmrc` (`package-lock=true`) at the worktree root — project config overrides user config; the repo defends itself on any machine.
- **Applied:** `npm install --package-lock` (npm 11.19.0 / node 24.18.0). Lockfile now pins three 0.186.1 + hyparquet 1.31.3, 151 packages. Diff reviewed clean: only additions are three + hyparquet (both zero-dep MIT); removals are 3 stale `@svta/cml-*` peer-ghost entries.
- **Proof:** `npm run build` = the full Vercel chain (test:customer-release → live-odds-vnext + board-release + edge-data + customer-truth + verify-data-sources.mjs → test:app-navigation → odds-scroll tests → vite build) — **PASSED (`✓ built in 1m 12s`)**.
- **Side notes:** killed the two stale previews (PIDs 7848 :8611, 30032 :8613 — only ours, Codex runtimes untouched). esbuild@0.21.5 postinstall is blocked by npm 11's install-scripts allowlist — harmless (binary ships via optionalDependencies; build proven).

### B3 — games.parquet never mirrored (loadGames() 404s on fresh clones) — FIXED
- **Fix:** `nfl-data-refresh.yml` gained the mirror line after the pbp-2026 copy: schedules release → `public/nfl-stats/parquet/games.parquet` (+ comment naming `loadGames()` in `src/lib/nflParquet.js` as the consumer).
- **Proof:** exporter fetch verified (`fetch(E["schedules"], …)`; cache-mangling pattern matches sibling lines); local mirror present (521,305 bytes); abet-stats snapshot re-synced (107 lines), commit `a2fe06b`.

### B2 — bundle staleness measured from mtime (CI checkouts stamp every file with checkout time) — FIXED (sentinel v1.0.2)
- **Fix:** `check_bundles()` now reads each bundle's own `generated_at` (parse_iso, ValueError-safe; mtime fallback), records `generated_at` + `ts_source` in state, and computes staleness vs the remote cut from `generated_at`.
- **Proof (live dry-run 2026-10-10T21:52Z):** `2026 bundle: weeks 1..4 contiguous=True stale_vs_remote=45.5h` — now the bundle's real stamp drives the math. Status lists all 28 season bundles with the new fields; proof-page bundles table gained generated_at + ts-source columns.
- **Known transient:** the 45.5h reading is inflated ~23h by the (since-corrected) clock skew that stamped the Oct 8 export; it exceeds STALE_HOURS=36 so a STALE_BUNDLES alarm event logged — directionally correct (our bundle does lag today's Saturday cuts) and self-heals on the next refresh, which now stamps honestly. Bundle alarms are log/digest-visible (daily 16:00Z digest), not alert-spam.

### B4 — CUSUM advertised in the docs but never wired — FIXED (sentinel v1.0.2)
- **Fix:** one-sided CUSUM wired into `observe_feed()` between the z-check and the EWMA update. Steps only on fresh cuts; only once the size baseline is trusted (`n >= MIN_BASELINE_N=5`, same trust gate as z); sigma floor `max(sqrt(var), |mu|·0.002, 1.0)`; on drift: SIZE_ANOMALY (dedup-guarded) + "cusum drift (sustained size growth over N cuts)" detail; statistic resets per episode so one drift episode pages once, not once per later cut. `--status` shows `cusum_s/n` per feed; check summary shows `c=`.
- **Proof:** replay 15/15 (cusum_step fires on +2σ drift within 10 steps, silent on flat) **and** the live dry-run stepped for real: `schedules … c=0.0` (baseline n=7, first live step; other feeds warm up at n=4).

## Gates (all green)

| Gate | Result |
|---|---|
| `npm run build` (full Vercel chain) | PASSED — `✓ built in 1m 12s` |
| Sentinel `--replay-test` | 15/15 |
| Sentinel `--check --dry-run` (live GitHub API) | 8/8 feeds, cuts 0.3h–8.3h fresh, z within ±1 |
| Sentinel `--status` | 28/28 season bundles contiguous; per-feed bytes baselines + cusum visible |
| `build_sentinel_proof.py` | proof page regenerated — 29,465 bytes, names v1.0.2 |
| `verify_sentinel.py` | 16/16 |
| `verify_data.py` | 25/25 |

## Backups (BEFORE-fix, never staged)

| File | Stamp |
|---|---|
| package.json + package-lock.json (worktree) | `20261010_1428_BEFORE_lockfile_sync` |
| nfl-data-refresh.yml (worktree) | `20261010_1443_BEFORE_games_parquet_mirror` |
| nfl_data_sentinel.py (abet-stats + worktree) | `20261010_1450_BEFORE_v1_0_2_generated_at_cusum` |
| build_sentinel_proof.py (abet-stats + worktree) | `20261010_1450_BEFORE_v1_0_2_generated_at_cusum` |
| nfl-data-sentinel-proof.html, sentinel_state.json, sentinel_log.jsonl | `20261010_1450_BEFORE_v1_0_2_generated_at_cusum` |

**Rollback:** copy each `_backup_…_BEFORE_…` file over its live path (restore original name), then re-run `npm run build` + the sentinel gates to confirm.

## Open items (operator decisions — not in this batch)

- **D-1..D-6** (pitch) gate the dashboard commit/push; the library-first abet-stats checkout wiring lands with it.
- **D-7** refresh cadence: workflow still Tue/Wed 14:00Z; recommendation on the table: `0 14 * * 0,1,2,3,5`.
- **D-8** RESOLVED by wiring (this doc) — veto window open.
- **User-global `~/.npmrc` `package-lock=false`** remains a machine-wide landmine for every other project on this box. Recommend removing that line (this repo is protected by its project `.npmrc` either way). Operator decision.
- **Machine clock** corrected ~2026-10-10 14:20 local (was ~23h slow). Commit dates before that carry the skew; harmless to contents.
- Optional: run a local refresh (or wait for CI) so the 2026 bundle picks up today's cuts and the skewed `generated_at` stamp self-heals.
