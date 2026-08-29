<!-- Excerpt from full session (bob_sessions/00_full_session_raw.md), lines 2080-2966 -->
<!-- Modules built in this segment: scoring/security_policy.py + priority/combine.py -->

Buatkan module scoring/security_policy.py dengan fungsi score_security_policy(diff_profile) yang mengembalikan (required_reviewer: str atau None, merge_blocker: bool, policy_reason: list of string). Deteksi berdasarkan keyword/path pada modules_touched dan flag has_config_change/has_dependency_change/has_ci_change dari input: kategori auth/permission/secret/token, dependency file, CI/CD workflow, config, migration. Fungsi ini TIDAK BOLEH pernah menghasilkan kondisi yang mengizinkan auto-merge — ini guardrail, bukan fast-lane generator. Buat unit test di tests/test_security_policy.py mencakup semua kategori sensitif di atas, plus 1 test eksplisit yang assert tidak ada return value yang mengandung field/kondisi auto-merge=true dalam bentuk apapun." Jalankan: pytest tests/test_security_policy.py -v

---

### 🤖 Assistant

> 🔧 called: read_file, read_file



> 🔧 **read_file** — scoring/blast_radius.py

> 🔧 **read_file** — data/home_assistant_100prs.json

### 🤖 Assistant

> 🔧 called: write_file, write_file, execute_command

Good — I have a clear picture of the schema. Now build the module and tests:

> 🔧 **write_file** — scoring/security_policy.py

> 🔧 **write_file** — tests/test_security_policy.py

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && .venv/bin/python -m pytest tests/test_security_policy.py -v 2>&1

### 🤖 Assistant

**57/57 passed.** Berikut ringkasan arsitektur:

---

## [`scoring/security_policy.py`](scoring/security_policy.py)

**Fungsi:** `score_security_policy(diff_profile) → (required_reviewer, merge_blocker, policy_reasons)`

### 7 Kategori sensitif

| Kategori | Deteksi via | Reviewer | Blocker |
|---|---|---|---|
| `auth_permission` | keyword: `auth`, `permission`, `rbac`, `oauth`, `session`, `login`, … | `security-team` | ✅ |
| `secret_token` | keyword: `secret`, `token`, `credential`, `api_key`, `vault`, `signing`, … | `security-team` | ✅ |
| `dependency` | flag `has_dependency_change` | `dependency-review` | ✅ |
| `ci_cd` | flag `has_ci_change` | `devops-team` | ✅ |
| `config` | flag `has_config_change` + keyword `config`, `settings`, `env` | `platform-team` | ✅ |
| `migration` | flag `has_migration` + keyword `migration`, `alembic`, `schema` | `db-team` | ✅ |
| `crypto` | keyword: `crypto`, `tls`, `ssl`, `encrypt`, `hmac`, `cipher`, … | `security-team` | ✅ |

**Reviewer priority** (saat multiple kategori trigger): `security-team` > `dependency-review` > `devops-team` > `db-team` > `platform-team`

### Kontrak Guardrail

Setiap code path menghasilkan salah satu dari dua kondisi:
- `merge_blocker=True` → human review wajib sebelum merge
- `merge_blocker=False` → tidak ada security block **tambahan** (bukan lampu hijau auto-merge)

Kontrak ini dibuktikan secara eksplisit oleh [`TestGuardrailNoAutoMerge`](tests/test_security_policy.py:55) yang:
1. Memindai semua return value dari 9 profil representatif terhadap kata terlarang (`auto_merge`, `automerge`, `fast_lane`, dll.)
2. Memverifikasi `merge_blocker=False` hanya berarti "tidak ada block tambahan", bukan persetujuan
3. Memastikan return selalu 3-tuple — field ke-4 bernama `auto_merge` tidak bisa diam-diam ditambahkan

---

### 👤 User

Buatkan module priority/combine.py dengan fungsi combine_priority(blast_radius_result, security_result, evidence_result=None) yang mengembalikan (priority_score: int 0-100, priority_label: 'Low'/'Medium'/'High'/'Critical'). Formula: priority_score = 0.5*blast_radius_score + 0.3*evidence_gap_score (pakai nilai netral 50 kalau evidence_result None) + 0.2*security_weight (100 kalau ada merge_blocker, 50 kalau ada required_reviewer, 0 kalau tidak ada). PENTING: kalau security_result.merge_blocker True, priority_label harus 'Critical' tanpa terkecuali, apapun nilai priority_score-nya. Buat unit test di tests/test_priority.py mencakup kombinasi: PR kecil aman, PR besar aman, PR kecil tapi sensitif (merge_blocker), PR besar dan sensitif." Jalankan: pytest tests/test_priority.py -v

---

### 🤖 Assistant

> 🔧 called: list_files, write_file, write_file, execute_command



> 🔧 **list_files** — priority

> 🔧 **write_file** — """
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


> 🔧 **write_file** — """
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


> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && .venv/bin/python -m pytest tests/test_priority.py -v 2>&1

### 🤖 Assistant

**32/32 passed.** Berikut ringkasannya:

---

## [`priority/combine.py`](priority/combine.py)

**Fungsi:** `combine_priority(blast_radius_result, security_result, evidence_result=None) → (priority_score, priority_label)`

### Formula

```
priority_score = round(
    0.5 × blast_radius_score
  + 0.3 × evidence_gap_score   (default 50 jika None)
  + 0.2 × security_weight
)
```

| `security_weight` | Kondisi |
|---|---|
| `100` | `merge_blocker = True` |
| `50` | `required_reviewer` ada, tapi tidak blocker |
| `0` | Tidak ada security concern |

### Label thresholds

| Score | Label |
|---|---|
| ≥ 80 | **Critical** |
| 60–79 | **High** |
| 40–59 | **Medium** |
| 0–39 | **Low** |

### Override rule (unconditional)

```python
if merge_blocker:
    priority_label = "Critical"   # always, regardless of score
```

Tidak ada kombinasi nilai blast-radius rendah + evidence rendah yang bisa menurunkan PR yang punya `merge_blocker=True` dari Critical. Override ini ditest oleh `test_merge_blocker_override_is_unconditional` yang sweeping semua blast score 0–100 step 10.

---

## 32 Unit Tests — coverage map

| Class | Skenario |
|---|---|
| `TestSmallSafePR` | PR kecil aman → Low, formula match |
| `TestLargeSafePR` | PR besar aman → skor tinggi, label sesuai |
| `TestSmallPRWithMergeBlocker` | PR kecil + blocker → Critical override (incl. sweep 0→100) |
| `TestLargeAndSensitivePR` | PR besar + blocker → Critical + skor formula |
| `TestRequiredReviewerNoBLocker` | reviewer ada tapi bukan blocker → skor naik, TIDAK force Critical |
| `TestEvidenceWiring` | evidence None=neutral, sweep 0/25/50/75/100 |
| `TestLabelThresholds` | boundary: 0, <40, 40, 60, 80 |
| `TestScoreClamping` | clamp ke [0, 100], tipe `int` |
| `TestReturnTypeInvariants` | 2-tuple, tipe elemen, label valid untuk semua kombinasi |

---

### 👤 User

Buatkan script scripts/fetch_vscode_100.py yang memanggil fetch_pr_list('microsoft', 'vscode', since='2026-03-01', until='2026-08-27') dari ingestion/github_pr.py, ambil 100 PR pertama, panggil get_pr_diff_profile() untuk masing-masing, simpan ke data/vscode_100prs.json (json.dump indent=2). Tampilkan progress setiap 10 PR. Baca GITHUB_TOKEN dari .env, tangani rate limit sama seperti script sebelumnya." Jalankan: python scripts/fetch_vscode_100.py (~5 menit, sabar)

---

### 🤖 Assistant

> 🔧 called: read_file, write_file



> 🔧 **read_file** — scripts/fetch_ha_core_100.py

> 🔧 **write_file** — """
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


### 🤖 Assistant

> 🔧 called: execute_command

Script siap. Menjalankan sekarang:

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && .venv/bin/python scripts/fetch_vscode_100.py 2>&1

### 🤖 Assistant

> 🔧 called: execute_command

Selesai tanpa error. Verifikasi cepat isi dataset:

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && .venv/bin/python -c "
import json
data = json.load(open('data/vscode_100prs.json'))
print(f'Total PR saved : {len(data)}')
print()

dep   = sum(1 for p in data if p['has_dependency_change'])
cfg   = sum(1 for p in data if p['has_config_change'])
ci    = sum(1 for p in data if p['has_ci_change'])
mig   = sum(1 for p in data if p['has_migration'])
add   = sum(p['additions'] for p in data)
rem   = sum(p['deletions'] for p in data)
print(f'has_dependency_change : {dep}/100')
print(f'has_config_change     : {cfg}/100')
print(f'has_ci_change         : {ci}/100')
print(f'has_migration         : {mig}/100')
print(f'Total additions       : {add:,}')
print(f'Total deletions       : {rem:,}')
print()

from collections import Counter
mods = Counter()
for p in data:
    for m in p['modules_touched']:
        mods[m] += 1
print('Top 10 modules touched:')
for mod, cnt in mods.most_common(10):
    print(f'  {cnt:>3}x  {mod}')
"


### 🤖 Assistant

**100 PR tersimpan ke [`data/vscode_100prs.json`](data/vscode_100prs.json) — 0 error.**

Ringkasan statistik `microsoft/vscode` vs `home-assistant/core`:

| Metrik | **vscode** | **home-assistant/core** |
|---|---|---|
| PR dalam window | 15.105 | 10.521 |
| `has_dependency_change` | 9% | 20% |
| `has_config_change` | 2% | — |
| `has_ci_change` | 3% | 0% |
| `has_migration` | 0% | 0% |
| Total additions | 48.114 | 65.812 |
| Total deletions | 9.850 | 10.659 |

Karakteristik berbeda: vscode lebih monolitik (`src` mendominasi 82%), sedangkan HA lebih modular (banyak komponen individual). Dataset vscode ini siap dipakai untuk validasi lintas-repo pada scoring pipeline.

---

### 👤 User

