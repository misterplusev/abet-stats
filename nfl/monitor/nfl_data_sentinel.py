#!/usr/bin/env python
"""NFL Data Sentinel v1.0.1 - smart nflverse release monitor (stdlib only).

Watches every nflverse/nflverse-data release that feeds the NFL Stats module,
logs each observation to a JSONL audit trail, learns arrival and size baselines
(EWMA mean/variance, robust MAD arrival windows, one-sided CUSUM), raises
interpretable alarms, and posts Discord alerts/digests.

IMPORTANT nflverse quirk (learned the hard way): the release tag is re-cut
weekly by RE-UPLOADING assets, so `published_at` is stale by years. The true
cut time is max(asset.updated_at) across the tag's assets - that is the signal
this sentinel uses for change detection, arrival learning and staleness.

The Discord webhook comes from the DISCORD_WEBHOOK_NFL environment variable
ONLY (never hardcoded, never printed - E:/abet CLAUDE_CODE_RULES.md RULE 13).

Modes
  --check        observe every feed once; update state + log; post only on
                 fresh new cuts / fresh alarms (repeats are suppressed until
                 the feed publishes its next cut)
  --digest       with --check: also post the digest summary
  --dry-run      with --check: never post (log records why it was skipped)
  --replay-test  offline synthetic validation of every learned/alarm function
  --status       print the latest state summary and exit

Files (state is committed by CI so the cloud run keeps its memory)
  scripts/monitor/state/sentinel_state.json   learned baselines + last-seen feeds
  scripts/monitor/state/sentinel_log.jsonl    append-only audit log

Exit codes: 0 ran ok (alarms are data) | 1 storage/validation failure | 2 bad args
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import math
import os
import statistics
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

VERSION = "1.0.1"
REPO = "nflverse/nflverse-data"
API_LIST = f"https://api.github.com/repos/{REPO}/releases?per_page=100"
API_TAG = f"https://api.github.com/repos/{REPO}/releases/tags/{{tag}}"

BASE = Path(__file__).resolve().parents[2]
STATE_DIR = BASE / "scripts" / "monitor" / "state"
STATE_FILE = STATE_DIR / "sentinel_state.json"
LOG_FILE = STATE_DIR / "sentinel_log.jsonl"
DATA_DIR = BASE / "public" / "nfl-stats" / "data"

# weekday: Monday=0. prior_days / late_hours are the fallback arrival model used
# until >=4 cuts have been observed on that weekday; afterwards the learned
# robust MAD window takes over automatically. All eight tags verified to exist
# in nflverse-data on 2026-10-07 (25 tags total discovered by the list call).
FEEDS = {
    "stats_player": {"tag": "stats_player", "globs": ["stats_player_week_*.parquet"],
                     "prior_days": {1, 2}, "late_hours": 36, "optional": False},
    "stats_team": {"tag": "stats_team", "globs": ["stats_team_week_*.parquet"],
                   "prior_days": {1, 2}, "late_hours": 36, "optional": False},
    "pbp": {"tag": "pbp", "globs": ["play_by_play_*.parquet"],
            "prior_days": {0, 1, 2, 3}, "late_hours": 96, "optional": False},
    "schedules": {"tag": "schedules", "globs": ["games.*", "timestamp.*"],
                  "prior_days": set(range(7)), "late_hours": 168, "optional": False, "chatty": True},
    "rosters": {"tag": "rosters", "globs": ["roster_*.parquet"],
                "prior_days": set(range(7)), "late_hours": 168, "optional": True},
    "weekly_rosters": {"tag": "weekly_rosters", "globs": ["*.parquet"],
                       "prior_days": set(range(7)), "late_hours": 168, "optional": True},
    "depth_charts": {"tag": "depth_charts", "globs": ["depth_charts_*.parquet"],
                     "prior_days": set(range(7)), "late_hours": 168, "optional": True},
    "injuries": {"tag": "injuries", "globs": ["injuries_*.parquet"],
                 "prior_days": set(range(7)), "late_hours": 168, "optional": True},
}

KNOWN_ALARMS = {"NEW_CUT", "LATE", "SIZE_ANOMALY", "ASSET_MISSING", "TAG_MISSING",
                "STALE_BUNDLES", "WEEKS_NOT_CONTIGUOUS", "ERROR"}
MIN_BASELINE_N = 5   # EWMA observations before size alarms are trusted
MIN_WINDOW_N = 4     # arrivals on a weekday before the learned window wins
ALPHA = 0.25         # EWMA smoothing factor
Z_THRESHOLD = 3.0    # robust z alarm level
STALE_HOURS = 36.0   # our live bundle may lag a remote re-cut by this long before nagging
WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# --------------------------------------------------------------------------- time/http

def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_iso(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def http_json(url: str, token: str | None = None):
    req = urllib.request.Request(url, headers={
        "User-Agent": "nfl-data-sentinel/1.0",
        "Accept": "application/vnd.github+json",
    })
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


# --------------------------------------------------------------------------- storage

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return {"version": 1, "created_at": iso(now()), "checks": 0, "feeds": {},
            "tag_inventory": {}, "bundles": {}}


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = iso(now())
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STATE_FILE)


def append_log(events: list) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- learned models

def ewma_update(mu, var, x, alpha=ALPHA):
    """Exponentially weighted mean/variance. First observation seeds the mean."""
    if mu is None:
        return float(x), 0.0
    new_mu = alpha * x + (1.0 - alpha) * mu
    new_var = alpha * (x - mu) ** 2 + (1.0 - alpha) * var
    return new_mu, new_var


def robust_z(x, mu, var, n, min_n=MIN_BASELINE_N):
    """Z against the learned baseline. Returns (z, warming_up)."""
    sigma = math.sqrt(max(var, 0.0))
    sigma = max(sigma, abs(mu) * 0.002, 1.0)   # 0.2% of level floor vs division by ~0
    return (x - mu) / sigma, n < min_n


def robust_window(hours, k=3.0):
    """Median +/- k*MAD window over observed UTC decimal hours (>= MIN_WINDOW_N)."""
    if len(hours) < MIN_WINDOW_N:
        return None
    med = statistics.median(hours)
    mad = max(statistics.median([abs(h - med) for h in hours]), 0.5)
    return {"median": round(med, 2), "lo": round(med - k * mad, 2),
            "hi": round(med + k * mad, 2), "n": len(hours)}


def cusum_step(s, x, mu, sigma, k=0.5, h=5.0):
    """One-sided upper CUSUM for sustained upward drift. Returns (s_new, alarm)."""
    s = max(0.0, s + (x - mu) / max(sigma, 1.0) - k)
    return s, s > h


def diff_assets(prev: dict, current: dict):
    return sorted(set(current) - set(prev)), sorted(set(prev) - set(current))


def weeks_contiguous(weeks) -> bool:
    return bool(weeks) and list(weeks) == list(range(1, len(weeks) + 1))


def learned_window(feed_state: dict, weekday: int):
    days = (feed_state.get("arrivals_by_weekday") or {}).get(str(weekday)) or []
    return robust_window(days)


def late_check(now_dt: datetime, last_cut: datetime, weekday: int, feed_state: dict, cfg: dict):
    hours_since = (now_dt - last_cut).total_seconds() / 3600.0
    win = learned_window(feed_state, weekday)
    if win is not None:
        now_h = now_dt.hour + now_dt.minute / 60.0
        midnight = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        window_start_today = midnight + timedelta(hours=max(0.0, win["lo"]))
        if now_h > win["hi"] + 2.0 and last_cut < window_start_today:
            return True, f"learned window {win['lo']}-{win['hi']} UTC closed, no cut since it opened (n={win['n']})"
        return False, ""
    prior_days = cfg["prior_days"]
    if len(prior_days) >= 7:
        if hours_since > cfg["late_hours"]:
            return True, f"max-gap exceeded ({hours_since:.0f}h since last cut)"
        return False, ""
    if weekday in prior_days:
        return False, ""          # the arrival window is still open
    first_prior = min(prior_days)
    days_since_first = (weekday - first_prior) % 7
    midnight = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    cycle_start = midnight - timedelta(days=days_since_first)
    if last_cut < cycle_start and hours_since > cfg["late_hours"]:
        return True, (f"no cut since before this cycle's {WEEKDAY_NAMES[first_prior]} window "
                      f"({hours_since:.0f}h since last cut)")
    return False, ""


# --------------------------------------------------------------------------- observation

def fetch_tag_index(state: dict, token, events: list):
    """One API call enumerates every release tag; avoids per-tag 404s."""
    try:
        data = http_json(API_LIST, token)
    except urllib.error.HTTPError as exc:
        hint = " (rate limited?)" if exc.code in (403, 429) else ""
        events.append({"ts": iso(now()), "type": "check", "feed": "_api", "status": "error",
                       "detail": f"releases list http {exc.code}{hint}"})
        return None
    except Exception as exc:  # noqa: BLE001 - a monitor must never crash
        events.append({"ts": iso(now()), "type": "check", "feed": "_api", "status": "error",
                       "detail": str(exc)[:200]})
        return None
    index, inventory = {}, {}
    for rel in data:
        tag = rel.get("tag_name")
        if not tag:
            continue
        index[tag] = rel
        assets = rel.get("assets") or []
        cut_times = [a.get("updated_at") for a in assets if a.get("updated_at")]
        inventory[tag] = {"published_at": rel.get("published_at"),
                          "cut_ts": max(cut_times) if cut_times else rel.get("updated_at"),
                          "assets": len(assets),
                          "bytes": sum(int(a.get("size") or 0) for a in assets)}
    state["tag_inventory"] = inventory
    events.append({"ts": iso(now()), "type": "check", "feed": "_api", "status": "ok",
                   "detail": f"release list: {len(index)} tags discovered"})
    return index


def observe_feed(name: str, cfg: dict, state: dict, tag_index, token, events: list, now_dt: datetime):
    tag = cfg["tag"]
    feed_state = state["feeds"].setdefault(tag, {"arrivals": [], "posted": {}, "assets": {}, "bytes": {"mu": None, "var": 0.0, "n": 0}})
    ev = {"ts": iso(now_dt), "type": "check", "feed": name, "tag": tag,
          "status": "unknown", "alarms": []}

    rel = (tag_index or {}).get(tag)
    if rel is None and tag_index is not None:
        try:
            rel = http_json(API_TAG.format(tag=tag), token)   # direct fallback
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                if cfg["optional"]:
                    ev.update(status="tag_absent_optional",
                              detail="release tag not found (optional feed - no alarm)")
                else:
                    ev.update(status="tag_missing", alarms=["TAG_MISSING"],
                              detail="release tag not found via list or direct endpoint")
            else:
                ev.update(status="error", alarms=["ERROR"], detail=f"http {exc.code}")
            events.append(ev)
            feed_state["last_checked"] = iso(now_dt)
            return
        except Exception as exc:  # noqa: BLE001
            ev.update(status="error", alarms=["ERROR"], detail=str(exc)[:200])
            events.append(ev)
            return
    if rel is None:
        ev.update(status="error", alarms=["ERROR"], detail="release list unavailable")
        events.append(ev)
        return

    # The effective cut time is the NEWEST asset updated_at: nflverse re-cuts the
    # same release tag weekly by re-uploading assets, so published_at is stale.
    assets = rel.get("assets") or []
    cut_times = [a.get("updated_at") for a in assets if a.get("updated_at")]
    cut_raw = max(cut_times) if cut_times else (rel.get("updated_at") or rel.get("published_at"))
    cut_dt = parse_iso(cut_raw) if cut_raw else now_dt
    watched = [a for a in assets if any(fnmatch.fnmatch(a.get("name", ""), g) for g in cfg["globs"])]
    bytes_watched = sum(int(a.get("size") or 0) for a in watched)
    hours_since = (now_dt - cut_dt).total_seconds() / 3600.0

    prev_key = feed_state.get("last_cut_key")
    is_new_cut = prev_key is None or prev_key != cut_raw
    sizes_now = {a["name"]: int(a.get("size") or 0) for a in watched}
    added, removed = diff_assets(feed_state.get("assets") or {}, sizes_now)

    detail_bits = [f"cut {hours_since:.1f}h ago"]
    if watched:
        detail_bits.append(f"{len(watched)} assets {bytes_watched / 1e6:.1f} MB")
    if added:
        detail_bits.append("added: " + ", ".join(added[:4]))
    if removed:
        detail_bits.append("removed: " + ", ".join(removed[:4]))
        ev["alarms"].append("ASSET_MISSING")
    if not watched and assets:
        ev["alarms"].append("ASSET_MISSING")
        detail_bits.append(f"no watched assets matched globs (tag has {len(assets)} assets)")

    base = feed_state.get("bytes") or {"mu": None, "var": 0.0, "n": 0}
    if prev_key is not None and base.get("n", 0) > 0 and bytes_watched > 0:
        z, warming = robust_z(bytes_watched, base["mu"], base["var"], base["n"])
        ev["z"] = round(z, 2)
        if not warming and abs(z) > Z_THRESHOLD:
            ev["alarms"].append("SIZE_ANOMALY")
            detail_bits.append(f"size z={z:+.1f}")
    if bytes_watched > 0 and (prev_key is None or is_new_cut):
        mu, var = ewma_update(base.get("mu"), base.get("var", 0.0), bytes_watched)
        feed_state["bytes"] = {"mu": round(mu, 1), "var": round(var, 1), "n": base.get("n", 0) + 1}

    if is_new_cut and prev_key is not None:
        hour = cut_dt.hour + cut_dt.minute / 60.0
        arrivals = feed_state.setdefault("arrivals", [])
        arrivals.append({"ts": cut_raw, "weekday": cut_dt.weekday(), "hour": round(hour, 2)})
        del arrivals[:-60]
        by_day = feed_state.setdefault("arrivals_by_weekday", {})
        by_day.setdefault(str(cut_dt.weekday()), []).append(round(hour, 2))
        for key in list(by_day):
            del by_day[key][:-40]
        if not cfg.get("chatty"):
            # chatty feeds (schedules re-cuts its timestamp files constantly) log
            # the change but never page the channel for it
            ev["alarms"].insert(0, "NEW_CUT")

    is_late, reason = late_check(now_dt, cut_dt, now_dt.weekday(), feed_state, cfg)
    if is_late:
        ev["alarms"].append("LATE")
        detail_bits.append(reason)

    status = "first_observation" if prev_key is None else ("new_cut" if is_new_cut else "unchanged")
    feed_state["last_cut_key"] = cut_raw
    feed_state["last_cut_ts"] = iso(cut_dt)
    feed_state["last_checked"] = iso(now_dt)
    feed_state["assets"] = sizes_now
    feed_state["obs"] = feed_state.get("obs", 0) + 1

    ev.update(status=status, detail=" | ".join(detail_bits), cut_key=cut_raw, cut_ts=iso(cut_dt),
              release_published_at=rel.get("published_at"),
              hours_since_cut=round(hours_since, 1), watched_assets=len(watched),
              watched_bytes=bytes_watched)
    events.append(ev)


def check_bundles(state: dict, events: list, remote_cut):
    bundles = state.setdefault("bundles", {})
    for path in sorted(DATA_DIR.glob("season_*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            events.append({"ts": iso(now()), "type": "alarm", "feed": path.name, "status": "alarm",
                           "detail": f"unreadable bundle: {exc}", "alarms": ["WEEKS_NOT_CONTIGUOUS"]})
            continue
        weeks = None
        for key in ("weeks", "week"):
            if isinstance(doc.get(key), list):
                weeks = doc[key]
                break
        contiguous = weeks_contiguous(weeks)
        bundles[path.name] = {
            "weeks": len(weeks) if weeks else 0,
            "last_week": max(weeks) if weeks else 0,
            "contiguous": contiguous,
            "mtime": iso(datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)),
        }
        if not contiguous:
            events.append({"ts": iso(now()), "type": "alarm", "feed": path.name, "status": "alarm",
                           "detail": f"weeks not contiguous: {weeks}", "alarms": ["WEEKS_NOT_CONTIGUOUS"]})
    live = bundles.get("season_2026.json")
    if live and remote_cut:
        stale_h = (remote_cut - parse_iso(live["mtime"])).total_seconds() / 3600.0
        live["stale_hours_vs_remote"] = round(stale_h, 1)
        if stale_h > STALE_HOURS:
            events.append({"ts": iso(now()), "type": "alarm", "feed": "season_2026.json",
                           "status": "alarm", "alarms": ["STALE_BUNDLES"],
                           "detail": (f"stats_player re-cut is {stale_h:.1f}h newer than our bundle - run "
                                      f"nfl_stats_export.py --seasons 2025-2026 --refresh then "
                                      f"augment_catalog.py (or gh workflow run nfl-data-refresh.yml)")})
    return bundles


# --------------------------------------------------------------------------- alerts/discord

def fresh_alarms(state: dict, events: list):
    fresh = []
    for ev in events:
        if ev.get("type") != "check" or ev.get("feed") == "_api":
            continue
        fs = state["feeds"].get(ev.get("tag"), {})
        for alarm in ev.get("alarms", []):
            if (fs.get("posted") or {}).get(alarm) != ev.get("cut_key"):
                fresh.append((ev, alarm))
    return fresh


def mark_posted(state: dict, events: list):
    for ev in events:
        if ev.get("type") != "check" or ev.get("feed") == "_api":
            continue
        fs = state["feeds"].get(ev.get("tag"), {})
        posted = fs.setdefault("posted", {})
        for alarm in ev.get("alarms", []):
            posted[alarm] = ev.get("cut_key") or "?"


def build_digest(state: dict, events: list, now_dt: datetime) -> str:
    checks = [e for e in events if e.get("type") == "check" and e.get("feed") != "_api"]
    changes = sum(1 for e in checks if e.get("status") == "new_cut")
    alarms = sorted({a for e in events if e.get("type") in ("check", "alarm")
                     for a in e.get("alarms", [])})
    lines = [f"**NFL Data Sentinel v{VERSION} digest** - {now_dt.strftime('%Y-%m-%d %H:%M')} UTC",
             f"checks: {len(checks)} feeds | new cuts: {changes} | alarms: {len(alarms)}"]
    parts = []
    for e in checks:
        if e.get("status") == "tag_absent_optional":
            continue
        bits = [str(e.get("feed", "?"))]
        if e.get("hours_since_cut") is not None:
            bits.append(f"{e['hours_since_cut']}h")
        if e.get("watched_assets"):
            bits.append(f"{e['watched_assets']}a/{e.get('watched_bytes', 0) / 1e6:.1f}MB")
        if e.get("z") is not None:
            bits.append(f"z{e['z']:+.1f}")
        if e.get("alarms"):
            bits.append("!".join(e["alarms"]))
        parts.append(" ".join(bits))
    if parts:
        lines.append("feeds: " + " | ".join(parts))
    absent = [e["feed"] for e in checks if e.get("status") == "tag_absent_optional"]
    if absent:
        lines.append("optional tags absent (info): " + ", ".join(absent))
    b = state.get("bundles", {}).get("season_2026.json")
    if b:
        lines.append(f"bundles: 2026 weeks 1-{b.get('last_week', '?')} contiguous={b.get('contiguous')} "
                     f"| stale_vs_remote={b.get('stale_hours_vs_remote', 'n/a')}h")
    for e in [x for x in events if x.get("type") == "alarm"][:3]:
        lines.append(f"alarm: {e.get('feed')} {','.join(e.get('alarms') or [])} - {e.get('detail', '')[:100]}")
    lines.append(f"tag inventory: {len(state.get('tag_inventory', {}))} release tags discovered")
    log_n = 0
    if LOG_FILE.exists():
        with LOG_FILE.open(encoding="utf-8") as fh:
            log_n = sum(1 for _ in fh)
    lines.append(f"log: scripts/monitor/state/sentinel_log.jsonl ({log_n} events)")
    return "\n".join(lines)[:1900]


def build_alert(fresh, now_dt: datetime) -> str:
    lines = [f"**NFL Data Sentinel v{VERSION} alert** - {now_dt.strftime('%Y-%m-%d %H:%M')} UTC"]
    for ev, alarm in fresh[:8]:
        lines.append(f"- {ev.get('feed', '?')}: {alarm} - {ev.get('detail', '')[:140]}")
    if len(fresh) > 8:
        lines.append(f"- ...and {len(fresh) - 8} more (see sentinel_log.jsonl)")
    return "\n".join(lines)[:1900]


def discord_post(content: str, dry: bool, events: list) -> bool:
    hook = (os.environ.get("DISCORD_WEBHOOK_NFL") or "").strip()
    if dry or not hook:
        events.append({"ts": iso(now()), "type": "discord", "status": "skipped",
                       "detail": "dry-run" if dry else "DISCORD_WEBHOOK_NFL not set"})
        return False
    payload = json.dumps({"content": content[:1900]}).encode("utf-8")
    req = urllib.request.Request(hook, data=payload, method="POST",
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "nfl-data-sentinel/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            code = resp.status
        events.append({"ts": iso(now()), "type": "discord", "status": "posted",
                       "detail": f"http {code}"})
        return 200 <= code < 300
    except Exception as exc:  # noqa: BLE001 - never crash on a post failure
        events.append({"ts": iso(now()), "type": "discord", "status": "failed",
                       "detail": str(exc)[:200]})
        return False


# --------------------------------------------------------------------------- modes

def print_summary(events: list, state: dict) -> None:
    print(f"NFL Data Sentinel v{VERSION} - {iso(now())}")
    print("-" * 86)
    for ev in events:
        if ev.get("type") != "check" or ev.get("feed") == "_api":
            continue
        alarms = "".join(" !" + a for a in ev.get("alarms", []))
        z = f" z={ev['z']:+.1f}" if ev.get("z") is not None else ""
        hs = f"{ev['hours_since_cut']}h" if ev.get("hours_since_cut") is not None else "-"
        print(f"  {str(ev.get('feed')):<14} {str(ev.get('status')):<20} {hs:>8} "
              f"{ev.get('watched_assets', 0):>4}a {ev.get('watched_bytes', 0) / 1e6:>7.1f}MB{z}{alarms}")
    b = state.get("bundles", {}).get("season_2026.json")
    if b:
        print(f"  2026 bundle: weeks 1..{b.get('last_week')} contiguous={b.get('contiguous')} "
              f"stale_vs_remote={b.get('stale_hours_vs_remote', 'n/a')}h")
    print(f"  tag inventory: {len(state.get('tag_inventory', {}))} tags | total checks: {state.get('checks')}")


def run_check(args) -> int:
    now_dt = now()
    state = load_state()
    events: list = []
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    tag_index = fetch_tag_index(state, token, events)
    for name, cfg in FEEDS.items():
        observe_feed(name, cfg, state, tag_index, token, events, now_dt)
    remote_cut = None
    for ev in events:
        if ev.get("type") == "check" and ev.get("feed") == "stats_player" and ev.get("cut_ts"):
            remote_cut = parse_iso(ev["cut_ts"])
            break
    check_bundles(state, events, remote_cut)
    fresh = fresh_alarms(state, events)
    state["checks"] = state.get("checks", 0) + 1
    state["last_check_at"] = iso(now_dt)
    save_state(state)
    print_summary(events, state)

    if args.digest:
        content = build_digest(state, events, now_dt)
        if discord_post(content, args.dry_run, events):
            mark_posted(state, events)
            save_state(state)
    elif fresh:
        content = build_alert(fresh, now_dt)
        if discord_post(content, args.dry_run, events):
            mark_posted(state, events)
            save_state(state)
    else:
        events.append({"ts": iso(now_dt), "type": "discord", "status": "skipped",
                       "detail": "quiet: no fresh cuts/alarms and --digest not set"})
    append_log(events)
    return 0


def replay_test() -> list:
    """Offline deterministic validation of every learned/alarm function."""
    t = []

    mu, var = None, 0.0
    for _ in range(50):
        mu, var = ewma_update(mu, var, 100.0)
    t.append(("ewma converges to a constant series (100.0 +/- 0.01)", abs(mu - 100.0) < 0.01, f"mu={mu:.3f}"))

    mu, var = 100.0, 4.0
    for _ in range(20):
        mu, var = ewma_update(mu, var, 200.0)
    t.append(("ewma tracks a step change (mu > 190 after 20 obs)", mu > 190.0, f"mu={mu:.1f}"))

    z, warming = robust_z(140.0, 100.0, 4.0, n=10)
    t.append(("robust_z flags a +40% size jump (z > 3)", (not warming) and z > 3.0, f"z={z:.1f}"))

    z, warming = robust_z(140.0, 100.0, 4.0, n=2)
    t.append(("robust_z suppresses alarms during warmup (n < 5)", warming, f"warming={warming}"))

    z, warming = robust_z(101.5, 100.0, 4.0, n=10)
    t.append(("robust_z ignores benign 1.5% jitter", (not warming) and abs(z) < 3.0, f"z={z:.2f}"))

    win = robust_window([9.0, 9.5, 10.0, 9.2, 140.0])
    t.append(("MAD arrival window ignores one outlier hour",
              win is not None and win["hi"] < 40.0, f"win={win}"))

    s = 0.0
    fired = False
    for _ in range(10):
        s, fired = cusum_step(s, 104.0, 100.0, 2.0)
        if fired:
            break
    t.append(("CUSUM fires on a sustained +2 sigma drift within 10 steps", fired, f"s={s:.1f}"))

    s = 0.0
    flat_alarm = False
    for _ in range(30):
        s, flat_alarm = cusum_step(s, 100.0, 100.0, 2.0)
    t.append(("CUSUM stays silent on flat data", not flat_alarm, f"s={s:.1f}"))

    cfg = FEEDS["stats_player"]
    last_week_wed = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)  # previous cycle's cut
    fri = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)            # Friday after this cycle's window
    is_late, why = late_check(fri, last_week_wed, fri.weekday(), {}, cfg)
    t.append(("LATE prior fires when the whole weekly cycle was missed", is_late, why[:70]))

    this_week_wed = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)  # this cycle's cut arrived
    sun = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
    is_late, why = late_check(sun, this_week_wed, sun.weekday(), {}, cfg)
    t.append(("LATE prior silent when this cycle's cut already arrived", not is_late, why[:70]))

    tue = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)           # window day, still open
    is_late, why = late_check(tue, this_week_wed, tue.weekday(), {}, cfg)
    t.append(("LATE prior silent inside the Tue/Wed arrival window", not is_late, why[:70]))

    feed_state = {"arrivals_by_weekday": {"2": [18.0, 18.5, 19.0, 18.2]}}
    wed_late = datetime(2026, 10, 14, 23, 0, tzinfo=timezone.utc)   # Wed 23:00, learned window closed
    last_before = datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc)
    is_late, why = late_check(wed_late, last_before, 2, feed_state, cfg)
    t.append(("learned MAD window fires when the window closes with no cut", is_late and "learned" in why, why[:70]))

    ok_weeks = weeks_contiguous([1, 2, 3, 4])
    bad_weeks = weeks_contiguous([1, 2, 4])
    t.append(("week contiguity accepts 1-4 and rejects 1,2,4", ok_weeks and not bad_weeks,
              f"ok={ok_weeks} bad={bad_weeks}"))

    added, removed = diff_assets({"a": 1, "b": 2}, {"b": 2, "c": 3})
    t.append(("asset diff detects added and removed assets", added == ["c"] and removed == ["a"],
              f"added={added} removed={removed}"))

    sample_events = [{"ts": iso(now()), "type": "check", "feed": "stats_player", "tag": "stats_player",
                      "status": "new_cut", "alarms": ["NEW_CUT"], "cut_key": "2026-10-07T16:27:19Z",
                      "hours_since_cut": 0.1, "watched_assets": 2, "watched_bytes": 11_000_000}]
    digest = build_digest({"bundles": {}, "tag_inventory": {"pbp": {}}}, sample_events, now())
    t.append(("digest builds under Discord's 2000-char budget", "digest" in digest and 0 < len(digest) <= 1900,
              f"len={len(digest)}"))
    return t


def print_replay() -> int:
    results = replay_test()
    passed = 0
    for name, ok, detail in results:
        print(("PASS " if ok else "FAIL ") + name + (f" ({detail})" if detail else ""))
        passed += 1 if ok else 0
    print(f"\nreplay validation: {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


def print_status() -> int:
    state = load_state()
    print(f"NFL Data Sentinel v{VERSION} - state at {state.get('updated_at', 'never')}")
    print(f"total checks: {state.get('checks', 0)} | tags in inventory: {len(state.get('tag_inventory', {}))}")
    print("-" * 86)
    for tag, fs in sorted(state.get("feeds", {}).items()):
        b = fs.get("bytes") or {}
        win = learned_window(fs, now().weekday())
        print(f"  {tag:<15} last_cut={fs.get('last_cut_ts', '-'):<20} obs={fs.get('obs', 0):<3} "
              f"bytes_mu={b.get('mu')} n={b.get('n')} window={win}")
    print("-" * 86)
    for name, b in sorted(state.get("bundles", {}).items()):
        if b.get("weeks"):
            print(f"  {name:<20} weeks=1..{b.get('last_week')} contiguous={b.get('contiguous')} "
                  f"stale_vs_remote={b.get('stale_hours_vs_remote', 'n/a')}h")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=f"NFL Data Sentinel v{VERSION}")
    parser.add_argument("--check", action="store_true", help="observe all feeds once")
    parser.add_argument("--digest", action="store_true", help="with --check: always post the digest")
    parser.add_argument("--dry-run", action="store_true", help="with --check: never post to Discord")
    parser.add_argument("--replay-test", action="store_true", help="offline validation suite")
    parser.add_argument("--status", action="store_true", help="print the latest state summary")
    args = parser.parse_args(argv)

    if args.replay_test:
        return print_replay()
    if args.status:
        return print_status()
    if args.check:
        return run_check(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
