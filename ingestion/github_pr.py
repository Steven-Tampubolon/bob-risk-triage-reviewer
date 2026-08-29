"""
ingestion/github_pr.py

Fetches GitHub Pull Request metadata and diff profiles via the GitHub REST API.
Requires GITHUB_TOKEN in the environment (loaded via python-dotenv).
"""

import os
import time
import logging
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"

# File-pattern classifiers
_MIGRATION_PATTERNS = (
    "migrations/",
    "migrate/",
    "alembic/",
    "db/migrate/",
    "flyway/",
)
# Dependency files: match by exact basename or well-known path suffix.
# These are checked BEFORE config patterns so that e.g. manifest.json /
# requirements_all.txt don't accidentally flip has_config_change.
_DEPENDENCY_BASENAMES = frozenset({
    "requirements.txt",
    "requirements_all.txt",
    "requirements_test_all.txt",
    "pipfile",
    "pipfile.lock",
    "poetry.lock",
    "setup.py",
    "setup.cfg",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "gemfile",
    "gemfile.lock",
    "go.mod",
    "go.sum",
    "cargo.toml",
    "cargo.lock",
    "manifest.json",
})
_DEPENDENCY_DIR_PREFIXES = (
    "requirements/",
)
# Config: explicit path keywords — NOT generic extensions like .yaml/.json
# which are too broad and overlap with dependency / source files.
_CONFIG_PATH_KEYWORDS = (
    "config/",
    "configuration/",
    "settings/",
    "configuration.yaml",
    "configuration.yml",
    "const.py",
    ".cfg",
    ".conf",
    ".ini",
    ".properties",
)
_CI_PATTERNS = (
    ".github/workflows/", ".gitlab-ci.yml", "Jenkinsfile",
    ".travis.yml", "circle.yml", ".circleci/", "bitbucket-pipelines.yml",
    "azure-pipelines.yml", ".buildkite/", "Makefile",
)


def _get_headers() -> dict[str, str]:
    """Return request headers, including Authorization if GITHUB_TOKEN is set."""
    token = os.getenv("GITHUB_TOKEN")
    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request(url: str, params: dict | None = None, timeout: int = 30) -> Any:
    """
    Perform a GET request with retry logic for GitHub rate limits (HTTP 429 / 403).

    Raises:
        requests.HTTPError: for non-retryable HTTP errors.
        requests.Timeout: when the request exceeds *timeout* seconds.
    """
    max_retries = 3
    for attempt in range(max_retries):
        response = requests.get(
            url,
            headers=_get_headers(),
            params=params,
            timeout=timeout,
        )

        if response.status_code in (403, 429):
            # Respect Retry-After or x-ratelimit-reset header
            retry_after = response.headers.get("Retry-After")
            rate_reset = response.headers.get("x-ratelimit-reset")

            if retry_after:
                wait = int(retry_after)
            elif rate_reset:
                wait = max(int(rate_reset) - int(time.time()), 1)
            else:
                wait = 60  # conservative fallback

            if attempt < max_retries - 1:
                logger.warning(
                    "GitHub rate limit hit (HTTP %s). Waiting %ds before retry %d/%d.",
                    response.status_code,
                    wait,
                    attempt + 1,
                    max_retries - 1,
                )
                time.sleep(wait)
                continue

        response.raise_for_status()
        return response.json()

    # Final attempt exhausted — raise on the last rate-limit response
    response.raise_for_status()


def fetch_pr_list(
    owner: str,
    repo: str,
    since: str | None = None,
    until: str | None = None,
    state: str = "all",
    per_page: int = 100,
) -> list[dict]:
    """
    Return a list of pull request summary objects for *owner/repo*.

    Args:
        owner:    Repository owner (user or organisation).
        repo:     Repository name.
        since:    ISO-8601 date string; filters PRs updated at or after this date.
        until:    ISO-8601 date string; filters PRs updated before or at this date.
        state:    'open', 'closed', or 'all' (default 'all').
        per_page: Number of results per page (max 100).

    Returns:
        List of PR dicts as returned by the GitHub API, optionally filtered by
        the *since*/*until* window (GitHub does not support *until* natively, so
        client-side filtering is applied).
    """
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls"
    params: dict[str, Any] = {
        "state": state,
        "per_page": per_page,
        "sort": "updated",
        "direction": "desc",
    }

    results: list[dict] = []
    page = 1

    while True:
        params["page"] = page
        page_data: list[dict] = _request(url, params=params)

        if not page_data:
            break

        for pr in page_data:
            updated_at = pr.get("updated_at", "")
            if since and updated_at < since:
                # Results are sorted newest-first; once we go past *since* we're done.
                return results
            if until and updated_at > until:
                continue
            results.append(pr)

        if len(page_data) < per_page:
            break
        page += 1

    return results


def fetch_pr_files(owner: str, repo: str, pr_number: int) -> list[dict]:
    """
    Return the list of files changed in a pull request.

    Args:
        owner:     Repository owner.
        repo:      Repository name.
        pr_number: Pull request number.

    Returns:
        List of file objects as returned by GET /repos/{owner}/{repo}/pulls/{pr_number}/files.
    """
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/files"
    return _request(url, params={"per_page": 100})


def _module_key(filename: str) -> str:
    """
    Return a human-readable module identifier for *filename*.

    Rules:
    - Files under ``homeassistant/components/<name>/`` → ``homeassistant/components/<name>``
    - All other files → first path segment only (e.g. ``tests``, ``scripts``)
    """
    parts = filename.split("/")
    if (
        len(parts) >= 3
        and parts[0] == "homeassistant"
        and parts[1] == "components"
    ):
        return f"homeassistant/components/{parts[2]}"
    return parts[0]


def _is_dependency_file(fname: str) -> bool:
    """Return True if *fname* is a dependency-manifest file."""
    basename = fname.split("/")[-1].lower()
    if basename in _DEPENDENCY_BASENAMES:
        return True
    fname_lower = fname.lower()
    return any(fname_lower.startswith(prefix) for prefix in _DEPENDENCY_DIR_PREFIXES)


def _is_config_file(fname: str) -> bool:
    """
    Return True if *fname* is a configuration file.

    Dependency files are explicitly excluded so that e.g. manifest.json /
    requirements_all.txt don't accidentally set has_config_change.
    """
    if _is_dependency_file(fname):
        return False
    fname_lower = fname.lower()
    return any(kw in fname_lower for kw in _CONFIG_PATH_KEYWORDS)


def _classify_files(files: list[dict]) -> dict[str, Any]:
    """Derive classifier flags and module list from a list of PR file objects."""
    filenames = [f.get("filename", "") for f in files]
    modules: set[str] = set()

    for fname in filenames:
        modules.add(_module_key(fname))

    def matches_migration() -> bool:
        return any(
            any(pat.lower() in fname.lower() for pat in _MIGRATION_PATTERNS)
            for fname in filenames
        )

    def matches_ci() -> bool:
        return any(
            any(pat.lower() in fname.lower() for pat in _CI_PATTERNS)
            for fname in filenames
        )

    return {
        "modules_touched": sorted(modules),
        "has_migration": matches_migration(),
        "has_config_change": any(_is_config_file(f) for f in filenames),
        "has_dependency_change": any(_is_dependency_file(f) for f in filenames),
        "has_ci_change": matches_ci(),
    }


def get_pr_diff_profile(owner: str, repo: str, pr_number: int) -> dict[str, Any]:
    """
    Build a structured diff profile for a pull request.

    Args:
        owner:     Repository owner.
        repo:      Repository name.
        pr_number: Pull request number.

    Returns:
        Dict matching the schema::

            {
                "pr_number":             int,
                "files_changed":         int,
                "additions":             int,
                "deletions":             int,
                "modules_touched":       list[str],
                "has_migration":         bool,
                "has_config_change":     bool,
                "has_dependency_change": bool,
                "has_ci_change":         bool,
                "pr_description":        str,
            }
    """
    # Fetch PR metadata and file list concurrently (sequential here — kept simple)
    pr_url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}"
    pr_meta: dict = _request(pr_url)
    files: list[dict] = fetch_pr_files(owner, repo, pr_number)

    additions = sum(f.get("additions", 0) for f in files)
    deletions = sum(f.get("deletions", 0) for f in files)

    classification = _classify_files(files)

    return {
        "pr_number": pr_number,
        "files_changed": len(files),
        "additions": additions,
        "deletions": deletions,
        **classification,
        "pr_description": pr_meta.get("body") or "",
    }
