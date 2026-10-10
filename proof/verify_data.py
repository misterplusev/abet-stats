"""Full verification suite for the NFL stats dashboard data bundles."""
import json
import math
from pathlib import Path

OUT = Path(r"D:\abet_dev\claude_dashboard_pills_20260925\public\nfl-stats\data")
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append({"name": name, "ok": bool(ok), "detail": str(detail)})
    print(("PASS" if ok else "FAIL"), name, f"({detail})" if detail else "")


files = sorted(OUT.glob("*.json"))
bad = []
strict_tokens = 0


def reject(token):
    global strict_tokens
    strict_tokens += 1
    raise ValueError(f"non-finite token {token}")


for f in files:
    try:
        json.loads(f.read_text(encoding="utf-8"), parse_constant=reject)
    except ValueError as exc:
        bad.append({"file": f.name, "error": str(exc)})

check("all JSON bundles are strict-parseable", not bad, f"{len(files)} files, {len(bad)} invalid")
check("no NaN/Infinity tokens in any bundle", strict_tokens == 0, f"{strict_tokens} tokens")

catalog = json.loads((OUT / "catalog.json").read_text(encoding="utf-8"))
check("catalog covers 1999-2026", catalog["seasons"] == list(range(1999, 2027)), f"{catalog['seasons'][0]}-{catalog['seasons'][-1]}, {len(catalog['seasons'])} seasons")
check("catalog stat counts", catalog["player_stat_count"] >= 177 and catalog["team_stat_count"] >= 151,
      f"{catalog['player_stat_count']} player / {catalog['team_stat_count']} team")


def load(season):
    return json.loads((OUT / f"season_{season}.json").read_text(encoding="utf-8"))


def series_total(data, key, needle, level="player_stats"):
    for s in data[level][key]:
        name = data["players"].get(s["id"], ["?"])[0] if level == "player_stats" else (catalog["team_meta"].get(s["id"], ["?"])[0])
        if needle.lower() in (name or "").lower():
            return sum(v for v in s["v"] if v is not None)
    return None


def leader(data, key, level="player_stats"):
    s = data[level][key][0]
    name = data["players"].get(s["id"], ["?"])[0] if level == "player_stats" else catalog["team_meta"].get(s["id"], [s["id"]])[0]
    return name, sum(v for v in s["v"] if v is not None)


d25, d24, d26, d99 = load(2025), load(2024), load(2026), load(1999)
d18 = load(2018)

name, total = leader(d25, "passing_yards")
check("2025 passing leader Stafford 4,707", total == 4707 and "Stafford" in name, f"{name} {total}")
name, total = leader(d25, "def_tackles_total")
check("2025 tackles leader Jordyn Brooks 180", total == 180 and "Brooks" in name, f"{name} {total}")
name, total = leader(d25, "receiving_yards")
check("2025 receiving leader JSN 1,793", total == 1793 and "Smith-Njigba" in name, f"{name} {total}")
name, total = leader(d24, "rushing_yards")
check("2024 rushing leader Barkley 2,005", total == 2005 and "Barkley" in name, f"{name} {total}")
name, total = leader(d24, "passing_yards")
check("2024 passing leader Burrow 4,918", total == 4918 and "Burrow" in name, f"{name} {total}")
name, total = leader(d25, "rushing_yards_after_contact")
check("2025 YAC leader Jonathan Taylor 759 (PFR)", total == 759 and "Taylor" in name, f"{name} {total}")
name, total = leader(d99, "passing_yards")
check("1999 passing leader Beuerlein 4,436", total == 4436 and "Beuerlein" in name, f"{name} {total}")
name, total = leader(d25, "points_for", "team_stats")
check("2025 team points-for leader Rams 518", total == 518 and "Rams" in name, f"{name} {total}")
pa = d25["team_stats"]["points_against"]
worst = max(pa, key=lambda s: sum(v for v in s["v"] if v is not None))
check("2025 most points allowed DAL 511", worst["id"] == "DAL" and sum(v for v in worst["v"] if v is not None) == 511,
      f"{worst['id']} {sum(v for v in worst['v'] if v is not None)}")
check("2026 live season weeks are contiguous from 1 (auto-grows with the data)", d26["weeks"] == list(range(1, len(d26["weeks"]) + 1)) and len(d26["weeks"]) >= 3, f"weeks {d26['weeks'][0]}-{d26['weeks'][-1]} ({len(d26['weeks'])} total)")
top26 = d26["player_stats"]["passing_yards"][0]
check("2026 passing leader is a QB", d26["players"][top26["id"]][2] == "QB" and sum(v for v in top26["v"] if v is not None) > 700,
      f"{d26['players'][top26['id']][0]} {sum(v for v in top26['v'] if v is not None)}")
check("2018+ has PFR advanced stats (177 player stats)", "rushing_yards_after_contact" in d18["player_stats"] and len(d18["player_stats"]) >= 170,
      f"{len(d18['player_stats'])} stats")
check("1999 has no PFR stats (pre-tracking era)", "rushing_yards_after_contact" not in d99["player_stats"], f"{len(d99['player_stats'])} stats")

ranks_ok = True
for s in d25["player_stats"]["passing_yards"]:
    if s["r"][0] is None or s["r"][-1] is None:
        ranks_ok = False
check("rank arrays present for every week (2025 passing)", ranks_ok)
wk1 = [s for s in d25["player_stats"]["passing_yards"] if s["v"][0] is not None]
wk1_sorted = sorted(wk1, key=lambda s: -s["v"][0])
monotonic = all(wk1_sorted[i]["r"][0] <= wk1_sorted[i + 1]["r"][0] for i in range(len(wk1_sorted) - 1))
check("week-1 ranks are league-ordered (spot check)", monotonic, f"top: {wk1_sorted[0]['r'][0]} -> {wk1_sorted[-1]['r'][0]}")

nonfinite_values = 0
for data in (d25, d26, d99):
    for pool in ("player_stats", "team_stats"):
        for key, series in data[pool].items():
            for s in series:
                for v in s["v"]:
                    if v is not None and (isinstance(v, float) and not math.isfinite(v)):
                        nonfinite_values += 1
check("no non-finite series values (2025/2026/1999)", nonfinite_values == 0, f"{nonfinite_values} found")

leaders = json.loads((OUT / "career_leaders.json").read_text(encoding="utf-8"))
idx = json.loads((OUT / "players_index.json").read_text(encoding="utf-8"))
check("career leaders bundle covers 130+ player stats", len(leaders["stats"]) >= 130, f"{len(leaders['stats'])} stats")
top_recv = leaders["stats"]["receiving_yards"]["top"][0]
check("career leaders: receiving yards #1 Larry Fitzgerald 17,493",
      idx.get(top_recv["id"], {}).get("n") == "Larry Fitzgerald" and top_recv["total"] == 17493,
      f"{idx.get(top_recv['id'], {}).get('n')} {top_recv['total']}")
top_pass = leaders["stats"]["passing_yards"]["top"][0]
check("career leaders: passing yards #1 Tom Brady 89,216",
      idx.get(top_pass["id"], {}).get("n") == "Tom Brady" and top_pass["total"] == 89216,
      f"{idx.get(top_pass['id'], {}).get('n')} {top_pass['total']}")

inv = json.loads((OUT / "widget_inventory.json").read_text(encoding="utf-8"))
check("widget inventory: monolith line coverage >= 99%", inv["coverage_pct"] >= 99, f"{inv['coverage_pct']}% of {inv['source_lines']} lines")
check("widget inventory: every declaration silo-mapped", not inv["unmapped"] and all(n["silo"] != "unmapped" for n in inv["nodes"]),
      f"{len(inv['nodes'])} nodes, {len(inv['unmapped'])} unmapped")

passed = sum(1 for r in RESULTS if r["ok"])
summary = {"passed": passed, "total": len(RESULTS), "all": passed == len(RESULTS), "results": RESULTS}
Path(r"D:\nfl-progression\proof\dashboard-module\verify_data.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
print(f"\n{passed}/{len(RESULTS)} data checks passed")
