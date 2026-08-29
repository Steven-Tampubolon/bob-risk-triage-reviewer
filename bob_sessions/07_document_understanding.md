<!-- Excerpt from full session (bob_sessions/00_full_session_raw.md), lines 6017-7076 -->
<!-- Modules built in this segment: ai_layer/document_understanding.py -->

Buatkan module ai_layer/document_understanding.py dengan fungsi extract_pr_intent(pr_description) yang memanggil watsonx.ai Granite (model_id 'ibm/granite-4-h-small', pakai chat() method sama seperti explainer.py) untuk mengekstrak informasi substantif dari pr_description mentah GitHub (yang penuh HTML comment, checkbox template, boilerplate). System prompt: minta model mengembalikan JSON dengan field: proposed_change (ringkasan 1-2 kalimat tentang apa yang diubah), change_type (dependency_upgrade/bugfix/new_feature/breaking_change/code_quality/other, ambil dari checkbox yang dicentang [x]), is_breaking_change (bool). Parse response jadi dict Python, kalau JSON parsing gagal, fallback return dict dengan proposed_change=pr_description[:200] dan field lain None. Buat unit test di tests/test_document_understanding.py yang MOCK panggilan API, cover kasus: JSON valid, JSON invalid (trigger fallback), pr_description kosong." Jalankan: pytest tests/test_document_understanding.py -v

---

### 🤖 Assistant

> 🔧 called: update_todo_list, read_file, write_file, update_todo_list, write_file, execute_command, update_todo_list



> 🔧 **update_todo_list** — 
[-] Create ai_layer/document_understanding.py
[ ] Create tests/test_document_understanding.py with mocks
[ ] Run pytest and confirm all pass


> 🔧 **read_file** — ai_layer/explainer.py

> 🔧 **write_file** — """
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


> 🔧 **update_todo_list** — 
[x] Create ai_layer/document_understanding.py
[-] Create tests/test_document_understanding.py with mocks
[ ] Run pytest and confirm all pass


> 🔧 **write_file** — """
tests/test_document_understanding.py

Unit tests for ai_layer/document_understanding.py.

ALL watsonx.ai API calls are mocked — no real network traffic is made.

Coverage:
  - Valid JSON response → parsed and returned correctly
  - JSON with markdown code fences → extracted and parsed
  - Invalid / non-JSON response → fallback dict returned
  - Empty pr_description → fallback dict with empty proposed_change
  - Missing credentials → immediate fallback, no SDK call
  - SDK exception → fallback returned, no exception propagated
  - change_type normalisation (valid and unknown values)
  - is_breaking_change parsing (bool, string, null)
  - proposed_change fallback when model omits it
  - No real API call ever made (paranoia check)
"""

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("WATSONX_API_KEY",    "test-key")
os.environ.setdefault("WATSONX_URL",        "https://test.watsonx.ibm.com")
os.environ.setdefault("WATSONX_PROJECT_ID", "test-project-id")

from ai_layer.document_understanding import (  # noqa: E402
    extract_pr_intent,
    _extract_json,
    _fallback,
    _VALID_CHANGE_TYPES,
)


# ---------------------------------------------------------------------------
# Sample PR descriptions
# ---------------------------------------------------------------------------

_PR_FULL = """\
<!--
  You are amazing! Thanks for contributing to our project!
-->

## Proposed change

Bumps `neopool-modbus` from 4.5.3 to 4.6.0.

## Type of change

- [x] Dependency upgrade
- [ ] Bugfix (non-breaking change which fixes an issue)
- [ ] New integration (thank you!)
- [ ] New feature
- [ ] Deprecation
- [ ] Breaking change
- [ ] Code quality improvements

## Checklist

- [x] Local tests pass.
- [x] I have followed the development checklist.
"""

_PR_BREAKING = """\
## Proposed change

Changes the Uptime sensor from duration in seconds to a timestamp sensor.

## Type of change

- [ ] Dependency upgrade
- [ ] Bugfix
- [x] Breaking change (fix/feature causing existing functionality to break)
"""

_PR_EMPTY = ""
_PR_WHITESPACE = "   \n\t  "


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _chat_response(content: str) -> dict:
    """Build a minimal chat() response dict."""
    return {
        "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}]
    }


def _patch_watsonx(chat_return_value):
    """
    Patch both Credentials and ModelInference in the document_understanding
    module namespace.  Returns (cred_patch, model_patch) to use as context managers.
    """
    mock_model = MagicMock()
    if isinstance(chat_return_value, Exception):
        mock_model.chat.side_effect = chat_return_value
    else:
        mock_model.chat.return_value = chat_return_value

    cred_patch  = patch("ai_layer.document_understanding.Credentials", return_value=MagicMock())
    model_patch = patch("ai_layer.document_understanding.ModelInference", return_value=mock_model)
    return cred_patch, model_patch, mock_model


# ---------------------------------------------------------------------------
# Tests: _extract_json helper
# ---------------------------------------------------------------------------

class TestExtractJson(unittest.TestCase):

    def test_clean_json_object(self):
        raw = '{"proposed_change": "Bump deps", "change_type": "dependency_upgrade", "is_breaking_change": false}'
        result = _extract_json(raw)
        self.assertIsNotNone(result)
        self.assertEqual(result["change_type"], "dependency_upgrade")

    def test_json_with_markdown_fence(self):
        raw = '```json\n{"proposed_change": "Fix bug", "change_type": "bugfix", "is_breaking_change": false}\n```'
        result = _extract_json(raw)
        self.assertIsNotNone(result)
        self.assertEqual(result["change_type"], "bugfix")

    def test_json_embedded_in_prose(self):
        raw = 'Here is the result: {"proposed_change": "Add feature", "change_type": "new_feature", "is_breaking_change": false} end.'
        result = _extract_json(raw)
        self.assertIsNotNone(result)
        self.assertEqual(result["change_type"], "new_feature")

    def test_invalid_json_returns_none(self):
        raw = "This is not JSON at all."
        self.assertIsNone(_extract_json(raw))

    def test_empty_string_returns_none(self):
        self.assertIsNone(_extract_json(""))

    def test_partial_json_returns_none(self):
        self.assertIsNone(_extract_json('{"proposed_change": "incomplete"'))

    def test_json_without_fence_no_prose(self):
        raw = '{"a": 1}'
        result = _extract_json(raw)
        self.assertIsNotNone(result)
        self.assertEqual(result["a"], 1)


# ---------------------------------------------------------------------------
# Tests: _fallback helper
# ---------------------------------------------------------------------------

class TestFallback(unittest.TestCase):

    def test_returns_dict_with_three_keys(self):
        result = _fallback("some description")
        self.assertIn("proposed_change", result)
        self.assertIn("change_type", result)
        self.assertIn("is_breaking_change", result)

    def test_proposed_change_is_first_200_chars(self):
        desc = "x" * 300
        result = _fallback(desc)
        self.assertEqual(result["proposed_change"], "x" * 200)

    def test_change_type_is_none(self):
        self.assertIsNone(_fallback("desc")["change_type"])

    def test_is_breaking_change_is_none(self):
        self.assertIsNone(_fallback("desc")["is_breaking_change"])

    def test_empty_description_returns_empty_proposed_change(self):
        result = _fallback("")
        self.assertEqual(result["proposed_change"], "")


# ---------------------------------------------------------------------------
# Tests: extract_pr_intent — valid JSON response
# ---------------------------------------------------------------------------

class TestExtractPrIntentValidResponse(unittest.TestCase):

    _VALID_JSON = '{"proposed_change": "Bumps neopool-modbus from 4.5.3 to 4.6.0.", "change_type": "dependency_upgrade", "is_breaking_change": false}'

    def test_returns_proposed_change(self):
        cred_p, model_p, _ = _patch_watsonx(_chat_response(self._VALID_JSON))
        with cred_p, model_p:
            result = extract_pr_intent(_PR_FULL)
        self.assertEqual(result["proposed_change"], "Bumps neopool-modbus from 4.5.3 to 4.6.0.")

    def test_returns_correct_change_type(self):
        cred_p, model_p, _ = _patch_watsonx(_chat_response(self._VALID_JSON))
        with cred_p, model_p:
            result = extract_pr_intent(_PR_FULL)
        self.assertEqual(result["change_type"], "dependency_upgrade")

    def test_returns_is_breaking_change_false(self):
        cred_p, model_p, _ = _patch_watsonx(_chat_response(self._VALID_JSON))
        with cred_p, model_p:
            result = extract_pr_intent(_PR_FULL)
        self.assertFalse(result["is_breaking_change"])

    def test_breaking_change_true(self):
        breaking_json = '{"proposed_change": "Changes Uptime sensor.", "change_type": "breaking_change", "is_breaking_change": true}'
        cred_p, model_p, _ = _patch_watsonx(_chat_response(breaking_json))
        with cred_p, model_p:
            result = extract_pr_intent(_PR_BREAKING)
        self.assertTrue(result["is_breaking_change"])
        self.assertEqual(result["change_type"], "breaking_change")

    def test_chat_called_exactly_once(self):
        cred_p, model_p, mock_model = _patch_watsonx(_chat_response(self._VALID_JSON))
        with cred_p, model_p:
            extract_pr_intent(_PR_FULL)
        mock_model.chat.assert_called_once()

    def test_fenced_json_is_parsed(self):
        fenced = f"```json\n{self._VALID_JSON}\n```"
        cred_p, model_p, _ = _patch_watsonx(_chat_response(fenced))
        with cred_p, model_p:
            result = extract_pr_intent(_PR_FULL)
        self.assertEqual(result["change_type"], "dependency_upgrade")

    def test_return_dict_has_exactly_three_keys(self):
        cred_p, model_p, _ = _patch_watsonx(_chat_response(self._VALID_JSON))
        with cred_p, model_p:
            result = extract_pr_intent(_PR_FULL)
        self.assertEqual(set(result.keys()), {"proposed_change", "change_type", "is_breaking_change"})


# ---------------------------------------------------------------------------
# Tests: extract_pr_intent — invalid / non-JSON response → fallback
# ---------------------------------------------------------------------------

class TestExtractPrIntentInvalidResponse(unittest.TestCase):

    def _call_with_text(self, text: str) -> dict:
        cred_p, model_p, _ = _patch_watsonx(_chat_response(text))
        with cred_p, model_p:
            return extract_pr_intent(_PR_FULL)

    def test_plain_text_triggers_fallback(self):
        result = self._call_with_text("I cannot parse this PR description.")
        # Fallback: proposed_change = first 200 chars of _PR_FULL
        self.assertEqual(result["proposed_change"], _PR_FULL[:200])
        self.assertIsNone(result["change_type"])
        self.assertIsNone(result["is_breaking_change"])

    def test_empty_response_triggers_fallback(self):
        result = self._call_with_text("")
        self.assertIsNone(result["change_type"])

    def test_truncated_json_triggers_fallback(self):
        result = self._call_with_text('{"proposed_change": "broken json')
        self.assertIsNone(result["change_type"])

    def test_fallback_proposed_change_is_pr_description_prefix(self):
        result = self._call_with_text("not json")
        self.assertEqual(result["proposed_change"], _PR_FULL[:200])

    def test_unknown_change_type_normalised_to_other(self):
        json_unknown = '{"proposed_change": "Some change.", "change_type": "refactor", "is_breaking_change": false}'
        result = self._call_with_text(json_unknown)
        # "refactor" is not in _VALID_CHANGE_TYPES → normalised to "other"
        self.assertEqual(result["change_type"], "other")

    def test_is_breaking_change_string_true(self):
        json_str_bool = '{"proposed_change": "Some change.", "change_type": "bugfix", "is_breaking_change": "true"}'
        result = self._call_with_text(json_str_bool)
        self.assertTrue(result["is_breaking_change"])

    def test_is_breaking_change_null_becomes_none(self):
        json_null = '{"proposed_change": "Some change.", "change_type": "bugfix", "is_breaking_change": null}'
        result = self._call_with_text(json_null)
        self.assertIsNone(result["is_breaking_change"])


# ---------------------------------------------------------------------------
# Tests: empty / whitespace pr_description → immediate fallback, no API call
# ---------------------------------------------------------------------------

class TestExtractPrIntentEmptyDescription(unittest.TestCase):

    def _call_empty(self, desc: str) -> tuple[dict, MagicMock]:
        mock_model = MagicMock()
        cred_p = patch("ai_layer.document_understanding.Credentials", return_value=MagicMock())
        model_p = patch("ai_layer.document_understanding.ModelInference", return_value=mock_model)
        with cred_p, model_p:
            result = extract_pr_intent(desc)
        return result, mock_model

    def test_empty_string_returns_fallback(self):
        result, _ = self._call_empty(_PR_EMPTY)
        self.assertEqual(result["proposed_change"], "")
        self.assertIsNone(result["change_type"])
        self.assertIsNone(result["is_breaking_change"])

    def test_whitespace_only_returns_fallback(self):
        result, _ = self._call_empty(_PR_WHITESPACE)
        self.assertIsNone(result["change_type"])

    def test_empty_description_does_not_call_api(self):
        _, mock_model = self._call_empty(_PR_EMPTY)
        mock_model.chat.assert_not_called()

    def test_whitespace_description_does_not_call_api(self):
        _, mock_model = self._call_empty(_PR_WHITESPACE)
        mock_model.chat.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: missing credentials → immediate fallback, no SDK call
# ---------------------------------------------------------------------------

class TestExtractPrIntentMissingCredentials(unittest.TestCase):

    def _call_without(self, var: str) -> tuple[dict, MagicMock]:
        mock_model = MagicMock()
        saved = os.environ.pop(var, None)
        try:
            cred_p = patch("ai_layer.document_understanding.Credentials", return_value=MagicMock())
            model_p = patch("ai_layer.document_understanding.ModelInference", return_value=mock_model)
            with cred_p, model_p:
                result = extract_pr_intent(_PR_FULL)
        finally:
            if saved is not None:
                os.environ[var] = saved
        return result, mock_model

    def test_missing_api_key_returns_fallback(self):
        result, mock_model = self._call_without("WATSONX_API_KEY")
        self.assertIsNone(result["change_type"])
        mock_model.chat.assert_not_called()

    def test_missing_url_returns_fallback(self):
        result, mock_model = self._call_without("WATSONX_URL")
        self.assertIsNone(result["change_type"])
        mock_model.chat.assert_not_called()

    def test_missing_project_id_returns_fallback(self):
        result, mock_model = self._call_without("WATSONX_PROJECT_ID")
        self.assertIsNone(result["change_type"])
        mock_model.chat.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: SDK exception → fallback, no propagation
# ---------------------------------------------------------------------------

class TestExtractPrIntentSDKException(unittest.TestCase):

    def test_runtime_error_returns_fallback(self):
        cred_p, model_p, _ = _patch_watsonx(RuntimeError("connection refused"))
        with cred_p, model_p:
            result = extract_pr_intent(_PR_FULL)
        self.assertIsNone(result["change_type"])
        self.assertEqual(result["proposed_change"], _PR_FULL[:200])

    def test_exception_does_not_propagate(self):
        cred_p, model_p, _ = _patch_watsonx(Exception("unexpected"))
        with cred_p, model_p:
            # Must not raise
            result = extract_pr_intent(_PR_FULL)
        self.assertIsInstance(result, dict)


# ---------------------------------------------------------------------------
# Tests: _VALID_CHANGE_TYPES completeness
# ---------------------------------------------------------------------------

class TestValidChangeTypes(unittest.TestCase):

    def test_all_expected_types_present(self):
        expected = {
            "dependency_upgrade", "bugfix", "new_feature",
            "breaking_change", "code_quality", "other",
        }
        self.assertEqual(_VALID_CHANGE_TYPES, expected)


# ---------------------------------------------------------------------------
# Tests: no real API call ever made
# ---------------------------------------------------------------------------

class TestNoRealAPICall(unittest.TestCase):

    def test_credentials_are_mocked(self):
        cred_p, model_p, mock_model = _patch_watsonx(
            _chat_response('{"proposed_change": "x", "change_type": "bugfix", "is_breaking_change": false}')
        )
        with cred_p as mock_cred, model_p:
            extract_pr_intent(_PR_FULL)
        mock_cred.assert_called_once()
        self.assertIsInstance(mock_cred.return_value, MagicMock)

    def test_model_inference_is_mocked(self):
        cred_p, model_p, mock_model = _patch_watsonx(
            _chat_response('{"proposed_change": "x", "change_type": "bugfix", "is_breaking_change": false}')
        )
        with cred_p, model_p as mock_mi:
            extract_pr_intent(_PR_FULL)
        mock_mi.assert_called_once()
        mock_model.chat.assert_called_once()


if __name__ == "__main__":
    unittest.main()


> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && .venv/bin/python -m pytest tests/test_document_understanding.py -v 2>&1

> 🔧 **update_todo_list** — 
[x] Create ai_layer/document_understanding.py
[x] Create tests/test_document_understanding.py with mocks
[x] Run pytest and confirm all pass


### 🤖 Assistant

**38/38 passed — zero real API calls.** Ringkasan:

---

## [`ai_layer/document_understanding.py`](ai_layer/document_understanding.py)

### `extract_pr_intent(pr_description: str) → dict`

```python
{
    "proposed_change":    "Bumps neopool-modbus from 4.5.3 to 4.6.0.",
    "change_type":        "dependency_upgrade",  # dari checkbox [x]
    "is_breaking_change": False
}
```

**Alur:**
```
pr_description kosong → fallback langsung (no API call)
credentials hilang   → fallback langsung (no API call)
                        ↓
chat(system_prompt + user_prompt) → raw_text
                        ↓
_extract_json(raw_text) → dict | None
  None  → fallback (proposed_change = desc[:200], change_type = None)
  dict  → normalise change_type + is_breaking_change → return
```

**Design choices:**
- `temperature=0.0` — maksimum deterministik untuk output JSON
- `_extract_json()` menangani: clean JSON, markdown fences, JSON embedded dalam prosa
- `change_type` unknown → dinormalkan ke `"other"` (bukan error)
- `is_breaking_change` mendukung `bool`, `"true"/"false"` string, dan `null`

---

## 38 Unit Tests — coverage map

| Class | Skenario |
|---|---|
| `TestExtractJson` (7) | Clean JSON, fenced, embedded, invalid, empty, truncated, no-fence |
| `TestFallback` (5) | 3-key dict, 200-char truncation, None fields, empty desc |
| `TestExtractPrIntentValidResponse` (7) | All fields, fenced JSON, breaking change True, `chat()` called once |
| `TestExtractPrIntentInvalidResponse` (7) | Plain text, empty, truncated, unknown type→other, string bool, null |
| `TestExtractPrIntentEmptyDescription` (4) | Empty + whitespace → fallback, API **tidak** dipanggil |
| `TestExtractPrIntentMissingCredentials` (3) | Key/URL/ProjectID hilang → fallback, API **tidak** dipanggil |
| `TestExtractPrIntentSDKException` (2) | RuntimeError → fallback tanpa propagasi |
| `TestValidChangeTypes` (1) | Set lengkap 6 nilai valid |
| `TestNoRealAPICall` (2) | Credentials dan ModelInference adalah MagicMock, bukan SDK asli |

---

### 👤 User

Update ai_layer/explainer.py: di call_explainer(), panggil extract_pr_intent(pr_data['pr_description']) dari ai_layer/document_understanding.py dulu sebelum bangun prompt ke Granite. Sertakan hasil proposed_change dan change_type dari document understanding itu ke dalam system/user prompt explainer, supaya penjelasan akhir lebih akurat mengacu ke isi PR description, bukan cuma field diff_profile. Update tests/test_explainer.py untuk mock extract_pr_intent() juga." Jalankan: pytest tests/test_explainer.py tests/test_document_understanding.py -v

---

### 🤖 Assistant

> 🔧 called: read_file, read_file, read_file



> 🔧 **read_file** — ai_layer/explainer.py

> 🔧 **read_file** — ai_layer/explainer.py

> 🔧 **read_file** — ai_layer/explainer.py

### 🤖 Assistant

Previous conversation summary:

---

## Goal

Build a complete **PR Risk Triage & Review Prioritization system** ("bob-risk-triage-reviewer") for IBM Tech Xchange 2026, capable of ingesting GitHub PRs, scoring their blast radius and security risk, prioritizing them, and generating AI explanations using IBM watsonx.ai (Granite).

The current pending task (interrupted mid-execution) is:

> **Update `ai_layer/explainer.py`**: In `call_explainer()`, call `extract_pr_intent(pr_data['pr_description'])` from `ai_layer/document_understanding.py` before building the Granite prompt. Include the resulting `proposed_change` and `change_type` in the system/user prompt so the explanation references actual PR content, not just diff metrics. Update `tests/test_explainer.py` to also mock `extract_pr_intent()`.

## Instructions

- **Language**: Python, following existing code style (type hints, docstrings, clean separation)
- **Always mock** watsonx API calls in unit tests — never call real API in tests
- **All tests must pass** before declaring completion
- **Validation**: run `pytest tests/test_explainer.py tests/test_document_understanding.py -v` to confirm
- Patch target for mocking `extract_pr_intent` in explainer tests: `ai_layer.explainer.extract_pr_intent`
- The function is called **inside** `call_explainer()`, so it must be imported at module level in explainer.py and patched from the explainer namespace in tests

## Discoveries

- `ibm/granite-4-h-small` does **not** support `generate_text()` (returns `''`) or `generate()` (returns empty `generated_text`). Must use `model.chat(messages=[...], params=_CHAT_PARAMS)` — response format: `{"choices": [{"message": {"content": "..."}}]}`
- SDK imports are at module level wrapped in `try/except ImportError` so tests can patch `ai_layer.explainer.Credentials` and `ai_layer.explainer.ModelInference` without SDK installed
- Mock helper in tests uses `model_mock.chat.side_effect` with `_wrap_as_chat_response()` that wraps strings into `{"choices": [{"message": {"content": text}}]}` dicts
- Consistency validator uses **context-aware regex** (not bare number matching) to avoid false positives on PR numbers, file counts, etc.
- `SIZE_THRESHOLD = 500` (calibrated empirically against 100 HA PRs → 36% multi_module, Δ=1% from 35% target)
- `NON_SUBSTANTIVE_MODULES = {"tests", "requirements_all.txt", "requirements_test_all.txt", "CODEOWNERS", "scripts"}` — excluded from breadth criterion
- `_build_fallback_explanation()` uses `"indeks {br_score}"` not `"skor {br_score}"` to avoid triggering the score consistency validator

## Accomplished

### Completed modules
| Module | Status | Description |
|---|---|---|
| `ingestion/github_pr.py` | ✅ Done | `fetch_pr_list`, `fetch_pr_files`, `get_pr_diff_profile`; rate-limit retry; smart `modules_touched` (HA components 2-segment); dependency vs config classifier |
| `scoring/blast_radius.py` | ✅ Done | `score_blast_radius()` → (score, label, modules, facts); SIZE_THRESHOLD=500; NON_SUBSTANTIVE_MODULES |
| `scoring/security_policy.py` | ✅ Done | `score_security_policy()` → (reviewer, merge_blocker, reasons); 7 categories; guardrail design |
| `priority/combine.py` | ✅ Done | `combine_priority()` → (score, label); formula 0.5·BR + 0.3·EV + 0.2·SEC; Critical override on merge_blocker |
| `ai_layer/explainer.py` | ✅ Done (needs update) | `call_explainer()` using chat API; retry logic; consistency validator; fallback template |
| `ai_layer/document_understanding.py` | ✅ Done | `extract_pr_intent()` → {proposed_change, change_type, is_breaking_change}; JSON extraction; fallback |

### Completed tests
| Test file | Tests | Status |
|---|---|---|
| `tests/test_ingestion.py` | 52 | ✅ All pass |
| `tests/test_scoring.py` | 30 | ✅ All pass |
| `tests/test_security_policy.py` | 57 | ✅ All pass |
| `tests/test_priority.py` | 32 | ✅ All pass |
| `tests/test_explainer.py` | 36 | ✅ All pass (needs update for extract_pr_intent mock) |
| `tests/test_document_understanding.py` | 38 | ✅ All pass |

### Completed scripts / data
| File | Description |
|---|---|
| `scripts/fetch_ha_core_sample.py` | 5 PR sample from HA/core |
| `scripts/fetch_ha_core_100.py` | 100 PR from HA/core → `data/home_assistant_100prs.json` |
| `scripts/fetch_vscode_100.py` | 100 PR from microsoft/vscode → `data/vscode_100prs.json` |
| `scripts/validate_blast_radius.py` | Distribution + calibration table (SIZE_THRESHOLD=500 → best fit) |
| `scripts/validate_cross_repo.py` | Full pipeline validation on vscode data |
| `scripts/build_priority_queue.py` | Pipeline → `output/priority_queue.json` (100 entries, sorted) |
| `scripts/test_explainer_live.py` | Live watsonx API test for 3 PRs |
| `scripts/build_explained_queue.py` | Full 100-PR run → `output/explained_priority_queue.json` (98 AI, 2 fallback) |

### In progress
- `ai_layer/explainer.py` — add `extract_pr_intent()` call before prompt building; include `proposed_change` and `change_type` in prompt context
- `tests/test_explainer.py` — add mock for `ai_layer.explainer.extract_pr_intent`

## Relevant files / directories

```
ai_layer/
  explainer.py              ← NEEDS UPDATE (add extract_pr_intent call + prompt enrichment)
  document_understanding.py ← Done (extract_pr_intent lives here)

tests/
  test_explainer.py         ← NEEDS UPDATE (mock extract_pr_intent)
  test_document_understanding.py ← Done

scoring/
  blast_radius.py           ← Done
  security_policy.py        ← Done

priority/
  combine.py                ← Done

ingestion/
  github_pr.py              ← Done

scripts/
  build_explained_queue.py  ← Done (reads priority_queue.json, calls call_explainer for all 100)
  test_explainer_live.py    ← Done

data/
  home_assistant_100prs.json  ← 100 PR profiles (HA/core)
  vscode_100prs.json          ← 100 PR profiles (vscode)

output/
  priority_queue.json            ← 100 entries, sorted by priority_score desc
  explained_priority_queue.json  ← 100 entries + explanation field
```



---

### 👤 User

continue

---

### 🤖 Assistant

> 🔧 called: read_file, read_file



> 🔧 **read_file** — ai_layer/explainer.py

> 🔧 **read_file** — tests/test_explainer.py

### 🤖 Assistant

> 🔧 called: read_file

Now let me read the `document_understanding.py` to understand `extract_pr_intent`'s signature and return shape:

> 🔧 **read_file** — ai_layer/document_understanding.py

### 🤖 Assistant

> 🔧 called: update_todo_list, apply_diff

Good. Now I have the full picture. Let me set up the todo list and make both changes:

> 🔧 **update_todo_list** — [-] Update ai_layer/explainer.py — import extract_pr_intent, call it in call_explainer(), enrich prompt with proposed_change + change_type
[ ] Update tests/test_explainer.py — add mock for ai_layer.explainer.extract_pr_intent in all call_explainer tests
[ ] Run pytest to confirm all tests pass


> 🔧 **apply_diff** — ai_layer/explainer.py

### 🤖 Assistant

> 🔧 called: read_file, apply_diff

The `import` line wasn't applied. Let me check and fix:

> 🔧 **read_file** — ai_layer/explainer.py

> 🔧 **apply_diff** — ai_layer/explainer.py

### 🤖 Assistant

> 🔧 called: apply_diff

Good. Now update [`tests/test_explainer.py`](tests/test_explainer.py) to mock `ai_layer.explainer.extract_pr_intent` in all `call_explainer` tests:

> 🔧 **apply_diff** — tests/test_explainer.py

### 🤖 Assistant

> 🔧 called: execute_command, execute_command, execute_command

Now run the tests:

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && python -m pytest tests/test_explainer.py tests/test_document_understanding.py -v 2>&1

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && python3 -m pytest tests/test_explainer.py tests/test_document_understanding.py -v 2>&1

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && source .venv/bin/activate && pytest tests/test_explainer.py tests/test_document_understanding.py -v 2>&1

### 🤖 Assistant

> 🔧 called: execute_command

77/77 passed. Let me also do a quick sanity run on the full test suite to make sure nothing regressed:

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && source .venv/bin/activate && pytest tests/ -v --tb=short 2>&1 | tail -30

### 🤖 Assistant

> 🔧 called: update_todo_list

248/248 — zero regressions.

> 🔧 **update_todo_list** — [x] Update ai_layer/explainer.py — import extract_pr_intent, call it in call_explainer(), enrich prompt with proposed_change + change_type
[x] Update tests/test_explainer.py — add mock for ai_layer.explainer.extract_pr_intent in all call_explainer tests
[x] Run pytest to confirm all tests pass


### 🤖 Assistant

All done. Here's a summary of every change made:

---

### Changes

#### [`ai_layer/explainer.py`](ai_layer/explainer.py)

**1. Module-level import** (line 38):
```python
from ai_layer.document_understanding import extract_pr_intent
```

**2. [`_build_user_prompt()`](ai_layer/explainer.py:93)** — added optional `pr_intent` parameter. When `proposed_change` is populated, it injects a `Ringkasan perubahan PR` section into the prompt body, and adds a sentence instructing the model to use `proposed_change` + `change_type` in its explanation.

**3. [`call_explainer()`](ai_layer/explainer.py:329)** — after credential check, calls `extract_pr_intent(pr_description)` and forwards the result as `pr_intent=` to `_build_user_prompt()`. Only called when `pr_description` is non-empty.

---

#### [`tests/test_explainer.py`](tests/test_explainer.py)

- **`_patch_watsonx()`** now returns a **3-tuple** `(cred_patch, model_patch, intent_patch)` where the third item patches `ai_layer.explainer.extract_pr_intent` with a fixed `_INTENT_RESULT` dict.
- All `call_explainer` test methods updated to unpack and enter the third context manager.
- **2 new tests** in `TestCallExplainerConsistentResponse`:
  - `test_extract_pr_intent_called_with_description` — asserts the mock was called once with the exact `pr_description` string.
  - `test_intent_proposed_change_in_user_prompt` — inspects the `messages` kwarg passed to `chat()` and asserts both `proposed_change` and `change_type` appear in the user message content.
- **1 new test** in `TestNoRealAPICallMade`: `test_extract_pr_intent_is_mocked_not_real` — paranoia check that the mock was called (never the real watsonx API).

---

### 👤 User

Tambahkan section baru di README.md dengan heading '### Document Understanding — Design Decision'. Isi section ini: 'Document Understanding diimplementasikan sebagai layer terpisah (ai_layer/document_understanding.py) yang memanggil watsonx.ai Granite untuk mengekstrak intent dari PR description mentah GitHub. Kami memilih pendekatan ini alih-alih watsonx.ai Text Extraction API resmi karena Text Extraction dirancang untuk file/OCR (PDF, scan, gambar) via Cloud Object Storage dan async job, sedangkan PR description GitHub sudah berupa teks markdown terstruktur — memaksakan pipeline OCR untuk teks yang sudah plain text tidak memberikan nilai tambah dan berisiko tinggi terhadap waktu solo hackathon yang terbatas.' Rapikan formatnya sesuai gaya README yang sudah ada."(gunakan bahasa inggris di readme)

---

### 🤖 Assistant

> 🔧 called: read_file



> 🔧 **read_file** — README.md

### 🤖 Assistant

> 🔧 called: apply_diff

The README is mostly empty placeholders. I'll add the new section at the end, in a style consistent with the existing heading hierarchy:

> 🔧 **apply_diff** — <<<<<<< SEARCH
:start_line:19
-------
## Screenshots

<!-- Add screenshots here -->
=======
## Screenshots

<!-- Add screenshots here -->

## Design Decisions

### Document Understanding — Design Decision

Document Understanding is implemented as a dedicated layer
([`ai_layer/document_understanding.py`](ai_layer/document_understanding.py)) that
calls watsonx.ai Granite to extract structured intent from a raw GitHub PR description.

We chose this approach instead of the watsonx.ai Text Extraction API for the
following reasons:

- **Wrong tool for the job.** The Text Extraction API is designed for
  file-based OCR pipelines — PDFs, scanned documents, and images stored in
  Cloud Object Storage, processed via asynchronous jobs. GitHub PR descriptions
  are already structured Markdown text; forcing them through an OCR pipeline
  adds no value.
- **Latency and complexity.** The async job model (upload → poll → download)
  would introduce significant round-trip overhead for what is ultimately a
  short string that fits in a single LLM prompt.
- **Scope risk.** Integrating Cloud Object Storage buckets for plain-text
  content would have been a disproportionate engineering investment for a
  time-boxed solo hackathon.

Using the Granite chat endpoint directly keeps the call synchronous, testable
with standard `unittest.mock` patches, and consistent with the rest of the
`ai_layer` stack.
>>>>>>> REPLACE


### 🤖 Assistant

Section added. Here's what was written and why each choice was made:

- **`## Design Decisions`** — a new top-level section (consistent with the existing `##` headings like `## Architecture`, `## How to Run`) that can house multiple `###` sub-decisions as the project grows.
- **`### Document Understanding — Design Decision`** — the exact heading requested.
- The three bullet points break the reasoning into distinct concerns (wrong tool, latency, scope risk) rather than one long paragraph, which matches how technical decision records are typically written in READMEs.
- The inline link `[ai_layer/document_understanding.py](ai_layer/document_understanding.py)` makes it directly navigable from GitHub's rendered Markdown.
- The closing sentence ties the decision back to the codebase's testing strategy, connecting it to what reviewers will actually see in the code.

---

### 👤 User

