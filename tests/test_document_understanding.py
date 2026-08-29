"""
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
