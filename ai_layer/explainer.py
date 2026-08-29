"""
ai_layer/explainer.py

Generates a human-readable Indonesian explanation for why a PR received its
priority label, using IBM watsonx.ai (Granite model).

Design constraints
------------------
* The model MUST NOT alter the numeric score or label supplied to it.
  The system prompt enforces this explicitly.
* If the model's output mentions a score or label that differs from the
  authoritative priority_result, the call is retried (up to MAX_RETRIES times).
* After all retries are exhausted, a deterministic template explanation is
  returned — no AI output is used, so the caller always gets a valid string.
* ibm_watsonx_ai is imported at module level (guarded by try/except) so that
  unit tests can patch ai_layer.explainer.Credentials and
  ai_layer.explainer.ModelInference without the SDK needing to be installed.

Public API
----------
call_explainer(pr_data, priority_result, blast_radius_result, security_result)
    -> str

validate_explanation_consistency(explanation, priority_result)
    -> bool
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from dotenv import load_dotenv

from ai_layer.document_understanding import extract_pr_intent

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SDK import — guarded so the module loads even when ibm_watsonx_ai is absent.
# Unit tests patch Credentials and ModelInference at ai_layer.explainer level.
# ---------------------------------------------------------------------------
try:
    from ibm_watsonx_ai import Credentials
    from ibm_watsonx_ai.foundation_models import ModelInference
except ImportError:  # pragma: no cover
    Credentials = None      # type: ignore[assignment,misc]
    ModelInference = None   # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL_ID = "ibm/granite-4-h-small"
MAX_RETRIES = 2          # retry limit before falling back to template
MAX_NEW_TOKENS = 350

GENERATE_PARAMS = {
    "max_new_tokens": MAX_NEW_TOKENS,
    "temperature": 0.2,  # low temperature → deterministic, factual output
}

# Chat params use slightly different key names for the chat endpoint
_CHAT_PARAMS = {
    "max_tokens": MAX_NEW_TOKENS,
    "temperature": 0.2,
}

_LABEL_TO_ID: dict[str, str] = {
    "Low": "Low",
    "Medium": "Medium",
    "High": "High",
    "Critical": "Critical",
}

# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
Kamu adalah asisten review PR (pull request) yang membantu tim engineering.
Tugasmu HANYA menjelaskan mengapa PR ini mendapat priority_label dan skor yang \
sudah dihitung oleh sistem — JANGAN mengubah, mempertanyakan, atau mengoreksi \
angka score maupun label yang diberikan kepadamu.
Jawab dalam Bahasa Indonesia, maksimal 5 kalimat, ringkas dan informatif.
Sertakan saran reviewer yang tepat berdasarkan konteks yang diberikan.\
"""


def _build_user_prompt(
    pr_data: dict[str, Any],
    priority_result: tuple[int, str],
    blast_radius_result: tuple,
    security_result: tuple,
    pr_intent: dict[str, Any] | None = None,
) -> str:
    priority_score, priority_label = priority_result
    br_score, br_label = blast_radius_result[0], blast_radius_result[1]
    modules = blast_radius_result[2] if len(blast_radius_result) > 2 else []
    required_reviewer, merge_blocker, sec_reasons = security_result

    pr_number = pr_data.get("pr_number", "N/A")
    files_changed = pr_data.get("files_changed", 0)
    additions = pr_data.get("additions", 0)
    deletions = pr_data.get("deletions", 0)
    has_migration = pr_data.get("has_migration", False)
    has_config = pr_data.get("has_config_change", False)
    has_dep = pr_data.get("has_dependency_change", False)
    has_ci = pr_data.get("has_ci_change", False)

    sec_summary = (
        f"merge_blocker={merge_blocker}, "
        f"reviewer_yang_disarankan={required_reviewer or 'tidak ada'}"
    )
    if sec_reasons:
        sec_summary += f", alasan_keamanan=[{'; '.join(sec_reasons[:2])}]"

    modules_str = ", ".join(modules[:5]) if modules else "tidak ada"

    # Enrich prompt with structured PR intent when available
    intent_lines = ""
    if pr_intent:
        proposed = pr_intent.get("proposed_change") or ""
        change_type = pr_intent.get("change_type") or "other"
        if proposed:
            intent_lines = (
                f"\nRingkasan perubahan PR (dari deskripsi):\n"
                f"- proposed_change: {proposed}\n"
                f"- change_type: {change_type}"
            )

    return f"""\
Data PR #{pr_number}:
- files_changed: {files_changed}, additions: {additions}, deletions: {deletions}
- modules_touched: {modules_str}
- has_migration: {has_migration}, has_config_change: {has_config}, \
has_dependency_change: {has_dep}, has_ci_change: {has_ci}{intent_lines}

Hasil scoring sistem:
- blast_radius_score: {br_score}, blast_radius_label: {br_label}
- priority_score: {priority_score} (skala 0-100)
- priority_label: {priority_label}
- security: {sec_summary}

Jelaskan dalam Bahasa Indonesia mengapa PR ini mendapat priority_label \
"{priority_label}" dengan priority_score {priority_score}. \
Sebutkan reviewer yang disarankan jika ada. \
Gunakan konteks proposed_change dan change_type di atas dalam penjelasanmu jika tersedia. \
JANGAN mengubah angka atau label di atas.\
"""


# ---------------------------------------------------------------------------
# Consistency validator
# ---------------------------------------------------------------------------

def validate_explanation_consistency(
    explanation: str,
    priority_result: tuple[int, str],
) -> bool:
    """
    Return True if the explanation text is consistent with priority_result.

    Checks (label first, then score):
    1. If an English priority label word (Low/Medium/High/Critical) appears
       in a scoring context — i.e. preceded or followed by "label", "priority",
       or "skor" — it must match priority_result[1].
    2. If a number appears in a clear score context (adjacent to "skor",
       "score", "poin", or "nilai") it must match priority_result[0].

    Numbers that appear in other contexts (PR number, file count, churn, year,
    etc.) are intentionally ignored so the validator does not produce false
    positives on normal explanatory prose.
    """
    priority_score, priority_label = priority_result

    # --- Label check ---
    # Match patterns like:
    #   priority_label "Critical"   priority_label: High   label=Medium
    #   label "Critical"            prioritas Critical
    # Strategy: scan for any priority-label word (Low/Medium/High/Critical)
    # that is immediately preceded (within 30 chars) by a label-context keyword.
    label_keywords_re = re.compile(
        r'(?:priority_label|prioritas|label)\b',
        re.IGNORECASE,
    )
    label_values_re = re.compile(
        r'\b(' + '|'.join(_LABEL_TO_ID.keys()) + r')\b',
        re.IGNORECASE,
    )
    # Collect positions of label-context keywords
    keyword_positions = [m.end() for m in label_keywords_re.finditer(explanation)]
    for val_match in label_values_re.finditer(explanation):
        word = val_match.group(1)
        val_start = val_match.start()
        # Check if any label keyword appears within 30 chars before this value
        in_context = any(
            0 <= val_start - kw_end <= 30
            for kw_end in keyword_positions
        )
        if in_context and word != priority_label:
            logger.warning(
                "Consistency check failed: explanation mentions label '%s' "
                "in label context but priority_label is '%s'.",
                word,
                priority_label,
            )
            return False

    # --- Score check ---
    # Only flag numbers that sit near score-context keywords.
    score_context = re.compile(
        r"(?:priority_score|skor|score|poin|nilai)\s*[=:\"]?\s*(\d{1,3})",
        re.IGNORECASE,
    )
    for match in score_context.finditer(explanation):
        num = int(match.group(1))
        if 0 <= num <= 100 and num != priority_score:
            logger.warning(
                "Consistency check failed: explanation mentions score %d "
                "in score context but priority_score is %d.",
                num,
                priority_score,
            )
            return False

    return True


# ---------------------------------------------------------------------------
# Fallback template (no AI)
# ---------------------------------------------------------------------------

def _build_fallback_explanation(
    pr_data: dict[str, Any],
    priority_result: tuple[int, str],
    blast_radius_result: tuple,
    security_result: tuple,
) -> str:
    """
    Deterministic Indonesian explanation built entirely from structured fields.
    Used when watsonx is unavailable or returns inconsistent output.
    """
    priority_score, priority_label = priority_result
    br_score, br_label = blast_radius_result[0], blast_radius_result[1]
    modules = blast_radius_result[2] if len(blast_radius_result) > 2 else []
    required_reviewer, merge_blocker, sec_reasons = security_result

    pr_number = pr_data.get("pr_number", "N/A")
    files_changed = pr_data.get("files_changed", 0)
    additions = pr_data.get("additions", 0)
    deletions = pr_data.get("deletions", 0)

    parts: list[str] = [
        f"PR #{pr_number} mendapat priority_label \"{priority_label}\" "
        f"dengan skor {priority_score}/100.",
    ]

    if br_label == "multi_module":
        mod_list = ", ".join(modules[:3]) if modules else "beberapa modul"
        parts.append(
            f"Blast radius tergolong multi_module (indeks {br_score}) karena PR ini "
            f"menyentuh lebih dari satu modul substantif: {mod_list}."
        )
    else:
        parts.append(
            f"Blast radius tergolong small_or_local (indeks {br_score}), "
            f"perubahan terlokalisasi dalam satu modul."
        )

    churn = additions + deletions
    parts.append(
        f"Total perubahan: {files_changed} file, "
        f"{additions} baris tambahan, {deletions} baris dihapus "
        f"(churn {churn} baris)."
    )

    if merge_blocker:
        reviewer_str = required_reviewer or "tim terkait"
        reasons_str = "; ".join(sec_reasons[:2]) if sec_reasons else "perubahan sensitif terdeteksi"
        parts.append(
            f"⚠ PR ini memerlukan review wajib dari {reviewer_str} sebelum dapat di-merge. "
            f"Alasan: {reasons_str}."
        )
    elif required_reviewer:
        parts.append(
            f"Disarankan melibatkan {required_reviewer} dalam review PR ini."
        )

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def call_explainer(
    pr_data: dict[str, Any],
    priority_result: tuple[int, str],
    blast_radius_result: tuple,
    security_result: tuple,
) -> str:
    """
    Generate an Indonesian explanation for the PR's priority label.

    Calls watsonx.ai (Granite) with temperature=0.2.  If the response
    mentions an inconsistent score or label, retries up to MAX_RETRIES times.
    If all retries are exhausted, returns a deterministic fallback string.

    Args:
        pr_data:             Dict from ingestion.github_pr.get_pr_diff_profile.
        priority_result:     (priority_score, priority_label) from combine_priority.
        blast_radius_result: 4-tuple from score_blast_radius.
        security_result:     3-tuple from score_security_policy.

    Returns:
        str — Indonesian explanation (AI-generated or fallback template).
    """
    api_key    = os.getenv("WATSONX_API_KEY")
    url        = os.getenv("WATSONX_URL")
    project_id = os.getenv("WATSONX_PROJECT_ID")

    if not all([api_key, url, project_id]):
        logger.warning(
            "watsonx credentials incomplete — returning fallback explanation."
        )
        return _build_fallback_explanation(
            pr_data, priority_result, blast_radius_result, security_result
        )

    pr_description = pr_data.get("pr_description", "")
    pr_intent = extract_pr_intent(pr_description) if pr_description else None

    user_prompt = _build_user_prompt(
        pr_data, priority_result, blast_radius_result, security_result,
        pr_intent=pr_intent,
    )
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ]

    credentials = Credentials(url=url, api_key=api_key)
    model = ModelInference(
        model_id=MODEL_ID,
        credentials=credentials,
        project_id=project_id,
    )

    last_explanation: str = ""
    for attempt in range(1, MAX_RETRIES + 2):  # attempts: 1, 2, 3 (= 1 + MAX_RETRIES)
        try:
            raw = model.chat(messages=messages, params=_CHAT_PARAMS)
            # chat() returns {"choices": [{"message": {"content": "..."}}], ...}
            if isinstance(raw, dict):
                choices = raw.get("choices") or []
                explanation = (
                    choices[0].get("message", {}).get("content", "")
                    if choices else ""
                ).strip()
            else:
                explanation = str(raw).strip()
        except Exception as exc:
            logger.error(
                "watsonx call failed on attempt %d/%d: %s",
                attempt, MAX_RETRIES + 1, exc,
            )
            break

        if validate_explanation_consistency(explanation, priority_result):
            return explanation

        last_explanation = explanation
        if attempt <= MAX_RETRIES:
            logger.warning(
                "Inconsistent explanation on attempt %d — retrying (%d left).",
                attempt,
                MAX_RETRIES - attempt + 1,
            )
        else:
            logger.warning(
                "All %d attempts returned inconsistent explanations — "
                "falling back to template.",
                MAX_RETRIES + 1,
            )

    return _build_fallback_explanation(
        pr_data, priority_result, blast_radius_result, security_result
    )
