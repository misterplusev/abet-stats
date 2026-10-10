# 20261008_133000 — NFL STATS MODULE — CLOUD INTEGRATION MASTER PITCH FOR CLAUDE CODE OPUS 5.5 — v1_0_0

Audience: Claude Code Opus 5.5 (the agent that will execute the cloud integration).
Authority: this document supersedes `docs/20261005_131500_NFL_STATS_MODULE_ABET_DASHBOARD_INTEGRATION_
PLAN_v1_0_0.md` for everything except its historical record (the old plan's numbers are stale).
Companion documents (read in this order):
1. `docs/20261008_112000_NFL_DATA_SENTINEL_v1_0_1.md` — the data pipeline + sentinel system.
2. `docs/20261005_150000_NFL_STATS_MODULE_SESSION_HANDOFF_FULL_STATE_v1_0_0.md` — full module state.
3. `docs/20261002_141343_NFL_STATS_MODULE_ARCHITECTURE_OPERATIONS_AND_DATA_BIBLE_v1_0_0.md` — bible
   (schemas, algorithms, changelog #1-#33).
4. `AGENTS.md` (worktree root) — hard rules that repeat offenders keep relearning.
5. `E:\abet\CLAUDE_CODE_RULES.md` — production rules (backups RULE 2, session logs RULE 4, POC
   RULE 5, verify RULE 6, same-origin RULE 7, VM deploy RULE 11, heavy ops RULE 12, Discord
   env-only RULE 13).
6. `docs/20261008_134000_LEGACY_NFLVERSE_SYNC_ORCHESTRATOR_AUDIT_AND_RETIREMENT_DOCUMENTATION_
   v1_0_0.md` — the legacy system this plan replaces.

User decision on record (2026-10-08): **cloud, exclusively cloud build dashboard.** The entire NFL
Stats module — code, data, automation, monitoring — must run from GitHub + GitHub Actions + the
cloud dashboard build. Local machines become development/reference only; no local step may be
required for steady-state operation.

---

## 1. Verified current state (2026-10-08, do not re-derive — verify once and proceed)

| Fact | Value |
|---|---|
| Worktree | `D:\abet_dev\claude_dashboard_pills_20260925` |
| Branch | `claude/odds-pills-4codds-20260925` |
| Remote | `https://github.com/misterplusev/abet-mlb-monitor-widgets.git` (gh CLI logged in as misterplusev) |
| Local gates | **173/173** suite assertions · **25/25** data checks · **47** proof screenshots · 0 page errors |
| Sentinel gates | **15/15** replay validation · **16/16** machine checks |
| Proof pages | `http://127.0.0.1:8612/nfl-dashboard-module-proof.html` (23.08 MB, 47 images) · `http://127.0.0.1:8612/nfl-data-sentinel-proof.html` (23,645 bytes) |
| Module URL (dev) | `http://127.0.0.1:8611/?section=stats&tab=nfl-stats` |
| Live 2026 data | week 4, contiguous 1-4, 2,601 players; players_index 15,480; refreshed 2026-10-08 |
| Asset weight | `public/nfl-stats/` = 98.7 MB (data 51.1 MB + parquet 47.6 MB) |
| Node local | v24.18.0 / npm 11.19.0 (Vercel/Actions use their own pinned versions) |
| Discord evidence | NFL-channel digest http 204 2026-10-07 22:10Z; claudecode receipt msg id 1557825575366955029 |

Nothing is committed yet: 5 modified tracked files + all NFL/MLB/sentinel/docs paths are untracked
(see section 2). This is intentional — push/deploy requires explicit user approval (RULE: never
push without explicit user go).

---

## 2. Complete inventory of what must ship (the closed set question)

The dispatcher edit imports BOTH modules (verified diff 2026-10-08):

```
src/widgets/StatsEmbedWidget.jsx  (MODIFIED)
+ import NFLStatsWidget from './NFLStatsWidget'
+ import MLBStatsWidget from './mlbstats/MLBStatsWidget'
+ if (sportTab === 'nfl-stats') return <NFLStatsWidget />
+ if (sportTab === 'mlb-stats') return <MLBStatsWidget />
```

Therefore the commit is a CLOSED SET against the build: committing the dispatcher without the
files it imports breaks the cloud build. Two coherent options:

- **Option COMBINED (default recommendation):** ship the NFL module AND the MLB stats module
  together (both are complete untracked work in this branch, both reachable from the dispatcher).
  Precondition: the MLB module must pass its own local smoke + the repo build before staging.
- **Option NFL-ONLY (fallback):** ship only the NFL paths and adjust the dispatcher to a
  guarded import (e.g. lazy `React.lazy` for MLB or a commented route) so the build stays closed.
  Requires a small, separately verified dispatcher edit and leaves MLB work untracked.

### 2a. Untracked paths belonging to the NFL module + automation (must ship for Option COMBINED anyway)

| Path | Contents | Weight |
|---|---|---|
| `src/nflstats/` | core (engine/constants/urlState/registry), ui (8), charts (17 + scales/hover/theme), 11 feature silos | 49 files, ~233 KB |
| `src/widgets/NFLStatsWidget.jsx` + `src/widgets/NFLStatsWidget.css` | 511-line JSX shell + styles (the CSS was missing from the old plan's manifest — include it) | ~35 KB |
| `src/lib/nflStats.js`, `nflParquet.js`, `nflModels.js`, `chartExport.js` | data lane, parquet lane, models, PNG export | ~120 KB |
| `scripts/publish/` | `nfl_stats_export.py`, `augment_catalog.py`, `build_career_leaders.py`, `build_widget_inventory.py`, `build_stat_docs.py`, +2 | 7 files |
| `scripts/monitor/` | `nfl_data_sentinel.py` (v1.0.1), `build_sentinel_proof.py`, `.gitignore`, `state/` (sentinel_state.json + sentinel_log.jsonl — committed by design so CI keeps memory) | ~90 KB |
| `public/nfl-stats/data/` | 28 season bundles (1999-2026) + catalog + players_index + stat_docs + career_leaders + widget_inventory | 51.1 MB |
| `public/nfl-stats/parquet/` | same-origin mirrors: stats_player_week_1999..2026, team_week_1999..2025 + stats_team_week_2026, play_by_play_2025/2026, games.parquet | 47.6 MB |
| `.github/workflows/nfl-data-refresh.yml` | consolidated refresh pipeline (export --refresh → mirrors → augment → career leaders → inventory → strict-JSON + week gates → commit → optional Discord receipt) | — |
| `.github/workflows/nfl-data-sentinel.yml` | daily 16:00 UTC sentinel (check + digest + replay-test + state commit + artifact) | — |
| `docs/` (the NFL docs set) | all dated docs incl. this pitch (see section 11) | ~1 MB |
| `AGENTS.md` | auto-discovery entry point (must keep its exact name) | 2 KB |
| `src/data/cfbEspnTeams.json` | only if the dispatcher/build references it (verify with a grep before staging; otherwise leave) | small |

### 2b. Modified tracked files (5)

| File | Change |
|---|---|
| `package.json` | + `"hyparquet": "^1.31.2"`, + `"three": "^0.186.1"` (recommended: add `"engines": { "node": ">=20" }` while touching it — optional hardening) |
| `src/widgets/StatsEmbedWidget.jsx` | dispatcher routes `nfl-stats` and `mlb-stats` (closed-set implications above) |
| `src/widgets/index.js` | exports `NFLStatsWidget` + `MLBStatsWidget` |
| `src/lib/logoMaps.js` | NFL mappings |
| `src/lib/teamLogos.js` | NFL mappings |

### 2c. MLB co-residency (Option COMBINED only)

| Path | Notes |
|---|---|
| `src/widgets/MLBStatsWidget.jsx` + `.css` | MLB shell; backups exist (`*.backup_2026...`) — do NOT commit backups |
| `src/widgets/mlbstats/`, `src/statsui/` | MLB silos/ui |
| `src/lib/mlb/`, `src/lib/mlbStats.js` | MLB lanes; `mlbStats.legacy_backup_20261004_pre_modular.js` is a backup — do NOT commit |
| `public/mlb-stats/` | MLB data assets (measure before staging: `Get-ChildItem public/mlb-stats -Recurse -File | Measure-Object Length -Sum`) |

Backup-suffixed files (`*.backup_*`) and `refresh-nfl-data.bat` are development artifacts: exclude
from the commit (add to `.gitignore` or leave untracked; see section 8).

---

## 3. Knowledge base — everything discovered (F-register; do not relearn the hard way)

- **F-01 nflverse `published_at` trap (critical):** releases are re-cut by RE-UPLOADING assets;
  `published_at` is stale by YEARS. The true cut time = `max(asset.updated_at)`. Any staleness/
  arrival logic on `published_at` produces nonsense alarms. The sentinel uses asset timestamps
  exclusively; keep it that way.
- **F-02 Real tag names:** one API call (`/releases?per_page=100`) returns all 25 tags:
  stats_player, stats_team, pbp, schedules, rosters, weekly_rosters, depth_charts, injuries,
  pfr_advstats, snap_counts, nextgen_stats, ftn_charting, espn_data, players, players_components,
  draft_picks, contracts, trades, teams, officials, misc, combine, pbp_participation, player_stats,
  test. `pt_spread` does NOT exist in nflverse-data — never reference it.
- **F-03 Mandatory pipeline order:** exporter → `augment_catalog.py` → career leaders → inventory.
  The raw exporter WIPES catalog `qualifiers`/`stat_sources`; skipping augment breaks the Qualify
  control (the 173-suite caught this on 2026-10-05). The consolidated workflow enforces the order.
- **F-04 Build green ≠ runtime-safe:** a missing `RefreshCw` import passed the bundler and only the
  suite caught it. Run the suite, always.
- **F-05 The stale loop works:** sentinel caught the bundle 46.7h behind an overnight re-cut; the
  refresh chain was run and staleness went to -1.3h. This is the intended automatic behavior once
  the workflows are active.
- **F-06 Chatty feeds:** `schedules` re-cuts its timestamp files constantly; the sentinel logs the
  change but suppresses channel pages (config flag `chatty`). Add new feeds conservatively.
- **F-07 GitHub Actions YAML:** `secrets` is NOT usable in step `if:` (workflow fails validation);
  map to a job-level `env:` and test `env.X != ''`. Fixed in nfl-data-refresh.yml.
- **F-08 Windows docstring escapes:** paths like `D:\nfl-progression` inside normal `""" docstrings`
  trigger `\p` SyntaxWarnings/`\n` newlines; use `r"""` raw docstrings.
- **F-09 Verifiers must read versions dynamically** (`sentinel.VERSION`), never literals — the
  v1.0.0→v1.0.1 bump broke a hardcoded check and cost a cycle.
- **F-10 Cloud state:** Actions runners are stateless; the sentinel commits `scripts/monitor/state/`
  so the cloud keeps its learned baselines. The refresh bot commits data. Both use
  `abet-data-bot` identity with concurrency groups set.
- **F-11 Alarm suppression:** one Discord post per alarm per release cut (keyed by cut timestamp);
  without it the channel would be spammed daily.
- **F-12 Closed-set commits:** see section 2. Diff `StatsEmbedWidget.jsx` BEFORE staging.
- **F-13 Proof discipline:** run `build_module_proof.py` only AFTER `verify_data.py` (JSON race);
  proof bundle: `verify_data.py` → `capture_module.py` → `build_module_proof.py`.
- **F-14 Playwright + controlled React inputs:** range sliders need the native value setter
  (`Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set`) then an `input`
  event; `fill()` fails on float step grids.
- **F-15 PowerShell quoting:** write patch/one-off scripts to `.py` files and run them; never
  inline `python -c` (quoting hell). Same for long strings: use `--file` flags.
- **F-16 98.7 MB assets:** fine in-repo for now (see section 7 for the R2 decision gate).
- **F-17 Legacy orchestrator is dead** (see the companion legacy audit doc): disabled tasks, no
  recent logs, hardcoded webhooks predating RULE 13, DuckDB target incompatible with the module.
  Do not resurrect; use the sentinel + refresh workflows.
- **F-18 `refresh-nfl-data.bat`** is a local manual helper from a previous attempt: inspect, do not
  commit; the cloud workflow replaces it. Retire to `E:\abet\.cache\tmp\opencode\` on request.
- **F-19 `AGENTS.md` must ship untouched in name**; it is the entry point every future agent reads.
- **F-20 F7 live-odds is DO NOT TOUCH.** Never modify live-odds code/pipelines during this work.
- **F-21 The module is same-origin by construction (RULE 7):** bundles + parquet mirrors in
  `public/nfl-stats/`; only images hotlink ESPN/nflverse CDNs with `crossOrigin=anonymous`.
- **F-22 Roster/player churn is real:** the 2026-10-08 refresh grew 2026 from 2,542 → 2,601
  players and players_index 15,461 → 15,480. Contiguity checks are auto-growing; never hardcode
  week/player counts in assertions.

---

## 4. Target architecture — exclusively cloud

```
                     +------------------------------------------------------+
                     | GitHub: misterplusev/abet-mlb-monitor-widgets (main) |
                     +------------------+-----------------------------------+
                                        |
        push/merge (user-approved)      |     schedules + manual dispatch
                                        v
   +------------------------------------+-------------------------------------+
   | GitHub Actions (cloud)                                                   |
   |  nfl-data-refresh.yml   Tue+Wed 14:00 UTC : export --refresh -> mirrors  |
   |      -> augment_catalog.py -> career leaders -> inventory -> strict-JSON |
   |      + week gates -> commit data (abets-data-bot) -> optional receipt    |
   |  nfl-data-sentinel.yml  daily 16:00 UTC : check -> digest -> replay-test |
   |      -> commit scripts/monitor/state -> artifact                         |
   +------------------------------------+-------------------------------------+
                                        |
                                        v
   +------------------------------------+-------------------------------------+
   | Cloud dashboard build (abet-dashboard; Vercel or equivalent)             |
   |  builds from the GitHub repo on every push (code and data-bot commits)   |
   |  serves: /?section=stats&tab=nfl-stats + /nfl-stats/** (98.7 MB static)  |
   +------------------------------------+-------------------------------------+
                                        |
                                        v
                    Discord receipts (repo secret DISCORD_WEBHOOK_NFL)
                    RULE 13: webhooks exist only in .env locally / repo secrets in CI
```

Steady state after activation: no local machine is required. Local = development, proof reruns
and debugging only. The proof bundle remains a development artifact (never deployed).

---

## 5. Execution plan for Opus 5.5 (phases, exact commands, gates, approvals)

All commands run from `D:\abet_dev\claude_dashboard_pills_20260925` unless stated. Every phase:
gate first, act second, record evidence. STOP and ask the user at every [USER-GATE].

### P0 — Pre-flight and rollback anchors (no mutation)
```powershell
git status --short                     # expect the section-2 inventory; nothing staged
node "node_modules\vite\bin\vite.js" build        # must print "built in ..." (green baseline)
$env:PLAYWRIGHT_BROWSERS_PATH="D:\nfl-progression\.cache\pw-browsers"; $env:PYTHONIOENCODING="utf-8"
D:\nfl-progression\.venv\Scripts\python.exe D:\nfl-progression\proof\capture_module.py   # 173/173
D:\nfl-progression\.venv\Scripts\python.exe D:\nfl-progression\proof\verify_data.py      # 25/25
D:\nfl-progression\.venv\Scripts\python.exe D:\nfl-progression\proof\build_module_proof.py  # 47 images
git tag pre-nfl-cloud-20261008         # rollback anchor (local tag; push it with the branch)
```
Evidence to record: build time, suite counts, verify counts, proof image count. If ANY gate is red,
STOP — do not integrate a red baseline.

### P1 — Scope decision (closed set) [USER-GATE]
1. `git diff -- src/widgets/StatsEmbedWidget.jsx src/widgets/index.js` — confirm the current
   dispatcher shape.
2. Determine Option COMBINED vs NFL-ONLY (section 2). If COMBINED and the MLB module has not been
   verified in this session: run its local smoke first (build + any MLB checks that exist; ask the
   user which checks are authoritative for MLB). If unverifiable, take NFL-ONLY and make the
   dispatcher minimal-guarded so the build stays closed.
3. Grep for stray imports to keep the set closed:
   `rg -n "nflstats|NFLStatsWidget|mlbstats|MLBStatsWidget" src --glob "*.jsx" --glob "*.js"`
   Every import target must be in the staging set (or lazily guarded).

### P2 — Stage and commit (no push yet)
```powershell
# NFL core (always)
git add src/nflstats src/widgets/NFLStatsWidget.jsx src/widgets/NFLStatsWidget.css `
        src/lib/nflStats.js src/lib/nflParquet.js src/lib/nflModels.js src/lib/chartExport.js `
        scripts/publish scripts/monitor .github/workflows docs AGENTS.md `
        package.json src/widgets/StatsEmbedWidget.jsx src/widgets/index.js `
        src/lib/logoMaps.js src/lib/teamLogos.js public/nfl-stats
# Option COMBINED only (after its own green smoke):
# git add src/widgets/MLBStatsWidget.jsx src/widgets/MLBStatsWidget.css src/widgets/mlbstats `
#         src/statsui src/lib/mlb src/lib/mlbStats.js public/mlb-stats
git status --short                     # ONLY the closed set is staged; no backups, no dist, no bat
git check-ignore dist && echo "dist ignored (expected)"   # confirm dist NOT staged
git commit -m "feat(nfl-stats): ship NFL Stats module + data pipeline + sentinel automation; gates 173/25/47 + 15/15 + 16/16"
```
Do NOT stage: `*.backup_*`, `refresh-nfl-data.bat`, `dist/`, `node_modules/`, `__pycache__/`
(the monitor ships its own `.gitignore`).

### P3 — Repo secrets (RULE 13) [USER-GATE]
```powershell
# read the webhook from E:/abet/.env WITHOUT printing it, then set the repo secret:
$line = (Select-String -Path "E:\abet\.env" -Pattern '^DISCORD_WEBHOOK_NFL=' | Select-Object -First 1).Line
$env:DISCORD_WEBHOOK_NFL = $line.Substring($line.IndexOf('=')+1).Trim().Trim('"')
$env:DISCORD_WEBHOOK_NFL | gh secret set DISCORD_WEBHOOK_NFL --repo misterplusev/abet-mlb-monitor-widgets
gh secret list --repo misterplusev/abet-mlb-monitor-widgets
```
Never echo the value; never write it to a file that gets committed.

### P4 — Push branch + open PR [USER-GATE]
```powershell
git push -u origin claude/odds-pills-4codds-20260925
git push origin pre-nfl-cloud-20261008
gh pr create --title "NFL Stats module + sentinel automation (cloud)" --body-file <dated PR body doc>
```

### P5 — Preview verification (cloud build, RULE 6)
On the preview URL (from `gh pr checks` / Vercel comment) verify, in order:
1. `200` on `/?section=stats&tab=nfl-stats`; the rank chart renders; no console errors.
2. `200` + valid JSON on `/nfl-stats/data/season_2026.json` (weeks 1..4) and
   `/nfl-stats/data/career_leaders.json`.
3. `200` with correct byte size on `/nfl-stats/parquet/play_by_play_2026.parquet`.
4. 3D Lab renders (Teams + Players), Career compare works, Factory code map loads (on-demand).
5. PNG export button downloads a file (browser download event).
Record the exact preview URL + commit SHA in the session log. Any failure: fix on the branch,
re-push, re-verify. Do not merge red.

### P6 — Merge to default branch + activate schedules [USER-GATE]
```powershell
gh pr merge --squash          # then delete branch if the user wants
gh workflow list --repo misterplusev/abet-mlb-monitor-widgets   # all workflows visible
gh workflow run nfl-data-sentinel.yml --repo misterplusev/abet-mlb-monitor-widgets
gh run watch                   # expect success; state commit by abet-data-bot
gh workflow run nfl-data-refresh.yml --repo misterplusev/abet-mlb-monitor-widgets
gh run watch                   # expect success; data commit OR "No data changes this run."
```
Notes: scheduled triggers only run from the default branch — after merge they arm automatically.
The refresh bot's data commits will trigger a fresh cloud dashboard build each week (intended).

### P7 — Production verification, close-out, first-week watch
1. Production checklist = P5 checklist on the production URL.
2. Append to `E:\abet\docs\session_logs\2026-10-XX_session_log.md`: SHAs, run IDs, URLs,
   rollback (`git revert <sha>`; Vercel "previous deployment" instant rollback; tag
   `pre-nfl-cloud-20261008`).
3. RULE 13 receipt via `E:\abet\abet-scraper-scripts\scripts\abet_discord_post.py
   --category claudecode --file <receipt.txt>` (webhook from .env by name; never inline).
4. First-week watch: daily sentinel digest on the NFL channel; Tue/Wed refresh runs; check
   Vercel build minutes; confirm streak of green runs before declaring done.

---

## 6. Verification matrix (local + cloud)

| Gate | Where | Command / action | Expected |
|---|---|---|---|
| Build | local | `node node_modules\vite\bin\vite.js build` | "built in ...", no errors |
| Suite | local | `capture_module.py` | 173/173, 0 page errors |
| Data | local | `verify_data.py` | 25/25 |
| Module proof | local | `build_module_proof.py` | 47 images, ~23 MB html |
| Sentinel replay | local/CI | `nfl_data_sentinel.py --replay-test` | 15/15 |
| Sentinel checks | local | `verify_sentinel.py` | 16/16 |
| Preview smoke | PR preview | P5 checklist | all pass, no console errors |
| Workflows | cloud | `gh workflow list` + dispatch + `gh run watch` | green, commits present |
| Prod smoke | production | P5 checklist | all pass |
| Discord | cloud | first cloud digest + refresh receipt | http 204 equivalents in run logs |

---

## 7. Asset-size strategy for the cloud build (98.7 MB) — decision gate

Default: ship everything in-repo (works today; `public/` files are copy-only in the build; each
file < 100 MB; first build +1-2 min). Decision gate — only if the cloud build starts to hurt:
- Migrate ONLY `public/nfl-stats/parquet/` (47.6 MB, on-demand fetches) to R2/CDN; keep the ~51 MB
  of JSON bundles in-repo (they are synchronous first-paint data).
- Touchpoint is a single base-URL constant in `src/lib/nflParquet.js` (all parquet fetches are
  relative today). Add CORS on the bucket; keep same-origin as the fallback.
- Do NOT attempt Git LFS unless the cloud builder is verified to support it; plain files are the
  known-good path.
- `dist/` (786 MB locally, stale artifacts) must never be committed; verify `.gitignore` with
  `git check-ignore dist` in P2.

---

## 8. Legacy systems and cleanup register (verbose, on purpose)

1. **`E:\abet\scripts\pipelines\automated_sync_orchestrator.py` + `nflverse_sync.py` — DEAD.**
   Full audit in the companion legacy document. Summary: hourly 'nfl' change-detection posting to
   a HARDCODED webhook (predates RULE 13), syncing to DuckDB (not the module's parquet lane),
   logging to `E:\abet\scripts\pipelines\logs\sync\` with no recent files, and no enabled scheduled
   task (all ABET_* tasks Disabled). Recommendation: retire deliberately in a future E:\abet
   session (backup first, RULE 2), documented — do NOT re-enable for this module.
2. **`refresh-nfl-data.bat` (untracked, worktree root).** Local manual helper (exporter + build +
   pause). Superseded by `nfl-data-refresh.yml`. Do not commit; retire to
   `E:\abet\.cache\tmp\opencode\` when the user approves cleanup.
3. **`refresh-nfl-stats-data.yml` — already retired** (2026-10-07). It skipped
   `augment_catalog.py` (qualifier wipe) and lacked mirrors/career steps. Backup:
   `E:\abet\.cache\tmp\opencode\pre-consolidation\refresh-nfl-stats-data.yml.bak`.
4. **Disabled ABET_* scheduled tasks** (local): audit only; no module dependency. Leave alone.
5. **MLB module co-residency:** see section 2c — scope decision, not a cleanup.
6. **Backup-suffixed files** (`*.backup_2026...`): development artifacts; leave untracked,
   consider a `*.backup_*` ignore rule (only with user approval).
7. **`src/data/cfbEspnTeams.json`**: verify references before deciding; if unused by the closed
   set, leave untracked.

---

## 9. Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Closed-set violation (dispatcher imports unstaged files) | medium | P1 grep + local build BEFORE staging; PR preview gate |
| Secrets committed by accident | low | P3 uses env piping only; `git status` review; RULE 13 |
| Scheduled workflows not arming | medium | They only run from default branch; P6 dispatch tests prove them pre-schedule |
| 98.7 MB assets slow the cloud build | low/medium | Section 7 decision gate (R2 migration path, single constant) |
| Data bot commit loop conflicts | low | Concurrency groups set on both workflows; bot identity; small files |
| Discord spam or silence | low | Per-cut suppression + chatty flag; secrets verified in P3 |
| Local-only proof cannot gate prod | medium | P5/P7 cloud smoke checklist; optionally parameterize the Playwright suite base URL later (enhancement, not blocker) |
| RULE 12 violations (heavy ops on VM) | n/a | VM path is out of scope for the cloud-only decision |

---

## 10. Open decisions required from the user BEFORE Opus executes

- **D-1 Scope:** Option COMBINED (ship NFL + MLB together) vs NFL-ONLY (split dispatcher). If
  COMBINED, name the authoritative MLB checks to run.
- **D-2 Build linkage:** confirm the cloud dashboard project (`abet-dashboard`) builds from
  `misterplusev/abet-mlb-monitor-widgets` and which branch is production. Everything in this plan
  assumes main-triggered builds.
- **D-3 Push approval:** explicit go for commit + push + PR (this plan stops before pushing).
- **D-4 Secret:** approve setting repo secret `DISCORD_WEBHOOK_NFL`.
- **D-5 Cleanup:** approve retiring `refresh-nfl-data.bat` and (separately, in E:\abet) the legacy
  orchestrator, per the legacy audit doc.
- **D-6 VM:** confirm the VM dashboard (`E:\abet\dashboard`, RULE 11) is OUT of scope for now.

---

## 11. Cross-reference index

| Document | Purpose |
|---|---|
| `docs/20261008_133000_NFL_STATS_MODULE_CLOUD_INTEGRATION_MASTER_PITCH_FOR_CLAUDE_CODE_OPUS_5_5_v1_0_0.md` | this pitch |
| `docs/20261008_134000_LEGACY_NFLVERSE_SYNC_ORCHESTRATOR_AUDIT_AND_RETIREMENT_DOCUMENTATION_v1_0_0.md` | legacy system audit |
| `docs/20261008_112000_NFL_DATA_SENTINEL_v1_0_1.md` | sentinel system record |
| `docs/20261005_150000_NFL_STATS_MODULE_SESSION_HANDOFF_FULL_STATE_v1_0_0.md` | module handoff (+sentinel addendum) |
| `docs/20261005_150500_NFL_LIVE_PBP_AND_GAME_SIMILARITY_ROADMAP_v1_0_0.md` | next feature roadmap (M1-M5) |
| `docs/20261002_141343_NFL_STATS_MODULE_ARCHITECTURE_OPERATIONS_AND_DATA_BIBLE_v1_0_0.md` | bible, changelog #1-#33 |
| `AGENTS.md` | repo agent entry point |
| `E:\abet\CLAUDE_CODE_RULES.md` | production rules |
| `E:\abet\docs\session_logs\2026-10-08_session_log.md` | this session's actions |

End of pitch. Nothing in this document has been executed beyond local verification; all mutation
steps are user-gated.
