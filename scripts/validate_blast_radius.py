"""
scripts/validate_blast_radius.py

Runs score_blast_radius() across all profiles in data/home_assistant_100prs.json
and prints a full breakdown:

  1. Distribution: count + % of multi_module vs small_or_local
  2. Average score per label
  3. Criterion breakdown for multi_module PRs:
       - Triggered by breadth ONLY  (substantive_modules > 1, churn ≤ 150)
       - Triggered by size ONLY     (substantive_modules ≤ 1, churn > 150)
       - Triggered by BOTH          (substantive_modules > 1, churn > 150)
  4. Top 5 highest-score multi_module PRs
  5. Size threshold calibration table (target: 35% multi_module)

Usage:
    python scripts/validate_blast_radius.py
    python scripts/validate_blast_radius.py --json      # machine-readable output
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scoring.blast_radius import (
    score_blast_radius,
    MULTI_MODULE_THRESHOLD,
    NON_SUBSTANTIVE_MODULES,
    SIZE_THRESHOLD,
)

INPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "home_assistant_100prs.json"


def _bar(value: int, total: int, width: int = 30) -> str:
    filled = int(round(value / total * width)) if total else 0
    return "█" * filled + "░" * (width - filled)


def main() -> None:
    json_mode = "--json" in sys.argv

    if not INPUT_PATH.exists():
        print(f"ERROR: {INPUT_PATH} not found. Run fetch_ha_core_100.py first.")
        sys.exit(1)

    profiles = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    total = len(profiles)

    # ------------------------------------------------------------------
    # Score every profile and collect detailed signals
    # ------------------------------------------------------------------
    results = []
    for p in profiles:
        score, label, modules, facts = score_blast_radius(p)
        churn = (p.get("additions") or 0) + (p.get("deletions") or 0)
        # Mirror the scorer's substantive-module filter so breakdown numbers
        # are consistent with what score_blast_radius actually decided.
        substantive = [m for m in modules if m not in NON_SUBSTANTIVE_MODULES]
        breadth_fired = len(substantive) > MULTI_MODULE_THRESHOLD
        size_fired = churn > SIZE_THRESHOLD
        results.append({
            "pr_number": p.get("pr_number"),
            "score": score,
            "label": label,
            "modules": modules,
            "substantive_modules": substantive,
            "churn": churn,
            "breadth_fired": breadth_fired,
            "size_fired": size_fired,
        })

    # ------------------------------------------------------------------
    # 1. Label distribution
    # ------------------------------------------------------------------
    label_counts: dict[str, int] = defaultdict(int)
    label_score_sum: dict[str, float] = defaultdict(float)
    for r in results:
        label_counts[r["label"]] += 1
        label_score_sum[r["label"]] += r["score"]

    # ------------------------------------------------------------------
    # 2. Criterion breakdown (multi_module only)
    # ------------------------------------------------------------------
    breadth_only  = sum(1 for r in results if r["label"] == "multi_module" and     r["breadth_fired"] and not r["size_fired"])
    size_only     = sum(1 for r in results if r["label"] == "multi_module" and not r["breadth_fired"] and     r["size_fired"])
    both          = sum(1 for r in results if r["label"] == "multi_module" and     r["breadth_fired"] and     r["size_fired"])
    multi_total   = label_counts["multi_module"]
    small_total   = label_counts["small_or_local"]

    # ------------------------------------------------------------------
    # Machine-readable output
    # ------------------------------------------------------------------
    if json_mode:
        out = {
            "total": total,
            "distribution": {k: {"count": v, "pct": round(v / total * 100, 1)} for k, v in label_counts.items()},
            "avg_score_per_label": {k: round(label_score_sum[k] / v, 2) for k, v in label_counts.items()},
            "multi_module_criterion_breakdown": {
                "breadth_only": breadth_only,
                "size_only": size_only,
                "both": both,
            },
        }
        print(json.dumps(out, indent=2))
        return

    # ------------------------------------------------------------------
    # Human-readable output
    # ------------------------------------------------------------------
    SEP = "─" * 58

    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║          Blast-Radius Validation Report              ║")
    print(f"║  Dataset : {INPUT_PATH.name:<42}║")
    print(f"║  Total PR: {total:<42}║")
    print("╚══════════════════════════════════════════════════════╝")
    print()

    # --- 1. Distribution ---
    print("1.  LABEL DISTRIBUTION")
    print(SEP)
    for lbl in ("multi_module", "small_or_local"):
        cnt = label_counts[lbl]
        pct = cnt / total * 100
        bar = _bar(cnt, total)
        print(f"  {lbl:<18}  {cnt:>3} PR  ({pct:5.1f}%)  {bar}")
    print()

    # --- 2. Average score ---
    print("2.  AVERAGE SCORE PER LABEL")
    print(SEP)
    for lbl in ("multi_module", "small_or_local"):
        cnt = label_counts[lbl]
        avg = label_score_sum[lbl] / cnt if cnt else 0.0
        print(f"  {lbl:<18}  avg score = {avg:.1f}")
    print()

    # --- 3. Criterion breakdown ---
    print("3.  CRITERION BREAKDOWN  (multi_module PRs only, total = {})".format(multi_total))
    print(f"    (breadth evaluated on substantive modules; excludes: {', '.join(sorted(NON_SUBSTANTIVE_MODULES))})")
    print(SEP)
    rows = [
        ("Breadth only  (substantive_modules > {}, churn ≤ {})".format(MULTI_MODULE_THRESHOLD, SIZE_THRESHOLD), breadth_only),
        ("Size only     (substantive_modules ≤ {}, churn > {})".format(MULTI_MODULE_THRESHOLD, SIZE_THRESHOLD), size_only),
        ("Both criteria (substantive_modules > {} AND churn > {})".format(MULTI_MODULE_THRESHOLD, SIZE_THRESHOLD), both),
    ]
    for desc, cnt in rows:
        pct = cnt / multi_total * 100 if multi_total else 0
        bar = _bar(cnt, multi_total) if multi_total else ""
        print(f"  {desc}")
        print(f"    → {cnt:>3} PR  ({pct:5.1f}%)  {bar}")
    print()

    # --- sanity check ---
    accounted = breadth_only + size_only + both
    if accounted != multi_total:
        print(f"  ⚠  Breakdown sum ({accounted}) ≠ multi_module total ({multi_total})")
    else:
        print(f"  ✓  Breakdown sums correctly to {multi_total} multi_module PR(s).")
    print()

    # --- top multi-module PRs ---
    top = sorted(
        [r for r in results if r["label"] == "multi_module"],
        key=lambda r: (r["score"], r["churn"]),
        reverse=True,
    )[:5]
    if top:
        print("4.  TOP 5 HIGHEST-SCORE multi_module PRs")
        print(SEP)
        print(f"  {'PR #':>7}  {'score':>5}  {'churn':>6}  modules")
        print(f"  {'─'*7}  {'─'*5}  {'─'*6}  {'─'*30}")
        for r in top:
            mods_str = ", ".join(r["modules"])[:50]
            print(f"  #{r['pr_number']:<6}  {r['score']:>5}  {r['churn']:>6}  {mods_str}")
        print()

    # --- 5. Size threshold calibration ---
    calibrate_size_threshold(profiles, total)


# ---------------------------------------------------------------------------
# Size threshold calibration
# ---------------------------------------------------------------------------

#: Candidate thresholds to evaluate (lines of churn).
CALIBRATION_CANDIDATES = [50, 100, 150, 200, 300, 400, 500, 750, 1000, 1500, 2000]

#: Target percentage of PRs that should be labelled multi_module.
#: 35% is chosen so the scorer flags a meaningful minority as high-blast-radius
#: without flooding reviewers with false positives on a typical active repo.
CALIBRATION_TARGET_PCT = 35.0


def calibrate_size_threshold(profiles: list[dict], total: int) -> None:
    """
    For each candidate size threshold, compute how many PRs would be labelled
    multi_module using the rule:
        multi_module  ←→  len(substantive_modules) > MULTI_MODULE_THRESHOLD
                          OR (additions + deletions) > candidate_threshold

    Prints a table sorted by |pct_multi - target| ascending, so the best
    candidate appears first.
    """
    SEP = "─" * 58

    # Pre-compute per-PR signals that are threshold-independent.
    precomputed = []
    for p in profiles:
        churn = (p.get("additions") or 0) + (p.get("deletions") or 0)
        mods: list[str] = list(p.get("modules_touched") or [])
        substantive = [m for m in mods if m not in NON_SUBSTANTIVE_MODULES]
        breadth_multi = len(substantive) > MULTI_MODULE_THRESHOLD
        precomputed.append({"churn": churn, "breadth_multi": breadth_multi})

    # Evaluate every candidate.
    rows = []
    for candidate in CALIBRATION_CANDIDATES:
        multi_count = sum(
            1 for pr in precomputed
            if pr["breadth_multi"] or pr["churn"] > candidate
        )
        pct = multi_count / total * 100
        delta = abs(pct - CALIBRATION_TARGET_PCT)
        rows.append({
            "threshold": candidate,
            "multi_count": multi_count,
            "pct": pct,
            "delta": delta,
        })

    # Sort by closeness to target (ascending delta), then by threshold (ascending).
    rows.sort(key=lambda r: (r["delta"], r["threshold"]))

    print("5.  SIZE THRESHOLD CALIBRATION  (target: {:.0f}% multi_module)".format(
        CALIBRATION_TARGET_PCT
    ))
    print(SEP)
    print(
        f"  {'threshold':>10}  {'multi_module':>12}  {'%':>6}  "
        f"{'|Δ from target|':>16}  note"
    )
    print(f"  {'─'*10}  {'─'*12}  {'─'*6}  {'─'*16}  {'─'*20}")

    current_marker = f"← current ({SIZE_THRESHOLD})"
    best_marked = False
    for r in rows:
        note = ""
        if r["threshold"] == SIZE_THRESHOLD:
            note = f"← current"
        if not best_marked and r == rows[0]:
            note = (note + "  ← BEST FIT").strip() if note else "← BEST FIT"
            best_marked = True
        print(
            f"  {r['threshold']:>10}  {r['multi_count']:>12}  "
            f"{r['pct']:>5.1f}%  {r['delta']:>15.1f}%  {note}"
        )
    print()


if __name__ == "__main__":
    main()
