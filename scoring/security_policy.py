"""
scoring/security_policy.py

Security-policy guardrail for pull-request diff profiles.

Design principle
----------------
This module is a GUARDRAIL, not a fast-lane generator.
``score_security_policy`` never returns a state that permits auto-merge.
Every code path either:
  - raises ``merge_blocker=True``  (human review mandatory before merge), or
  - returns ``merge_blocker=False`` with ``required_reviewer=None``
    (no explicit block, but auto-merge is still not implied).

The only correct interpretation of ``merge_blocker=False`` is
"no *additional* security policy block detected at this time" — it is NOT
"safe to merge automatically".

Public API
----------
score_security_policy(diff_profile)
    -> tuple[str | None, bool, list[str]]

    Returns:
        required_reviewer  – suggested reviewer role string, or None.
        merge_blocker      – True  → PR MUST NOT be merged without human sign-off.
                             False → no security-policy block (merge decision
                                     belongs to the regular review process).
        policy_reasons     – Human-readable list of triggered policy rules.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Category definitions
# ---------------------------------------------------------------------------
# Each category maps to:
#   keywords     – substrings matched (case-insensitive) against each entry
#                  in modules_touched
#   flag_fields  – diff_profile boolean fields that trigger this category
#   reviewer     – recommended reviewer role when this category is flagged
#   blocker      – whether this category makes merge_blocker=True
#
# RATIONALE FOR BLOCKER STATUS:
#   auth/secret/token/permission  – credential or access-control surface;
#       any mistake here can be exploited without a visible diff artefact.
#   dependency                    – supply-chain attack vector; must be
#       verified against a known-good lock file or advisory database.
#   ci_cd                         – pipeline compromise = arbitrary code
#       execution in CI; very high blast radius if tampered with.
#   config                        – misconfiguration can silently degrade
#       security posture (e.g. debug mode left on, TLS disabled).
#   migration                     – irreversible schema changes; data loss
#       or privilege escalation via DB state cannot be rolled back easily.
#   secret_file                   – literal secret/credential filenames in
#       the repo are an immediate exfiltration risk.

_CATEGORIES: list[dict] = [
    # --- authentication / authorisation / secrets ---
    {
        "name": "auth_permission",
        "description": "Authentication, authorisation, or permission surface",
        "module_keywords": (
            "auth", "authn", "authz", "permission", "privilege",
            "rbac", "acl", "access_control", "iam", "oauth",
            "sso", "mfa", "2fa", "login", "logout", "session",
        ),
        "flag_fields": (),
        "reviewer": "security-team",
        "blocker": True,
    },
    # --- secrets / credentials / tokens ---
    {
        "name": "secret_token",
        "description": "Secret, credential, API key, or token handling",
        "module_keywords": (
            "secret", "token", "credential", "api_key", "apikey",
            "password", "passwd", "private_key", "cert", "vault",
            "keyring", "keystore", "signing",
        ),
        "flag_fields": (),
        "reviewer": "security-team",
        "blocker": True,
    },
    # --- dependency / supply-chain ---
    {
        "name": "dependency",
        "description": "Dependency or supply-chain change",
        "module_keywords": (),           # handled via flag
        "flag_fields": ("has_dependency_change",),
        "reviewer": "dependency-review",
        "blocker": True,
    },
    # --- CI/CD pipeline ---
    {
        "name": "ci_cd",
        "description": "CI/CD pipeline or build workflow change",
        "module_keywords": (),           # handled via flag
        "flag_fields": ("has_ci_change",),
        "reviewer": "devops-team",
        "blocker": True,
    },
    # --- configuration ---
    {
        "name": "config",
        "description": "Configuration or settings change",
        "module_keywords": (
            "config", "configuration", "settings", "env",
            "dotenv", "environ",
        ),
        "flag_fields": ("has_config_change",),
        "reviewer": "platform-team",
        "blocker": True,
    },
    # --- database migrations ---
    {
        "name": "migration",
        "description": "Database migration (irreversible schema change)",
        "module_keywords": (
            "migration", "migrate", "alembic", "flyway",
            "db/migrate", "schema",
        ),
        "flag_fields": ("has_migration",),
        "reviewer": "db-team",
        "blocker": True,
    },
    # --- cryptography ---
    {
        "name": "crypto",
        "description": "Cryptography or hashing implementation",
        "module_keywords": (
            "crypto", "cryptography", "encrypt", "decrypt",
            "hash", "hmac", "cipher", "tls", "ssl",
        ),
        "flag_fields": (),
        "reviewer": "security-team",
        "blocker": True,
    },
]

# Reviewer priority order: when multiple categories are triggered, the
# reviewer with the highest priority (lowest index) is surfaced.
_REVIEWER_PRIORITY: list[str] = [
    "security-team",       # highest: credential / auth / crypto risk
    "dependency-review",   # supply-chain
    "devops-team",         # CI pipeline
    "db-team",             # schema changes
    "platform-team",       # config
]


def _reviewer_rank(reviewer: str | None) -> int:
    """Lower rank = higher priority."""
    try:
        return _REVIEWER_PRIORITY.index(reviewer)
    except ValueError:
        return len(_REVIEWER_PRIORITY)


def score_security_policy(
    diff_profile: dict[str, Any],
) -> tuple[str | None, bool, list[str]]:
    """
    Evaluate security-policy rules for a pull request.

    This function is a GUARDRAIL — it NEVER produces a condition that
    permits auto-merge.  A return of ``merge_blocker=False`` means no
    *additional* security-policy block was detected; the regular review
    process still applies.

    Args:
        diff_profile: Dict matching the schema produced by
            ``ingestion.github_pr.get_pr_diff_profile``.

    Returns:
        A 3-tuple:
        - **required_reviewer** (str | None): Recommended reviewer role for
          the highest-priority triggered category, or None if no category fires.
        - **merge_blocker** (bool): True if this PR MUST NOT be merged without
          explicit human sign-off from the required_reviewer.  A value of False
          does NOT imply auto-merge is safe.
        - **policy_reasons** (list[str]): Human-readable descriptions of every
          triggered policy rule — useful for audit trails and PR comments.
    """
    modules: list[str] = [
        m.lower() for m in (diff_profile.get("modules_touched") or [])
    ]

    triggered_reviewers: list[str] = []
    policy_reasons: list[str] = []
    any_blocker = False

    for cat in _CATEGORIES:
        fired = False
        fire_reasons: list[str] = []

        # 1. Module keyword match
        kw_hits = [
            kw for kw in cat["module_keywords"]
            if any(kw in mod for mod in modules)
        ]
        if kw_hits:
            fired = True
            matching_modules = [
                m for m in modules
                if any(kw in m for kw in kw_hits)
            ]
            fire_reasons.append(
                f"[{cat['name']}] Module keyword match "
                f"({', '.join(kw_hits)}) in: {', '.join(matching_modules)}."
            )

        # 2. Boolean flag match
        for field in cat["flag_fields"]:
            if diff_profile.get(field):
                fired = True
                fire_reasons.append(
                    f"[{cat['name']}] Flag '{field}' is set — "
                    f"{cat['description']}."
                )

        if fired:
            for reason in fire_reasons:
                policy_reasons.append(reason)
            if cat["blocker"]:
                any_blocker = True
                triggered_reviewers.append(cat["reviewer"])

    # Select the highest-priority reviewer across all triggered categories.
    required_reviewer: str | None = None
    if triggered_reviewers:
        required_reviewer = min(triggered_reviewers, key=_reviewer_rank)

    return required_reviewer, any_blocker, policy_reasons
