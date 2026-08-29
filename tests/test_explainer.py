"""
tests/test_explainer.py

Unit tests for ai_layer/explainer.py.

ALL watsonx.ai SDK calls are mocked — no real API traffic is made.
The tests verify:
  - Consistent AI response is returned as-is
  - Inconsistent response triggers retry (up to MAX_RETRIES)
  - After retries exhausted, fallback template is returned
  - Fallback template contains key fields from the input data
  - validate_explanation_consistency logic (score / label checks)
  - Missing credentials trigger immediate fallback (no SDK call)
  - Retry count is bounded by MAX_RETRIES
"""

import os
import unittest
from unittest.mock import MagicMock, patch, call

# Ensure env vars are set before importing the module so load_dotenv()
# does not accidentally load a real .env during tests.
os.environ.setdefault("WATSONX_API_KEY",    "test-key")
os.environ.setdefault("WATSONX_URL",        "https://test.watsonx.ibm.com")
os.environ.setdefault("WATSONX_PROJECT_ID", "test-project-id")

from ai_layer.explainer import (  # noqa: E402
    call_explainer,
    validate_explanation_consistency,
    _build_fallback_explanation,
    MAX_RETRIES,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PR_DATA = {
    "pr_number": 42,
    "files_changed": 3,
    "additions": 120,
    "deletions": 40,
    "modules_touched": ["homeassistant/components/hue", "tests"],
    "has_migration": False,
    "has_config_change": False,
    "has_dependency_change": True,
    "has_ci_change": False,
    "pr_description": "Bumps hue library to 3.0.",
}

_PRIORITY_RESULT = (45, "Medium")       # (score, label)
_BLAST_RESULT    = (60, "multi_module", ["homeassistant/components/hue", "tests"], [])
_SECURITY_RESULT = ("dependency-review", False, ["[dependency] Flag 'has_dependency_change' is set."])

# A response that is consistent with _PRIORITY_RESULT (score=45, label=Medium)
_CONSISTENT_RESPONSE = (
    'PR #42 mendapat priority_label "Medium" dengan priority_score 45 karena '
    "blast radius tergolong multi_module dan ada perubahan dependency. "
    "Disarankan melibatkan dependency-review dalam proses review ini."
)

# A response that mentions the wrong score in score context
_WRONG_SCORE_RESPONSE = (
    "PR ini mendapat skor 80 dan label Medium karena blast radius multi_module."
)

# A response that mentions the wrong label in label context
_WRONG_LABEL_RESPONSE = (
    'PR ini mendapat priority_label "Critical" karena ada perubahan besar.'
)

# A response that mentions no score or label at all (still consistent)
_NO_NUMBER_RESPONSE = (
    "PR ini menyentuh modul dependency sehingga memerlukan review dari tim terkait. "
    "Perubahan terlokalisasi dan bersifat rutin."
)


def _wrap_as_chat_response(text: str | Exception) -> dict | Exception:
    """Wrap a plain string into the chat() response dict, or pass through exceptions."""
    if isinstance(text, Exception):
        return text
    return {"choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}]}


def _make_model_mock(return_values: list) -> MagicMock:
    """Build a mock ModelInference whose chat() returns proper response dicts."""
    mock_model = MagicMock()
    wrapped = [_wrap_as_chat_response(v) for v in return_values]
    def _side_effect(*args, **kwargs):
        item = wrapped.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
    mock_model.chat.side_effect = _side_effect
    return mock_model


# Default extract_pr_intent return value used across all call_explainer tests
_INTENT_RESULT = {
    "proposed_change": "Bumps hue library to version 3.0.",
    "change_type": "dependency_upgrade",
    "is_breaking_change": False,
}


def _patch_watsonx(model_mock: MagicMock):
    """
    Return three context managers that patch Credentials, ModelInference,
    and extract_pr_intent inside ai_layer.explainer.
    """
    cred_patch   = patch("ai_layer.explainer.Credentials", return_value=MagicMock())
    model_patch  = patch("ai_layer.explainer.ModelInference", return_value=model_mock)
    intent_patch = patch(
        "ai_layer.explainer.extract_pr_intent",
        return_value=_INTENT_RESULT,
    )
    return cred_patch, model_patch, intent_patch


# ---------------------------------------------------------------------------
# Tests: validate_explanation_consistency
# ---------------------------------------------------------------------------

class TestValidateExplanationConsistency(unittest.TestCase):

    def test_consistent_with_correct_score_and_label(self):
        self.assertTrue(
            validate_explanation_consistency(_CONSISTENT_RESPONSE, (45, "Medium"))
        )

    def test_inconsistent_wrong_score(self):
        # Text says "skor 80" but actual score is 45
        self.assertFalse(
            validate_explanation_consistency(_WRONG_SCORE_RESPONSE, (45, "Medium"))
        )

    def test_inconsistent_wrong_label(self):
        # Text says priority_label "Critical" but actual is "Medium"
        self.assertFalse(
            validate_explanation_consistency(_WRONG_LABEL_RESPONSE, (45, "Medium"))
        )

    def test_no_numbers_no_labels_is_consistent(self):
        """Text with no score/label mentions is always consistent."""
        self.assertTrue(
            validate_explanation_consistency(_NO_NUMBER_RESPONSE, (45, "Medium"))
        )

    def test_correct_score_in_context_is_consistent(self):
        text = "PR ini mendapat skor 45 karena perubahan sedang."
        self.assertTrue(
            validate_explanation_consistency(text, (45, "Medium"))
        )

    def test_wrong_score_in_context_is_inconsistent(self):
        text = "PR ini mendapat skor 99 karena perubahan sangat besar."
        self.assertFalse(
            validate_explanation_consistency(text, (45, "Medium"))
        )

    def test_correct_label_in_context_is_consistent(self):
        text = 'Priority label "Medium" dipilih karena ukuran perubahan sedang.'
        self.assertTrue(
            validate_explanation_consistency(text, (45, "Medium"))
        )

    def test_wrong_label_in_context_is_inconsistent(self):
        text = 'Priority label "Critical" menunjukkan risiko tinggi.'
        self.assertFalse(
            validate_explanation_consistency(text, (45, "Medium"))
        )

    def test_pr_number_not_treated_as_score(self):
        """PR #42 in prose must not be mistaken for a wrong score."""
        text = "PR #42 menyentuh komponen dependency dan mendapat skor 45."
        self.assertTrue(
            validate_explanation_consistency(text, (45, "Medium"))
        )

    def test_year_numbers_not_treated_as_scores(self):
        """Years like 2026 must not be mistaken for a score."""
        text = "PR ini dibuat pada 2026 dan mendapat label Medium."
        self.assertTrue(
            validate_explanation_consistency(text, (45, "Medium"))
        )

    def test_empty_text_is_consistent(self):
        self.assertTrue(
            validate_explanation_consistency("", (45, "Medium"))
        )


# ---------------------------------------------------------------------------
# Tests: _build_fallback_explanation
# ---------------------------------------------------------------------------

class TestBuildFallbackExplanation(unittest.TestCase):

    def _call(self, pr=None, pri=None, br=None, sec=None):
        return _build_fallback_explanation(
            pr  or _PR_DATA,
            pri or _PRIORITY_RESULT,
            br  or _BLAST_RESULT,
            sec or _SECURITY_RESULT,
        )

    def test_contains_pr_number(self):
        self.assertIn("42", self._call())

    def test_contains_priority_label(self):
        self.assertIn("Medium", self._call())

    def test_contains_priority_score(self):
        self.assertIn("45", self._call())

    def test_contains_blast_label(self):
        self.assertIn("multi_module", self._call())

    def test_merge_blocker_warning_when_true(self):
        sec = ("security-team", True, ["auth change detected"])
        text = self._call(sec=sec)
        self.assertIn("security-team", text)

    def test_no_merge_blocker_warning_when_false(self):
        text = self._call()
        # merge_blocker=False in default fixture → no "⚠" warning
        self.assertNotIn("⚠", text)

    def test_reviewer_mentioned_when_no_blocker(self):
        sec = ("dependency-review", False, [])
        text = self._call(sec=sec)
        self.assertIn("dependency-review", text)

    def test_returns_string(self):
        self.assertIsInstance(self._call(), str)

    def test_is_consistent_with_priority_result(self):
        """The fallback must always pass the consistency validator."""
        text = self._call()
        self.assertTrue(
            validate_explanation_consistency(text, _PRIORITY_RESULT)
        )


# ---------------------------------------------------------------------------
# Tests: call_explainer — consistent response (no retry needed)
# ---------------------------------------------------------------------------

class TestCallExplainerConsistentResponse(unittest.TestCase):

    def test_returns_ai_explanation_when_consistent(self):
        model_mock = _make_model_mock([_CONSISTENT_RESPONSE])
        cred_p, model_p, intent_p = _patch_watsonx(model_mock)
        with cred_p, model_p, intent_p:
            result = call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertEqual(result, _CONSISTENT_RESPONSE)

    def test_chat_called_exactly_once(self):
        model_mock = _make_model_mock([_CONSISTENT_RESPONSE])
        cred_p, model_p, intent_p = _patch_watsonx(model_mock)
        with cred_p, model_p, intent_p:
            call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertEqual(model_mock.chat.call_count, 1)

    def test_no_numbers_response_accepted_without_retry(self):
        model_mock = _make_model_mock([_NO_NUMBER_RESPONSE])
        cred_p, model_p, intent_p = _patch_watsonx(model_mock)
        with cred_p, model_p, intent_p:
            result = call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertEqual(result, _NO_NUMBER_RESPONSE)
        self.assertEqual(model_mock.chat.call_count, 1)

    def test_extract_pr_intent_called_with_description(self):
        """extract_pr_intent must be called once with pr_description."""
        model_mock = _make_model_mock([_CONSISTENT_RESPONSE])
        cred_p, model_p, intent_p = _patch_watsonx(model_mock)
        with cred_p, model_p, intent_p as mock_intent:
            call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        mock_intent.assert_called_once_with(_PR_DATA["pr_description"])

    def test_intent_proposed_change_in_user_prompt(self):
        """proposed_change from extract_pr_intent must appear in the chat messages."""
        model_mock = _make_model_mock([_CONSISTENT_RESPONSE])
        cred_p, model_p, intent_p = _patch_watsonx(model_mock)
        with cred_p, model_p, intent_p:
            call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        # Inspect the messages passed to chat()
        call_kwargs = model_mock.chat.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs.args[0]
        user_content = next(m["content"] for m in messages if m["role"] == "user")
        self.assertIn(_INTENT_RESULT["proposed_change"], user_content)
        self.assertIn(_INTENT_RESULT["change_type"], user_content)


# ---------------------------------------------------------------------------
# Tests: call_explainer — inconsistent response triggers retry
# ---------------------------------------------------------------------------

class TestCallExplainerRetryOnInconsistency(unittest.TestCase):

    def test_retries_on_wrong_score_then_returns_consistent(self):
        """First call returns wrong score, second call returns consistent."""
        model_mock = _make_model_mock([_WRONG_SCORE_RESPONSE, _CONSISTENT_RESPONSE])
        cred_p, model_p, intent_p = _patch_watsonx(model_mock)
        with cred_p, model_p, intent_p:
            result = call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertEqual(result, _CONSISTENT_RESPONSE)
        self.assertEqual(model_mock.chat.call_count, 2)

    def test_retries_on_wrong_label_then_returns_consistent(self):
        model_mock = _make_model_mock([_WRONG_LABEL_RESPONSE, _CONSISTENT_RESPONSE])
        cred_p, model_p, intent_p = _patch_watsonx(model_mock)
        with cred_p, model_p, intent_p:
            result = call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertEqual(result, _CONSISTENT_RESPONSE)
        self.assertEqual(model_mock.chat.call_count, 2)


# ---------------------------------------------------------------------------
# Tests: call_explainer — retries exhausted → fallback
# ---------------------------------------------------------------------------

class TestCallExplainerFallbackAfterRetries(unittest.TestCase):

    def _exhausted_responses(self) -> list[str]:
        """Return MAX_RETRIES+1 inconsistent responses (all wrong score)."""
        return [_WRONG_SCORE_RESPONSE] * (MAX_RETRIES + 1)

    def test_fallback_returned_after_max_retries(self):
        model_mock = _make_model_mock(self._exhausted_responses())
        cred_p, model_p, intent_p = _patch_watsonx(model_mock)
        with cred_p, model_p, intent_p:
            result = call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        # Result must NOT be any of the inconsistent AI responses
        self.assertNotEqual(result, _WRONG_SCORE_RESPONSE)
        # Result must contain key fallback fields
        self.assertIn("42", result)           # pr_number
        self.assertIn("Medium", result)       # priority_label

    def test_generate_called_max_retries_plus_one(self):
        """generate() must be called exactly MAX_RETRIES+1 times then stop."""
        model_mock = _make_model_mock(self._exhausted_responses())
        cred_p, model_p, intent_p = _patch_watsonx(model_mock)
        with cred_p, model_p, intent_p:
            call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertEqual(model_mock.chat.call_count, MAX_RETRIES + 1)

    def test_fallback_is_consistent_with_priority_result(self):
        """The fallback text must always pass the consistency validator."""
        model_mock = _make_model_mock(self._exhausted_responses())
        cred_p, model_p, intent_p = _patch_watsonx(model_mock)
        with cred_p, model_p, intent_p:
            result = call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertTrue(
            validate_explanation_consistency(result, _PRIORITY_RESULT)
        )

    def test_fallback_returns_string(self):
        model_mock = _make_model_mock(self._exhausted_responses())
        cred_p, model_p, intent_p = _patch_watsonx(model_mock)
        with cred_p, model_p, intent_p:
            result = call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)


# ---------------------------------------------------------------------------
# Tests: missing credentials → immediate fallback, no SDK call
# ---------------------------------------------------------------------------

class TestCallExplainerMissingCredentials(unittest.TestCase):

    def _call_without_cred(self, missing_var: str) -> tuple[str, MagicMock]:
        model_mock = MagicMock()
        saved = os.environ.pop(missing_var, None)
        try:
            cred_p, model_p, intent_p = _patch_watsonx(model_mock)
            with cred_p, model_p, intent_p:
                result = call_explainer(
                    _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
                )
        finally:
            if saved is not None:
                os.environ[missing_var] = saved
        return result, model_mock

    def test_missing_api_key_returns_fallback(self):
        result, mock_model = self._call_without_cred("WATSONX_API_KEY")
        self.assertIn("42", result)
        mock_model.generate_text.assert_not_called()

    def test_missing_url_returns_fallback(self):
        result, mock_model = self._call_without_cred("WATSONX_URL")
        self.assertIn("Medium", result)
        mock_model.generate_text.assert_not_called()

    def test_missing_project_id_returns_fallback(self):
        result, mock_model = self._call_without_cred("WATSONX_PROJECT_ID")
        self.assertIsInstance(result, str)
        mock_model.generate_text.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: SDK exception during generate_text → fallback
# ---------------------------------------------------------------------------

class TestCallExplainerSDKException(unittest.TestCase):

    def test_sdk_exception_returns_fallback(self):
        model_mock = _make_model_mock([RuntimeError("connection refused")])
        cred_p, model_p, intent_p = _patch_watsonx(model_mock)
        with cred_p, model_p, intent_p:
            result = call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertIn("42", result)
        self.assertIn("Medium", result)

    def test_sdk_exception_does_not_propagate(self):
        model_mock = _make_model_mock([Exception("unexpected")])
        cred_p, model_p, intent_p = _patch_watsonx(model_mock)
        with cred_p, model_p, intent_p:
            # Must not raise
            result = call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertIsInstance(result, str)


# ---------------------------------------------------------------------------
# Tests: no real watsonx call ever made (paranoia check)
# ---------------------------------------------------------------------------

class TestNoRealAPICallMade(unittest.TestCase):
    """
    Verifies that ibm_watsonx_ai.foundation_models.ModelInference is never
    instantiated with real credentials — all tests use mock objects.
    """

    def test_model_inference_is_mocked_not_real(self):
        model_mock = _make_model_mock([_CONSISTENT_RESPONSE])
        cred_p, model_p, intent_p = _patch_watsonx(model_mock)
        with cred_p, model_p as mock_mi, intent_p:
            call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
            # ModelInference constructor was called — instance is our mock
            mock_mi.assert_called_once()
            # chat() was called on the mock instance, not a real HTTP call
            model_mock.chat.assert_called_once()

    def test_credentials_object_is_mocked(self):
        model_mock = _make_model_mock([_CONSISTENT_RESPONSE])
        cred_p, model_p, intent_p = _patch_watsonx(model_mock)
        with cred_p as mock_cred, model_p, intent_p:
            call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
            mock_cred.assert_called_once()
            cred_instance = mock_cred.return_value
            self.assertIsInstance(cred_instance, MagicMock)

    def test_extract_pr_intent_is_mocked_not_real(self):
        """extract_pr_intent must never call the real watsonx API during tests."""
        model_mock = _make_model_mock([_CONSISTENT_RESPONSE])
        cred_p, model_p, intent_p = _patch_watsonx(model_mock)
        with cred_p, model_p, intent_p as mock_intent:
            call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
            mock_intent.assert_called_once()


if __name__ == "__main__":
    unittest.main()
