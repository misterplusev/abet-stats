#!/usr/bin/env python
"""Machine checks for the NFL Data Sentinel v1.0.0.

Run after: nfl_data_sentinel.py --check  and  build_sentinel_proof.py
Prints n/n sentinel checks passed; exit code 1 if any failed (stdlib only).
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

WORKTREE = pathlib.Path(r"D:\abet_dev\claude_dashboard_pills_20260925")
MON = WORKTREE / "scripts" / "monitor"
STATE_FILE = MON / "state" / "sentinel_state.json"
LOG_FILE = MON / "state" / "sentinel_log.jsonl"
PROOF = pathlib.Path(r"D:\nfl-progression\proof\nfl-data-sentinel-proof.html")

results: list = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), str(detail)))
    print(("PASS " if ok else "FAIL ") + name + (f" ({detail})" if detail else ""))


def load_sentinel():
    spec = importlib.util.spec_from_file_location("sentinel", MON / "nfl_data_sentinel.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sentinel"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    sentinel = load_sentinel()

    state = None
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except ValueError as exc:
            state = None
            check("sentinel_state.json parses", False, str(exc))
    check("sentinel_state.json exists and parses", isinstance(state, dict))
    check("state version == 1", bool(state) and state.get("version") == 1,
          f"version={state.get('version') if state else None}")
    check("state has a recent last_check_at", bool(state) and bool(state.get("last_check_at")),
          state.get("last_check_at") if state else "")

    events = []
    if LOG_FILE.exists():
        for line in LOG_FILE.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except ValueError:
                check("every sentinel_log.jsonl line parses", False, line[:80])
                break
    check("sentinel_log.jsonl exists with events", LOG_FILE.exists() and len(events) > 0,
          f"{len(events)} events")

    checks = [e for e in events if e.get("type") == "check" and e.get("feed") and e["feed"] != "_api"]
    latest = {}
    for ev in checks:
        latest[ev["feed"]] = ev
    check("latest check covers >= 5 feeds", len(latest) >= 5, f"{len(latest)} feeds: {sorted(latest)}")

    ok_shape = all(ev.get("ts") and ev.get("feed") and ev.get("status") for ev in checks)
    check("every check event has ts/feed/status", ok_shape)

    unknown = sorted({a for ev in events for a in (ev.get("alarms") or []) if a not in sentinel.KNOWN_ALARMS})
    check("all alarm types are known", not unknown, f"unknown={unknown}")

    replay = sentinel.replay_test()
    passed = sum(1 for _, ok, _ in replay if ok)
    check("replay validation fully passes", passed == len(replay), f"{passed}/{len(replay)}")

    check("proof page exists", PROOF.exists(), str(PROOF))
    html = PROOF.read_text(encoding="utf-8") if PROOF.exists() else ""
    need = ["id='feeds'", "id='baselines'", "id='bundles'", "id='events'", "id='validation'", "id='ops'"]
    missing = [m for m in need if m not in html]
    check("proof page has all six required sections", not missing, f"missing={missing}")
    check(f"proof page names v{sentinel.VERSION}", f"v{sentinel.VERSION}" in html)
    check("proof page is a substantive document (> 12 KB)",
          PROOF.exists() and PROOF.stat().st_size > 12_000,
          f"{PROOF.stat().st_size if PROOF.exists() else 0:,} bytes")

    data_dir = WORKTREE / "public" / "nfl-stats" / "data"
    live = data_dir / "season_2026.json"
    weeks_ok = False
    if live.exists():
        doc = json.loads(live.read_text(encoding="utf-8"))
        weeks = doc.get("weeks") or []
        weeks_ok = weeks == list(range(1, len(weeks) + 1)) and len(weeks) >= 3
    check("season_2026.json weeks contiguous and >= 3", weeks_ok)

    discord = [e for e in events if e.get("type") == "discord"]
    check("a discord outcome was recorded (posted/skipped/failed)",
          bool(discord), discord[-1].get("status") if discord else "none")

    check("tag inventory has >= 10 tags", bool(state) and len(state.get("tag_inventory", {})) >= 10,
          f"{len(state.get('tag_inventory', {})) if state else 0} tags")

    check("no unparsed log lines", all(e.get("type") != "unparsed" for e in events))

    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} sentinel checks passed")
    if failed:
        print("failed: " + "; ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
