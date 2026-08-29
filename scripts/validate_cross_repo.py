"""
scripts/validate_cross_repo.py

Runs the full scoring pipeline on data/vscode_100prs.json:
    diff_profile → score_blast_radius → score_security_policy → combine_priority

Prints:
  1. Blast-radius label distribution (multi_module vs small_or_local)
  2. Average priority_score per blast-radius label
  3. Priority label distribution (Low / Medium / High / Critical)
     + count of PRs where merge_blocker=True
  4. Cross-repo comparison: does multi_module have higher avg priority_score
     than small_or_local? (validates the pattern found on home-assistant/core)

Usage:
    python scripts/validate_cross_repo.py
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scoring.blast_radius import score_blast_radius
from scoring.security_policy import score_security_policy
from priority.combine import combine_priority

INPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "vscode_100prs.json"

# Home-assistant/core Day-1 reference numbers (for comparison text)
HA_AVG_PRIORITY = {
    "multi_module":   None,   # computed below for narrative
    "small_or_local": None,
}
HA_MULTI_PCT = 36.0   # from validate_blast_radius.py run on HA data


def _bar(value: int, total: int, width: int = 30) -> str:
    filled = int(round(value / total * width)) if total else 0
    return "█" * filled + "░" * (width - filled)


def main() -> None:
    if not INPUT_PATH.exists():
        print(f"ERROR: {INPUT_PATH} not found. Run fetch_vscode_100.py first.")
        sys.exit(1)

    profiles = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    total = len(profiles)
    SEP = "─" * 62

    # ------------------------------------------------------------------
    # Run pipeline for every PR
    # ------------------------------------------------------------------
    records = []
    for p in profiles:
        br_result = score_blast_radius(p)
        sec_result = score_security_policy(p)
        pri_score, pri_label = combine_priority(br_result, sec_result)

        br_score, br_label = br_result[0], br_result[1]
        reviewer, merge_blocker, sec_reasons = sec_result

        records.append({
            "pr_number":     p.get("pr_number"),
            "br_score":      br_score,
            "br_label":      br_label,
            "merge_blocker": merge_blocker,
            "pri_score":     pri_score,
            "pri_label":     pri_label,
            "sec_reasons":   sec_reasons,
        })

    # ------------------------------------------------------------------
    # 1. Blast-radius label distribution
    # ------------------------------------------------------------------
    br_counts: dict[str, int] = defaultdict(int)
    br_score_sum: dict[str, float] = defaultdict(float)
    br_pri_sum: dict[str, float] = defaultdict(float)
    for r in records:
        br_counts[r["br_label"]] += 1
        br_score_sum[r["br_label"]] += r["br_score"]
        br_pri_sum[r["br_label"]] += r["pri_score"]

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║        Cross-Repo Validation — microsoft/vscode          ║")
    print(f"║  Dataset : {INPUT_PATH.name:<48}║")
    print(f"║  Total PR: {total:<48}║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    print("1.  BLAST-RADIUS LABEL DISTRIBUTION")
    print(SEP)
    for lbl in ("multi_module", "small_or_local"):
        cnt = br_counts[lbl]
        pct = cnt / total * 100
        bar = _bar(cnt, total)
        print(f"  {lbl:<18}  {cnt:>3} PR  ({pct:5.1f}%)  {bar}")
    print()

    # ------------------------------------------------------------------
    # 2. Average priority_score per blast-radius label
    # ------------------------------------------------------------------
    print("2.  AVERAGE priority_score PER BLAST-RADIUS LABEL")
    print(SEP)
    avg_by_br: dict[str, float] = {}
    for lbl in ("multi_module", "small_or_local"):
        cnt = br_counts[lbl]
        avg = br_pri_sum[lbl] / cnt if cnt else 0.0
        avg_by_br[lbl] = avg
        print(f"  {lbl:<18}  avg priority_score = {avg:.1f}")
    print()

    # ------------------------------------------------------------------
    # 3. Priority label distribution + merge_blocker count
    # ------------------------------------------------------------------
    pri_counts: dict[str, int] = defaultdict(int)
    merge_blocker_count = sum(1 for r in records if r["merge_blocker"])
    for r in records:
        pri_counts[r["pri_label"]] += 1

    print("3.  PRIORITY LABEL DISTRIBUTION")
    print(SEP)
    for lbl in ("Critical", "High", "Medium", "Low"):
        cnt = pri_counts[lbl]
        pct = cnt / total * 100
        bar = _bar(cnt, total)
        print(f"  {lbl:<10}  {cnt:>3} PR  ({pct:5.1f}%)  {bar}")
    print()
    print(f"  merge_blocker = True  :  {merge_blocker_count} PR  "
          f"({merge_blocker_count / total * 100:.1f}%)")
    print()

    # ------------------------------------------------------------------
    # 4. Cross-repo comparison narrative
    # ------------------------------------------------------------------
    avg_multi  = avg_by_br.get("multi_module", 0.0)
    avg_small  = avg_by_br.get("small_or_local", 0.0)
    multi_pct  = br_counts["multi_module"] / total * 100

    print("4.  CROSS-REPO COMPARISON  (vscode vs home-assistant/core)")
    print(SEP)

    # Pattern check: multi_module > small_or_local in priority_score?
    pattern_holds = avg_multi > avg_small
    pattern_word  = "HOLDS" if pattern_holds else "does NOT hold"
    diff = avg_multi - avg_small

    print(f"  vscode multi_module avg priority_score   : {avg_multi:.1f}")
    print(f"  vscode small_or_local avg priority_score : {avg_small:.1f}")
    print(f"  Difference (multi − small)               : {diff:+.1f} pts")
    print()
    print(
        f"  Pattern 'multi_module > small_or_local in priority_score' "
        f"→ {pattern_word}."
    )
    print()
    print(f"  Blast-radius distribution comparison:")
    print(f"    home-assistant/core  multi_module : {HA_MULTI_PCT:.0f}%")
    print(f"    microsoft/vscode     multi_module : {multi_pct:.1f}%")

    if multi_pct > HA_MULTI_PCT:
        delta = multi_pct - HA_MULTI_PCT
        print(f"    → vscode has MORE multi_module PRs (+{delta:.1f} pp).")
        print(f"      vscode's monolithic src/ structure means more PRs")
        print(f"      trigger the size criterion (churn > 500 lines).")
    elif multi_pct < HA_MULTI_PCT:
        delta = HA_MULTI_PCT - multi_pct
        print(f"    → vscode has FEWER multi_module PRs (-{delta:.1f} pp).")
    else:
        print(f"    → Distribution is identical across both repos.")

    print()
    if pattern_holds:
        print(
            "  ✓ Consistent finding across both repos: multi_module PRs\n"
            "    carry higher priority scores than small_or_local PRs.\n"
            "    This validates that blast-radius is a reliable predictor\n"
            "    of review priority independent of the repo's tech stack."
        )
    else:
        print(
            "  ✗ Pattern does not hold for vscode. Investigate whether\n"
            "    the size threshold (500 lines) needs repo-specific tuning."
        )
    print()


if __name__ == "__main__":
    main()
