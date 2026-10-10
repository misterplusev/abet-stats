"""Build widget_inventory.json — every top-level piece of the NFL Stats widget tree.

Parses top-level declarations (components/functions/consts) from the root monolith and from
every extracted module, assigns each a target silo from the decomposition plan
(docs/20261002_163000_..._WIDGET_DECOMPOSITION_PLAN), and reports line coverage so nothing
falls out of the refactor silently. Consumed by the Factory "Code map" three.js scene, the
proof page, and verify_data.py.

Usage: python scripts/publish/build_widget_inventory.py
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
OUT = ROOT / "public" / "nfl-stats" / "data" / "widget_inventory.json"

MONOLITH = SRC / "widgets" / "NFLStatsWidget.jsx"

SILOS = {
    "shell": ("Shell", "#FDB515"),
    "core": ("Core", "#3B7DD8"),
    "ui": ("UI primitives", "#8A9BB0"),
    "charts": ("Charts", "#00A86B"),
    "features/progression": ("Progression", "#FF4D6D"),
    "features/table": ("Table", "#4DD0E1"),
    "features/career": ("Career", "#FF6B35"),
    "features/records": ("Records", "#B45BFF"),
    "features/playerCard": ("Player card", "#F48FB1"),
    "features/radar": ("Radar", "#7CFF6B"),
    "features/plays": ("Game Center", "#FFD166"),
    "features/models": ("Models", "#00C2FF"),
    "features/betting": ("Betting", "#FF8A00"),
    "features/quadrant3d": ("3D Lab", "#E879F9"),
    "features/factory": ("Factory", "#94A3B8"),
}

MONOLITH_SILO = {
    "W": "core", "H": "core", "TOP": "core", "BOTTOM": "core",
    "MODES": "core", "POS_ORDER": "core", "DIVISIONS": "core",
    "readUrlState": "core",
    "frameFor": "charts", "niceStep": "charts", "niceTicks": "charts",
    "rankScaleOf": "charts", "valueScaleOf": "charts", "useContainerSize": "charts",
    "buildTip": "charts", "ChartAxes": "charts",
    "CompareCell": "features/progression",
    "BumpChart": "charts", "LineChart": "charts", "RadarChart": "charts",
    "TableView": "features/table",
    "CareerTable": "features/career", "CareerChart": "features/career",
    "CareerPanel": "features/career", "AllTimeLeaders": "features/career",
    "PlayerCard": "features/playerCard",
    "defaultThreshold": "features/records", "defaultMilestone": "features/records",
    "RecordsPanel": "features/records",
    "PLAY_TYPE_LABELS": "features/plays", "GameTimeline": "features/plays", "PlaysPanel": "features/plays",
    "DRIVER_COLORS": "features/models", "DriverTrendChart": "features/models",
    "ConvergenceChart": "features/models", "FACTOR_DEFS": "features/models",
    "STAT_TERMS": "features/models", "CorrMatrix": "features/models",
    "R2BarChart": "features/models", "WxepaQuadrant": "features/models",
    "ModelMarketScatter": "features/models", "ModelsPanel": "features/models",
    "PROP_STATS": "features/betting", "PropHistogram": "features/betting", "BettingPanel": "features/betting",
    "NFLStatsWidget": "shell",
}

EXTRACTED_FILES = [
    ("src/widgets/AbetChipLoader.jsx", "ui"),
    ("src/lib/nflStats.js", "core"),
    ("src/lib/nflParquet.js", "core"),
    ("src/lib/nflModels.js", "core"),
    ("src/lib/chartExport.js", "core"),
]

PAT_FUNC = re.compile(r"^(?:export default |export )?function ([A-Za-z0-9_]+)\s*\(")
PAT_CONST = re.compile(r"^(?:export )?const ([A-Za-z0-9_]+)\s*=")


def parse_decls(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    found = []
    for i, line in enumerate(lines):
        m = PAT_FUNC.match(line)
        kind = "function"
        if not m:
            m = PAT_CONST.match(line)
            kind = "const"
        if m:
            found.append({"name": m.group(1), "kind": kind, "start": i + 1})
    for i, d in enumerate(found):
        d["end"] = found[i + 1]["start"] - 1 if i + 1 < len(found) else len(lines)
        d["lines"] = d["end"] - d["start"] + 1
    return found, len(lines)


def main():
    nodes = []

    decls, monolith_lines = parse_decls(MONOLITH)
    unmapped = [d["name"] for d in decls if d["name"] not in MONOLITH_SILO]
    if decls and decls[0]["start"] > 1:
        nodes.append({
            "name": "(imports + header)", "kind": "header", "file": "src/widgets/NFLStatsWidget.jsx",
            "start": 1, "end": decls[0]["start"] - 1, "lines": decls[0]["start"] - 1,
            "silo": "shell", "status": "inline",
        })
    for d in decls:
        nodes.append({
            "name": d["name"], "kind": d["kind"], "file": "src/widgets/NFLStatsWidget.jsx",
            "start": d["start"], "end": d["end"], "lines": d["lines"],
            "silo": MONOLITH_SILO.get(d["name"], "unmapped"), "status": "inline",
        })
    header_lines = decls[0]["start"] - 1 if decls else 0
    covered = header_lines + sum(d["lines"] for d in decls)
    coverage = round(covered / monolith_lines * 100, 1)

    scan = list(EXTRACTED_FILES)
    for p in sorted((SRC / "nflstats").rglob("*.jsx")) + sorted((SRC / "nflstats").rglob("*.js")):
        rel = p.relative_to(ROOT).as_posix()
        if rel.endswith("index.js"):
            continue
        if p.parent.name == "ui":
            silo = "ui"
        elif p.parent.name == "charts":
            silo = "charts"
        elif p.parent.parent.name == "features":
            silo = f"features/{p.parent.name}"
        else:
            silo = "core"
        scan.append((rel, silo))

    seen = set()
    for rel, silo in scan:
        if rel in seen:
            continue
        seen.add(rel)
        path = ROOT / rel
        if not path.exists():
            continue
        decls, total = parse_decls(path)
        if decls:
            for d in decls:
                nodes.append({
                    "name": d["name"], "kind": d["kind"], "file": rel,
                    "start": d["start"], "end": d["end"], "lines": d["lines"],
                    "silo": silo, "status": "extracted",
                })
        else:
            nodes.append({"name": path.stem, "kind": "file", "file": rel, "lines": total, "silo": silo, "status": "extracted"})

    silo_totals = {}
    for n in nodes:
        s = silo_totals.setdefault(n["silo"], {"lines": 0, "nodes": 0, "inline": 0, "extracted": 0})
        s["lines"] += n["lines"]
        s["nodes"] += 1
        s["inline" if n["status"] == "inline" else "extracted"] += 1

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "src/widgets/NFLStatsWidget.jsx",
        "source_lines": monolith_lines,
        "coverage_pct": coverage,
        "unmapped": unmapped,
        "silos": [
            {"id": sid, "label": SILOS.get(sid, (sid, "#888888"))[0], "color": SILOS.get(sid, (sid, "#888888"))[1], **silo_totals.get(sid, {"lines": 0, "nodes": 0, "inline": 0, "extracted": 0})}
            for sid in SILOS
        ],
        "nodes": nodes,
    }
    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    inline = sum(1 for n in nodes if n["status"] == "inline")
    extracted = sum(1 for n in nodes if n["status"] == "extracted")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
    print(f"monolith: {monolith_lines} lines | coverage {coverage}% | unmapped: {unmapped or 'none'}")
    print(f"nodes: {len(nodes)} ({inline} inline / {extracted} extracted) | silos: {len([s for s in out['silos'] if s['nodes']])}")


if __name__ == "__main__":
    main()
