"""Build career_leaders.json — all-time career leaderboards per player stat (1999-2026).

Source: same-origin mirrors public/nfl-stats/parquet/stats_player_week_{season}.parquet
(nflverse stats_player weekly files). Mirrors buildCareer() semantics in the dashboard:
REG-season rows only, per-season sum (agg=sum) or mean over non-null weekly values
(agg=mean); career totals pool all weekly values. Rate stats require >= 48 career weeks
and the catalog qualifier volume when declared. Four derived stats mirror
nfl_stats_export.add_derived_stats (total_yards, total_tds, def_tackles_total, off_plays).

Usage: python scripts/publish/build_career_leaders.py
"""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "public" / "nfl-stats" / "data"
PQ = ROOT / "public" / "nfl-stats" / "parquet"
OUT = DATA / "career_leaders.json"

TOP_N = 25
MIN_WEEKS_MEAN = 48

DERIVED = {
    "def_tackles_total": ["def_tackles_solo", "def_tackle_assists"],
    "total_yards": ["passing_yards", "rushing_yards"],
    "off_plays": ["attempts", "carries"],
    "total_tds": ["passing_tds", "rushing_tds", "receiving_tds"],
}


def round_val(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    f = float(v)
    if not math.isfinite(f):
        return None
    if f.is_integer():
        return int(f) if abs(f) < 1e15 else f
    return round(f, 2)


def main():
    catalog = json.loads((DATA / "catalog.json").read_text(encoding="utf-8"))
    stats_meta = {}
    for g in catalog["player_groups"]:
        for s in g["stats"]:
            stats_meta[s["key"]] = {"label": s["label"], "agg": s.get("agg", "sum")}
    qualifiers = {k: v for k, v in (catalog.get("qualifiers") or {}).items() if isinstance(v, dict)}

    files = sorted(PQ.glob("stats_player_week_*.parquet"))
    seasons = [int(p.stem.split("_")[-1]) for p in files]
    print(f"loading {len(files)} season files {seasons[0]}-{seasons[-1]}")

    frames = []
    for p in files:
        df = pd.read_parquet(p)
        if "season_type" in df.columns:
            df = df[df["season_type"].eq("REG") | df["season_type"].isna()]
        frames.append(df)
    all_df = pd.concat(frames, ignore_index=True)
    print(f"rows: {len(all_df):,} | cols: {len(all_df.columns)}")

    for key, parts in DERIVED.items():
        if set(parts) <= set(all_df.columns):
            all_df[key] = sum(all_df[part].fillna(0) for part in parts)
            print(f"derived {key} from {parts}")

    available = [k for k in stats_meta if k in all_df.columns]
    missing = [k for k in stats_meta if k not in all_df.columns]
    print(f"stats: {len(available)} available, {len(missing)} skipped (not in weekly mirror)")

    sum_keys = [k for k in available if stats_meta[k]["agg"] == "sum"]
    mean_keys = [k for k in available if stats_meta[k]["agg"] == "mean"]

    gb = all_df.groupby(["player_id", "season"], sort=False)
    season_sum = gb[sum_keys].sum(min_count=1)
    season_mean = gb[mean_keys].mean() if mean_keys else None
    season_cnt = gb[mean_keys].count() if mean_keys else None
    player_teams = all_df.groupby("player_id", sort=False)["team"].agg(
        lambda s: list(dict.fromkeys([t for t in s.dropna().tolist() if t]))
    )

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "public/nfl-stats/parquet/stats_player_week_*.parquet (nflverse stats_player weekly, REG only)",
        "seasons": [seasons[0], seasons[-1]],
        "top_n": TOP_N,
        "min_weeks_mean": MIN_WEEKS_MEAN,
        "stats": {},
    }

    for key in available:
        agg = stats_meta[key]["agg"]
        label = stats_meta[key]["label"]
        if agg == "sum":
            tidy = season_sum[key].dropna()
        else:
            tidy = season_mean[key].dropna()
        if tidy.empty:
            continue
        players = tidy.groupby(level=0).size()
        if agg == "sum":
            total = tidy.groupby(level=0).sum()
            weeks = None
        else:
            cnt = season_cnt[key].loc[tidy.index]
            wtot = cnt.groupby(level=0).sum()
            wmean = tidy.groupby(level=0).mean()
            total = (wmean * wtot) / wtot
            weeks = wtot
            gate = qualifiers.get(key)
            ok = wmean.index[wtot.reindex(wmean.index).fillna(0) >= MIN_WEEKS_MEAN]
            total = total.loc[ok]
            if gate and gate.get("by") in season_sum.columns:
                gtot = season_sum[gate["by"]].dropna()
                gsum = gtot.groupby(level=0).sum()
                total = total[total.index.intersection(gsum[gsum >= float(gate.get("min", 0))].index)]
        top = total.sort_values(ascending=False).head(TOP_N)
        entries = []
        for pid, val in top.items():
            pr = tidy.xs(pid, level=0)
            seq = sorted([(int(s), round_val(v)) for s, v in pr.items()])
            entries.append({
                "id": str(pid),
                "total": round_val(val),
                "weeks": int(weeks.get(pid, 0)) if weeks is not None else int(players.get(pid, 0)),
                "first": seq[0][0],
                "last": seq[-1][0],
                "best": max([v for _, v in seq if v is not None], default=None),
                "teams": (player_teams.get(pid) or [])[:4],
                "seasons": seq,
            })
        if entries:
            out["stats"][key] = {"agg": agg, "label": label, "top": entries}

    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    size_mb = OUT.stat().st_size / 1e6
    print(f"wrote {OUT} ({size_mb:.2f} MB) | stats: {len(out['stats'])}")

    idx = json.loads((DATA / "players_index.json").read_text(encoding="utf-8"))
    for probe in ("receiving_yards", "passing_yards", "total_tds", "receiving_tds"):
        if probe in out["stats"]:
            names = [(e["id"], idx.get(e["id"], {}).get("n", "?"), e["total"]) for e in out["stats"][probe]["top"][:5]]
            print(probe, "->", ", ".join(f"{n} {t}" for _, n, t in names))


if __name__ == "__main__":
    main()
