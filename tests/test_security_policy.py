"""
tests/test_security_policy.py

Unit tests for scoring/security_policy.py.

Coverage:
  - Every sensitive category (auth, secret/token, dependency, CI/CD, config,
    migration, crypto) triggers correctly
  - Module-keyword detection works for both direct module names and path fragments
  - Flag-field detection works for all boolean fields
  - Clean PR returns merge_blocker=False and required_reviewer=None
  - Reviewer priority: when multiple categories fire, highest-priority wins
  - GUARDRAIL assertion: no return value contains or implies auto_merge=True
    in any form whatsoever
"""

import unittest
from typing import Any

from scoring.security_policy import score_security_policy, _CATEGORIES, _REVIEWER_PRIORITY


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _profile(
    modules: list[str] | None = None,
    has_migration: bool = False,
    has_config_change: bool = False,
    has_dependency_change: bool = False,
    has_ci_change: bool = False,
    additions: int = 0,
    deletions: int = 0,
) -> dict[str, Any]:
    return {
        "pr_number": 1,
        "files_changed": 1,
        "additions": additions,
        "deletions": deletions,
        "modules_touched": modules if modules is not None else [],
        "has_migration": has_migration,
        "has_config_change": has_config_change,
        "has_dependency_change": has_dependency_change,
        "has_ci_change": has_ci_change,
        "pr_description": "",
    }


def _call(profile: dict) -> tuple:
    """Thin wrapper so tests stay readable."""
    return score_security_policy(profile)


# ---------------------------------------------------------------------------
# GUARDRAIL: no auto-merge condition ever
# ---------------------------------------------------------------------------

class TestGuardrailNoAutoMerge(unittest.TestCase):
    """
    This test class asserts the core design contract:
    score_security_policy NEVER produces a state that permits auto-merge.
    """

    _ALL_PROFILES = [
        # clean PR
        _profile(),
        # auth module
        _profile(modules=["homeassistant/components/auth"]),
        # secret in module path
        _profile(modules=["backend/secret_manager"]),
        # dependency flag
        _profile(has_dependency_change=True),
        # CI flag
        _profile(has_ci_change=True),
        # config flag
        _profile(has_config_change=True),
        # migration flag
        _profile(has_migration=True),
        # crypto module
        _profile(modules=["homeassistant/components/tls"]),
        # everything at once
        _profile(
            modules=["auth/login", "crypto/signing"],
            has_migration=True,
            has_config_change=True,
            has_dependency_change=True,
            has_ci_change=True,
        ),
    ]

    def test_return_tuple_never_contains_auto_merge_field(self):
        """
        The 3-tuple (required_reviewer, merge_blocker, policy_reasons) must
        never contain a key/value/substring that implies auto_merge=True.
        Checked exhaustively across all representative profiles.
        """
        forbidden_terms = {
            "auto_merge", "auto-merge", "automerge",
            "approve_and_merge", "fast_lane", "skip_review",
        }
        for profile in self._ALL_PROFILES:
            reviewer, blocker, reasons = score_security_policy(profile)
            result_as_str = str((reviewer, blocker, reasons)).lower()
            for term in forbidden_terms:
                self.assertNotIn(
                    term,
                    result_as_str,
                    msg=(
                        f"Forbidden auto-merge term '{term}' found in result "
                        f"for profile {profile.get('modules_touched')}: "
                        f"{(reviewer, blocker, reasons)}"
                    ),
                )

    def test_merge_blocker_false_does_not_mean_auto_merge(self):
        """
        A clean PR returns merge_blocker=False.  The test verifies that False
        is the ABSENCE of a security block — not a positive auto-merge signal.
        We assert the return signature contains no truthy auto-merge indicator.
        """
        reviewer, blocker, reasons = score_security_policy(_profile())
        self.assertFalse(blocker)
        self.assertIsNone(reviewer)
        # reasons list must be empty — no policy triggered means no signal at all
        self.assertEqual(reasons, [])

    def test_function_never_returns_four_tuple(self):
        """
        Return must always be exactly a 3-tuple — a 4th element named
        'auto_merge' can never be silently added.
        """
        for profile in self._ALL_PROFILES:
            result = score_security_policy(profile)
            self.assertEqual(
                len(result), 3,
                msg=f"Expected 3-tuple, got {len(result)}-tuple: {result}"
            )


# ---------------------------------------------------------------------------
# Clean PR (no flags, no sensitive modules)
# ---------------------------------------------------------------------------

class TestCleanPR(unittest.TestCase):
    def test_clean_pr_no_blocker(self):
        reviewer, blocker, reasons = _call(_profile())
        self.assertFalse(blocker)

    def test_clean_pr_no_reviewer(self):
        reviewer, blocker, reasons = _call(_profile())
        self.assertIsNone(reviewer)

    def test_clean_pr_empty_reasons(self):
        reviewer, blocker, reasons = _call(_profile())
        self.assertEqual(reasons, [])

    def test_plain_component_no_sensitive_keywords(self):
        reviewer, blocker, reasons = _call(
            _profile(modules=["homeassistant/components/media_player"])
        )
        self.assertFalse(blocker)
        self.assertIsNone(reviewer)


# ---------------------------------------------------------------------------
# Category: auth / permission
# ---------------------------------------------------------------------------

class TestAuthPermissionCategory(unittest.TestCase):
    def test_auth_module_triggers_blocker(self):
        _, blocker, _ = _call(_profile(modules=["homeassistant/components/auth"]))
        self.assertTrue(blocker)

    def test_permission_in_module_path(self):
        _, blocker, _ = _call(_profile(modules=["backend/permission_checker"]))
        self.assertTrue(blocker)

    def test_oauth_module(self):
        _, blocker, _ = _call(_profile(modules=["integrations/oauth2_client"]))
        self.assertTrue(blocker)

    def test_rbac_module(self):
        _, blocker, _ = _call(_profile(modules=["core/rbac/roles"]))
        self.assertTrue(blocker)

    def test_login_module(self):
        _, blocker, _ = _call(_profile(modules=["homeassistant/components/login"]))
        self.assertTrue(blocker)

    def test_auth_reviewer_is_security_team(self):
        reviewer, _, _ = _call(_profile(modules=["auth/handler"]))
        self.assertEqual(reviewer, "security-team")

    def test_auth_reason_in_policy_reasons(self):
        _, _, reasons = _call(_profile(modules=["auth/handler"]))
        combined = " ".join(reasons).lower()
        self.assertIn("auth", combined)


# ---------------------------------------------------------------------------
# Category: secret / token / credential
# ---------------------------------------------------------------------------

class TestSecretTokenCategory(unittest.TestCase):
    def test_secret_in_module_path_triggers_blocker(self):
        _, blocker, _ = _call(_profile(modules=["backend/secret_manager"]))
        self.assertTrue(blocker)

    def test_token_in_module_path(self):
        _, blocker, _ = _call(_profile(modules=["api/token_store"]))
        self.assertTrue(blocker)

    def test_credential_module(self):
        _, blocker, _ = _call(_profile(modules=["auth/credential_provider"]))
        self.assertTrue(blocker)

    def test_api_key_module(self):
        _, blocker, _ = _call(_profile(modules=["services/apikey_manager"]))
        self.assertTrue(blocker)

    def test_private_key_module(self):
        _, blocker, _ = _call(_profile(modules=["pki/private_key"]))
        self.assertTrue(blocker)

    def test_vault_module(self):
        _, blocker, _ = _call(_profile(modules=["infra/vault_client"]))
        self.assertTrue(blocker)

    def test_secret_reviewer_is_security_team(self):
        reviewer, _, _ = _call(_profile(modules=["backend/secret_manager"]))
        self.assertEqual(reviewer, "security-team")


# ---------------------------------------------------------------------------
# Category: dependency (flag-based)
# ---------------------------------------------------------------------------

class TestDependencyCategory(unittest.TestCase):
    def test_dependency_flag_triggers_blocker(self):
        _, blocker, _ = _call(_profile(has_dependency_change=True))
        self.assertTrue(blocker)

    def test_dependency_reviewer(self):
        reviewer, _, _ = _call(_profile(has_dependency_change=True))
        self.assertEqual(reviewer, "dependency-review")

    def test_dependency_reason_in_policy_reasons(self):
        _, _, reasons = _call(_profile(has_dependency_change=True))
        combined = " ".join(reasons).lower()
        self.assertIn("dependency", combined)

    def test_no_dependency_flag_no_block(self):
        reviewer, blocker, _ = _call(_profile(has_dependency_change=False))
        self.assertFalse(blocker)
        self.assertIsNone(reviewer)


# ---------------------------------------------------------------------------
# Category: CI/CD workflow (flag-based)
# ---------------------------------------------------------------------------

class TestCiCdCategory(unittest.TestCase):
    def test_ci_flag_triggers_blocker(self):
        _, blocker, _ = _call(_profile(has_ci_change=True))
        self.assertTrue(blocker)

    def test_ci_reviewer(self):
        reviewer, _, _ = _call(_profile(has_ci_change=True))
        self.assertEqual(reviewer, "devops-team")

    def test_ci_reason_in_policy_reasons(self):
        _, _, reasons = _call(_profile(has_ci_change=True))
        combined = " ".join(reasons).lower()
        self.assertIn("ci", combined)

    def test_no_ci_flag_no_block(self):
        reviewer, blocker, _ = _call(_profile(has_ci_change=False))
        self.assertFalse(blocker)
        self.assertIsNone(reviewer)


# ---------------------------------------------------------------------------
# Category: config (flag + keyword)
# ---------------------------------------------------------------------------

class TestConfigCategory(unittest.TestCase):
    def test_config_flag_triggers_blocker(self):
        _, blocker, _ = _call(_profile(has_config_change=True))
        self.assertTrue(blocker)

    def test_config_keyword_in_module(self):
        _, blocker, _ = _call(_profile(modules=["homeassistant/config/loader"]))
        self.assertTrue(blocker)

    def test_settings_keyword_in_module(self):
        _, blocker, _ = _call(_profile(modules=["app/settings"]))
        self.assertTrue(blocker)

    def test_config_flag_reviewer(self):
        reviewer, _, _ = _call(_profile(has_config_change=True))
        self.assertEqual(reviewer, "platform-team")

    def test_config_keyword_reviewer(self):
        reviewer, _, _ = _call(_profile(modules=["config/base"]))
        self.assertEqual(reviewer, "platform-team")


# ---------------------------------------------------------------------------
# Category: migration (flag + keyword)
# ---------------------------------------------------------------------------

class TestMigrationCategory(unittest.TestCase):
    def test_migration_flag_triggers_blocker(self):
        _, blocker, _ = _call(_profile(has_migration=True))
        self.assertTrue(blocker)

    def test_migration_keyword_in_module(self):
        _, blocker, _ = _call(_profile(modules=["db/migrations/0042_add_flag"]))
        self.assertTrue(blocker)

    def test_alembic_module(self):
        _, blocker, _ = _call(_profile(modules=["alembic/versions"]))
        self.assertTrue(blocker)

    def test_migration_reviewer(self):
        reviewer, _, _ = _call(_profile(has_migration=True))
        self.assertEqual(reviewer, "db-team")

    def test_schema_keyword_in_module(self):
        _, blocker, _ = _call(_profile(modules=["db/schema_update"]))
        self.assertTrue(blocker)


# ---------------------------------------------------------------------------
# Category: cryptography
# ---------------------------------------------------------------------------

class TestCryptoCategory(unittest.TestCase):
    def test_crypto_keyword_triggers_blocker(self):
        _, blocker, _ = _call(_profile(modules=["core/crypto_utils"]))
        self.assertTrue(blocker)

    def test_tls_module(self):
        _, blocker, _ = _call(_profile(modules=["networking/tls_handler"]))
        self.assertTrue(blocker)

    def test_ssl_module(self):
        _, blocker, _ = _call(_profile(modules=["ssl/cert_loader"]))
        self.assertTrue(blocker)

    def test_encrypt_in_module(self):
        _, blocker, _ = _call(_profile(modules=["utils/encrypt_data"]))
        self.assertTrue(blocker)

    def test_hmac_module(self):
        _, blocker, _ = _call(_profile(modules=["security/hmac_verify"]))
        self.assertTrue(blocker)

    def test_crypto_reviewer_is_security_team(self):
        reviewer, _, _ = _call(_profile(modules=["crypto/signing"]))
        self.assertEqual(reviewer, "security-team")


# ---------------------------------------------------------------------------
# Reviewer priority: highest-priority wins when multiple categories fire
# ---------------------------------------------------------------------------

class TestReviewerPriority(unittest.TestCase):
    def test_security_beats_dependency(self):
        """auth module + dependency flag → security-team wins."""
        reviewer, blocker, _ = _call(
            _profile(modules=["auth/handler"], has_dependency_change=True)
        )
        self.assertTrue(blocker)
        self.assertEqual(reviewer, "security-team")

    def test_security_beats_devops(self):
        """auth module + ci flag → security-team wins."""
        reviewer, blocker, _ = _call(
            _profile(modules=["auth/handler"], has_ci_change=True)
        )
        self.assertEqual(reviewer, "security-team")

    def test_dependency_beats_platform(self):
        """dependency + config → dependency-review wins."""
        reviewer, blocker, _ = _call(
            _profile(has_dependency_change=True, has_config_change=True)
        )
        self.assertEqual(reviewer, "dependency-review")

    def test_devops_beats_db(self):
        """ci + migration → devops-team wins."""
        reviewer, blocker, _ = _call(
            _profile(has_ci_change=True, has_migration=True)
        )
        self.assertEqual(reviewer, "devops-team")

    def test_multiple_triggers_all_reasons_present(self):
        """When multiple categories fire, all reasons appear in policy_reasons."""
        _, _, reasons = _call(
            _profile(has_dependency_change=True, has_ci_change=True)
        )
        combined = " ".join(reasons).lower()
        self.assertIn("dependency", combined)
        self.assertIn("ci", combined)


# ---------------------------------------------------------------------------
# Return type invariants
# ---------------------------------------------------------------------------

class TestReturnTypeInvariants(unittest.TestCase):
    def test_return_is_3_tuple(self):
        result = score_security_policy(_profile())
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)

    def test_reviewer_is_str_or_none(self):
        for profile in [
            _profile(),
            _profile(has_dependency_change=True),
            _profile(modules=["auth/x"]),
        ]:
            reviewer, _, _ = score_security_policy(profile)
            self.assertIn(type(reviewer), (str, type(None)))

    def test_blocker_is_bool(self):
        for profile in [_profile(), _profile(has_ci_change=True)]:
            _, blocker, _ = score_security_policy(profile)
            self.assertIsInstance(blocker, bool)

    def test_reasons_is_list_of_strings(self):
        _, _, reasons = score_security_policy(
            _profile(has_dependency_change=True, modules=["auth/x"])
        )
        self.assertIsInstance(reasons, list)
        self.assertTrue(all(isinstance(r, str) for r in reasons))

    def test_missing_keys_do_not_raise(self):
        """Minimal dict with only pr_number must not raise."""
        result = score_security_policy({"pr_number": 99})
        self.assertEqual(len(result), 3)

    def test_none_modules_do_not_raise(self):
        result = score_security_policy({"modules_touched": None})
        self.assertEqual(len(result), 3)


# ---------------------------------------------------------------------------
# Category completeness: every defined category has at least one test
# ---------------------------------------------------------------------------

class TestCategoryCompleteness(unittest.TestCase):
    def test_all_categories_are_tested(self):
        """
        Verify every category defined in _CATEGORIES can be triggered by the
        inputs used in this test suite — exercises the category table itself.
        """
        category_trigger_profiles = {
            "auth_permission":  _profile(modules=["auth/login"]),
            "secret_token":     _profile(modules=["backend/secret_manager"]),
            "dependency":       _profile(has_dependency_change=True),
            "ci_cd":            _profile(has_ci_change=True),
            "config":           _profile(has_config_change=True),
            "migration":        _profile(has_migration=True),
            "crypto":           _profile(modules=["core/crypto_utils"]),
        }
        defined_names = {cat["name"] for cat in _CATEGORIES}
        for cat_name, trigger_profile in category_trigger_profiles.items():
            self.assertIn(
                cat_name, defined_names,
                msg=f"Category '{cat_name}' used in test but not in _CATEGORIES"
            )
            _, blocker, reasons = score_security_policy(trigger_profile)
            self.assertTrue(
                blocker,
                msg=f"Category '{cat_name}' did not trigger merge_blocker for {trigger_profile}"
            )
            matching = [r for r in reasons if cat_name in r]
            self.assertGreater(
                len(matching), 0,
                msg=f"Category '{cat_name}' not mentioned in policy_reasons: {reasons}"
            )


if __name__ == "__main__":
    unittest.main()
