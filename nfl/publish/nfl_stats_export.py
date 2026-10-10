"""Standalone nflverse -> NFL stats progression bundle exporter (cloud-safe).

Self-contained (no streamlit): downloads nflverse-data release assets, computes
weekly cumulative leader series with true league ranks, and writes one compact
JSON per season plus catalog.json. Used by the dashboard's scheduled GitHub
Action and by the local refresh script.

Usage:
  python nfl_stats_export.py --seasons 2026 --out public/nfl-stats/data
  python nfl_stats_export.py --seasons 1999-2026 --out public/nfl-stats/data
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

GITHUB_RELEASE = "https://github.com/nflverse/nflverse-data/releases/download/"

E = {
    "player_week": GITHUB_RELEASE + "stats_player/stats_player_week_{season}.parquet",
    "team_week": GITHUB_RELEASE + "stats_team/stats_team_week_{season}.parquet",
    "pbp": GITHUB_RELEASE + "pbp/play_by_play_{season}.parquet",
    "schedules": GITHUB_RELEASE + "schedules/games.parquet",
    "teams": GITHUB_RELEASE + "teams/teams_colors_logos.parquet",
    "pfr_rush": GITHUB_RELEASE + "pfr_advstats/advstats_week_rush_{season}.parquet",
    "pfr_pass": GITHUB_RELEASE + "pfr_advstats/advstats_week_pass_{season}.parquet",
    "pfr_rec": GITHUB_RELEASE + "pfr_advstats/advstats_week_rec_{season}.parquet",
    "pfr_def": GITHUB_RELEASE + "pfr_advstats/advstats_week_def_{season}.parquet",
    "players": GITHUB_RELEASE + "players/players.parquet",
}

PBP_TEAM_COLS = [
    "game_id", "season", "season_type", "week", "posteam", "play", "pass", "rush",
    "epa", "success", "yards_gained", "first_down", "touchdown", "penalty",
    "penalty_yards", "fumble_lost", "interception", "qb_hit", "sack",
    "third_down_converted", "third_down_failed", "fourth_down_converted", "fourth_down_failed",
]

SCHEDULE_TEAM_STATS = {
    "points_for": "Points scored",
    "points_against": "Points allowed",
    "point_diff": "Point differential",
    "wins": "Wins (1 per win, 0.5 per tie)",
}

PBP_TEAM_STATS = {
    "plays": "Plays run",
    "epa_per_play": "EPA per play (2006+)",
    "success_rate": "Success rate (2006+)",
    "pass_rate": "Pass rate",
    "yards_per_play": "Yards per play",
    "yards": "Total yards",
    "first_downs": "First downs",
    "touchdowns": "Touchdowns",
    "turnovers": "Turnovers",
    "sacks_allowed": "Sacks allowed",
    "qb_hits_allowed": "QB hits allowed",
    "penalties": "Penalties",
    "penalty_yards": "Penalty yards",
    "explosive": "Explosive plays (20+ yds)",
    "explosive_rate": "Explosive play rate",
    "third_down_rate": "Third down conversion rate",
    "fourth_down_rate": "Fourth down conversion rate",
}

PLAYER_GROUPS = {
    "Passing": {
        "passing_yards": "Passing yards", "passing_tds": "Passing TDs", "completions": "Completions",
        "attempts": "Pass attempts", "passing_interceptions": "Interceptions", "passing_air_yards": "Air yards",
        "passing_yards_after_catch": "Yards after catch (by receivers)", "passing_first_downs": "Passing first downs",
        "passing_epa": "Passing EPA", "passing_cpoe": "CPOE", "sacks_suffered": "Sacks suffered", "pacr": "PACR",
    },
    "Rushing": {
        "rushing_yards": "Rushing yards", "rushing_tds": "Rushing TDs", "carries": "Carries",
        "rushing_first_downs": "Rushing first downs", "rushing_epa": "Rushing EPA", "rushing_fumbles": "Rushing fumbles",
    },
    "Receiving": {
        "receiving_yards": "Receiving yards", "receiving_tds": "Receiving TDs", "receptions": "Receptions",
        "targets": "Targets", "receiving_yards_after_catch": "Yards after catch", "receiving_air_yards": "Air yards",
        "receiving_first_downs": "Receiving first downs", "receiving_epa": "Receiving EPA", "racr": "RACR",
        "target_share": "Target share",
    },
    "Defense": {
        "def_tackles_total": "Total tackles", "def_tackles_solo": "Solo tackles",
        "def_tackles_with_assist": "Assisted tackles", "def_tackles_for_loss": "Tackles for loss",
        "def_tackles_for_loss_yards": "TFL yards", "def_sacks": "Sacks", "def_sack_yards": "Sack yards",
        "def_qb_hits": "QB hits", "def_interceptions": "Interceptions", "def_interception_yards": "INT return yards",
        "def_pass_defended": "Passes defended", "def_fumbles_forced": "Forced fumbles", "def_tds": "Defensive TDs",
        "def_safeties": "Safeties",
    },
    "Special Teams": {
        "special_teams_tds": "ST TDs", "fg_made": "FGs made", "fg_att": "FG attempts", "fg_missed": "FGs missed",
        "fg_blocked": "FGs blocked", "fg_long": "Longest FG", "fg_made_distance": "FG distance (made)",
        "pat_made": "PATs made", "punt_returns": "Punt returns", "punt_return_yards": "Punt return yards",
        "kickoff_returns": "Kickoff returns", "kickoff_return_yards": "Kickoff return yards", "pt_att": "Punts",
        "pt_yards": "Punt yards", "pt_net_yards": "Punt net yards", "pt_inside_20": "Punts inside 20",
        "misc_yards": "Misc yards", "fumble_recovery_own": "Fumble recoveries (own)",
        "fumble_recovery_opp": "Fumble recoveries (opp)", "fumble_recovery_yards_opp": "FR return yards",
        "fumble_recovery_tds": "FR TDs",
    },
    "Ball Security & Penalties": {
        "fumbles_total": "Fumbles", "fumbles_lost_total": "Fumbles lost", "penalties": "Penalties",
        "penalty_yards": "Penalty yards",
    },
    "Fantasy": {"fantasy_points": "Fantasy points", "fantasy_points_ppr": "Fantasy points (PPR)"},
}

PFR_GROUPS = {
    "Rushing (PFR)": {
        "rushing_yards_after_contact": "Yards after contact",
        "rushing_yards_after_contact_avg": "Yards after contact per att",
        "rushing_yards_before_contact": "Yards before contact",
        "rushing_broken_tackles": "Broken tackles",
        "receiving_broken_tackles": "Broken tackles (as receiver)",
    },
    "Passing (PFR)": {
        "passing_drops": "Drops by receivers", "passing_bad_throws": "Bad throws", "times_pressured": "Times pressured",
        "times_blitzed": "Times blitzed", "times_hit": "Times hit", "times_hurried": "Times hurried",
    },
    "Coverage (PFR)": {
        "def_targets": "Targets in coverage", "def_completions_allowed": "Completions allowed",
        "def_yards_allowed": "Yards allowed in coverage", "def_receiving_td_allowed": "TDs allowed",
        "def_passer_rating_allowed": "Passer rating allowed", "def_missed_tackles": "Missed tackles",
        "def_pressures": "Pressures", "def_yards_after_catch": "YAC allowed",
    },
}

TEAM_GROUPS = {
    "Results & Points": dict(SCHEDULE_TEAM_STATS),
    "Offense": {
        "total_yards": "Total yards (pass + rush)", "passing_yards": "Passing yards", "rushing_yards": "Rushing yards",
        "total_tds": "Total TDs (pass + rush)", "passing_tds": "Passing TDs", "rushing_tds": "Rushing TDs",
        "off_plays": "Offensive plays (att + carries)", "completions": "Completions", "attempts": "Pass attempts",
        "carries": "Rush attempts", "passing_first_downs": "Passing first downs",
        "rushing_first_downs": "Rushing first downs", "passing_air_yards": "Passing air yards",
        "passing_epa": "Passing EPA", "rushing_epa": "Rushing EPA", "sacks_suffered": "Sacks suffered",
        "receiving_yards_after_catch": "Yards after catch",
    },
    "Defense": {
        "def_tackles_total": "Total tackles", "def_tackles_for_loss": "Tackles for loss", "def_sacks": "Sacks",
        "def_qb_hits": "QB hits", "def_interceptions": "Interceptions", "def_pass_defended": "Passes defended",
        "def_fumbles_forced": "Forced fumbles", "def_tds": "Defensive TDs", "def_safeties": "Safeties",
    },
    "Efficiency (play-by-play, 2006+)": dict(PBP_TEAM_STATS),
    "Special Teams": {
        "fg_made": "FGs made", "fg_att": "FG attempts", "fg_missed": "FGs missed", "fg_blocked": "FGs blocked",
        "pat_made": "PATs made", "punt_returns": "Punt returns", "punt_return_yards": "Punt return yards",
        "kickoff_returns": "Kickoff returns", "kickoff_return_yards": "Kickoff return yards", "pt_att": "Punts",
        "pt_net_yards": "Punt net yards", "pt_inside_20": "Punts inside 20",
    },
    "Ball Security & Penalties": {
        "fumbles_total": "Fumbles", "fumbles_lost_total": "Fumbles lost", "penalties": "Penalties",
        "penalty_yards": "Penalty yards",
    },
}

META_EXCLUDE = {
    "season", "week", "game_id", "old_game_id", "pfr_game_id", "player_id",
    "pfr_player_id", "jersey_number", "games", "season_type", "game_type",
    "team", "opponent", "opponent_team", "recent_team", "pfr_player_name",
    "player_name", "player_display_name", "position", "position_group",
    "headshot_url", "game_date",
}

RATE_SUFFIXES = ("_avg", "_pct", "_rate", "_share")
RATE_STATS = {
    "passing_cpoe", "pacr", "racr", "target_share", "air_yards_share", "wopr",
    "def_passer_rating_allowed", "epa_per_play", "success_rate", "pass_rate",
    "yards_per_play", "explosive_rate", "third_down_rate", "fourth_down_rate",
}

PFR_KINDS = ("rush", "pass", "rec", "def")
PBP_SEASONS = (2024, 2025, 2026)

POOL_OVERALL = 30
POOL_PER_GROUP = 6
POOL_CAP = 40

POSITION_TO_GROUP = {
    "QB": "QB",
    "RB": "RB", "FB": "RB", "HB": "RB",
    "WR": "WR",
    "TE": "TE",
    "OT": "OL", "OG": "OL", "C": "OL", "G": "OL", "T": "OL", "OL": "OL",
    "DE": "DL", "DT": "DL", "NT": "DL", "DL": "DL", "EDGE": "DL",
    "LB": "LB", "ILB": "LB", "MLB": "LB", "OLB": "LB",
    "CB": "DB", "DB": "DB", "S": "DB", "SS": "DB", "FS": "DB", "SAF": "DB",
    "K": "SPEC", "P": "SPEC", "LS": "SPEC",
}


def group_for(position: str) -> str:
    return POSITION_TO_GROUP.get(str(position or "").strip().upper(), "")


def is_rate(stat: str) -> bool:
    return stat.endswith(RATE_SUFFIXES) or stat in RATE_STATS


def agg_kind(stat: str) -> str:
    return "mean" if is_rate(stat) else "sum"


def fmt_kind(stat: str) -> str:
    return "f2" if is_rate(stat) else "i0"


def prettify(key: str) -> str:
    words = key.replace("_", " ").strip()
    return words[:1].upper() + words[1:]


def fetch(url: str, cache_dir: Path, refresh: bool = False) -> pd.DataFrame:
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe = url.split("://", 1)[1].replace("/", "__")
    path = cache_dir / safe
    if refresh and path.exists():
        path.unlink()
    if not path.exists():
        tmp = path.with_name(path.name + ".part")
        with requests.get(url, timeout=300, stream=True) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        tmp.replace(path)
    return pd.read_parquet(path)


def add_derived_stats(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if {"def_tackles_solo", "def_tackle_assists"} <= set(df.columns):
        df["def_tackles_total"] = df["def_tackles_solo"].fillna(0) + df["def_tackle_assists"].fillna(0)
    if {"passing_yards", "rushing_yards"} <= set(df.columns):
        df["total_yards"] = df["passing_yards"].fillna(0) + df["rushing_yards"].fillna(0)
    if {"attempts", "carries"} <= set(df.columns):
        df["off_plays"] = df["attempts"].fillna(0) + df["carries"].fillna(0)
    if {"passing_tds", "rushing_tds", "receiving_tds"} <= set(df.columns):
        df["total_tds"] = df["passing_tds"].fillna(0) + df["rushing_tds"].fillna(0) + df["receiving_tds"].fillna(0)
    return df


def round_val(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    f = float(v)
    if not math.isfinite(f):
        return None
    if f.is_integer():
        return int(f) if abs(f) < 1e15 else f
    return round(f, 2)


def numeric_stats(df: pd.DataFrame, exclude_ids: set[str]) -> list[str]:
    out = []
    for c in df.columns:
        if c in exclude_ids or c in META_EXCLUDE:
            continue
        if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c]):
            out.append(c)
    return out


def pack_panel(df, id_col, name_col, team_col, stat, weeks, top_n, group_of=None):
    kind = agg_kind(stat)
    cols = [id_col]
    for c in (name_col, team_col):
        if c and c not in cols:
            cols.append(c)
    cols += ["week", stat]
    sub = df[df[stat].notna()][cols]
    if sub.empty:
        return None
    agg_map = {"_name": (name_col, "first"), "_v": (stat, "sum" if kind == "sum" else "mean")}
    grouped = sub.groupby([id_col, "week"], as_index=False).agg(**agg_map)
    pivot = grouped.pivot_table(index=id_col, columns="week", values="_v", aggfunc="last").reindex(columns=weeks)
    pivot = pivot.replace([float("inf"), float("-inf")], float("nan"))
    if kind == "sum":
        final = pivot.sum(axis=1, skipna=True)
        run = pivot.fillna(0).cumsum(axis=1)
    else:
        final = pivot.mean(axis=1, skipna=True)
        run = pivot.T.expanding().mean().T
    final = final[(final.notna()) & (final.abs() > 1e-9)]
    if final.empty:
        return None
    ranks = run.loc[final.index].rank(axis=0, ascending=False, method="min")
    weekly_ranks = pivot.rank(axis=0, ascending=False, method="min")
    ordered = list(final.sort_values(ascending=False).index)
    if group_of:
        chosen = {str(eid) for eid in ordered[:POOL_OVERALL]}
        per_group: dict[str, int] = {}
        for eid in ordered:
            g = group_of.get(str(eid), "")
            if not g or per_group.get(g, 0) >= POOL_PER_GROUP:
                continue
            chosen.add(str(eid))
            per_group[g] = per_group.get(g, 0) + 1
        ordered = [eid for eid in ordered if str(eid) in chosen]
    ordered = ordered[: max(top_n, POOL_CAP)]
    series = []
    for eid in ordered:
        row = pivot.loc[eid]
        vals = [round_val(row.get(w)) for w in weeks]
        if all(v is None for v in vals):
            continue
        rrow = ranks.loc[eid]
        rank_vals = [None if pd.isna(rrow.get(w)) else int(rrow.get(w)) for w in weeks]
        wrow = weekly_ranks.loc[eid]
        week_rank_vals = [None if pd.isna(wrow.get(w)) else int(wrow.get(w)) for w in weeks]
        series.append({"id": str(eid), "v": vals, "r": rank_vals, "wr": week_rank_vals})
    return series or None


def load_pbp_team_metrics(season: int, cache_dir: Path, refresh: bool) -> pd.DataFrame:
    pbp = fetch(E["pbp"].format(season=season), cache_dir, refresh)[PBP_TEAM_COLS]
    pbp = pbp[pbp["posteam"].notna() & (pbp["season_type"] == "REG")].copy()
    pbp["explosive"] = (pbp["yards_gained"] >= 20).astype("int64")
    agg = pbp.groupby(["posteam", "week"], as_index=False).agg(
        plays=("play", "sum"), epa_sum=("epa", "sum"), success_sum=("success", "sum"),
        pass_plays=("pass", "sum"), yards=("yards_gained", "sum"), first_downs=("first_down", "sum"),
        touchdowns=("touchdown", "sum"), fumbles_lost=("fumble_lost", "sum"),
        interceptions=("interception", "sum"), sacks_allowed=("sack", "sum"),
        qb_hits_allowed=("qb_hit", "sum"), penalties=("penalty", "sum"),
        penalty_yards=("penalty_yards", "sum"), explosive=("explosive", "sum"),
        third_conv=("third_down_converted", "sum"), third_att=("third_down_failed", "sum"),
        fourth_conv=("fourth_down_converted", "sum"), fourth_att=("fourth_down_failed", "sum"),
    )
    agg["turnovers"] = agg["fumbles_lost"] + agg["interceptions"]
    agg["epa_per_play"] = agg["epa_sum"] / agg["plays"]
    agg["success_rate"] = agg["success_sum"] / agg["plays"]
    agg["pass_rate"] = agg["pass_plays"] / agg["plays"]
    agg["yards_per_play"] = agg["yards"] / agg["plays"]
    agg["explosive_rate"] = agg["explosive"] / agg["plays"]
    agg["third_down_rate"] = agg["third_conv"] / (agg["third_conv"] + agg["third_att"])
    agg["fourth_down_rate"] = agg["fourth_conv"] / (agg["fourth_conv"] + agg["fourth_att"])
    if season < 2006:
        agg["epa_per_play"] = float("nan")
        agg["success_rate"] = float("nan")
    agg = agg.rename(columns={"posteam": "team"})
    keep = ["team", "week", "plays", "epa_per_play", "success_rate", "pass_rate", "yards_per_play",
            "yards", "first_downs", "touchdowns", "turnovers", "sacks_allowed", "qb_hits_allowed",
            "penalties", "penalty_yards", "explosive", "explosive_rate", "third_down_rate", "fourth_down_rate"]
    return agg[keep]


def schedule_team_panel(sched: pd.DataFrame, season: int, stat: str) -> pd.DataFrame:
    s = sched[(sched["season"] == season) & (sched["game_type"] == "REG")]
    home = s[["week", "home_team", "home_score", "away_score"]].rename(
        columns={"home_team": "team", "home_score": "pts_for", "away_score": "pts_against"})
    away = s[["week", "away_team", "away_score", "home_score"]].rename(
        columns={"away_team": "team", "away_score": "pts_for", "home_score": "pts_against"})
    long = pd.concat([home, away], ignore_index=True)
    long = long[long["pts_for"].notna()]
    if stat == "points_for":
        long["value"] = long["pts_for"]
    elif stat == "points_against":
        long["value"] = long["pts_against"]
    elif stat == "point_diff":
        long["value"] = long["pts_for"] - long["pts_against"]
    else:
        long["value"] = (long["pts_for"] > long["pts_against"]).astype(float) + (long["pts_for"] == long["pts_against"]) * 0.5
    return long[["team", "week", "value"]].sort_values(["team", "week"]).reset_index(drop=True)


def load_pfr_crosswalk(cache_dir: Path) -> dict:
    try:
        pl = fetch(E["players"], cache_dir)
    except Exception:
        return {}
    if "pfr_id" not in pl.columns:
        return {}
    sub = pl.dropna(subset=["pfr_id"]).drop_duplicates("pfr_id")
    out = {}
    for pid, pos, hs in zip(sub["pfr_id"], sub["position"].fillna(""), sub["headshot"].fillna("")):
        pos = str(pos)
        out[str(pid)] = {"position": pos, "group": group_for(pos), "headshot": str(hs)}
    return out


def export_season(season: int, out_dir: Path, cache_dir: Path, top_n: int, refresh: bool) -> dict:
    t0 = time.time()
    stats: dict[str, list[dict]] = {}
    team_stats: dict[str, list[dict]] = {}
    players: dict[str, list] = {}
    teams_seen: set[str] = set()

    def add_player_stat(df, id_col, name_col, team_col, stat, weeks, group_of):
        series = pack_panel(df, id_col, name_col, team_col, stat, weeks, top_n, group_of)
        if series:
            stats[stat] = series

    wk = add_derived_stats(fetch(E["player_week"].format(season=season), cache_dir, refresh))
    if "season_type" in wk.columns:
        wk = wk[wk["season_type"] == "REG"].copy()
    weeks = sorted(int(w) for w in wk["week"].dropna().unique())
    wk["team"] = wk["team"].fillna("").astype(str)
    wk["player_display_name"] = wk["player_display_name"].fillna("")
    if "position_group" not in wk.columns:
        wk["position_group"] = ""
    wk["position_group"] = wk["position_group"].fillna("")
    wk["_pos_group"] = [
        g if g else group_for(p)
        for g, p in zip(wk["position_group"], wk["position"].fillna(""))
    ]
    player_groups = dict(zip(wk["player_id"].astype(str), wk["_pos_group"]))
    for pid, g in wk.groupby("player_id"):
        last = g.iloc[-1]
        players[str(pid)] = [
            str(last.get("player_display_name") or ""),
            str(g["team"].iloc[-1] or ""),
            str(last.get("position") or ""),
            str(last.get("headshot_url") or ""),
            str(last.get("_pos_group") or ""),
        ]
    good = wk[wk["player_id"].notna()]
    for stat in numeric_stats(wk, {"player_id"}):
        add_player_stat(good, "player_id", "player_display_name", "team", stat, weeks, player_groups)

    crosswalk = load_pfr_crosswalk(cache_dir)
    for kind in PFR_KINDS:
        try:
            pfr = fetch(E[f"pfr_{kind}"].format(season=season), cache_dir, refresh)
        except Exception:
            continue
        if pfr is None or pfr.empty:
            continue
        if "game_type" in pfr.columns:
            pfr = pfr[pfr["game_type"] == "REG"]
        pfr = pfr[pfr["pfr_player_id"].notna()].copy()
        pfr["team"] = pfr["team"].fillna("").astype(str)
        pfr["pfr_player_name"] = pfr["pfr_player_name"].fillna("")
        pfr["pfr_player_id"] = "pfr:" + pfr["pfr_player_id"].astype(str)
        pfr_groups: dict[str, str] = {}
        for pid, g in pfr.groupby("pfr_player_id"):
            info = crosswalk.get(pid.split(":", 1)[1], {})
            players.setdefault(pid, [
                str(g["pfr_player_name"].iloc[-1] or ""),
                str(g["team"].iloc[-1] or ""),
                info.get("position", ""),
                info.get("headshot", ""),
                info.get("group", ""),
            ])
            pfr_groups[pid] = info.get("group", "")
        for stat in numeric_stats(pfr, {"pfr_player_id", "pfr_player_name"}):
            add_player_stat(pfr, "pfr_player_id", "pfr_player_name", "team", stat, weeks, pfr_groups)

    try:
        tw = add_derived_stats(fetch(E["team_week"].format(season=season), cache_dir, refresh))
        if "season_type" in tw.columns:
            tw = tw[tw["season_type"] == "REG"].copy()
        tw["team"] = tw["team"].fillna("").astype(str)
        tw = tw[tw["team"].str.len() > 0]
        teams_seen.update(tw["team"].unique())
        for stat in numeric_stats(tw, set()):
            series = pack_panel(tw, "team", "team", None, stat, weeks, top_n)
            if series:
                team_stats[stat] = series
    except Exception as exc:
        print(f"  team week skipped: {exc}")

    sched = fetch(E["schedules"], cache_dir, refresh)
    for stat in SCHEDULE_TEAM_STATS:
        panel = schedule_team_panel(sched, season, stat)
        if panel.empty:
            continue
        teams_seen.update(panel["team"].unique())
        series = pack_panel(panel, "team", "team", None, "value", weeks, top_n)
        if series:
            team_stats[stat] = series

    if season in PBP_SEASONS:
        try:
            m = load_pbp_team_metrics(season, cache_dir, refresh)
            teams_seen.update(m["team"].unique())
            for stat in PBP_TEAM_STATS:
                if stat not in m.columns:
                    continue
                series = pack_panel(m, "team", "team", None, stat, weeks, top_n)
                if series:
                    team_stats[stat] = series
        except Exception as exc:
            print(f"  pbp metrics skipped: {exc}")

    payload = {
        "season": season,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "nflverse-data releases (stats_player_week, pfr_advstats week, stats_team_week, schedules, play_by_play)",
        "top_n": top_n,
        "weeks": weeks,
        "players": {k: v for k, v in players.items() if v},
        "player_stats": stats,
        "team_stats": team_stats,
        "team_ids": sorted(teams_seen),
    }
    out = out_dir / f"season_{season}.json"
    out.write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    print(f"season {season}: {len(stats)} player stats, {len(team_stats)} team stats, "
          f"{len(players)} players, {len(weeks)} weeks, {out.stat().st_size/1024:.0f} KB, {time.time()-t0:.1f}s")
    return payload


def source_for(key: str, level: str) -> str:
    if level == "team":
        if key in SCHEDULE_TEAM_STATS:
            return "schedules/games.parquet"
        if key in PBP_TEAM_STATS:
            return "pbp/play_by_play_{season}.parquet"
        return "stats_team/stats_team_week_{season}.parquet"
    if key in PFR_GROUPS.get("Rushing (PFR)", {}):
        return "pfr_advstats/advstats_week_rush_{season}.parquet"
    if key in PFR_GROUPS.get("Passing (PFR)", {}):
        return "pfr_advstats/advstats_week_pass_{season}.parquet"
    if key in PFR_GROUPS.get("Coverage (PFR)", {}):
        return "pfr_advstats/advstats_week_def_{season}.parquet"
    return "stats_player/stats_player_week_{season}.parquet"


def build_players_index(out_dir: Path, merged: dict[int, dict]) -> None:
    index: dict[str, dict] = {}
    for season in sorted(merged.keys()):
        for pid, info in merged[season].get("players", {}).items():
            entry = index.get(pid)
            if not entry:
                index[pid] = {"n": info[0], "p": info[2] if len(info) > 2 else "", "g": info[4] if len(info) > 4 else "",
                              "h": info[3] if len(info) > 3 else "", "f": season, "l": season, "t": info[1] if len(info) > 1 else ""}
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
    (out_dir / "players_index.json").write_text(json.dumps(index, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    print(f"players_index: {len(index)} players, {(out_dir / 'players_index.json').stat().st_size/1024:.0f} KB")


def build_catalog(out_dir: Path, exported: dict[int, dict], team_meta: dict, top_n: int) -> dict:
    if not exported:
        print("catalog: no seasons exported yet")
        return {}
    season_stats = {s: set(p["player_stats"].keys()) for s, p in exported.items()}
    season_team_stats = {s: set(p["team_stats"].keys()) for s, p in exported.items()}
    all_player = set().union(*season_stats.values())
    all_team = set().union(*season_team_stats.values())

    def groups_from(reg_groups, universe):
        seen = set()
        out = []
        for group, mapping in reg_groups.items():
            stats = [{"key": k, "label": v, "agg": agg_kind(k), "fmt": fmt_kind(k)} for k, v in mapping.items() if k in universe]
            seen.update(s["key"] for s in stats)
            if stats:
                out.append({"group": group, "stats": stats})
        leftover = sorted(universe - seen)
        if leftover:
            out.append({"group": "Other", "stats": [{"key": k, "label": prettify(k), "agg": agg_kind(k), "fmt": fmt_kind(k)} for k in leftover]})
        return out

    player_groups = groups_from(PLAYER_GROUPS, all_player)
    known = {s["key"] for g in player_groups for s in g["stats"]}
    player_groups += groups_from(PFR_GROUPS, all_player - known)
    team_groups = groups_from(TEAM_GROUPS, all_team)

    catalog = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "top_n": POOL_CAP,
        "seasons": sorted(exported.keys()),
        "season_weeks": {str(s): len(p["weeks"]) for s, p in exported.items()},
        "player_groups": player_groups,
        "team_groups": team_groups,
        "player_stat_count": len(all_player),
        "team_stat_count": len(all_team),
        "team_meta": team_meta,
        "stat_sources": {
            "player": {k: source_for(k, "player") for k in sorted(all_player)},
            "team": {k: source_for(k, "team") for k in sorted(all_team)},
        },
    }
    (out_dir / "catalog.json").write_text(json.dumps(catalog, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    print(f"catalog: {len(all_player)} player stats, {len(all_team)} team stats, seasons {catalog['seasons'][0]}-{catalog['seasons'][-1]}")
    return catalog


def team_meta(cache_dir: Path) -> dict:
    tc = fetch(E["teams"], cache_dir)
    out = {}
    for _, row in tc.iterrows():
        abbr = str(row.get("team_abbr") or "")
        if not abbr:
            continue
        name = str(row.get("team_name") or row.get("team_nick") or abbr)
        out[abbr] = [name, str(row.get("team_color") or ""), str(row.get("team_color2") or ""),
                     str(row.get("team_logo_espn") or "")]
    return out


def parse_seasons(spec: str) -> list[int]:
    seasons = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            seasons.extend(range(int(a), int(b) + 1))
        else:
            seasons.append(int(part))
    return seasons


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", default="1999-2026")
    ap.add_argument("--out", default="public/nfl-stats/data")
    ap.add_argument("--cache", default=".nfl-cache")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--refresh", action="store_true", help="ignore cached parquet and re-download")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(args.cache)

    exported: dict[int, dict] = {}
    for season in parse_seasons(args.seasons):
        try:
            exported[season] = export_season(season, out_dir, cache_dir, args.top, args.refresh)
        except Exception as exc:
            print(f"season {season}: FAILED {type(exc).__name__}: {exc}")

    existing: dict[int, dict] = {}
    for path in out_dir.glob("season_*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            existing[int(data["season"])] = data
        except Exception:
            continue
    merged = {**existing, **exported}
    build_catalog(out_dir, merged, team_meta(cache_dir), args.top)
    build_players_index(out_dir, merged)


if __name__ == "__main__":
    main()
