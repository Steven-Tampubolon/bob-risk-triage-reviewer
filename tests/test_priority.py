"""
tests/test_priority.py

Unit tests for priority/combine.py.
No external I/O — all inputs are constructed inline.

Coverage:
  - Small safe PR                  → Low priority
  - Large safe PR                  → High/Critical by score
  - Small PR with merge_blocker    → Critical (override)
  - Large PR with merge_blocker    → Critical (override + score)
  - required_reviewer (no blocker) → score elevated, label Medium/High
  - Evidence result wiring         → score reflects evidence gap
  - Evidence result = None         → neutral 50 used
  - Score clamped to [0, 100]
  - Label thresholds (boundary values)
  - merge_blocker override is unconditional regardless of score
"""

import unittest

from priority.combine import (
    combine_priority,
    WEIGHT_BLAST_RADIUS,
    WEIGHT_EVIDENCE,
    WEIGHT_SECURITY,
    EVIDENCE_NEUTRAL,
    _SECURITY_WEIGHT_BLOCKER,
    _SECURITY_WEIGHT_REVIEWER,
    _SECURITY_WEIGHT_CLEAN,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _blast(score: int, label: str = "small_or_local") -> tuple:
    """Minimal blast_radius_result tuple."""
    return (score, label, [], [])


def _security(
    reviewer: str | None = None,
    blocker: bool = False,
    reasons: list | None = None,
) -> tuple:
    """Minimal security_result tuple."""
    return (reviewer, blocker, reasons or [])


def _evidence(score: int) -> tuple:
    """Minimal evidence_result tuple."""
    return (score,)


def _expected_score(br: int, ev: int, sw: int) -> int:
    """Compute expected priority_score with the published formula."""
    return max(0, min(100, round(
        WEIGHT_BLAST_RADIUS * br
        + WEIGHT_EVIDENCE * ev
        + WEIGHT_SECURITY * sw
    )))


# ---------------------------------------------------------------------------
# Small, safe PR  (low blast radius, no security concern)
# ---------------------------------------------------------------------------

class TestSmallSafePR(unittest.TestCase):
    def test_small_safe_is_low(self):
        score, label = combine_priority(
            _blast(20, "small_or_local"),
            _security(),
        )
        self.assertEqual(label, "Low")

    def test_small_safe_score_matches_formula(self):
        score, _ = combine_priority(
            _blast(20, "small_or_local"),
            _security(),
        )
        expected = _expected_score(20, EVIDENCE_NEUTRAL, _SECURITY_WEIGHT_CLEAN)
        self.assertEqual(score, expected)

    def test_small_safe_with_evidence(self):
        score, label = combine_priority(
            _blast(20, "small_or_local"),
            _security(),
            _evidence(10),   # low evidence gap
        )
        expected = _expected_score(20, 10, _SECURITY_WEIGHT_CLEAN)
        self.assertEqual(score, expected)
        self.assertEqual(label, "Low")

    def test_no_reviewer_no_blocker_security_weight_zero(self):
        score, _ = combine_priority(_blast(0), _security())
        # all weights zero or neutral → score = 0.3*50 = 15
        expected = _expected_score(0, EVIDENCE_NEUTRAL, _SECURITY_WEIGHT_CLEAN)
        self.assertEqual(score, expected)


# ---------------------------------------------------------------------------
# Large, safe PR  (high blast radius, no security concern)
# ---------------------------------------------------------------------------

class TestLargeSafePR(unittest.TestCase):
    def test_large_safe_score_matches_formula(self):
        score, _ = combine_priority(
            _blast(80, "multi_module"),
            _security(),
        )
        expected = _expected_score(80, EVIDENCE_NEUTRAL, _SECURITY_WEIGHT_CLEAN)
        self.assertEqual(score, expected)

    def test_large_safe_high_label(self):
        # blast=80, evidence neutral=50, security clean=0
        # score = 0.5*80 + 0.3*50 + 0.2*0 = 40+15 = 55 → Medium
        score, label = combine_priority(
            _blast(80, "multi_module"),
            _security(),
        )
        expected = _expected_score(80, EVIDENCE_NEUTRAL, _SECURITY_WEIGHT_CLEAN)
        self.assertEqual(score, expected)
        # label derived from score
        if score >= 80:
            self.assertEqual(label, "Critical")
        elif score >= 60:
            self.assertEqual(label, "High")
        elif score >= 40:
            self.assertEqual(label, "Medium")
        else:
            self.assertEqual(label, "Low")

    def test_large_safe_with_high_evidence_gap(self):
        # large blast + large evidence gap → higher score
        score, label = combine_priority(
            _blast(80, "multi_module"),
            _security(),
            _evidence(80),
        )
        expected = _expected_score(80, 80, _SECURITY_WEIGHT_CLEAN)
        self.assertEqual(score, expected)


# ---------------------------------------------------------------------------
# Small PR with merge_blocker → Critical override
# ---------------------------------------------------------------------------

class TestSmallPRWithMergeBLocker(unittest.TestCase):
    def test_merge_blocker_forces_critical_label(self):
        """Even a tiny blast-radius PR must be Critical when merge_blocker=True."""
        _, label = combine_priority(
            _blast(20, "small_or_local"),
            _security(reviewer="security-team", blocker=True),
        )
        self.assertEqual(label, "Critical")

    def test_merge_blocker_score_reflects_security_weight(self):
        score, _ = combine_priority(
            _blast(20, "small_or_local"),
            _security(reviewer="security-team", blocker=True),
        )
        expected = _expected_score(20, EVIDENCE_NEUTRAL, _SECURITY_WEIGHT_BLOCKER)
        self.assertEqual(score, expected)

    def test_merge_blocker_zero_blast_radius_still_critical(self):
        """Absolute minimum blast-radius + blocker → still Critical."""
        _, label = combine_priority(
            _blast(0, "small_or_local"),
            _security(reviewer="security-team", blocker=True),
        )
        self.assertEqual(label, "Critical")

    def test_merge_blocker_override_is_unconditional(self):
        """
        Exhaustive check: for every blast score 0-100 (step 10), a merge_blocker
        ALWAYS produces 'Critical' regardless of score magnitude.
        """
        for br_score in range(0, 101, 10):
            _, label = combine_priority(
                _blast(br_score),
                _security(reviewer="security-team", blocker=True),
            )
            self.assertEqual(
                label, "Critical",
                msg=f"merge_blocker=True but label={label!r} for blast={br_score}"
            )


# ---------------------------------------------------------------------------
# Large PR that is also sensitive
# ---------------------------------------------------------------------------

class TestLargeAndSensitivePR(unittest.TestCase):
    def test_large_blocker_is_critical_label(self):
        _, label = combine_priority(
            _blast(80, "multi_module"),
            _security(reviewer="security-team", blocker=True),
        )
        self.assertEqual(label, "Critical")

    def test_large_blocker_score_formula(self):
        score, _ = combine_priority(
            _blast(80, "multi_module"),
            _security(reviewer="security-team", blocker=True),
        )
        expected = _expected_score(80, EVIDENCE_NEUTRAL, _SECURITY_WEIGHT_BLOCKER)
        self.assertEqual(score, expected)

    def test_large_blocker_with_evidence_formula(self):
        score, label = combine_priority(
            _blast(80, "multi_module"),
            _security(reviewer="security-team", blocker=True),
            _evidence(80),
        )
        expected = _expected_score(80, 80, _SECURITY_WEIGHT_BLOCKER)
        self.assertEqual(score, expected)
        self.assertEqual(label, "Critical")


# ---------------------------------------------------------------------------
# required_reviewer without merge_blocker
# ---------------------------------------------------------------------------

class TestRequiredReviewerNoBLocker(unittest.TestCase):
    def test_reviewer_only_elevates_score(self):
        score_with, _ = combine_priority(
            _blast(20),
            _security(reviewer="dependency-review", blocker=False),
        )
        score_without, _ = combine_priority(
            _blast(20),
            _security(),
        )
        self.assertGreater(score_with, score_without)

    def test_reviewer_only_security_weight_is_50(self):
        score, _ = combine_priority(
            _blast(20),
            _security(reviewer="dependency-review", blocker=False),
        )
        expected = _expected_score(20, EVIDENCE_NEUTRAL, _SECURITY_WEIGHT_REVIEWER)
        self.assertEqual(score, expected)

    def test_reviewer_only_does_not_force_critical(self):
        """required_reviewer without blocker must NOT force Critical label."""
        _, label = combine_priority(
            _blast(20),
            _security(reviewer="dependency-review", blocker=False),
        )
        self.assertNotEqual(label, "Critical")


# ---------------------------------------------------------------------------
# Evidence result wiring
# ---------------------------------------------------------------------------

class TestEvidenceWiring(unittest.TestCase):
    def test_no_evidence_uses_neutral_50(self):
        score_none, _ = combine_priority(_blast(40), _security())
        score_neutral, _ = combine_priority(_blast(40), _security(), _evidence(EVIDENCE_NEUTRAL))
        self.assertEqual(score_none, score_neutral)

    def test_high_evidence_gap_raises_score(self):
        score_high, _ = combine_priority(_blast(40), _security(), _evidence(100))
        score_low, _  = combine_priority(_blast(40), _security(), _evidence(0))
        self.assertGreater(score_high, score_low)

    def test_evidence_zero_lowers_score(self):
        score_zero, _ = combine_priority(_blast(40), _security(), _evidence(0))
        score_neutral, _ = combine_priority(_blast(40), _security(), None)
        self.assertLess(score_zero, score_neutral)

    def test_evidence_score_formula(self):
        for ev in (0, 25, 50, 75, 100):
            score, _ = combine_priority(_blast(60), _security(), _evidence(ev))
            expected = _expected_score(60, ev, _SECURITY_WEIGHT_CLEAN)
            self.assertEqual(score, expected, msg=f"evidence={ev}")


# ---------------------------------------------------------------------------
# Label threshold boundary values
# ---------------------------------------------------------------------------

class TestLabelThresholds(unittest.TestCase):
    """
    Test the four label bands using evidence as the knob to hit exact scores.
    (blast=0, security_clean=0) → score = 0.3 * evidence
    """

    def _score_from_evidence(self, ev: int) -> int:
        return _expected_score(0, ev, _SECURITY_WEIGHT_CLEAN)

    def test_score_0_is_low(self):
        score, label = combine_priority(_blast(0), _security(), _evidence(0))
        self.assertEqual(label, "Low")
        self.assertEqual(score, 0)

    def test_score_39_is_low(self):
        # find evidence that gives score=39: 0.3*ev = 39 → ev=130 → clamp
        # use blast+evidence to get 39
        # blast=40, evidence=30, security=0 → 0.5*40+0.3*30+0 = 20+9=29 Low
        score, label = combine_priority(_blast(40), _security(), _evidence(30))
        self.assertLess(score, 40)
        self.assertEqual(label, "Low")

    def test_score_40_is_medium(self):
        # blast=60, evidence=50, security=0 → 0.5*60+0.3*50 = 30+15 = 45 → Medium
        score, label = combine_priority(_blast(60), _security(), _evidence(50))
        self.assertGreaterEqual(score, 40)
        self.assertLess(score, 60)
        self.assertEqual(label, "Medium")

    def test_score_60_is_high(self):
        # blast=80, evidence=50, security=0 → 0.5*80+0.3*50 = 40+15 = 55 → Medium
        # blast=80, evidence=80, security=0 → 40+24 = 64 → High
        score, label = combine_priority(_blast(80), _security(), _evidence(80))
        self.assertGreaterEqual(score, 60)
        self.assertLess(score, 80)
        self.assertEqual(label, "High")

    def test_score_80_is_critical_by_score(self):
        # blast=100, evidence=100, security=0 → 50+30 = 80 → Critical
        score, label = combine_priority(_blast(100), _security(), _evidence(100))
        self.assertGreaterEqual(score, 80)
        self.assertEqual(label, "Critical")


# ---------------------------------------------------------------------------
# Score clamping to [0, 100]
# ---------------------------------------------------------------------------

class TestScoreClamping(unittest.TestCase):
    def test_score_never_below_zero(self):
        score, _ = combine_priority(_blast(0), _security(), _evidence(0))
        self.assertGreaterEqual(score, 0)

    def test_score_never_above_100(self):
        score, _ = combine_priority(
            _blast(100),
            _security(reviewer="security-team", blocker=True),
            _evidence(100),
        )
        self.assertLessEqual(score, 100)

    def test_score_is_int(self):
        score, _ = combine_priority(_blast(55), _security(), _evidence(55))
        self.assertIsInstance(score, int)


# ---------------------------------------------------------------------------
# Return type invariants
# ---------------------------------------------------------------------------

class TestReturnTypeInvariants(unittest.TestCase):
    def test_returns_2_tuple(self):
        result = combine_priority(_blast(20), _security())
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_first_element_is_int(self):
        score, _ = combine_priority(_blast(20), _security())
        self.assertIsInstance(score, int)

    def test_second_element_is_valid_label(self):
        valid_labels = {"Low", "Medium", "High", "Critical"}
        for br in (0, 20, 60, 100):
            for blocker in (True, False):
                _, label = combine_priority(
                    _blast(br),
                    _security(reviewer="security-team" if blocker else None, blocker=blocker),
                )
                self.assertIn(label, valid_labels, msg=f"br={br}, blocker={blocker}")


if __name__ == "__main__":
    unittest.main()
