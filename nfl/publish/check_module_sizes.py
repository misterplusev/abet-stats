"""LOC guard for the modular MLB stats code.

Policy: target <=400 lines/file; 400-1000 allowed with reason; >1000 fails unless allowlisted.
Run: python scripts/publish/check_module_sizes.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET_DIRS = [
    ROOT / "src" / "lib" / "mlb",
    ROOT / "src" / "statsui",
    ROOT / "src" / "widgets" / "mlbstats",
    ROOT / "scripts" / "publish",
]
PATTERNS = ("*.js", "*.jsx", "mlb_stats_export.py", "mlb_*.py", "check_module_sizes.py")
WARN = 400
FAIL = 1000
ALLOWLIST = set()  # e.g. {"src/widgets/mlbstats/labs/Quadrant3D.jsx"}


def line_count(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return 0


def main() -> int:
    found = set()
    for base in TARGET_DIRS:
        if not base.exists():
            continue
        for pattern in PATTERNS:
            for path in sorted(base.rglob(pattern)):
                if path.is_file():
                    found.add(path)
    rows = sorted(((line_count(p), p.relative_to(ROOT).as_posix()) for p in found), reverse=True)

    failures = []
    for lines, rel in rows:
        tag = ""
        if lines > FAIL and rel not in ALLOWLIST:
            tag = "FAIL"
            failures.append(rel)
        elif lines > WARN:
            tag = "warn"
        print(f"{lines:5d} {tag:4s} {rel}")

    total = sum(lines for lines, _ in rows)
    print(f"\n{len(rows)} files | {total:,} lines | fail>{FAIL}: {len(failures)}")
    if failures:
        print("Over-budget files (add a justification or split):")
        for rel in failures:
            print(f"  - {rel}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
