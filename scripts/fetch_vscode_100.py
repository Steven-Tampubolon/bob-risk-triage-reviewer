"""
scripts/fetch_vscode_100.py

Fetches 100 merged PRs from microsoft/vscode between 2026-03-01 and 2026-08-27,
builds a diff profile for each, and saves results to data/vscode_100prs.json.

Progress is printed to console every 10 PRs.
Rate-limit retries are handled automatically by ingestion/github_pr._request().

Usage:
    python scripts/fetch_vscode_100.py
"""

import json
import os
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from ingestion.github_pr import fetch_pr_list, get_pr_diff_profile

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OWNER = "microsoft"
REPO = "vscode"
SINCE = "2026-03-01T00:00:00Z"
UNTIL = "2026-08-27T23:59:59Z"
SAMPLE_SIZE = 100
PROGRESS_EVERY = 10
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "vscode_100prs.json"

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
            "GITHUB_TOKEN is not set — requests will be unauthenticated "
            "(rate-limited to 60 req/hr)."
        )

    # ------------------------------------------------------------------
    # 1. Fetch PR list for the date window
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
        state="closed",
        per_page=100,
    )

    if not pr_list:
        logger.error("No PRs found in the given date window. Exiting.")
        sys.exit(1)

    total_found = len(pr_list)
    sample = pr_list[:SAMPLE_SIZE]
    actual = len(sample)

    logger.info(
        "Found %d PRs in window. Processing %d PR%s ...",
        total_found,
        actual,
        "s" if actual != 1 else "",
    )

    # ------------------------------------------------------------------
    # 2. Fetch diff profile for each PR
    # ------------------------------------------------------------------
    profiles: list[dict] = []
    error_count = 0

    for idx, pr in enumerate(sample, start=1):
        pr_number = pr["number"]
        try:
            profile = get_pr_diff_profile(OWNER, REPO, pr_number)
            profiles.append(profile)
        except Exception as exc:  # noqa: BLE001
            logger.error("  PR #%d failed: %s", pr_number, exc)
            error_count += 1

        if idx % PROGRESS_EVERY == 0 or idx == actual:
            print(f"Processed {idx}/{actual} PRs ...", flush=True)

    # ------------------------------------------------------------------
    # 3. Save to disk
    # ------------------------------------------------------------------
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(profiles, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info(
        "Done. %d profiles saved to %s  (%d error%s).",
        len(profiles),
        OUTPUT_PATH,
        error_count,
        "s" if error_count != 1 else "",
    )


if __name__ == "__main__":
    main()
