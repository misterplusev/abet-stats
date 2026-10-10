#!/usr/bin/env python
r"""Build nfl-data-sentinel-proof.html from the sentinel's state + log (stdlib only).

Reads scripts/monitor/state/sentinel_{state.json,log.jsonl}, re-runs the sentinel's
offline replay validation, and emits a self-contained proof page to
D:\nfl-progression\proof\nfl-data-sentinel-proof.html (served on :8612).
"""
from __future__ import annotations

import html
import importlib.util
import json
import pathlib
import sys
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
WORKTREE = HERE.parents[1]
STATE_FILE = HERE / "state" / "sentinel_state.json"
LOG_FILE = HERE / "state" / "sentinel_log.jsonl"
OUT = pathlib.Path(r"D:\nfl-progression\proof\nfl-data-sentinel-proof.html")

CSS = """
:root { color-scheme: dark; }
body { background:#0b0e14; color:#d7dce5; font:13px/1.55 ui-monospace,Consolas,monospace; margin:0; padding:28px; }
h1 { color:#d4af37; font-size:22px; margin:0 0 4px; }
h2 { color:#d4af37; font-size:15px; margin:30px 0 10px; border-bottom:1px solid #262c38; padding-bottom:5px; }
.sub { color:#8a93a6; margin-bottom:18px; }
.badges span { display:inline-block; border:1px solid #262c38; border-radius:10px; padding:1px 10px; margin-right:6px; font-size:12px; }
.ok { color:#7ee787; } .warn { color:#e3b341; } .bad { color:#ff7b72; }
table { border-collapse:collapse; width:100%; margin:6px 0 14px; }
th, td { border:1px solid #262c38; padding:4px 8px; text-align:left; vertical-align:top; }
th { background:#12161f; color:#d4af37; font-weight:600; }
tr:nth-child(even) td { background:#0e1219; }
pre { background:#0e1219; border:1px solid #262c38; border-radius:6px; padding:12px; overflow:auto; font-size:12px; }
code { color:#9cd1ff; }
.small { color:#8a93a6; font-size:12px; }
"""


def load_sentinel():
    spec = importlib.util.spec_from_file_location("sentinel", HERE / "nfl_data_sentinel.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sentinel"] = mod
    spec.loader.exec_module(mod)
    return mod


def all_events() -> list:
    if not LOG_FILE.exists():
        return []
    out = []
    for line in LOG_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            out.append({"ts": "?", "type": "unparsed", "detail": line[:160]})
    return out


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def main() -> int:
    sentinel = load_sentinel()
    state = sentinel.load_state()
    events = all_events()
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    replay = sentinel.replay_test()
    passed = sum(1 for _, ok, _ in replay if ok)

    latest = {}
    for ev in events:
        if ev.get("type") == "check" and ev.get("feed") and ev["feed"] != "_api":
            latest[ev["feed"]] = ev

    parts = []
    add = parts.append
    add(f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>NFL Data Sentinel proof</title><style>{CSS}</style></head><body>")
    add(f"<h1>NFL Data Sentinel v{sentinel.VERSION} - proof page</h1>")
    add(f"<div class='sub'>Generated {esc(generated)} by scripts/monitor/build_sentinel_proof.py - "
        f"state: {esc(STATE_FILE)} - log: {esc(LOG_FILE)}</div>")
    n_alarms = sum(len(ev.get("alarms", [])) for ev in latest.values())
    verdict_cls = "ok" if passed == len(replay) else "bad"
    alarm_cls = "warn" if n_alarms else "ok"
    add("<div class='badges'>"
        f"<span class='{verdict_cls}'>replay validation {passed}/{len(replay)}</span>"
        f"<span>feeds tracked {len(latest)}</span>"
        f"<span class='{alarm_cls}'>open alarms {n_alarms}</span>"
        f"<span>total checks {state.get('checks', 0)}</span>"
        f"<span>tags discovered {len(state.get('tag_inventory', {}))}</span>"
        "</div>")

    add("<h2 id='mission'>1. Mission and architecture</h2>")
    add("<p class='small'>The sentinel watches every nflverse/nflverse-data release that feeds the NFL Stats module, "
        "logs each observation to an append-only JSONL audit trail, learns arrival/size baselines, raises "
        "human-readable alarms, posts Discord alerts/digests (webhook via env only), and recommends the refresh "
        "runbook when our shipped bundles fall behind.</p>")
    add("<pre>"
        "nflverse-data releases (GitHub)\n"
        "        |  one API call: releases?per_page=100  -&gt; tag inventory (exhaustive discovery)\n"
        "        v\n"
        "  [nfl_data_sentinel.py --check]\n"
        "        |-- observations -------&gt; scripts/monitor/state/sentinel_log.jsonl  (audit, append-only)\n"
        "        |-- learned baselines --&gt; sentinel_state.json  (EWMA bytes, MAD arrival windows, CUSUM)\n"
        "        |-- alarms: NEW_CUT LATE SIZE_ANOMALY ASSET_MISSING TAG_MISSING STALE_BUNDLES WEEKS_NOT_CONTIGUOUS\n"
        "        v\n"
        "  DISCORD_WEBHOOK_NFL (env) -- digest/alert --&gt; Discord NFL channel\n"
        "        v\n"
        "  shipped bundles public/nfl-stats/data/season_*.json checked for continuity + staleness\n"
        "        (stale -&gt; recommend: nfl_stats_export.py --refresh + augment_catalog.py)\n"
        "</pre>")

    add("<h2 id='feeds'>2. Feed status (latest check)</h2>")
    add("<table><tr><th>feed</th><th>status</th><th>tag</th><th>cut age (h)</th><th>watched assets</th>"
        "<th>bytes (MB)</th><th>z</th><th>alarms</th><th>detail</th></tr>")
    for feed, ev in sorted(latest.items()):
        cls = "bad" if ev.get("alarms") else "ok"
        wb = "-" if ev.get("watched_bytes") is None else f"{ev['watched_bytes'] / 1e6:.2f}"
        alarms_txt = ", ".join(ev.get("alarms") or []) or "-"
        add("<tr>"
            f"<td>{esc(feed)}</td><td class='{cls}'>{esc(ev.get('status'))}</td><td>{esc(ev.get('tag'))}</td>"
            f"<td>{esc(ev.get('hours_since_cut', '-'))}</td><td>{esc(ev.get('watched_assets', 0))}</td>"
            f"<td>{wb}</td>"
            f"<td>{esc(ev.get('z', '-'))}</td><td>{esc(alarms_txt)}</td>"
            f"<td class='small'>{esc(ev.get('detail', ''))}</td></tr>")
    add("</table>")

    add("<h2 id='baselines'>3. Learned baselines</h2>")
    add("<p class='small'>EWMA updates only on new cuts (re-observing an unchanged release does not deflate variance). "
        "Size alarms are trusted after n&gt;=5 observations (warmup). Arrival windows switch from the configured prior "
        "to the learned median +/- 3*MAD after &gt;=4 cuts on the same weekday.</p>")
    add("<table><tr><th>tag</th><th>observations</th><th>bytes mu (EWMA)</th><th>bytes var (EWMA)</th>"
        "<th>cuts seen</th><th>learned window today</th></tr>")
    today = sentinel.now().weekday()
    for tag, fs in sorted(state.get("feeds", {}).items()):
        b = fs.get("bytes") or {}
        win = sentinel.learned_window(fs, today)
        mu_s = "-" if b.get("mu") is None else f"{b['mu']:,.0f}"
        var_s = "-" if b.get("var") is None else f"{b['var']:,.0f}"
        win_s = win if win else "prior / learning (needs 4+ same-weekday cuts)"
        add("<tr>"
            f"<td>{esc(tag)}</td><td>{esc(fs.get('obs', 0))}</td>"
            f"<td>{mu_s}</td><td>{var_s}</td>"
            f"<td>{esc(len(fs.get('arrivals') or []))}</td>"
            f"<td>{esc(win_s)}</td></tr>")
    add("</table>")

    add("<h2 id='bundles'>4. Shipped-bundle continuity and freshness</h2>")
    add("<table><tr><th>bundle</th><th>weeks</th><th>last week</th><th>contiguous</th>"
        "<th>stale vs remote (h)</th><th>mtime (UTC)</th></tr>")
    for name, b in sorted(state.get("bundles", {}).items()):
        if not b.get("weeks"):
            continue
        contig_cls = "ok" if b.get("contiguous") else "bad"
        add("<tr>"
            f"<td>{esc(name)}</td><td>{esc(b.get('weeks'))}</td><td>{esc(b.get('last_week'))}</td>"
            f"<td class='{contig_cls}'>{esc(b.get('contiguous'))}</td>"
            f"<td>{esc(b.get('stale_hours_vs_remote', 'n/a'))}</td><td class='small'>{esc(b.get('mtime'))}</td></tr>")
    add("</table>")

    add("<h2 id='events'>5. Event log (last 80, newest first)</h2>")
    add("<table><tr><th>ts (UTC)</th><th>type</th><th>feed</th><th>status</th><th>detail</th></tr>")
    for ev in list(reversed(events))[:80]:
        cls = "bad" if ev.get("status") in ("alarm", "error", "failed") else ""
        feed = ev.get("feed", ev.get("tag", ""))
        add("<tr><td class='small'>{}</td><td>{}</td><td>{}</td><td class='{}'>{}</td>"
            "<td class='small'>{}</td></tr>".format(
                esc(ev.get("ts")), esc(ev.get("type")), esc(feed),
                cls, esc(ev.get("status", "")), esc(ev.get("detail", ""))))
    add("</table>")

    add("<h2 id='validation'>6. Validation suite and formulas</h2>")
    add("<table><tr><th>test</th><th>result</th><th>detail</th></tr>")
    for name, ok, detail in replay:
        cls = "ok" if ok else "bad"
        verdict = "PASS" if ok else "FAIL"
        add(f"<tr><td>{esc(name)}</td><td class='{cls}'>{verdict}</td>"
            f"<td class='small'>{esc(detail)}</td></tr>")
    add("</table>")
    add("<pre>"
        "EWMA mean/variance:  mu' = a*x + (1-a)*mu ;  v' = a*(x-mu)^2 + (1-a)*v ;  a = 0.25\n"
        "Robust size z:       z = (x - mu) / max(sqrt(v), 0.002*|mu|, 1) ;  alarm |z| &gt; 3 after n &gt;= 5\n"
        "MAD arrival window:  med = median(hours) ; mad = max(median(|h-med|), 0.5) ; window = med +/- 3*mad (n &gt;= 4)\n"
        "LATE rule:           prior: after the arrival window closes, no cut since this cycle's\n"
        "                     window start and hours_since_cut &gt; late_hours (all-days feeds: pure max-gap)\n"
        "                     learned: now &gt; window.hi + 2h and last_cut &lt; today's window start\n"
        "CUSUM drift:         s = max(0, s + (x-mu)/sigma - 0.5) ; alarm s &gt; 5 (upward size drift)\n"
        "Suppression:         each alarm posts at most once per release cut (keyed by published_at)\n"
        "</pre>")

    add("<h2 id='ops'>7. Operations</h2>")
    add("<pre>"
        "local check:   python scripts/monitor/nfl_data_sentinel.py --check --dry-run\n"
        "local digest:  python scripts/monitor/nfl_data_sentinel.py --check --digest   (posts to DISCORD_WEBHOOK_NFL)\n"
        "status:        python scripts/monitor/nfl_data_sentinel.py --status\n"
        "validation:    python scripts/monitor/nfl_data_sentinel.py --replay-test\n"
        "cloud:         .github/workflows/nfl-data-sentinel.yml (daily 16:00 UTC + manual dispatch;\n"
        "               commits scripts/monitor/state so the cloud keeps its memory)\n"
        "machine gate:  D:\\nfl-progression\\proof\\verify_sentinel.py\n"
        "refresh chain: nfl-data-refresh.yml -&gt; export --refresh, mirrors, augment_catalog.py,\n"
        "               build_career_leaders.py, build_widget_inventory.py, strict-JSON + week gate, commit\n"
        "rules:         webhook URLs never committed or printed (RULE 13); state committed by the bot only\n"
        "</pre>")

    add(f"<div class='small'>End of proof. Generated by build_sentinel_proof.py - sentinel v{sentinel.VERSION} - "
        "served at http://127.0.0.1:8612/nfl-data-sentinel-proof.html</div>")
    add("</body></html>")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(parts), encoding="utf-8")
    size = OUT.stat().st_size
    print(f"wrote {OUT} ({size:,} bytes) | replay {passed}/{len(replay)} | feeds {len(latest)} | events {len(events)}")
    return 0 if passed == len(replay) else 1


if __name__ == "__main__":
    sys.exit(main())
