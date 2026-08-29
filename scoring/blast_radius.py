"""
scoring/blast_radius.py

Blast-radius scorer for a pull-request diff profile.

A PR's "blast radius" captures how *widely* a change propagates through the
codebase — i.e., how many independent modules might be affected and how large
the change volume is.  A large blast radius correlates with higher review cost,
more regression risk, and harder rollback.

Public API
----------
score_blast_radius(diff_profile) -> tuple[int, str, list[str], list[str]]
    Returns (score, label, affected_modules, explanation_facts).
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Non-substantive module names
# ---------------------------------------------------------------------------
# These entries appear in modules_touched but do NOT represent an independent
# logical module for blast-radius purposes:
#
#   "tests"               — test files travel with the component they cover;
#                           a PR touching homeassistant/components/hue + tests/
#                           is still scoped to a single feature area.
#
#   "requirements_all.txt"  — auto-generated aggregate file updated by tooling
#   "requirements_test_all.txt" — idem
#   "CODEOWNERS"          — ownership metadata, not logic
#   "scripts"             — repo-level helper scripts, not a product module
#
# When evaluating breadth we count only *substantive* modules (i.e. modules
# NOT in this set).  The full modules_touched list is still returned to callers
# for transparency.
NON_SUBSTANTIVE_MODULES: frozenset[str] = frozenset({
    "tests",
    "requirements_all.txt",
    "requirements_test_all.txt",
    "CODEOWNERS",
    "scripts",
})

# ---------------------------------------------------------------------------
# Threshold constants — each is documented so the rationale is clear during
# jury / stakeholder presentations.
# ---------------------------------------------------------------------------

# THRESHOLD: module breadth  (evaluated on *substantive* modules only)
# A PR that touches more than one *independent* logical module implies
# side-effects that span team ownership boundaries, requiring reviewers from
# multiple domains.  Test files and auto-generated files are excluded from
# this count because they shadow the component they belong to — a PR that
# touches homeassistant/components/hue + tests/ is still a single-component
# change.
MULTI_MODULE_THRESHOLD = 1          # len(substantive_modules) > 1  →  multi_module

# THRESHOLD: change size (lines added + deleted)
# 500 lines was chosen via empirical calibration against 100 merged PRs from
# home-assistant/core (period 2026-03-01 to 2026-08-27):
#
#   threshold 150  →  56% multi_module  (over-triggers; nearly every PR flagged)
#   threshold 500  →  36% multi_module  (Δ = 1% from the research baseline of 35%)
#
# The 35% baseline comes from our own internal research analysis
# (see: fitur_dan_target_eksperimen_BOB_2_0.md), not an external study.  
#  Using 500 instead of the naive 150 avoids flooding reviewers with
# false positives on large repos with many small single-component changes.
#
# Using combined churn (additions + deletions) instead of just additions
# accounts for refactors that swap large blocks — which carry the same
# cognitive load even if net-line count is near zero.
SIZE_THRESHOLD = 500                # additions + deletions > 500  →  multi_module

# ---------------------------------------------------------------------------
# Score mapping
# ---------------------------------------------------------------------------
# Scores are bucketed into three tiers so downstream risk-aggregation models
# can use a numerical signal without over-fitting to false precision.
#
#   small_or_local  →  base 20  (low blast radius, contained change)
#   multi_module    →  base 60  (moderate blast radius, some spread)
#
# Within multi_module, we add up to +20 points for each additional signal
# that independently confirms wide impact (both criteria firing simultaneously
# means both breadth AND depth are large → max 80).

_SCORE_SMALL = 20
_SCORE_MULTI_BASE = 60
_SCORE_MULTI_BOTH_BONUS = 20        # bonus when BOTH criteria fire together


def score_blast_radius(
    diff_profile: dict[str, Any],
) -> tuple[int, str, list[str], list[str]]:
    """
    Score the blast radius of a pull request.

    Args:
        diff_profile: Dict matching the schema produced by
            ``ingestion.github_pr.get_pr_diff_profile``.

    Returns:
        A 4-tuple:
        - **score** (int, 0–100): Numeric blast-radius score.
        - **label** (str): ``'small_or_local'`` or ``'multi_module'``.
        - **affected_modules** (list[str]): Copy of ``modules_touched`` from
          the profile (convenience passthrough for callers).
        - **explanation_facts** (list[str]): Human-readable sentences
          explaining *why* this score was assigned — useful for audit trails
          and presentation slides.
    """
    modules: list[str] = list(diff_profile.get("modules_touched") or [])
    additions: int = int(diff_profile.get("additions") or 0)
    deletions: int = int(diff_profile.get("deletions") or 0)
    churn: int = additions + deletions

    # Substantive modules: strip test/tooling entries that shadow the real
    # component.  The breadth criterion is evaluated on this reduced set so
    # that "1 component + tests" is not penalised as multi-module.
    substantive_modules: list[str] = [
        m for m in modules if m not in NON_SUBSTANTIVE_MODULES
    ]

    # --- evaluate the two independent criteria ---
    is_multi_module_by_breadth: bool = len(substantive_modules) > MULTI_MODULE_THRESHOLD
    is_multi_module_by_size: bool = churn > SIZE_THRESHOLD

    is_multi_module: bool = is_multi_module_by_breadth or is_multi_module_by_size

    # --- build explanation facts (always include at least one fact) ---
    facts: list[str] = []

    facts.append(
        f"Substantive modules: {len(substantive_modules)} "
        f"(total modules_touched: {len(modules)}, "
        f"excluded non-substantive: {len(modules) - len(substantive_modules)}; "
        f"{'>' if is_multi_module_by_breadth else '<='} threshold {MULTI_MODULE_THRESHOLD})."
    )
    facts.append(
        f"Change size (additions + deletions): {churn} lines "
        f"({'>' if is_multi_module_by_size else '<='} threshold {SIZE_THRESHOLD})."
    )

    if is_multi_module_by_breadth:
        facts.append(
            f"Breadth criterion triggered: PR spans {len(substantive_modules)} "
            f"substantive module(s): " + ", ".join(substantive_modules) + "."
        )
    if is_multi_module_by_size:
        facts.append(
            f"Size criterion triggered: {additions} additions + {deletions} deletions "
            f"= {churn} lines of churn."
        )

    # --- compute score ---
    if not is_multi_module:
        score = _SCORE_SMALL
        label = "small_or_local"
        facts.append(
            "Neither criterion triggered → label: small_or_local, "
            f"score: {score}."
        )
    else:
        label = "multi_module"
        if is_multi_module_by_breadth and is_multi_module_by_size:
            # Both criteria fire: maximum confidence the PR has wide impact.
            score = _SCORE_MULTI_BASE + _SCORE_MULTI_BOTH_BONUS
            facts.append(
                "Both breadth AND size criteria triggered → maximum multi_module "
                f"confidence, score: {score}."
            )
        else:
            score = _SCORE_MULTI_BASE
            trigger = "breadth" if is_multi_module_by_breadth else "size"
            facts.append(
                f"Single criterion ({trigger}) triggered → label: multi_module, "
                f"score: {score}."
            )

    return score, label, modules, facts
