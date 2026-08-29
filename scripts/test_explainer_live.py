"""
scripts/test_explainer_live.py

Picks 3 PRs from output/priority_queue.json (highest, median, lowest score),
looks up their full diff profiles in data/home_assistant_100prs.json, re-runs
the scoring pipeline, and calls call_explainer() — a LIVE watsonx.ai API call.

This script is intentionally NOT mocked.  Requires .env with:
    WATSONX_API_KEY=...
    WATSONX_URL=...
    WATSONX_PROJECT_ID=...

Usage:
    python scripts/test_explainer_live.py
"""

import json
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from scoring.blast_radius import score_blast_radius
from scoring.security_policy import score_security_policy
from priority.combine import combine_priority
from ai_layer.explainer import call_explainer

QUEUE_PATH   = Path(__file__).resolve().parent.parent / "output" / "priority_queue.json"
PROFILE_PATH = Path(__file__).resolve().parent.parent / "data"   / "home_assistant_100prs.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DIVIDER = "=" * 68


def pick_three(queue: list[dict]) -> list[dict]:
    """Return [highest-score, median-score, lowest-score] entries."""
    sorted_q = sorted(queue, key=lambda r: (-r["priority_score"], r["pr_number"]))
    high   = sorted_q[0]
    low    = sorted_q[-1]
    mid    = sorted_q[len(sorted_q) // 2]
    return [high, mid, low]


def main() -> None:
    for path in (QUEUE_PATH, PROFILE_PATH):
        if not path.exists():
            logger.error("Required file not found: %s", path)
            sys.exit(1)

    queue    = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    profiles = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))

    # Build a lookup by pr_number for O(1) access
    profile_by_number = {p["pr_number"]: p for p in profiles}

    selected = pick_three(queue)
    labels   = ["HIGHEST SCORE", "MEDIAN SCORE", "LOWEST SCORE"]

    print()
    print(DIVIDER)
    print("  Live Explainer Test — home-assistant/core × watsonx.ai (Granite)")
    print(DIVIDER)
    print()

    for rank_label, entry in zip(labels, selected):
        pr_number = entry["pr_number"]
        pr_data   = profile_by_number.get(pr_number)

        if pr_data is None:
            logger.warning("PR #%d not found in profiles — skipping.", pr_number)
            continue

        # Re-run pipeline to get full result tuples
        br_result  = score_blast_radius(pr_data)
        sec_result = score_security_policy(pr_data)
        pri_score, pri_label = combine_priority(br_result, sec_result)

        print(f"{'─' * 68}")
        print(f"  [{rank_label}]  PR #{pr_number}")
        print(f"{'─' * 68}")
        print(f"  priority_score   : {pri_score}")
        print(f"  priority_label   : {pri_label}")
        print(f"  blast_radius     : {br_result[1]}  (score {br_result[0]})")
        print(f"  merge_blocker    : {sec_result[1]}")
        print(f"  required_reviewer: {sec_result[0] or '–'}")
        print(f"  modules_touched  : {', '.join(pr_data.get('modules_touched', [])[:4])}")
        print()

        logger.info("Calling watsonx.ai for PR #%d ...", pr_number)
        explanation = call_explainer(
            pr_data        = pr_data,
            priority_result = (pri_score, pri_label),
            blast_radius_result = br_result,
            security_result     = sec_result,
        )

        print("  Penjelasan AI:")
        print()
        # Indent each line of the explanation for readability
        for line in explanation.strip().splitlines():
            print(f"    {line}")
        print()

    print(DIVIDER)
    print("  Done.")
    print(DIVIDER)
    print()


if __name__ == "__main__":
    main()
