"""
ai_layer/document_understanding.py

Extracts structured intent from a raw GitHub PR description using
IBM watsonx.ai (Granite model).

GitHub PR descriptions are typically filled with HTML comments, checkbox
templates, and boilerplate.  This module uses the LLM to parse through
the noise and return a clean, structured representation.

Public API
----------
extract_pr_intent(pr_description: str) -> dict

    Returns a dict with:
        proposed_change  – str: 1-2 sentence summary of what the PR changes.
        change_type      – str | None: one of
                             'dependency_upgrade' | 'bugfix' | 'new_feature' |
                             'breaking_change'   | 'code_quality' | 'other'
        is_breaking_change – bool | None: True if the PR is a breaking change.

    On JSON parse failure, returns a safe fallback dict:
        proposed_change    = pr_description[:200]
        change_type        = None
        is_breaking_change = None
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SDK import — guarded so the module loads even when ibm_watsonx_ai is absent.
# Unit tests patch Credentials and ModelInference at this module's namespace.
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

_CHAT_PARAMS: dict[str, Any] = {
    "max_tokens": 300,
    "temperature": 0.0,  # zero temperature → maximally deterministic JSON output
}

# Valid change_type values (lowercase, normalised)
_VALID_CHANGE_TYPES = frozenset({
    "dependency_upgrade",
    "bugfix",
    "new_feature",
    "breaking_change",
    "code_quality",
    "other",
})

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a code-review assistant.  Your ONLY task is to parse a GitHub Pull
Request description and return a JSON object — nothing else, no explanation,
no prose, no markdown fences.

The JSON object must have exactly these three fields:
  "proposed_change"    – string, 1–2 sentences summarising what the PR changes.
  "change_type"        – one of: "dependency_upgrade", "bugfix", "new_feature",
                         "breaking_change", "code_quality", "other".
                         Infer from the checked checkbox [x] in the description.
  "is_breaking_change" – boolean, true only if the PR is a breaking change.

Rules:
- Ignore all HTML comments (<!-- ... -->), unchecked checkboxes ([ ]), and
  boilerplate template text.
- Focus on the "Proposed change" section and the checked [x] checkbox under
  "Type of change".
- Return ONLY valid JSON — no markdown code fences, no extra keys.\
"""


def _build_user_prompt(pr_description: str) -> str:
    # Truncate very long descriptions to avoid exceeding token limits.
    truncated = pr_description[:4000] if len(pr_description) > 4000 else pr_description
    return f"Parse this GitHub PR description and return JSON:\n\n{truncated}"


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------

def _fallback(pr_description: str) -> dict[str, Any]:
    """Return a safe dict when JSON parsing fails or API is unavailable."""
    return {
        "proposed_change":    (pr_description[:200] if pr_description else ""),
        "change_type":        None,
        "is_breaking_change": None,
    }


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------

def _extract_json(raw: str) -> dict[str, Any] | None:
    """
    Attempt to extract and parse a JSON object from the model's raw output.

    Handles:
    - Clean JSON string
    - JSON wrapped in markdown code fences (```json ... ```)
    - JSON with minor leading/trailing prose
    """
    if not raw:
        return None

    # Strip markdown fences if present
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fenced:
        raw = fenced.group(1)

    # Try to find the first {...} block
    obj_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if obj_match:
        raw = obj_match.group(0)

    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_pr_intent(pr_description: str) -> dict[str, Any]:
    """
    Extract structured intent from a raw GitHub PR description.

    Calls watsonx.ai (Granite) with temperature=0.0 to get maximally
    deterministic JSON output.  If the API is unavailable or the response
    cannot be parsed as valid JSON, a fallback dict is returned.

    Args:
        pr_description: Raw PR body string from the GitHub API (may contain
                        HTML comments, template boilerplate, checkboxes, etc.)

    Returns:
        dict with keys:
            proposed_change    (str)
            change_type        (str | None)
            is_breaking_change (bool | None)
    """
    if not pr_description or not pr_description.strip():
        logger.debug("Empty PR description — returning fallback.")
        return _fallback("")

    api_key    = os.getenv("WATSONX_API_KEY")
    url        = os.getenv("WATSONX_URL")
    project_id = os.getenv("WATSONX_PROJECT_ID")

    if not all([api_key, url, project_id]):
        logger.warning("watsonx credentials incomplete — returning fallback for extract_pr_intent.")
        return _fallback(pr_description)

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": _build_user_prompt(pr_description)},
    ]

    credentials = Credentials(url=url, api_key=api_key)
    model = ModelInference(
        model_id=MODEL_ID,
        credentials=credentials,
        project_id=project_id,
    )

    try:
        raw_response = model.chat(messages=messages, params=_CHAT_PARAMS)

        # Extract text content from the chat response dict
        if isinstance(raw_response, dict):
            choices = raw_response.get("choices") or []
            raw_text = (
                choices[0].get("message", {}).get("content", "")
                if choices else ""
            ).strip()
        else:
            raw_text = str(raw_response).strip()

    except Exception as exc:
        logger.error("watsonx call failed in extract_pr_intent: %s", exc)
        return _fallback(pr_description)

    # Parse and validate the JSON
    parsed = _extract_json(raw_text)

    if parsed is None:
        logger.warning(
            "JSON parse failed for extract_pr_intent — raw response: %r",
            raw_text[:200],
        )
        return _fallback(pr_description)

    # Normalise and validate fields
    proposed_change = str(parsed.get("proposed_change") or "").strip()
    if not proposed_change:
        proposed_change = pr_description[:200]

    raw_change_type = str(parsed.get("change_type") or "").strip().lower()
    change_type = raw_change_type if raw_change_type in _VALID_CHANGE_TYPES else "other"

    raw_breaking = parsed.get("is_breaking_change")
    if isinstance(raw_breaking, bool):
        is_breaking_change: bool | None = raw_breaking
    elif isinstance(raw_breaking, str):
        is_breaking_change = raw_breaking.lower() in ("true", "1", "yes")
    else:
        is_breaking_change = None

    return {
        "proposed_change":    proposed_change,
        "change_type":        change_type,
        "is_breaking_change": is_breaking_change,
    }
