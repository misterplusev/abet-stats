"""Build stat_docs.json — descriptions, exact formulas, variables for every stat.

Curated entries for the important stats; template-generated entries for the long
tail. Consumed by the Stat Info panel and Catalog browser in NFLStatsWidget.
"""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent.parent / "public" / "nfl-stats" / "data"

VAR = {
    "C": "completions",
    "A": "pass attempts",
    "Y": "passing yards",
    "TD": "touchdowns",
    "INT": "interceptions thrown",
    "AY": "air yards on the throw",
    "p_hat": "model-predicted completion probability for each attempt (nflfastR)",
    "EPA": "expected points added on the play (nflfastR)",
    "n": "number of games/attempts in the sample",
    "x_i": "value in game/week i",
    "T": "team total for the season to date",
}

CURATED = {
    "player:passing_yards": {
        "desc": "Total passing yards thrown, as charted by nflverse from play-by-play. Includes yards gained in the air and after the catch on completed passes; excludes sack yardage (sacks are charged as negative pass plays under the passer's EPA, not as passing yards).",
        "formula": "passing_yards = Σ yards_gained on completed passes",
        "vars": {"yards_gained": "nflfastR field: yards gained on the pass play"},
    },
    "player:passing_epa": {
        "desc": "Total expected points added on pass plays attributed to this passer. EPA measures how much a play changed the expected points of the drive versus an average play from the same situation (down, distance, field position, time). Summed here — for per-play value divide by attempts.",
        "formula": "passing_EPA = Σ EPA_i over pass attempts",
        "vars": {"EPA_i": "expected points added on attempt i (nflfastR model on down, distance, yardline, time, score)"},
    },
    "player:passing_cpoe": {
        "desc": "Completion Percentage Over Expected: how much better (or worse) a passer completed passes than an average QB would on the same throws. Positive = more accurate than expected given throw difficulty.",
        "formula": "CPOE = C/A − (Σ p̂_i)/A",
        "vars": {"C": VAR["C"], "A": VAR["A"], "p̂_i": VAR["p_hat"]},
        "notes": "nflverse reports CPOE per game; this chart's cumulative line is the running mean of weekly CPOE. Requires 100+ attempts to be meaningful — use the Qualify control.",
    },
    "player:pacr": {
        "desc": "Passing Air Conversion Ratio: passing yards per air yard. Above 1.0 means the receiver room is adding yards after the catch on top of the throw.",
        "formula": "PACR = Y / AY",
        "vars": {"Y": VAR["Y"], "AY": VAR["AY"]},
    },
    "player:racr": {
        "desc": "Receiver Air Conversion Ratio: receiving yards per air yard targeted. Measures how efficiently a receiver turns target depth into total yards (separation + YAC).",
        "formula": "RACR = receiving_yards / receiving_air_yards",
        "vars": {"receiving_yards": "yards gained on receptions", "receiving_air_yards": "depth of target beyond the line of scrimmage"},
    },
    "player:passing_air_yards": {
        "desc": "Total depth of target on all pass attempts (sum of air yards), regardless of completion.",
        "formula": "air_yards = Σ depth_of_target_i",
        "vars": {"depth_of_target_i": "yards from the line of scrimmage to the catch point on attempt i"},
    },
    "player:passing_yards_after_catch": {
        "desc": "Yards gained after the catch on this passer's completions (credited to the passer's ledger; also visible from the receiver side).",
        "formula": "passing_YAC = Σ yards_gained − air_yards per completion",
        "vars": {"yards_gained": "total yards on the completion", "air_yards": "depth of target"},
    },
    "player:passing_cpoe_note": None,
    "player:target_share": {
        "desc": "Share of the team's pass attempts that targeted this player while he was on the field (team attempts as denominator per nflverse).",
        "formula": "target_share = targets / team_pass_attempts",
        "vars": {"targets": "passes thrown in the player's direction", "team_pass_attempts": "total pass attempts by the team"},
    },
    "player:air_yards_share": {
        "desc": "Share of the team's total air yards targeted to this player — a volume-weighted depth measure.",
        "formula": "air_yards_share = player_air_yards / team_air_yards",
        "vars": {"player_air_yards": "sum of depth of target", "team_air_yards": "team total air yards"},
    },
    "player:wopr": {
        "desc": "Weighted Opportunity Rating: a single number blending target volume and target depth — the standard 'how much does the offense feature this receiver' metric.",
        "formula": "WOPR = 1.5 × target_share + 0.7 × air_yards_share",
        "vars": {"target_share": "see target share", "air_yards_share": "see air-yards share"},
        "notes": "Constants 1.5 and 0.7 are the standard nflfastR weightings.",
    },
    "player:def_tackles_total": {
        "desc": "Total tackles = solo tackles + assisted tackles. NOTE: nflverse weekly/season files report solo and assist counts separately; we derive the total as solo + assists, which was validated to best match official season totals (official attribution differs slightly by scorer).",
        "formula": "tackles_total = solo + assists",
        "vars": {"solo": "unassisted tackles", "assists": "assisted tackles (def_tackle_assists)"},
    },
    "player:def_sacks": {
        "desc": "Sacks recorded by the defender (0.5 credited on shared sacks where charted).",
        "formula": "sacks = Σ sack events credited",
        "vars": {},
    },
    "player:def_interceptions": {
        "desc": "Interceptions caught by the defender.",
        "formula": "ints = count of interception events",
        "vars": {},
    },
    "player:def_passer_rating_allowed": {
        "desc": "NFL passer rating allowed when targeting the receiver this defender covers — lower is better.",
        "formula": "PR = (a + b + c + d)/6 × 100, with a = (C/A − 0.3)×5, b = (Y/A − 3)×0.25, c = TD/A×20, d = 2.375 − INT/A×25 (each clamped 0–2.375)",
        "vars": {"C": "completions allowed", "A": "targets in coverage", "Y": "yards allowed", "TD": "TDs allowed", "INT": "interceptions by this defender"},
    },
    "player:rushing_yards_after_contact": {
        "desc": "Yards gained after first contact by the rusher (Pro Football Reference charting). Requires PFR data — available 2018+.",
        "formula": "YAC = Σ yards after contact per carry",
        "vars": {"carry": "rushing attempt"},
        "notes": "Source: pfr_advstats weekly rush file.",
    },
    "player:rushing_yards_after_contact_avg": {
        "desc": "Yards after contact per rushing attempt.",
        "formula": "YAC/att = rushing_yards_after_contact / carries",
        "vars": {"carries": "rushing attempts"},
    },
    "player:fumbles_total": {
        "desc": "Total fumbles (lost or recovered) charged to the player.",
        "formula": "fumbles = rushing + receiving + sack fumbles",
        "vars": {},
    },
    "player:fantasy_points": {
        "desc": "Standard (non-PPR) fantasy points, as computed by nflverse.",
        "formula": "FP = 0.04×pass_yds + 4×pass_td − 2×INT + 0.1×(rush_yds + rec_yds) + 6×(rush_td + rec_td) + 2×(2pt) − 2×(fumbles lost)",
        "vars": {"pass_yds": "passing yards", "INT": "interceptions", "2pt": "two-point conversions"},
    },
    "player:fantasy_points_ppr": {
        "desc": "PPR fantasy points = standard + 1 point per reception.",
        "formula": "FP_ppr = FP_standard + receptions",
        "vars": {"receptions": "catches"},
    },
    "team:points_for": {
        "desc": "Points scored by the team (from final scores in the nflverse schedule file, not play-by-play reconstruction).",
        "formula": "points_for = Σ final_score over games",
        "vars": {},
    },
    "team:points_against": {
        "desc": "Points allowed by the team, from final scores.",
        "formula": "points_against = Σ opponent_final_score over games",
        "vars": {},
    },
    "team:point_diff": {
        "desc": "Scoring differential = points for − points against.",
        "formula": "diff = Σ (own_score − opp_score)",
        "vars": {},
    },
    "team:wins": {
        "desc": "Wins, counting ties as half a win.",
        "formula": "wins = count(score > opp) + 0.5 × count(score = opp)",
        "vars": {},
    },
    "team:plays": {
        "desc": "Offensive plays run (pass + rush attempts with a play, excluding penalties/kneels per nflfastR play flags).",
        "formula": "plays = count of scrimmage plays with posteam = team",
        "vars": {},
    },
    "team:epa_per_play": {
        "desc": "Expected points added per offensive play. EPA uses the nflfastR expected-points model: how many points the drive-state change was worth versus average from the same situation.",
        "formula": "EPA/play = (Σ EPA_i) / plays",
        "vars": {"EPA_i": "expected points added on play i"},
        "notes": "Available 2024+ in our bundles (play-by-play derived); EPA itself models well from 2006+ in nflfastR.",
    },
    "team:success_rate": {
        "desc": "Share of plays that were 'successful' by nflfastR's success definition.",
        "formula": "success = 1 if (1st down: gain ≥ 40% of needed; 2nd: ≥ 60%; 3rd/4th: ≥ 100% or first down/TD), else 0; rate = Σ success / plays",
        "vars": {"needed": "yards to go for a first down"},
    },
    "team:pass_rate": {
        "desc": "Share of offensive plays that were pass attempts.",
        "formula": "pass_rate = pass_plays / plays",
        "vars": {},
    },
    "team:turnovers": {
        "desc": "Giveaways = lost fumbles + interceptions thrown.",
        "formula": "turnovers = fumbles_lost + interceptions",
        "vars": {},
    },
    "team:explosive": {
        "desc": "Explosive plays: gains of 20+ yards.",
        "formula": "explosive = count(yards_gained ≥ 20)",
        "vars": {},
    },
    "team:third_down_rate": {
        "desc": "Third-down conversion rate.",
        "formula": "rate = third_converted / (third_converted + third_failed)",
        "vars": {},
    },
    "team:fourth_down_rate": {
        "desc": "Fourth-down conversion rate.",
        "formula": "rate = fourth_converted / (fourth_converted + fourth_failed)",
        "vars": {},
    },
}


GENERIC_CODE = """// How this stat is computed in this app
// 1) Exporter precomputes weekly values from the nflverse parquet column:
//    stats_player_week_{season}.parquet (players) / stats_team_week_{season}.parquet (teams)
weekly[w] = SUM(rows["{key}"])                 # null/NaN weeks skipped
// 2) Cumulative curve (src/lib/nflStats.js -> runningAccumulate):
cum[w]    = cum[w-1] + weekly[w]               # sum stats
cum[w]    = acc / games_seen                   # mean/rate stats
// 3) Ranks (exporter, pandas):
rank_week[w] = pivot[w].rank(ascending=False, method="min")   # all entities
rank_cum[w]  = run[w].rank(ascending=False, method="min")
// 4) Client renders entry.v (weekly), entry.r (cum rank), entry.wr (week rank)"""

CODE_OVERRIDES = {
    "player:passing_cpoe": """// nflverse ships passing_cpoe per game; the model grades each attempt:
# For every pass attempt i: p_hat_i = P(complete | air yards, pressure, separation...)
cpoe_game = completions/attempts - SUM(p_hat_i)/attempts
# Chart line for rate stats = running MEAN across games played
cum[w] = (SUM cpoe_game[0..w]) / games_seen[w]""",
    "player:wopr": """target_share  = targets / team_attempts
air_yards_share = receiving_air_yards / team_air_yards
wopr = 1.5 * target_share + 0.7 * air_yards_share""",
    "player:def_tackles_total": """// nflverse weekly files report solo + assist columns separately.
// We derive the official-style total (validated vs season totals):
solo   = row["def_tackles_solo"]
assist = row["def_tackle_assists"]        # nflverse assist column
tackles_total = solo + assist             # our derived field in add_derived_stats()
# alt column def_tackles_with_assist is a different charting subset - not used""",
    "team:epa_per_play": """// From play-by-play (pbp/play_by_play_{season}.parquet), REG only:
plays = COUNT(play WHERE posteam = team)
epa_sum = SUM(epa)                         # nflfastR EP model per play
epa_per_play = epa_sum / plays""",
    "player:passing_epa": """// Sum of nflfastR expected points added on this passer's attempts:
passing_epa = SUM(epa WHERE play is a pass by this player)
# EPA(play) = EP(after) - EP(before), EP from the nflfastR down/distance/field model""",
}


def auto_doc(key, label, group, fmt, agg, source, qualifier):
    if agg == "mean":
        desc = f"{label}: per-game average across the player's games in the season (nflverse weekly data, '{key}' field)."
        formula = "x̄ = (Σ x_i) / n"
        vars_ = {"x_i": VAR["x_i"], "n": "games with a recorded value"}
    else:
        desc = f"{label}: season {('sum' if fmt == 'i0' else 'value')} accumulated from the nflverse weekly '{key}' field." if fmt != "i0" else f"{label}: season total accumulated from the nflverse weekly '{key}' field."
        formula = "total = Σ x_i"
        vars_ = {"x_i": "value recorded in week i (weeks with no game are skipped)"}
    if group.startswith("Times"):
        formula = "total = count of charted events"
    notes = None
    if source.startswith("pfr"):
        notes = "Pro Football Reference advanced charting — available from the 2018 season onward."
    if qualifier:
        notes = (notes + " " if notes else "") + f"Qualify gate: {qualifier['by']} ≥ {qualifier['min']} (adjustable)."
    return {"desc": desc, "formula": formula, "vars": vars_, "notes": notes, "auto": True}


def main():
    catalog = json.loads((DATA / "catalog.json").read_text(encoding="utf-8"))
    sources = catalog.get("stat_sources", {})
    qualifiers = catalog.get("qualifiers", {})
    docs = {"player": {}, "team": {}, "variables": VAR, "updated": catalog.get("generated_at")}

    for level, groups_key in (("player", "player_groups"), ("team", "team_groups")):
        for group in catalog.get(groups_key, []):
            for stat in group["stats"]:
                key = stat["key"]
                doc_key = f"{level}:{key}"
                curated = CURATED.get(doc_key)
                src = (sources.get(level) or {}).get(key, "")
                q = qualifiers.get(key) if level == "player" else None
                entry = {
                    "label": stat["label"],
                    "group": group["group"],
                    "agg": stat.get("agg", "sum"),
                    "fmt": stat.get("fmt", "i0"),
                    "source": src,
                    "qualifier": q,
                }
                if curated:
                    entry.update({
                        "desc": curated["desc"],
                        "formula": curated["formula"],
                        "vars": curated.get("vars", {}),
                        "notes": curated.get("notes"),
                    })
                else:
                    entry.update(auto_doc(key, stat["label"], group["group"], entry["fmt"], entry["agg"], src, q))
                entry["code"] = CODE_OVERRIDES.get(doc_key, GENERIC_CODE.replace("{key}", key))
                docs[level][key] = entry

    out = DATA / "stat_docs.json"
    out.write_text(json.dumps(docs, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    n = len(docs["player"]) + len(docs["team"])
    print(f"stat_docs: {len(docs['player'])} player + {len(docs['team'])} team = {n} docs, {out.stat().st_size/1024:.0f} KB")


if __name__ == "__main__":
    main()
