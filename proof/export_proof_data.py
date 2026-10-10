import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

import charts
import data as d
import stats_registry as reg

OUT = Path(__file__).resolve().parent / "nfl_stats_data.json"

TC = charts.team_color_map()
PALETTE = charts.FALLBACK


def entity_color(entities, color_map):
    return charts.entity_colors(entities, color_map)


def pack_bump(panel, top_n, color_map, fmt):
    if "entity" not in panel.columns and "team" in panel.columns:
        panel = panel.rename(columns={"team": "entity"})
    pivot = panel.pivot_table(index="entity", columns="week", values="value", aggfunc="last").sort_index(axis=1)
    totals = pivot.sum(axis=1)
    cum = pivot.fillna(0).cumsum(axis=1)
    weeks = [int(w) for w in cum.columns]
    cap = top_n * 2
    ranks = cum.rank(axis=0, ascending=False, method="min").clip(upper=cap)
    entities = list(totals[totals > 0].nlargest(top_n).index)
    colors = entity_color(entities, color_map)
    series = []
    for e in entities:
        weekly = panel[panel["entity"] == e].set_index("week")["value"]
        series.append({
            "name": e,
            "color": colors[e],
            "weeks": weeks,
            "rank": [None if (w not in ranks.columns or ranks.loc[e, w] != ranks.loc[e, w]) else int(ranks.loc[e, w]) for w in weeks],
            "cum": [round(float(cum.loc[e, w]), 2) if cum.loc[e, w] == cum.loc[e, w] else None for w in weeks],
            "per_game": [round(float(weekly[w]), 2) if w in weekly.index else None for w in weeks],
        })
    return {"kind": "bump", "fmt": fmt, "weeks": weeks, "cap": cap, "series": series}


def pack_dots(panel, top_n, color_map, fmt):
    if "entity" not in panel.columns and "team" in panel.columns:
        panel = panel.rename(columns={"team": "entity"})
    totals = panel.groupby("entity")["value"].sum()
    entities = list(totals.nlargest(top_n).index)
    colors = entity_color(entities, color_map)
    series = []
    for e in entities:
        grp = panel[panel["entity"] == e].sort_values("week")
        series.append({
            "name": e,
            "color": colors[e],
            "weeks": [int(w) for w in grp["week"]],
            "values": [round(float(v), 2) for v in grp["value"]],
            "season_total": round(float(totals[e]), 2),
        })
    return {"kind": "dots", "fmt": fmt, "series": series}


def main():
    payload = {"generated": "", "charts": {}, "tables": {}, "meta": {}}
    from datetime import datetime, timezone
    payload["generated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    py25 = reg.player_week_panel(2025, "passing_yards")
    payload["charts"]["passing_bump_2025"] = pack_bump(py25, 10, charts.player_color_map(py25), ",.0f")

    rush25 = reg.player_week_panel(2025, "rushing_yards")
    payload["charts"]["rushing_dots_2025"] = pack_dots(rush25, 10, charts.player_color_map(rush25), ",.1f")

    tk25 = reg.player_week_panel(2025, "def_tackles_total")
    payload["charts"]["tackles_bump_2025"] = pack_bump(tk25, 10, charts.player_color_map(tk25), ",.0f")

    rec25 = reg.player_week_panel(2025, "receiving_yards")
    payload["charts"]["receiving_bump_2025"] = pack_bump(rec25, 10, charts.player_color_map(rec25), ",.0f")

    yac25 = reg.player_week_panel(2025, "rushing_yards_after_contact")
    payload["charts"]["yac_bump_2025"] = pack_bump(yac25, 10, charts.player_color_map(yac25), ",.0f")

    pa25 = d.team_week_panel(2025, "points_against")
    payload["charts"]["points_allowed_bump_2025"] = pack_bump(pa25, 8, TC, ",.0f")

    plays25 = d.team_week_panel(2025, "plays")
    payload["charts"]["plays_dots_2025"] = pack_dots(plays25, 8, TC, ",.0f")

    py26 = reg.player_week_panel(2026, "passing_yards")
    payload["charts"]["passing_bump_2026"] = pack_bump(py26, 8, charts.player_color_map(py26), ",.0f")

    t_pass = reg.player_season_table(2025, "passing_yards").head(15)
    payload["tables"]["passing_leaders_2025"] = t_pass.to_dict("records")

    t_tk = reg.player_season_table(2025, "def_tackles_total").head(15)
    payload["tables"]["tackles_leaders_2025"] = t_tk.to_dict("records")

    sanity = []
    for stat, expected, expect_player in [("passing_yards", 4918, "Joe Burrow"), ("rushing_yards", 2005, "Saquon Barkley"), ("def_tackles_total", 155, "Zaire Franklin")]:
        row = reg.player_season_table(2024, stat).iloc[0]
        ok = row["player"] == expect_player and int(row["value"]) == expected
        sanity.append({"stat": stat, "expected": f"{expect_player} = {expected:,}", "got": f"{row['player']} = {int(row['value']):,}", "match": ok})
    payload["tables"]["sanity_2024"] = sanity

    avail = []
    for key in ["player_week", "player_season", "team_week", "team_season", "pbp", "schedules", "snap_counts", "pfr_rush", "pfr_pass", "pfr_def", "ngs_pass", "qbr_weekly"]:
        try:
            ss = d.endpoint_seasons(key)
            avail.append({"endpoint": key, "seasons": f"{ss[0]}-{ss[-1]} ({len(ss)})" if ss else "single file", "rows_sampled": ""})
        except Exception as e:
            avail.append({"endpoint": key, "seasons": "probe failed", "rows_sampled": str(e)[:40]})
    payload["tables"]["endpoints"] = avail

    payload["meta"] = {
        "seasons": f"{d.endpoint_seasons('player_week')[0]}-{d.endpoint_seasons('player_week')[-1]}",
        "sources": "nflverse-data GitHub releases (stats_player, stats_team, pbp, schedules, pfr_advstats, nextgen_stats, snap_counts)",
        "notes": "Tackles = solo + assisted. EPA/success rate require 2006+. 2026 updates live as weeks complete.",
    }

    OUT.write_text(json.dumps(payload, allow_nan=True))
    print("wrote", OUT, OUT.stat().st_size, "bytes")
    print("charts:", list(payload["charts"].keys()))


if __name__ == "__main__":
    main()
