"""
scripts/fetch_ha_core_sample.py

Fetches 5 merged PRs from home-assistant/core between 2026-03-01 and 2026-08-27,
builds a diff profile for each, prints to console as JSON, and saves to
data/sample_5_prs.json.

Requires GITHUB_TOKEN in .env (or environment).

Usage:
    python scripts/fetch_ha_core_sample.py
"""

import json
import os
import sys
import logging
from pathlib import Path

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from ingestion.github_pr import fetch_pr_list, get_pr_diff_profile

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OWNER = "home-assistant"
REPO = "core"
SINCE = "2026-03-01T00:00:00Z"
UNTIL = "2026-08-27T23:59:59Z"
SAMPLE_SIZE = 5
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_5_prs.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    load_dotenv()

    if not os.getenv("GITHUB_TOKEN"):
        logger.warning(
            "GITHUB_TOKEN is not set. Requests will be unauthenticated "
            "(rate-limited to 60 req/hr)."
        )

    # ------------------------------------------------------------------
    # 1. Get the list of PRs in the date window
    # ------------------------------------------------------------------
    logger.info(
        "Fetching PR list for %s/%s  since=%s  until=%s ...",
        OWNER, REPO, SINCE, UNTIL,
    )
    pr_list = fetch_pr_list(
        owner=OWNER,
        repo=REPO,
        since=SINCE,
        until=UNTIL,
        state="closed",   # merged PRs are closed
        per_page=100,
    )

    if not pr_list:
        logger.error("No PRs found in the given date window. Exiting.")
        sys.exit(1)

    logger.info("Found %d PRs in window. Taking first %d.", len(pr_list), SAMPLE_SIZE)

    sample_prs = pr_list[:SAMPLE_SIZE]

    # ------------------------------------------------------------------
    # 2. Build a diff profile for each sampled PR
    # ------------------------------------------------------------------
    profiles = []
    for idx, pr in enumerate(sample_prs, start=1):
        pr_number = pr["number"]
        logger.info(
            "[%d/%d] Fetching diff profile for PR #%d ...",
            idx, SAMPLE_SIZE, pr_number,
        )
        try:
            profile = get_pr_diff_profile(OWNER, REPO, pr_number)
            profiles.append(profile)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to fetch profile for PR #%d: %s", pr_number, exc)

    # ------------------------------------------------------------------
    # 3. Print to console
    # ------------------------------------------------------------------
    output_json = json.dumps(profiles, indent=2, ensure_ascii=False)
    print("\n" + "=" * 60)
    print(output_json)
    print("=" * 60 + "\n")

    # ------------------------------------------------------------------
    # 4. Save to data/sample_5_prs.json
    # ------------------------------------------------------------------
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(output_json, encoding="utf-8")
    logger.info("Saved %d profiles to %s", len(profiles), OUTPUT_PATH)


if __name__ == "__main__":
    main()
