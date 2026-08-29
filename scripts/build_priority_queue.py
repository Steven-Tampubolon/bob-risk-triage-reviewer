"""
scripts/build_priority_queue.py

Reads data/home_assistant_100prs.json, runs the full scoring pipeline
(score_blast_radius → score_security_policy → combine_priority) for every PR,
and writes the prioritised queue to output/priority_queue.json.

Output schema per PR:
    {
        "pr_number":          int,
        "blast_radius_label": str,   # "multi_module" | "small_or_local"
        "priority_score":     int,   # 0-100
        "priority_label":     str,   # "Low" | "Medium" | "High" | "Critical"
        "merge_blocker":      bool,
        "required_reviewer":  str | null
    }

The list is sorted by priority_score descending so the most urgent PRs
appear at the top.

Usage:
    python scripts/build_priority_queue.py
"""

import json
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scoring.blast_radius import score_blast_radius
from scoring.security_policy import score_security_policy
from priority.combine import combine_priority

INPUT_PATH  = Path(__file__).resolve().parent.parent / "data"  / "home_assistant_100prs.json"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "output" / "priority_queue.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    if not INPUT_PATH.exists():
        logger.error("Input file not found: %s", INPUT_PATH)
        sys.exit(1)

    profiles = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    logger.info("Loaded %d PR profiles from %s", len(profiles), INPUT_PATH.name)

    queue = []
    for p in profiles:
        br_result  = score_blast_radius(p)
        sec_result = score_security_policy(p)
        pri_score, pri_label = combine_priority(br_result, sec_result)

        queue.append({
            "pr_number":         p["pr_number"],
            "blast_radius_label": br_result[1],
            "priority_score":    pri_score,
            "priority_label":    pri_label,
            "merge_blocker":     sec_result[1],
            "required_reviewer": sec_result[0],
        })

    # Sort by priority_score descending; tie-break on pr_number ascending
    queue.sort(key=lambda r: (-r["priority_score"], r["pr_number"]))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(queue, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Priority queue saved to %s  (%d entries)", OUTPUT_PATH, len(queue))

    # Quick summary to console
    from collections import Counter
    label_dist = Counter(r["priority_label"] for r in queue)
    blockers   = sum(1 for r in queue if r["merge_blocker"])
    print()
    for lbl in ("Critical", "High", "Medium", "Low"):
        print(f"  {lbl:<10} {label_dist[lbl]:>3} PR")
    print(f"  {'merge_blocker':.<10} {blockers:>3} PR")
    print()


if __name__ == "__main__":
    main()
