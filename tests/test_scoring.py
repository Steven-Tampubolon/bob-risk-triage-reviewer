"""
tests/test_scoring.py

Unit tests for scoring/blast_radius.py.
No external I/O — all inputs are constructed inline.
"""

import unittest

from scoring.blast_radius import (
    score_blast_radius,
    MULTI_MODULE_THRESHOLD,
    NON_SUBSTANTIVE_MODULES,
    SIZE_THRESHOLD,
    _SCORE_SMALL,
    _SCORE_MULTI_BASE,
    _SCORE_MULTI_BOTH_BONUS,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _profile(
    modules: list[str] | None = None,
    additions: int = 0,
    deletions: int = 0,
    files_changed: int = 1,
) -> dict:
    """Build a minimal diff_profile dict for testing."""
    return {
        "pr_number": 1,
        "files_changed": files_changed,
        "additions": additions,
        "deletions": deletions,
        "modules_touched": modules if modules is not None else [],
        "has_migration": False,
        "has_config_change": False,
        "has_dependency_change": False,
        "has_ci_change": False,
        "pr_description": "",
    }


# ---------------------------------------------------------------------------
# Tests: small / local PRs
# ---------------------------------------------------------------------------

class TestSmallOrLocal(unittest.TestCase):
    def test_single_module_small_churn_is_small(self):
        profile = _profile(modules=["homeassistant/components/hue"], additions=10, deletions=5)
        score, label, _, facts = score_blast_radius(profile)
        self.assertEqual(label, "small_or_local")
        self.assertEqual(score, _SCORE_SMALL)

    def test_single_module_exactly_at_size_threshold_is_small(self):
        # churn == SIZE_THRESHOLD is NOT > threshold → still small
        profile = _profile(
            modules=["homeassistant/components/hue"],
            additions=SIZE_THRESHOLD // 2,
            deletions=SIZE_THRESHOLD - SIZE_THRESHOLD // 2,
        )
        score, label, _, _ = score_blast_radius(profile)
        self.assertEqual(label, "small_or_local")

    def test_single_module_zero_churn_is_small(self):
        profile = _profile(modules=["homeassistant/components/hue"], additions=0, deletions=0)
        score, label, _, _ = score_blast_radius(profile)
        self.assertEqual(label, "small_or_local")
        self.assertEqual(score, _SCORE_SMALL)

    def test_score_is_int(self):
        profile = _profile(modules=["homeassistant/components/hue"], additions=5)
        score, _, _, _ = score_blast_radius(profile)
        self.assertIsInstance(score, int)

    def test_affected_modules_passthrough(self):
        mods = ["homeassistant/components/hue"]
        profile = _profile(modules=mods, additions=5)
        _, _, affected, _ = score_blast_radius(profile)
        self.assertEqual(affected, mods)

    def test_explanation_facts_not_empty(self):
        profile = _profile(modules=["homeassistant/components/hue"], additions=5)
        _, _, _, facts = score_blast_radius(profile)
        self.assertGreater(len(facts), 0)
        self.assertTrue(all(isinstance(f, str) for f in facts))


# ---------------------------------------------------------------------------
# Tests: multi-module PRs (breadth criterion)
# ---------------------------------------------------------------------------

class TestMultiModuleByBreadth(unittest.TestCase):
    def test_two_substantive_modules_small_churn_is_multi(self):
        """Two real components (no tests) → breadth criterion fires."""
        profile = _profile(
            modules=["homeassistant/components/hue", "homeassistant/components/mqtt"],
            additions=10, deletions=5,
        )
        score, label, _, _ = score_blast_radius(profile)
        self.assertEqual(label, "multi_module")
        self.assertEqual(score, _SCORE_MULTI_BASE)

    def test_one_component_plus_tests_small_churn_is_small(self):
        """
        1 component + tests → tests is non-substantive → only 1 substantive
        module → breadth criterion does NOT fire → small_or_local.
        """
        profile = _profile(
            modules=["homeassistant/components/hue", "tests"],
            additions=10, deletions=5,
        )
        score, label, _, _ = score_blast_radius(profile)
        self.assertEqual(label, "small_or_local")
        self.assertEqual(score, _SCORE_SMALL)

    def test_one_component_plus_requirements_all_is_small(self):
        """
        requirements_all.txt is non-substantive → only 1 substantive module
        → small_or_local (typical HA dependency-bump pattern).
        """
        profile = _profile(
            modules=["homeassistant/components/neopool", "requirements_all.txt"],
            additions=2, deletions=2,
        )
        score, label, _, _ = score_blast_radius(profile)
        self.assertEqual(label, "small_or_local")

    def test_two_components_plus_tests_is_multi(self):
        """2 real components + tests → 2 substantive → still multi_module."""
        profile = _profile(
            modules=[
                "homeassistant/components/hue",
                "homeassistant/components/mqtt",
                "tests",
            ],
            additions=10, deletions=5,
        )
        score, label, _, _ = score_blast_radius(profile)
        self.assertEqual(label, "multi_module")

    def test_many_modules_small_churn_is_multi(self):
        mods = [f"homeassistant/components/comp{i}" for i in range(5)]
        profile = _profile(modules=mods, additions=20, deletions=10)
        score, label, _, _ = score_blast_radius(profile)
        self.assertEqual(label, "multi_module")

    def test_breadth_criterion_mentioned_in_facts(self):
        profile = _profile(
            modules=["homeassistant/components/hue", "homeassistant/components/mqtt"],
            additions=10, deletions=5,
        )
        _, _, _, facts = score_blast_radius(profile)
        combined = " ".join(facts).lower()
        self.assertIn("breadth", combined)

    def test_affected_modules_includes_tests_for_transparency(self):
        """affected_modules must be the full modules_touched, including tests."""
        mods = ["homeassistant/components/hue", "tests"]
        profile = _profile(modules=mods, additions=10, deletions=5)
        _, _, affected, _ = score_blast_radius(profile)
        self.assertEqual(affected, mods)
        self.assertIn("tests", affected)


# ---------------------------------------------------------------------------
# Tests: multi-module PRs (size criterion)
# ---------------------------------------------------------------------------

class TestMultiModuleBySize(unittest.TestCase):
    def test_single_module_large_churn_is_multi(self):
        # size > threshold, breadth = 1 → only size criterion fires
        profile = _profile(
            modules=["homeassistant/components/hue"],
            additions=SIZE_THRESHOLD,   # SIZE_THRESHOLD additions makes churn = SIZE_THRESHOLD + 1 deletions below
            deletions=1,
        )
        score, label, _, _ = score_blast_radius(profile)
        self.assertEqual(label, "multi_module")
        self.assertEqual(score, _SCORE_MULTI_BASE)

    def test_size_criterion_exactly_one_over_threshold(self):
        profile = _profile(
            modules=["homeassistant/components/hue"],
            additions=SIZE_THRESHOLD,
            deletions=1,                # total = SIZE_THRESHOLD + 1 > SIZE_THRESHOLD
        )
        _, label, _, _ = score_blast_radius(profile)
        self.assertEqual(label, "multi_module")

    def test_size_criterion_mentioned_in_facts(self):
        profile = _profile(
            modules=["homeassistant/components/hue"],
            additions=SIZE_THRESHOLD,
            deletions=1,
        )
        _, _, _, facts = score_blast_radius(profile)
        combined = " ".join(facts).lower()
        self.assertIn("size", combined)


# ---------------------------------------------------------------------------
# Tests: both criteria fire simultaneously
# ---------------------------------------------------------------------------

class TestMultiModuleBothCriteria(unittest.TestCase):
    def test_both_criteria_give_max_score(self):
        """Two substantive components + large churn → both criteria fire → score 80."""
        profile = _profile(
            modules=["homeassistant/components/hue", "homeassistant/components/mqtt"],
            additions=SIZE_THRESHOLD,
            deletions=1,
        )
        score, label, _, facts = score_blast_radius(profile)
        self.assertEqual(label, "multi_module")
        self.assertEqual(score, _SCORE_MULTI_BASE + _SCORE_MULTI_BOTH_BONUS)

    def test_one_component_plus_tests_large_churn_is_size_only(self):
        """
        1 component + tests, large churn → breadth does NOT fire (tests excluded),
        size fires → multi_module by size only → score 60, not 80.
        """
        profile = _profile(
            modules=["homeassistant/components/hue", "tests"],
            additions=SIZE_THRESHOLD,
            deletions=1,
        )
        score, label, _, facts = score_blast_radius(profile)
        self.assertEqual(label, "multi_module")
        self.assertEqual(score, _SCORE_MULTI_BASE)   # NOT _SCORE_MULTI_BASE + bonus

    def test_both_criteria_mentioned_in_facts(self):
        profile = _profile(
            modules=["homeassistant/components/hue", "homeassistant/components/mqtt"],
            additions=SIZE_THRESHOLD,
            deletions=1,
        )
        _, _, _, facts = score_blast_radius(profile)
        combined = " ".join(facts).lower()
        self.assertIn("breadth", combined)
        self.assertIn("size", combined)


# ---------------------------------------------------------------------------
# Tests: score range invariant
# ---------------------------------------------------------------------------

class TestScoreRange(unittest.TestCase):
    def test_all_scores_within_0_100(self):
        """Score must always be within [0, 100] regardless of input extremes."""
        cases = [
            _profile(modules=[], additions=0, deletions=0),
            _profile(modules=["a"], additions=0, deletions=0),
            _profile(modules=["a"], additions=10_000, deletions=10_000),
            _profile(modules=["a"] * 50, additions=10_000, deletions=10_000),
            _profile(modules=["a", "b"], additions=SIZE_THRESHOLD, deletions=1),
        ]
        for profile in cases:
            score, _, _, _ = score_blast_radius(profile)
            self.assertGreaterEqual(score, 0, f"Score below 0 for {profile}")
            self.assertLessEqual(score, 100, f"Score above 100 for {profile}")


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases(unittest.TestCase):
    def test_empty_pr_zero_files(self):
        """A completely empty PR (no files) → small_or_local."""
        profile = _profile(modules=[], additions=0, deletions=0, files_changed=0)
        score, label, affected, facts = score_blast_radius(profile)
        self.assertEqual(label, "small_or_local")
        self.assertEqual(score, _SCORE_SMALL)
        self.assertEqual(affected, [])
        self.assertGreater(len(facts), 0)

    def test_rename_only_pr(self):
        """Rename-only PR: additions==0, deletions==0, one module → small."""
        profile = _profile(
            modules=["homeassistant/components/hue"],
            additions=0,
            deletions=0,
            files_changed=1,
        )
        score, label, _, _ = score_blast_radius(profile)
        self.assertEqual(label, "small_or_local")
        self.assertEqual(score, _SCORE_SMALL)

    def test_rename_spanning_two_modules(self):
        """Rename touching two SUBSTANTIVE modules still triggers breadth criterion."""
        profile = _profile(
            modules=["homeassistant/components/hue", "homeassistant/components/mqtt"],
            additions=0,
            deletions=0,
            files_changed=2,
        )
        score, label, _, _ = score_blast_radius(profile)
        self.assertEqual(label, "multi_module")

    def test_rename_one_component_plus_tests_is_small(self):
        """Rename in 1 component + tests → tests excluded → small_or_local."""
        profile = _profile(
            modules=["homeassistant/components/hue", "tests"],
            additions=0,
            deletions=0,
            files_changed=2,
        )
        score, label, _, _ = score_blast_radius(profile)
        self.assertEqual(label, "small_or_local")

    def test_none_modules_treated_as_empty(self):
        """modules_touched=None must not raise and behaves like []."""
        profile = _profile(modules=None, additions=0, deletions=0)
        score, label, affected, facts = score_blast_radius(profile)
        self.assertEqual(label, "small_or_local")
        self.assertEqual(affected, [])

    def test_missing_keys_use_defaults(self):
        """Caller passing a minimal dict (missing optional keys) must not raise."""
        profile = {"pr_number": 99}
        score, label, affected, facts = score_blast_radius(profile)
        self.assertIn(label, ("small_or_local", "multi_module"))
        self.assertIsInstance(score, int)

    def test_large_module_list_no_churn(self):
        """50 modules touched, 0 churn → breadth criterion fires → multi_module."""
        profile = _profile(
            modules=[f"homeassistant/components/comp{i}" for i in range(50)],
            additions=0,
            deletions=0,
        )
        _, label, affected, _ = score_blast_radius(profile)
        self.assertEqual(label, "multi_module")
        self.assertEqual(len(affected), 50)

    def test_ha_dependency_bump_pr_is_small(self):
        """
        Typical HA dependency-bump PR: component + requirements_all.txt.
        requirements_all.txt is non-substantive → only 1 substantive module
        → small_or_local (not penalised as cross-module).
        """
        profile = _profile(
            modules=["homeassistant/components/neopool", "requirements_all.txt"],
            additions=2,
            deletions=2,
        )
        score, label, _, facts = score_blast_radius(profile)
        self.assertEqual(label, "small_or_local")
        self.assertEqual(score, _SCORE_SMALL)
        # affected_modules must still expose the full list for transparency
        _, _, affected, _ = score_blast_radius(profile)
        self.assertIn("requirements_all.txt", affected)

    def test_non_substantive_set_exported(self):
        """NON_SUBSTANTIVE_MODULES must be importable and contain expected entries."""
        self.assertIn("tests", NON_SUBSTANTIVE_MODULES)
        self.assertIn("requirements_all.txt", NON_SUBSTANTIVE_MODULES)
        self.assertIn("CODEOWNERS", NON_SUBSTANTIVE_MODULES)

    def test_return_type_signature(self):
        """Return type is exactly (int, str, list, list)."""
        profile = _profile(modules=["a", "b"], additions=200, deletions=50)
        result = score_blast_radius(profile)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 4)
        score, label, modules, facts = result
        self.assertIsInstance(score, int)
        self.assertIsInstance(label, str)
        self.assertIsInstance(modules, list)
        self.assertIsInstance(facts, list)


if __name__ == "__main__":
    unittest.main()
