"""MLB Stats API -> MLB stats progression bundle exporter (dashboard-safe, standalone).

Reads the local raw archive of MLB Stats API responses:
    <archive>/seasons/<year>/players/*.json   (hitting/pitching/fielding gameLogs)
and writes one compact JSON per season plus catalog.json, players_index.json consumed
by the dashboard's MLBStatsWidget (mirrors the nflverse exporter contract).

Axis: team-game ordinal (<=163 points per entity, trades accepted as-is for v1).
Each series also carries "g" (global game refs) so the widget can switch to by-date.

Usage:
  python mlb_stats_export.py --seasons 2024 --out public/mlb-stats/data
  python mlb_stats_export.py --seasons 2010-2026 --out public/mlb-stats/data
"""
from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ARCHIVE_DEFAULT = r"D:\20260504 e to d transfer\mlb_api"

TEAM_META = {
    108: ("LAA", "Los Angeles Angels", "#003263", "#BA0021"),
    109: ("ARI", "Arizona Diamondbacks", "#A71930", "#E3D4AD"),
    110: ("BAL", "Baltimore Orioles", "#DF4601", "#000000"),
    111: ("BOS", "Boston Red Sox", "#BD3039", "#0C2340"),
    112: ("CHC", "Chicago Cubs", "#0E3386", "#CC3433"),
    113: ("CIN", "Cincinnati Reds", "#C6011F", "#000000"),
    114: ("CLE", "Cleveland Guardians", "#00385D", "#E50022"),
    115: ("COL", "Colorado Rockies", "#33006F", "#C4CED4"),
    116: ("DET", "Detroit Tigers", "#0C2340", "#FA4616"),
    117: ("HOU", "Houston Astros", "#002D62", "#EB6E1F"),
    118: ("KC", "Kansas City Royals", "#004687", "#BD9B60"),
    119: ("LAD", "Los Angeles Dodgers", "#005A9C", "#EF3E42"),
    120: ("WSH", "Washington Nationals", "#AB0003", "#14225A"),
    121: ("NYM", "New York Mets", "#002D72", "#FF5910"),
    133: ("ATH", "Athletics", "#003831", "#EFB21E"),
    134: ("PIT", "Pittsburgh Pirates", "#FDB827", "#27251F"),
    135: ("SD", "San Diego Padres", "#2F241D", "#FFC425"),
    136: ("SEA", "Seattle Mariners", "#0C2C56", "#005C5C"),
    137: ("SF", "San Francisco Giants", "#FD5A1E", "#27251F"),
    138: ("STL", "St. Louis Cardinals", "#C41E3A", "#0C2340"),
    139: ("TB", "Tampa Bay Rays", "#092C5C", "#8FBCE6"),
    140: ("TEX", "Texas Rangers", "#003278", "#C0111F"),
    141: ("TOR", "Toronto Blue Jays", "#134A8E", "#E8291C"),
    142: ("MIN", "Minnesota Twins", "#002B5C", "#D31145"),
    143: ("PHI", "Philadelphia Phillies", "#E81828", "#002D72"),
    144: ("ATL", "Atlanta Braves", "#CE1141", "#13274F"),
    145: ("CWS", "Chicago White Sox", "#27251F", "#C4CED4"),
    146: ("MIA", "Miami Marlins", "#00A3E0", "#EF3340"),
    147: ("NYY", "New York Yankees", "#0C2340", "#C4CED4"),
    158: ("MIL", "Milwaukee Brewers", "#12284B", "#FFC52F"),
}

POS_TO_GROUP = {
    "P": "P", "C": "C", "1B": "IF", "2B": "IF", "3B": "IF", "SS": "IF",
    "LF": "OF", "CF": "OF", "RF": "OF", "OF": "OF", "DH": "DH",
}

HIT_RATES = {
    "avg": {"num": ("hits",), "den": ("atBats",), "asc": False, "label": "Batting average", "min_den": 100},
    "obp": {"num": ("hits", "baseOnBalls", "hitByPitch"), "den": ("atBats", "baseOnBalls", "hitByPitch", "sacFlies"), "asc": False, "label": "On-base percentage", "min_den": 100},
    "slg": {"num": ("totalBases",), "den": ("atBats",), "asc": False, "label": "Slugging percentage", "min_den": 100},
    "ops": {"num": None, "den": None, "asc": False, "label": "OPS", "compose": ("obp", "slg")},
    "iso": {"num": ("totalBases", "hits_neg"), "den": ("atBats",), "asc": False, "label": "ISO (isolated power)", "min_den": 100},
    "babip": {"num": ("hits", "homeRuns_neg"), "den": ("atBats", "strikeOuts_neg", "homeRuns_neg", "sacFlies"), "asc": False, "label": "BABIP", "min_den": 100},
    "kRate": {"num": ("strikeOuts",), "den": ("plateAppearances",), "factor": 100.0, "asc": True, "label": "K%", "min_den": 100},
    "bbRate": {"num": ("baseOnBalls",), "den": ("plateAppearances",), "factor": 100.0, "asc": False, "label": "BB%", "min_den": 100},
    "kMinusBB": {"num": ("strikeOuts", "baseOnBalls_neg"), "den": ("plateAppearances",), "factor": 100.0, "asc": True, "label": "K-BB%", "min_den": 100},
    "pitchesPerPA": {"num": ("numberOfPitches",), "den": ("plateAppearances",), "factor": 1.0, "asc": False, "label": "Pitches/PA", "min_den": 100},
}
PIT_RATES = {
    "era": {"num": ("earnedRuns",), "den": ("outs",), "factor": 27.0, "asc": True, "label": "ERA", "min_den": 150},
    "whip": {"num": ("hits", "baseOnBalls"), "den": ("outs",), "factor": 3.0, "asc": True, "label": "WHIP", "min_den": 150},
    "kPer9": {"num": ("strikeOuts",), "den": ("outs",), "factor": 27.0, "asc": False, "label": "K/9", "min_den": 150},
    "bbPer9": {"num": ("baseOnBalls",), "den": ("outs",), "factor": 27.0, "asc": True, "label": "BB/9", "min_den": 150},
    "hrPer9": {"num": ("homeRuns",), "den": ("outs",), "factor": 27.0, "asc": True, "label": "HR/9", "min_den": 150},
    "strikeoutWalkRatio": {"num": ("strikeOuts",), "den": ("baseOnBalls",), "factor": 1.0, "asc": False, "label": "K/BB", "min_den": 150},
    "fip": {"weights": {"homeRuns": 13.0, "baseOnBalls": 3.0, "hitBatsmen": 3.0, "strikeOuts": -2.0}, "den": ("outs",), "factor": 3.0, "asc": True, "label": "FIP", "min_den": 150},
    "kRate": {"num": ("strikeOuts",), "den": ("battersFaced",), "factor": 100.0, "asc": True, "label": "K% (pitching)", "min_den": 150},
    "bbRate": {"num": ("baseOnBalls",), "den": ("battersFaced",), "factor": 100.0, "asc": True, "label": "BB% (pitching)", "min_den": 150},
    "pitchesPerBF": {"num": ("numberOfPitches",), "den": ("battersFaced",), "factor": 1.0, "asc": False, "label": "Pitches/BF", "min_den": 150},
}
FLD_RATES = {
    "fieldingPct": {"num": ("putOuts", "assists"), "den": ("putOuts", "assists", "errors"), "factor": 1.0, "asc": False, "label": "Fielding %", "min_den": 50},
}

HIT_COUNTING = ["gamesPlayed", "atBats", "plateAppearances", "runs", "hits", "doubles", "triples",
                "homeRuns", "rbi", "baseOnBalls", "intentionalWalks", "strikeOuts", "stolenBases",
                "caughtStealing", "hitByPitch", "sacBunts", "sacFlies", "groundIntoDoublePlay",
                "leftOnBase", "totalBases", "numberOfPitches", "catcherInterference"]
PIT_COUNTING = ["gamesPlayed", "gamesStarted", "wins", "losses", "saves", "saveOpportunities", "holds",
                "blownSaves", "completeGames", "shutouts", "earnedRuns", "runs", "hits", "baseOnBalls",
                "intentionalWalks", "strikeOuts", "homeRuns", "hitBatsmen", "balks", "wildPitches",
                "battersFaced", "outs", "strikes", "numberOfPitches"]
FLD_COUNTING = ["gamesStarted", "innings", "putOuts", "assists", "errors", "chances", "doublePlays",
                "triplePlays", "throwingErrors"]

HIT_LABELS = {"avg": "AVG", "obp": "OBP", "slg": "SLG", "ops": "OPS",
              "homeRuns": "Home runs", "rbi": "RBI", "stolenBases": "Stolen bases", "hits": "Hits",
              "runs": "Runs", "doubles": "Doubles", "triples": "Triples", "baseOnBalls": "Walks",
              "strikeOuts": "Strikeouts", "totalBases": "Total bases", "atBats": "At bats",
              "gamesPlayed": "Games", "plateAppearances": "Plate appearances",
              "extraBaseHits": "Extra-base hits"}
PIT_LABELS = {"era": "ERA", "whip": "WHIP", "kPer9": "K/9", "bbPer9": "BB/9", "hrPer9": "HR/9",
              "strikeoutWalkRatio": "K/BB", "strikeOuts": "Strikeouts", "wins": "Wins", "losses": "Losses",
              "saves": "Saves", "earnedRuns": "Earned runs", "inningsPitched": "Innings pitched",
              "hits": "Hits allowed", "baseOnBalls": "Walks allowed", "homeRuns": "Home runs allowed",
              "gamesPlayed": "Games", "gamesStarted": "Games started", "holds": "Holds",
              "blownSaves": "Blown saves", "battersFaced": "Batters faced", "outs": "Outs"}
FLD_LABELS = {"fieldingPct": "Fielding %", "putOuts": "Putouts", "assists": "Assists", "errors": "Errors",
              "chances": "Chances", "doublePlays": "Double plays", "triplePlays": "Triple plays",
              "innings": "Innings", "gamesStarted": "Games started"}
TEAM_LABELS = {"runsScored": "Runs scored", "runsAllowed": "Runs allowed", "runDiff": "Run differential",
               "wins": "Wins", "losses": "Losses", "winPct": "Win %", "gamesPlayed": "Games played"}

POOL_OVERALL = 30
POOL_PER_GROUP = 6
POOL_CAP = 40


def sf(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        return f if math.isfinite(f) else None
    try:
        f = float(str(v).replace("%", ""))
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def round_val(v, digits=3):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    f = float(v)
    if abs(f - round(f)) < 1e-9:
        return int(round(f))
    return round(f, digits)


def parse_seasons(spec: str) -> list[int]:
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def load_season_frames(archive: Path, season: int, verbose: bool = True):
    players_dir = archive / "seasons" / str(season) / "players"
    if not players_dir.exists():
        raise FileNotFoundError(f"missing {players_dir}")
    files = sorted(players_dir.glob("*.json"))
    hit_rows, pit_rows, fld_rows = [], [], []
    games_meta = {}
    player_names = {}
    positions = {}
    for i, path in enumerate(files):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        pid = str(data.get("id") or path.stem)
        name = data.get("fullName") or ""
        if name:
            player_names[pid] = name
        for kind, rows in (("hitting_gamelogs", hit_rows),
                           ("pitching_gamelogs", pit_rows),
                           ("fielding_gamelogs", fld_rows)):
            logs = data.get(kind) or {}
            reg = logs.get("R") or {}
            stats = reg.get("stats") or []
            splits = stats[0].get("splits", []) if stats else []
            for s in splits:
                g = s.get("game") or {}
                pk = g.get("gamePk")
                date = s.get("date")
                if not pk or not date:
                    continue
                team = s.get("team") or {}
                opp = s.get("opponent") or {}
                is_home = bool(s.get("isHome"))
                home = team if is_home else opp
                away = opp if is_home else team
                key = str(pk)
                if key not in games_meta:
                    games_meta[key] = {"pk": pk, "date": date, "h": home.get("id"), "a": away.get("id")}
                stat = s.get("stat") or {}
                row = {"pid": pid, "pk": pk, "team": team.get("id")}
                for k, v in stat.items():
                    f = sf(v)
                    if f is not None:
                        row[k] = f
                rows.append(row)
                if kind == "fielding_gamelogs":
                    pos = (s.get("position") or {}).get("abbreviation")
                    if pos:
                        positions.setdefault(pid, {})
                        positions[pid][pos] = positions[pid].get(pos, 0) + 1
        if verbose and (i + 1) % 500 == 0:
            print(f"    parsed {i+1}/{len(files)} player files")
    gm = sorted(games_meta.values(), key=lambda x: (x["date"], x["pk"]))
    gidx = {str(x["pk"]): idx for idx, x in enumerate(gm, start=1)}
    game_list = [{"i": idx, "d": x["date"], "pk": x["pk"], "h": x["h"], "a": x["a"]} for idx, x in enumerate(gm, start=1)]
    team_cal = {}
    for x in gm:
        for t in (x["h"], x["a"]):
            if t is not None:
                team_cal.setdefault(t, []).append(x)
    tord = {}
    for t, arr in team_cal.items():
        for idx, x in enumerate(arr, start=1):
            tord[(t, x["pk"])] = idx
    max_games = max((len(a) for a in team_cal.values()), default=0)
    for rows in (hit_rows, pit_rows, fld_rows):
        by_pid = {}
        for r in rows:
            by_pid.setdefault(r["pid"], []).append(r)
        for pid, rs in by_pid.items():
            rs.sort(key=lambda r: gidx[str(r["pk"])])
            offset = 0
            last_tgi = 0
            current_team = None
            stint_first_base = None
            for r in rs:
                g = gidx[str(r["pk"])]
                base = tord.get((r["team"], r["pk"]))
                if base is None:
                    tgi = last_tgi + 1 if last_tgi else g
                    current_team = r["team"]
                    stint_first_base = None
                else:
                    if current_team is None or r["team"] != current_team or stint_first_base is None:
                        current_team = r["team"]
                        stint_first_base = base
                        offset = last_tgi
                    tgi = offset + (base - stint_first_base) + 1
                r["tgi"] = tgi
                r["gi"] = g
                last_tgi = tgi
                if tgi > max_games:
                    max_games = tgi
    def to_df(rows):
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["pid", "gi", "tgi", "team", "pk"])
    pos_group = {}
    pos_detail = {}
    for pid, counts in positions.items():
        top = max(counts.items(), key=lambda kv: kv[1])[0]
        pos_detail[pid] = top
        pos_group[pid] = POS_TO_GROUP.get(top, "UT")
    hit_df, pit_df, fld_df = to_df(hit_rows), to_df(pit_rows), to_df(fld_rows)
    if "gamesStarted" in pit_df.columns:
        for pid, n in pit_df.groupby("pid")["gamesStarted"].sum().items():
            if pid not in pos_group and n and float(n) >= 1:
                pos_group[pid] = "P"
                pos_detail.setdefault(pid, "P")
    return hit_df, pit_df, fld_df, game_list, player_names, positions, pos_group, pos_detail, max_games


def derive_team_frames(hit_df, pit_df, fld_df):
    def teamify(df):
        if df.empty:
            return pd.DataFrame()
        cols = [c for c in df.columns if c not in ("pid", "pk", "gi", "tgi", "team")]
        agg = {c: "sum" for c in cols if c != "innings"}
        if "innings" in cols:
            agg["innings"] = "sum"
        out = df.groupby(["team", "tgi"], as_index=False).agg(agg).rename(columns={"team": "pid"})
        gmap = df.groupby(["team", "tgi"], as_index=False)["gi"].min().rename(columns={"team": "pid"})
        return out.merge(gmap, on=["pid", "tgi"], how="left")
    return teamify(hit_df), teamify(pit_df), teamify(fld_df)


def build_team_results(team_hit, team_pit):
    if team_hit.empty or team_pit.empty:
        return pd.DataFrame()
    rs = team_hit[["pid", "tgi", "gi", "runs"]].rename(columns={"runs": "runsScored"})
    ra = team_pit[["pid", "tgi", "gi", "runs"]].rename(columns={"runs": "runsAllowed"})
    m = rs.merge(ra, on=["pid", "tgi", "gi"], how="outer").fillna({"runsScored": 0.0, "runsAllowed": 0.0})
    m["runDiff"] = m["runsScored"] - m["runsAllowed"]
    m["wins"] = (m["runsScored"] > m["runsAllowed"]).astype(float)
    m["losses"] = (m["runsScored"] < m["runsAllowed"]).astype(float)
    return m


def panel(pivot_v: pd.DataFrame, run: pd.DataFrame, gmap: pd.DataFrame, asc: bool, group_of=None, top_n=15, cum: pd.DataFrame = None, tmap: pd.DataFrame = None):
    keep = run.index[(run.notna()).any(axis=1)]
    if len(keep) == 0:
        return None
    final = run.loc[keep].ffill(axis=1).iloc[:, -1]
    final = final[final.notna()]
    if final.empty:
        return None
    ranks = run.loc[final.index].rank(axis=0, ascending=asc, method="min")
    ordered = list(final.sort_values(ascending=asc).index)
    if group_of:
        chosen = {str(e) for e in ordered[:POOL_OVERALL]}
        seen = {}
        for e in ordered:
            g = group_of.get(str(e), "")
            if not g or seen.get(g, 0) >= POOL_PER_GROUP:
                continue
            chosen.add(str(e))
            seen[g] = seen.get(g, 0) + 1
        ordered = [e for e in ordered if str(e) in chosen]
    ordered = ordered[: max(top_n, POOL_CAP)]
    cols = list(pivot_v.columns)
    series = []
    for e in ordered:
        vrow = pivot_v.loc[e]
        rrow = ranks.loc[e]
        grow = gmap.loc[e] if e in gmap.index else None
        vals = [round_val(vrow.get(c)) for c in cols]
        if all(v is None for v in vals):
            continue
        entry = {
            "id": str(e),
            "v": vals,
            "r": [None if pd.isna(rrow.get(c)) else int(rrow.get(c)) for c in cols],
            "g": [None if (grow is None or pd.isna(grow.get(c))) else int(grow.get(c)) for c in cols],
        }
        if cum is not None and e in cum.index:
            crow = cum.loc[e]
            entry["c"] = [round_val(crow.get(c)) for c in cols]
        if tmap is not None and e in tmap.index:
            trow = tmap.loc[e]
            teams = {int(trow.get(c)) for c in cols if not pd.isna(trow.get(c))}
            if len(teams) > 1:
                entry["tm"] = [None if pd.isna(trow.get(c)) else int(trow.get(c)) for c in cols]
        series.append(entry)
    return series or None


def stat_panels(df: pd.DataFrame, counting, rates, max_games: int, group_of=None, top_n=15):
    out = {}
    cols = list(range(1, max_games + 1))
    if df.empty:
        return out
    gi_map = df[["pid", "tgi", "gi"]].dropna()
    team_map = None
    if "team" in df.columns and not df.empty:
        team_map = (
            df[["pid", "tgi", "team"]].dropna()
            .pivot_table(index="pid", columns="tgi", values="team", aggfunc="last")
            .reindex(columns=cols)
        )
    for stat in counting:
        if stat not in df.columns:
            continue
        sub = df[["pid", "tgi", stat]].dropna(subset=[stat])
        if sub.empty:
            continue
        pivot = sub.pivot_table(index="pid", columns="tgi", values=stat, aggfunc="sum").reindex(columns=cols)
        run = pivot.fillna(0).cumsum(axis=1)
        gpivot = gi_map.pivot_table(index="pid", columns="tgi", values="gi", aggfunc="min").reindex(columns=cols)
        series = panel(pivot, run, gpivot, asc=False, group_of=group_of, top_n=top_n, tmap=team_map)
        if series:
            out[stat] = series
    if "extraBaseHits" not in out and {"doubles", "triples", "homeRuns"} <= set(df.columns):
        d = df[["pid", "tgi", "gi", "doubles", "triples", "homeRuns"]].copy()
        d["extraBaseHits"] = d["doubles"].fillna(0) + d["triples"].fillna(0) + d["homeRuns"].fillna(0)
        pivot = d.pivot_table(index="pid", columns="tgi", values="extraBaseHits", aggfunc="sum").reindex(columns=cols)
        run = pivot.fillna(0).cumsum(axis=1)
        gpivot = gi_map.pivot_table(index="pid", columns="tgi", values="gi", aggfunc="min").reindex(columns=cols)
        series = panel(pivot, run, gpivot, asc=False, group_of=group_of, top_n=top_n, tmap=team_map)
        if series:
            out["extraBaseHits"] = series
    def component_rate(spec):
        num_cols = spec.get("num") or ()
        den_cols = spec.get("den") or ()
        comp = sorted({c.replace("_neg", "") for c in tuple(num_cols) + tuple(den_cols)})
        if not set(comp) <= set(df.columns):
            return None
        dd = df[["pid", "tgi", "gi"] + comp].copy()
        sign = {c: (-1.0 if c.endswith("_neg") else 1.0) for c in num_cols}
        dd["_num"] = sum(dd[c.replace("_neg", "")].fillna(0) * s for c, s in sign.items()) if num_cols else 0.0
        dd["_den"] = sum(dd[c.replace("_neg", "")].fillna(0) * (-1.0 if c.endswith("_neg") else 1.0) for c in den_cols) if den_cols else 0.0
        pv = dd.pivot_table(index="pid", columns="tgi", values=["_num", "_den"], aggfunc="sum")
        np_ = pv["_num"].reindex(columns=cols)
        dp_ = pv["_den"].reindex(columns=cols)
        cum_den = dp_.fillna(0).cumsum(axis=1)
        factor = float(spec.get("factor", 1.0))
        const = float(spec.get("const", 0.0))
        run_ = (np_.fillna(0).cumsum(axis=1) / cum_den.replace(0, float("nan"))) * factor + const
        if spec.get("min_den"):
            run_ = run_.where(cum_den >= float(spec["min_den"]))
        vv = (np_ / dp_.replace(0, float("nan"))) * factor + const
        return run_, vv

    for key, spec in rates.items():
        if key == "ops":
            if not (rates.get("obp") and rates.get("slg")):
                continue
            obp_parts = component_rate(rates["obp"])
            slg_parts = component_rate(rates["slg"])
            if obp_parts is None or slg_parts is None:
                continue
            run = obp_parts[0] + slg_parts[0]
            vvals = obp_parts[1] + slg_parts[1]
            gpivot = df.pivot_table(index="pid", columns="tgi", values="gi", aggfunc="min").reindex(columns=cols)
            series = panel(vvals, run, gpivot, asc=False, group_of=group_of, top_n=top_n, cum=run, tmap=team_map)
            if series:
                out[key] = series
            continue
        num_cols = spec.get("num") or ()
        den_cols = spec.get("den") or ()
        weights = spec.get("weights") or {}
        factor = float(spec.get("factor", 1.0))
        const = float(spec.get("const", 0.0))
        need = {c.replace("_neg", "") for c in tuple(num_cols) + tuple(den_cols)} | set(weights.keys())
        if not need <= set(df.columns):
            continue
        comp_cols = sorted(need)
        d = df[["pid", "tgi", "gi"] + comp_cols].copy()
        if weights:
            d["_num"] = sum(d[c_].fillna(0) * float(w) for c_, w in weights.items())
        else:
            sign = {c: (-1.0 if c.endswith("_neg") else 1.0) for c in num_cols}
            d["_num"] = sum(d[c_.replace("_neg", "")].fillna(0) * s for c_, s in sign.items()) if num_cols else 0.0
        d["_den"] = sum(d[c_.replace("_neg", "")].fillna(0) * (-1.0 if c_.endswith("_neg") else 1.0) for c_ in den_cols) if den_cols else 0.0
        vpiv = d.pivot_table(index="pid", columns="tgi", values=["_num", "_den"], aggfunc="sum")
        num_p = vpiv["_num"].reindex(columns=cols)
        den_p = vpiv["_den"].reindex(columns=cols)
        cum_num = num_p.fillna(0).cumsum(axis=1)
        cum_den = den_p.fillna(0).cumsum(axis=1)
        run = (cum_num / cum_den.replace(0, float("nan"))) * factor + const
        if spec.get("min_den"):
            run = run.where(cum_den >= float(spec["min_den"]))
        vvals = (num_p / den_p.replace(0, float("nan"))) * factor + const
        gpivot = d.pivot_table(index="pid", columns="tgi", values="gi", aggfunc="min").reindex(columns=cols)
        series = panel(vvals, run, gpivot, asc=bool(spec.get("asc")), group_of=group_of, top_n=top_n, cum=run, tmap=team_map)
        if series:
            out[key] = series
    return out


def export_season(archive: Path, season: int, out_dir: Path, top_n: int, full: bool = False) -> dict:
    t0 = time.time()
    print(f"  season {season}: scanning players...")
    hit_df, pit_df, fld_df, game_list, names, positions, pos_group, pos_detail, max_games = load_season_frames(archive, season)
    print(f"    games={len(game_list)} max_team_games={max_games} players={len(names)} "
          f"rows: hit={len(hit_df)} pit={len(pit_df)} fld={len(fld_df)}")
    pit_rates = dict(PIT_RATES)
    need_pit = {"earnedRuns", "outs", "homeRuns", "baseOnBalls", "hitBatsmen", "strikeOuts"}
    if not pit_df.empty and need_pit <= set(pit_df.columns):
        lg_er = pit_df["earnedRuns"].sum(); lg_outs = pit_df["outs"].sum()
        lg_hr = pit_df["homeRuns"].sum(); lg_bb = pit_df["baseOnBalls"].sum()
        lg_hbp = pit_df["hitBatsmen"].sum(); lg_k = pit_df["strikeOuts"].sum()
        if lg_outs > 0:
            c_fip = 27.0 * lg_er / lg_outs - 3.0 * (13.0 * lg_hr + 3.0 * (lg_bb + lg_hbp) - 2.0 * lg_k) / lg_outs
            pit_rates["fip"] = {**PIT_RATES["fip"], "const": c_fip}
            print(f"    cFIP({season}) = {c_fip:.3f}")
    player_stats = {}
    player_stats.update({f"hit_{k}": v for k, v in stat_panels(hit_df, HIT_COUNTING, HIT_RATES, max_games, pos_group, top_n).items()})
    player_stats.update({f"pit_{k}": v for k, v in stat_panels(pit_df, PIT_COUNTING, pit_rates, max_games, pos_group, top_n).items()})
    player_stats.update({f"fld_{k}": v for k, v in stat_panels(fld_df, FLD_COUNTING, FLD_RATES, max_games, pos_group, top_n).items()})
    team_hit, team_pit, team_fld = derive_team_frames(hit_df, pit_df, fld_df)
    team_res = build_team_results(team_hit, team_pit)
    team_stats = {}
    team_stats.update(stat_panels(team_res, ["runsScored", "runsAllowed", "runDiff", "wins", "losses"],
                                  {"winPct": {"num": ("wins",), "den": ("wins", "losses"), "factor": 1.0, "asc": False, "label": "Win %", "min_den": 5}},
                                  max_games, None, top_n))
    team_stats.update({f"hit_{k}": v for k, v in stat_panels(team_hit, HIT_COUNTING, HIT_RATES, max_games, None, top_n).items()})
    team_stats.update({f"pit_{k}": v for k, v in stat_panels(team_pit, PIT_COUNTING, pit_rates, max_games, None, top_n).items()})
    team_stats.update({f"fld_{k}": v for k, v in stat_panels(team_fld, FLD_COUNTING, FLD_RATES, max_games, None, top_n).items()})
    players = {}
    for pid, name in names.items():
        group = pos_group.get(pid, "")
        detail = pos_detail.get(pid) or group
        team_id = ""
        for frame in (hit_df, pit_df, fld_df):
            if frame.empty:
                continue
            rows = frame[frame["pid"] == pid]
            if not rows.empty:
                team_id = str(int(rows["team"].dropna().iloc[-1]))
                break
        players[pid] = [name, team_id, detail, "", group]
    teams_seen = sorted({str(int(t)) for t in set(hit_df.get("team", pd.Series(dtype=float)).dropna()) | set(pit_df.get("team", pd.Series(dtype=float)).dropna())})
    payload = {
        "season": season,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "mlb-api (statsapi.mlb.com) via local archive seasons/" + str(season) + "/players gameLogs",
        "top_n": top_n,
        "mode": "game",
        "axes": {"game": "team-game ordinal (<= " + str(max_games) + ")", "date": "resolve via games[g-1].d"},
        "max_games": max_games,
        "games": game_list,
        "players": players,
        "player_stats": player_stats,
        "team_stats": team_stats,
        "team_ids": teams_seen,
    }
    out = out_dir / f"season_{season}.json"
    out.write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    if full:
        write_full_stats(out_dir, season, hit_df, pit_df, max_games, pit_rates)
    print(f"  season {season}: {len(player_stats)} player stats, {len(team_stats)} team stats, "
          f"{len(game_list)} games, {out.stat().st_size/1024/1024:.1f} MB, {time.time()-t0:.1f}s")
    return payload


FULL_KEYS = ["hit_homeRuns", "hit_hits", "hit_runs", "hit_rbi", "hit_stolenBases", "hit_avg", "hit_obp",
             "hit_slg", "hit_ops", "hit_iso", "pit_strikeOuts", "pit_wins", "pit_saves", "pit_era",
             "pit_whip", "pit_fip"]


def write_full_stats(out_dir: Path, season: int, hit_df, pit_df, max_games: int, pit_rates: dict):
    fdir = out_dir / "full" / str(season)
    fdir.mkdir(parents=True, exist_ok=True)
    written = 0
    for key in FULL_KEYS:
        prefix, base = key.split("_", 1)
        if prefix == "hit":
            df, rates, labels, group = hit_df, HIT_RATES, HIT_LABELS, "Hitting"
        else:
            df, rates, labels, group = pit_df, pit_rates, PIT_LABELS, "Pitching"
        if base == "ops":
            stats = stat_panels(df, [], {"obp": rates["obp"], "slg": rates["slg"], "ops": rates["ops"]}, max_games, None, 10 ** 9)
        else:
            stats = stat_panels(df, [base], rates, max_games, None, 10 ** 9)
        series = stats.get(base)
        if not series:
            continue
        spec = rates.get(base) or {}
        payload = {
            "stat": key, "season": season, "group": group, "label": labels.get(base, base),
            "agg": "rate" if base in rates else "sum",
            "asc": bool(spec.get("asc", False)),
            "fmt": "f3" if base in rates else "i0",
            "count": len(series),
            "series": series,
        }
        (fdir / f"{key}.json").write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False), encoding="utf-8")
        written += 1
    print(f"  season {season}: full files written: {written} -> {fdir}")


def groups_from(registry, universe, labels):
    out = []
    seen = set()
    for group, items in registry:
        stats = []
        for key, label in items:
            if key in universe:
                is_rate = key in labels.get("_rates", set())
                stats.append({"key": key, "label": label, "agg": "rate" if is_rate else "sum",
                              "fmt": "f3" if is_rate else "i0", "asc": bool(labels.get("_asc", {}).get(key, False))})
                seen.add(key)
        if stats:
            out.append({"group": group, "stats": stats})
    leftover = sorted(universe - seen)
    if leftover:
        out.append({"group": "Other", "stats": [{"key": k, "label": k, "agg": "sum", "fmt": "i0", "asc": False} for k in leftover]})
    return out


def build_catalog(out_dir: Path, exported: dict, top_n: int):
    all_player = set().union(*[set(p["player_stats"]) for p in exported.values()]) if exported else set()
    all_team = set().union(*[set(p["team_stats"]) for p in exported.values()]) if exported else set()
    hit_registry = [("Hitting", [(f"hit_{k}", HIT_LABELS.get(k, k)) for k in HIT_COUNTING] + [(f"hit_{k}", v["label"]) for k, v in HIT_RATES.items() if k not in ("iso", "babip", "kRate", "bbRate", "kMinusBB", "pitchesPerPA")])]
    pit_registry = [("Pitching", [(f"pit_{k}", PIT_LABELS.get(k, k)) for k in PIT_COUNTING] + [(f"pit_{k}", v["label"]) for k, v in PIT_RATES.items() if k not in ("fip", "kRate", "bbRate", "pitchesPerBF")])]
    adv_registry = [("Advanced", [(f"hit_{k}", HIT_RATES[k]["label"]) for k in ("iso", "babip", "kRate", "bbRate", "kMinusBB", "pitchesPerPA")]
                    + [(f"pit_{k}", PIT_RATES[k]["label"]) for k in ("fip", "kRate", "bbRate", "pitchesPerBF")])]
    fld_registry = [("Fielding", [(f"fld_{k}", FLD_LABELS.get(k, k)) for k in FLD_COUNTING] + [(f"fld_{k}", v["label"]) for k, v in FLD_RATES.items()])]
    rate_keys = {f"hit_{k}" for k in HIT_RATES} | {f"pit_{k}" for k in PIT_RATES} | {f"fld_{k}" for k in FLD_RATES} | {"winPct"}
    asc_map = {f"hit_{k}": v.get("asc", False) for k, v in HIT_RATES.items()}
    asc_map.update({f"pit_{k}": v.get("asc", False) for k, v in PIT_RATES.items()})
    asc_map.update({f"fld_{k}": v.get("asc", False) for k, v in FLD_RATES.items()})
    asc_map["winPct"] = False
    label_ctx = {"_rates": rate_keys, "_asc": asc_map}
    team_registry = [
        ("Results", [(k, TEAM_LABELS.get(k, k)) for k in ["runsScored", "runsAllowed", "runDiff", "wins", "losses"]] + [("winPct", "Win %")]),
        ("Team Hitting", [(f"hit_{k}", HIT_LABELS.get(k, k)) for k in HIT_COUNTING] + [(f"hit_{k}", v["label"]) for k, v in HIT_RATES.items() if k not in ("iso", "babip", "kRate", "bbRate", "kMinusBB", "pitchesPerPA")]),
        ("Team Pitching", [(f"pit_{k}", PIT_LABELS.get(k, k)) for k in PIT_COUNTING] + [(f"pit_{k}", v["label"]) for k, v in PIT_RATES.items() if k not in ("fip", "kRate", "bbRate", "pitchesPerBF")]),
        ("Advanced", [(f"hit_{k}", HIT_RATES[k]["label"]) for k in ("iso", "babip", "kRate", "bbRate", "kMinusBB", "pitchesPerPA")]
         + [(f"pit_{k}", PIT_RATES[k]["label"]) for k in ("fip", "kRate", "bbRate", "pitchesPerBF")]),
        ("Team Fielding", [(f"fld_{k}", FLD_LABELS.get(k, k)) for k in FLD_COUNTING] + [(f"fld_{k}", v["label"]) for k, v in FLD_RATES.items()]),
    ]
    team_meta = {}
    for tid, (abbr, name, c1, c2) in TEAM_META.items():
        team_meta[str(tid)] = [abbr, name, c1, c2, f"https://www.mlbstatic.com/team-logos/{tid}.svg"]
    catalog = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sport": "mlb",
        "source": "mlb-api (statsapi.mlb.com)",
        "source_policy": "mlb-api preferred; see D:\\mlb-api\\API_COVERAGE_AND_SOURCES.md",
        "top_n": POOL_CAP,
        "seasons": sorted(exported.keys()),
        "season_games": {str(s): len(p["games"]) for s, p in exported.items()},
        "season_max_games": {str(s): p.get("max_games") for s, p in exported.items()},
        "player_groups": groups_from(hit_registry + pit_registry + adv_registry + fld_registry, all_player, label_ctx),
        "team_groups": groups_from(team_registry, all_team, label_ctx),
        "player_stat_count": len(all_player),
        "team_stat_count": len(all_team),
        "team_meta": team_meta,
        "position_groups": ["P", "C", "IF", "OF", "DH", "UT"],
        "axes": ["game", "date"],
        "headshot_pattern": "https://img.mlbstatic.com/mlb-photos/image/upload/d_people:generic:headshot:67:current.png/w_213,q_auto:best/v1/people/{id}/headshot/67/current",
    }
    (out_dir / "catalog.json").write_text(json.dumps(catalog, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    print(f"catalog: {len(all_player)} player stats, {len(all_team)} team stats, seasons {catalog['seasons']}")
    return catalog


def build_players_index(out_dir: Path, exported: dict):
    index = {}
    for season in sorted(exported):
        for pid, info in exported[season].get("players", {}).items():
            e = index.get(pid)
            if not e:
                index[pid] = {"n": info[0], "t": info[1], "p": info[2], "f": season, "l": season}
            else:
                e["l"] = season
                if info[0]:
                    e["n"] = info[0]
                if info[1]:
                    e["t"] = info[1]
                if info[2]:
                    e["p"] = info[2]
    (out_dir / "players_index.json").write_text(json.dumps(index, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    print(f"players_index: {len(index)} players")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", default="2010-2026")
    ap.add_argument("--archive", default=ARCHIVE_DEFAULT)
    ap.add_argument("--out", default="public/mlb-stats/data")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--full", action="store_true", help="also write full-pool per-stat files (all entities)")
    args = ap.parse_args()
    archive = Path(args.archive)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    exported = {}
    for season in parse_seasons(args.seasons):
        try:
            exported[season] = export_season(archive, season, out_dir, args.top, args.full)
        except Exception as exc:
            print(f"  season {season}: FAILED {type(exc).__name__}: {exc}")
    existing = {}
    for path in out_dir.glob("season_*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            existing[int(data["season"])] = data
        except Exception:
            continue
    merged = {**existing, **exported}
    build_catalog(out_dir, merged, args.top)
    build_players_index(out_dir, merged)


if __name__ == "__main__":
    main()
