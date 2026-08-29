"""
scripts/build_explained_queue.py

Reads output/priority_queue.json and data/home_assistant_100prs.json.
For every PR:
  1. Looks up the full diff profile by pr_number.
  2. Re-runs score_blast_radius + score_security_policy.
  3. Calls call_explainer() (live watsonx.ai API).
  4. Appends the 'explanation' field to the priority-queue entry.

Saves the merged result to output/explained_priority_queue.json.

At the end, prints:
  - Total PRs processed
  - PRs with direct AI response (no retry)
  - PRs that required at least one retry
  - PRs that fell back to the template (no AI text)
  - Total wall-clock execution time

Usage:
    python scripts/build_explained_queue.py

Requires .env with WATSONX_API_KEY, WATSONX_URL, WATSONX_PROJECT_ID.
"""

import json
import sys
import time
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from scoring.blast_radius import score_blast_radius
from scoring.security_policy import score_security_policy
from priority.combine import combine_priority
from ai_layer.explainer import (
    call_explainer,
    validate_explanation_consistency,
    _build_fallback_explanation,
    MAX_RETRIES,
)

QUEUE_PATH   = Path(__file__).resolve().parent.parent / "output" / "priority_queue.json"
PROFILE_PATH = Path(__file__).resolve().parent.parent / "data"   / "home_assistant_100prs.json"
OUTPUT_PATH  = Path(__file__).resolve().parent.parent / "output" / "explained_priority_queue.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Fallback text is always built from the same helper; check its prefix
_FALLBACK_PREFIX = "PR #"   # unique prefix of _build_fallback_explanation output


def _classify_response(
    explanation: str,
    pr_data: dict,
    priority_result: tuple,
    blast_radius_result: tuple,
    security_result: tuple,
) -> str:
    """
    Return 'direct', 'retry', or 'fallback' for the explanation origin.

    We can't directly count retries from outside call_explainer, so we use a
    heuristic: call validate_explanation_consistency on the first-pass result
    independently and compare to the actual explanation.

    A simpler approach: generate a fallback string and see if the explanation
    matches it (fallback), otherwise consider it AI-generated. We can't
    distinguish direct vs retry from outside the function — for stats purposes
    we tag everything non-fallback as 'ai_direct' and rely on the logged
    retries shown in stderr.
    """
    fallback = _build_fallback_explanation(
        pr_data, priority_result, blast_radius_result, security_result
    )
    if explanation.strip() == fallback.strip():
        return "fallback"
    return "ai"


def main() -> None:
    for path in (QUEUE_PATH, PROFILE_PATH):
        if not path.exists():
            logger.error("Required file not found: %s", path)
            sys.exit(1)

    queue    = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    profiles = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    profile_by_number = {p["pr_number"]: p for p in profiles}

    total = len(queue)
    logger.info("Processing %d PRs from %s ...", total, QUEUE_PATH.name)

    # --- stats counters ---
    n_ai        = 0   # got an AI explanation (no retry observed externally)
    n_fallback  = 0   # fell back to template
    n_error     = 0   # profile not found or unexpected exception

    explained_queue = []
    wall_start = time.time()

    for idx, entry in enumerate(queue, start=1):
        pr_number = entry["pr_number"]
        pr_data   = profile_by_number.get(pr_number)

        if pr_data is None:
            logger.warning("[%d/%d] PR #%d not found in profiles — skipping.", idx, total, pr_number)
            n_error += 1
            continue

        br_result  = score_blast_radius(pr_data)
        sec_result = score_security_policy(pr_data)
        pri_result = combine_priority(br_result, sec_result)

        logger.info("[%d/%d] Calling explainer for PR #%d ...", idx, total, pr_number)
        try:
            explanation = call_explainer(
                pr_data             = pr_data,
                priority_result     = pri_result,
                blast_radius_result = br_result,
                security_result     = sec_result,
            )
        except Exception as exc:
            logger.error("[%d/%d] PR #%d explainer raised: %s", idx, total, pr_number, exc)
            explanation = _build_fallback_explanation(pr_data, pri_result, br_result, sec_result)
            n_error += 1

        origin = _classify_response(explanation, pr_data, pri_result, br_result, sec_result)
        if origin == "fallback":
            n_fallback += 1
        else:
            n_ai += 1

        explained_queue.append({**entry, "explanation": explanation})

    wall_elapsed = time.time() - wall_start

    # --- save output ---
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(explained_queue, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Saved %d entries to %s", len(explained_queue), OUTPUT_PATH)

    # --- final stats ---
    print()
    print("=" * 62)
    print("  Build Explained Queue — Summary")
    print("=" * 62)
    print(f"  Total PRs processed      : {total}")
    print(f"  AI explanation (direct)  : {n_ai}   (no retry needed or retried & succeeded)")
    print(f"  Fallback to template     : {n_fallback}   (all retries exhausted or no credentials)")
    print(f"  Skipped (profile missing): {n_error}")
    print(f"  Total wall-clock time    : {wall_elapsed:.1f}s  "
          f"({wall_elapsed / total:.1f}s avg/PR)")
    print("=" * 62)
    print()


if __name__ == "__main__":
    main()
