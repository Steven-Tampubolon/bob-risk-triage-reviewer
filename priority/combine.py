"""
priority/combine.py

Combines blast-radius, security-policy, and (optional) evidence-gap signals
into a single priority score and label for a pull request.

Formula
-------
    priority_score = round(
        0.5 * blast_radius_score
        + 0.3 * evidence_gap_score
        + 0.2 * security_weight
    )

Where:
    blast_radius_score  – 0-100 from scoring.blast_radius.score_blast_radius()
    evidence_gap_score  – 0-100 from an evidence module (default 50 when None)
    security_weight     – 100 if merge_blocker, 50 if required_reviewer only,
                          0 if no security concern at all

Priority label thresholds (applied AFTER override rules):
    [0,  39]  → 'Low'
    [40, 59]  → 'Medium'
    [60, 79]  → 'High'
    [80,100]  → 'Critical'

Override rule (unconditional):
    If security_result.merge_blocker is True → label is ALWAYS 'Critical',
    regardless of the numeric priority_score.  This ensures that no security-
    policy block can ever be down-graded by a low blast-radius or evidence score.

Public API
----------
combine_priority(blast_radius_result, security_result, evidence_result=None)
    -> tuple[int, str]   (priority_score, priority_label)
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Weight constants — documented for presenter clarity
# ---------------------------------------------------------------------------

# Blast-radius carries the most weight (50%) because it directly measures
# how many modules and reviewers are affected by the change.
WEIGHT_BLAST_RADIUS: float = 0.5

# Evidence gap (e.g. missing tests, no docs update) contributes 30%.
# When no evidence module result is available, we use a neutral 50 so the
# score is neither inflated nor deflated by missing data.
WEIGHT_EVIDENCE: float = 0.3
EVIDENCE_NEUTRAL: int = 50  # default when evidence_result is None

# Security policy carries 20%.  Small weight — but the override rule below
# means a merge_blocker always escalates to Critical regardless.
WEIGHT_SECURITY: float = 0.2

# Security contribution lookup:
#   merge_blocker=True           → 100  (maximum signal: human sign-off required)
#   required_reviewer (no block) →  50  (elevated: specialist reviewer requested)
#   no security concern          →   0  (clean)
_SECURITY_WEIGHT_BLOCKER: int = 100
_SECURITY_WEIGHT_REVIEWER: int = 50
_SECURITY_WEIGHT_CLEAN: int = 0

# ---------------------------------------------------------------------------
# Label thresholds
# ---------------------------------------------------------------------------
# Chosen to produce roughly equal-width bands while keeping 'Critical' rare
# (requires either a very high composite score or a security override).

_LABEL_THRESHOLDS: list[tuple[int, str]] = [
    (80, "Critical"),
    (60, "High"),
    (40, "Medium"),
    (0,  "Low"),
]


def _score_to_label(score: int) -> str:
    """Map a 0-100 score to a priority label."""
    for min_score, label in _LABEL_THRESHOLDS:
        if score >= min_score:
            return label
    return "Low"  # unreachable, but satisfies the type checker


def combine_priority(
    blast_radius_result: tuple[int, str, list, list],
    security_result: tuple[str | None, bool, list],
    evidence_result: tuple[int, ...] | None = None,
) -> tuple[int, str]:
    """
    Combine three scoring signals into a single priority decision.

    Args:
        blast_radius_result:
            4-tuple from ``scoring.blast_radius.score_blast_radius``:
            (score: int, label: str, modules: list, facts: list).
            Only the first element (score) is consumed.

        security_result:
            3-tuple from ``scoring.security_policy.score_security_policy``:
            (required_reviewer: str|None, merge_blocker: bool, reasons: list).

        evidence_result:
            Optional tuple whose first element is a 0-100 evidence-gap score.
            When None, the neutral value (50) is used so the score is not
            skewed by missing data.

    Returns:
        (priority_score, priority_label)

        priority_score  – int, 0-100.
        priority_label  – 'Low' | 'Medium' | 'High' | 'Critical'.
                          Always 'Critical' when merge_blocker is True,
                          regardless of priority_score.
    """
    # --- unpack blast radius ---
    blast_radius_score: int = int(blast_radius_result[0])

    # --- unpack security ---
    required_reviewer: str | None = security_result[0]
    merge_blocker: bool = bool(security_result[1])

    security_weight: int
    if merge_blocker:
        security_weight = _SECURITY_WEIGHT_BLOCKER
    elif required_reviewer is not None:
        security_weight = _SECURITY_WEIGHT_REVIEWER
    else:
        security_weight = _SECURITY_WEIGHT_CLEAN

    # --- unpack evidence (optional) ---
    if evidence_result is not None:
        evidence_gap_score: int = int(evidence_result[0])
    else:
        evidence_gap_score = EVIDENCE_NEUTRAL

    # --- compute weighted score ---
    raw = (
        WEIGHT_BLAST_RADIUS * blast_radius_score
        + WEIGHT_EVIDENCE    * evidence_gap_score
        + WEIGHT_SECURITY    * security_weight
    )
    priority_score: int = max(0, min(100, round(raw)))

    # --- derive label ---
    priority_label: str = _score_to_label(priority_score)

    # --- OVERRIDE: security merge_blocker always means Critical ---
    # This is an unconditional guardrail: no combination of low blast-radius
    # or missing evidence can down-grade a PR that has a mandatory security
    # hold.  A human reviewer must sign off before any merge can proceed.
    if merge_blocker:
        priority_label = "Critical"

    return priority_score, priority_label
