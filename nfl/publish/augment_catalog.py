"""Augment catalog.json with stat source paths + build players_index.json from bundles."""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent.parent / "public" / "nfl-stats" / "data"

SCHEDULE_STATS = {"points_for", "points_against", "point_diff", "wins"}
PBP_STATS = {
    "plays", "epa_per_play", "success_rate", "pass_rate", "yards_per_play", "yards",
    "first_downs", "touchdowns", "turnovers", "sacks_allowed", "qb_hits_allowed",
    "penalties", "penalty_yards", "explosive", "explosive_rate", "third_down_rate",
    "fourth_down_rate",
}
PFR_RUSH = {
    "rushing_yards_after_contact", "rushing_yards_after_contact_avg",
    "rushing_yards_before_contact", "rushing_broken_tackles", "receiving_broken_tackles",
}
PFR_PASS = {
    "passing_drops", "passing_bad_throws", "times_pressured", "times_blitzed",
    "times_hit", "times_hurried",
}
PFR_DEF = {
    "def_targets", "def_completions_allowed", "def_yards_allowed", "def_receiving_td_allowed",
    "def_passer_rating_allowed", "def_missed_tackles", "def_pressures", "def_yards_after_catch",
}


def source_for(key: str, level: str) -> str:
    if level == "team":
        if key in SCHEDULE_STATS:
            return "schedules/games.parquet"
        if key in PBP_STATS:
            return "pbp/play_by_play_{season}.parquet"
        return "stats_team/stats_team_week_{season}.parquet"
    if key in PFR_RUSH:
        return "pfr_advstats/advstats_week_rush_{season}.parquet"
    if key in PFR_PASS:
        return "pfr_advstats/advstats_week_pass_{season}.parquet"
    if key in PFR_DEF:
        return "pfr_advstats/advstats_week_def_{season}.parquet"
    return "stats_player/stats_player_week_{season}.parquet"


QUALIFIER_PREFIXES = [
    ("passing_", "attempts", 100),
    ("rushing_", "carries", 50),
    ("receiving_", "targets", 25),
]
QUALIFIER_EXPLICIT = {
    "def_passer_rating_allowed": ("def_targets", 25),
    "def_yards_allowed": ("def_targets", 25),
    "def_yards_after_catch": ("def_targets", 25),
    "def_completions_allowed": ("def_targets", 25),
    "def_receiving_td_allowed": ("def_targets", 25),
    "rushing_yards_after_contact_avg": ("carries", 50),
    "rushing_yards_before_contact_avg": ("carries", 50),
}


def qualifier_for(key: str, fmt: str):
    if fmt != "f2":
        return None
    if key in QUALIFIER_EXPLICIT:
        return QUALIFIER_EXPLICIT[key]
    for prefix, vol, minimum in QUALIFIER_PREFIXES:
        if key.startswith(prefix):
            return (vol, minimum)
    return None


def main():
    catalog = json.loads((DATA / "catalog.json").read_text(encoding="utf-8"))
    player_sources = {}
    team_sources = {}
    qualifiers = {}
    for group in catalog.get("player_groups", []):
        for stat in group["stats"]:
            player_sources[stat["key"]] = source_for(stat["key"], "player")
            q = qualifier_for(stat["key"], stat.get("fmt", ""))
            if q:
                qualifiers[stat["key"]] = {"by": q[0], "min": q[1]}
    for group in catalog.get("team_groups", []):
        for stat in group["stats"]:
            team_sources[stat["key"]] = source_for(stat["key"], "team")
    catalog["stat_sources"] = {"player": player_sources, "team": team_sources}
    catalog["qualifiers"] = qualifiers
    (DATA / "catalog.json").write_text(json.dumps(catalog, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    print(f"stat_sources added: {len(player_sources)} player / {len(team_sources)} team stats | qualifiers: {len(qualifiers)}")

    index = {}
    for path in sorted(DATA.glob("season_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        season = int(data["season"])
        for pid, info in data.get("players", {}).items():
            entry = index.get(pid)
            if not entry:
                index[pid] = {
                    "n": info[0], "p": info[2] if len(info) > 2 else "", "g": info[4] if len(info) > 4 else "",
                    "h": info[3] if len(info) > 3 else "", "f": season, "l": season, "t": info[1] if len(info) > 1 else "",
                }
            else:
                entry["l"] = season
                if info[0]:
                    entry["n"] = info[0]
                if len(info) > 3 and info[3]:
                    entry["h"] = info[3]
                if len(info) > 4 and info[4]:
                    entry["g"] = info[4]
                if len(info) > 1 and info[1]:
                    entry["t"] = info[1]
    (DATA / "players_index.json").write_text(json.dumps(index, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    size_kb = (DATA / "players_index.json").stat().st_size / 1024
    print(f"players_index: {len(index)} players, {size_kb:.0f} KB")


if __name__ == "__main__":
    main()
