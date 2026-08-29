"""
tests/test_ingestion.py

Unit tests for ingestion/github_pr.py — all GitHub API calls are mocked;
no real network traffic is made.
"""

import os
import time
import unittest
from unittest.mock import patch, MagicMock

import requests

# Ensure no real token leaks into tests
os.environ.setdefault("GITHUB_TOKEN", "test-token")

from ingestion.github_pr import (  # noqa: E402
    fetch_pr_list,
    fetch_pr_files,
    get_pr_diff_profile,
    _classify_files,
    _module_key,
    _is_dependency_file,
    _is_config_file,
    _request,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

OWNER = "acme"
REPO = "backend"
PR_NUMBER = 42

PR_META = {
    "number": PR_NUMBER,
    "state": "closed",
    "updated_at": "2024-05-10T12:00:00Z",
    "body": "Fix the login flow and update dependencies.",
}

PR_FILES = [
    {
        "filename": "src/auth/login.py",
        "additions": 30,
        "deletions": 10,
        "status": "modified",
    },
    {
        "filename": "requirements.txt",
        "additions": 2,
        "deletions": 1,
        "status": "modified",
    },
    {
        "filename": ".github/workflows/ci.yml",
        "additions": 5,
        "deletions": 0,
        "status": "added",
    },
    {
        "filename": "migrations/0042_add_user_flag.sql",
        "additions": 15,
        "deletions": 0,
        "status": "added",
    },
    {
        "filename": "config/settings.yaml",
        "additions": 3,
        "deletions": 1,
        "status": "modified",
    },
]

PR_LIST_PAGE1 = [
    {"number": 1, "updated_at": "2024-05-10T11:00:00Z"},
    {"number": 2, "updated_at": "2024-05-09T08:00:00Z"},
]


def _make_response(json_data, status_code=200, headers=None):
    """Return a mock requests.Response-like object."""
    mock = MagicMock(spec=requests.Response)
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.headers = headers or {}
    mock.raise_for_status = MagicMock()
    if status_code >= 400:
        mock.raise_for_status.side_effect = requests.HTTPError(
            response=mock
        )
    return mock


# ---------------------------------------------------------------------------
# Tests: _module_key
# ---------------------------------------------------------------------------

class TestModuleKey(unittest.TestCase):
    def test_ha_component_returns_two_segment_key(self):
        self.assertEqual(
            _module_key("homeassistant/components/motion_blinds/sensor.py"),
            "homeassistant/components/motion_blinds",
        )

    def test_ha_component_init_file(self):
        self.assertEqual(
            _module_key("homeassistant/components/zwave_js/__init__.py"),
            "homeassistant/components/zwave_js",
        )

    def test_ha_non_component_returns_top_segment(self):
        # homeassistant/helpers/... → just "homeassistant"
        self.assertEqual(
            _module_key("homeassistant/helpers/entity.py"),
            "homeassistant",
        )

    def test_tests_returns_top_segment(self):
        self.assertEqual(
            _module_key("tests/components/motion_blinds/test_sensor.py"),
            "tests",
        )

    def test_top_level_file_returns_filename(self):
        self.assertEqual(_module_key("requirements_all.txt"), "requirements_all.txt")

    def test_scripts_dir(self):
        self.assertEqual(_module_key("scripts/gen_requirements_all.py"), "scripts")


# ---------------------------------------------------------------------------
# Tests: _is_dependency_file / _is_config_file
# ---------------------------------------------------------------------------

class TestDependencyVsConfigClassifiers(unittest.TestCase):
    # --- dependency positives ---
    def test_requirements_txt_is_dependency(self):
        self.assertTrue(_is_dependency_file("requirements.txt"))

    def test_requirements_all_txt_is_dependency(self):
        self.assertTrue(_is_dependency_file("requirements_all.txt"))

    def test_manifest_json_is_dependency(self):
        self.assertTrue(
            _is_dependency_file("homeassistant/components/hue/manifest.json")
        )

    def test_package_json_is_dependency(self):
        self.assertTrue(_is_dependency_file("frontend/package.json"))

    def test_go_mod_is_dependency(self):
        self.assertTrue(_is_dependency_file("go.mod"))

    def test_pyproject_toml_is_dependency(self):
        self.assertTrue(_is_dependency_file("pyproject.toml"))

    def test_requirements_subdir_is_dependency(self):
        self.assertTrue(_is_dependency_file("requirements/base.txt"))

    # --- dependency negatives (must NOT be mistaken for dependency) ---
    def test_source_yaml_not_dependency(self):
        self.assertFalse(_is_dependency_file("config/settings.yaml"))

    def test_arbitrary_json_not_dependency(self):
        self.assertFalse(_is_dependency_file("data/fixtures/response.json"))

    # --- config positives ---
    def test_config_dir_yaml_is_config(self):
        self.assertTrue(_is_config_file("config/settings.yaml"))

    def test_configuration_yaml_is_config(self):
        self.assertTrue(_is_config_file("configuration.yaml"))

    def test_const_py_is_config(self):
        self.assertTrue(
            _is_config_file("homeassistant/components/hue/const.py")
        )

    def test_ini_file_is_config(self):
        self.assertTrue(_is_config_file("setup.ini"))

    # --- config negatives: dependency files must NOT set has_config_change ---
    def test_manifest_json_not_config(self):
        self.assertFalse(
            _is_config_file("homeassistant/components/hue/manifest.json")
        )

    def test_requirements_all_not_config(self):
        self.assertFalse(_is_config_file("requirements_all.txt"))

    def test_package_json_not_config(self):
        self.assertFalse(_is_config_file("frontend/package.json"))

    def test_plain_source_py_not_config(self):
        self.assertFalse(_is_config_file("homeassistant/components/hue/sensor.py"))


# ---------------------------------------------------------------------------
# Tests: _classify_files
# ---------------------------------------------------------------------------

class TestClassifyFiles(unittest.TestCase):
    def test_migration_detected(self):
        result = _classify_files(PR_FILES)
        self.assertTrue(result["has_migration"])

    def test_config_change_detected(self):
        # config/settings.yaml triggers config (path contains "config/")
        result = _classify_files(PR_FILES)
        self.assertTrue(result["has_config_change"])

    def test_dependency_change_detected(self):
        result = _classify_files(PR_FILES)
        self.assertTrue(result["has_dependency_change"])

    def test_ci_change_detected(self):
        result = _classify_files(PR_FILES)
        self.assertTrue(result["has_ci_change"])

    def test_modules_touched_generic_repo(self):
        # PR_FILES uses src/, migrations/, config/ — all return top-level segment
        result = _classify_files(PR_FILES)
        self.assertIn("src", result["modules_touched"])
        self.assertIn("migrations", result["modules_touched"])
        self.assertIn("config", result["modules_touched"])

    def test_modules_touched_ha_components(self):
        ha_files = [
            {"filename": "homeassistant/components/motion_blinds/sensor.py",
             "additions": 5, "deletions": 0},
            {"filename": "homeassistant/components/zwave_js/__init__.py",
             "additions": 2, "deletions": 1},
            {"filename": "homeassistant/helpers/entity.py",
             "additions": 1, "deletions": 0},
            {"filename": "tests/components/motion_blinds/test_sensor.py",
             "additions": 10, "deletions": 0},
        ]
        result = _classify_files(ha_files)
        self.assertIn("homeassistant/components/motion_blinds", result["modules_touched"])
        self.assertIn("homeassistant/components/zwave_js", result["modules_touched"])
        # homeassistant/helpers → top-level "homeassistant"
        self.assertIn("homeassistant", result["modules_touched"])
        # tests → top-level only
        self.assertIn("tests", result["modules_touched"])
        # Should NOT collapse everything into a single "homeassistant" entry
        self.assertGreater(len(result["modules_touched"]), 1)

    def test_ha_dependency_bump_pr(self):
        """requirements_all.txt + manifest.json must set dep=True, config=False."""
        dep_files = [
            {"filename": "requirements_all.txt", "additions": 1, "deletions": 1},
            {"filename": "homeassistant/components/hue/manifest.json",
             "additions": 1, "deletions": 1},
        ]
        result = _classify_files(dep_files)
        self.assertTrue(result["has_dependency_change"])
        self.assertFalse(result["has_config_change"])

    def test_no_special_files(self):
        plain = [{"filename": "src/utils.py", "additions": 1, "deletions": 0}]
        result = _classify_files(plain)
        self.assertFalse(result["has_migration"])
        self.assertFalse(result["has_ci_change"])
        self.assertFalse(result["has_dependency_change"])
        self.assertFalse(result["has_config_change"])


# ---------------------------------------------------------------------------
# Tests: fetch_pr_list
# ---------------------------------------------------------------------------

class TestFetchPrList(unittest.TestCase):
    @patch("ingestion.github_pr.requests.get")
    def test_returns_pr_list(self, mock_get):
        mock_get.return_value = _make_response(PR_LIST_PAGE1)

        result = fetch_pr_list(OWNER, REPO)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["number"], 1)

    @patch("ingestion.github_pr.requests.get")
    def test_since_filter_stops_early(self, mock_get):
        # Page returns two PRs; only the first is within the since window
        mock_get.return_value = _make_response(PR_LIST_PAGE1)

        result = fetch_pr_list(OWNER, REPO, since="2024-05-10T00:00:00Z")

        # PR #1 updated at 2024-05-10T11 is OK; PR #2 updated at 2024-05-09 is before since
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["number"], 1)

    @patch("ingestion.github_pr.requests.get")
    def test_until_filter_excludes_newer(self, mock_get):
        mock_get.return_value = _make_response(PR_LIST_PAGE1)

        result = fetch_pr_list(OWNER, REPO, until="2024-05-09T23:59:59Z")

        # Only PR #2 (2024-05-09) passes; PR #1 (2024-05-10) is after until
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["number"], 2)

    @patch("ingestion.github_pr.requests.get")
    def test_empty_repo_returns_empty_list(self, mock_get):
        mock_get.return_value = _make_response([])

        result = fetch_pr_list(OWNER, REPO)
        self.assertEqual(result, [])

    @patch("ingestion.github_pr.requests.get")
    def test_auth_header_sent(self, mock_get):
        mock_get.return_value = _make_response(PR_LIST_PAGE1)

        fetch_pr_list(OWNER, REPO)

        _, kwargs = mock_get.call_args
        headers = kwargs.get("headers", {})
        self.assertIn("Authorization", headers)
        self.assertTrue(headers["Authorization"].startswith("Bearer "))


# ---------------------------------------------------------------------------
# Tests: fetch_pr_files
# ---------------------------------------------------------------------------

class TestFetchPrFiles(unittest.TestCase):
    @patch("ingestion.github_pr.requests.get")
    def test_returns_file_list(self, mock_get):
        mock_get.return_value = _make_response(PR_FILES)

        result = fetch_pr_files(OWNER, REPO, PR_NUMBER)

        self.assertEqual(len(result), len(PR_FILES))
        filenames = [f["filename"] for f in result]
        self.assertIn("requirements.txt", filenames)

    @patch("ingestion.github_pr.requests.get")
    def test_correct_url_called(self, mock_get):
        mock_get.return_value = _make_response(PR_FILES)

        fetch_pr_files(OWNER, REPO, PR_NUMBER)

        args, _ = mock_get.call_args
        expected_url = (
            f"https://api.github.com/repos/{OWNER}/{REPO}/pulls/{PR_NUMBER}/files"
        )
        self.assertEqual(args[0], expected_url)


# ---------------------------------------------------------------------------
# Tests: get_pr_diff_profile
# ---------------------------------------------------------------------------

class TestGetPrDiffProfile(unittest.TestCase):
    @patch("ingestion.github_pr.requests.get")
    def test_full_profile_schema(self, mock_get):
        # First call → PR metadata; second call → file list
        mock_get.side_effect = [
            _make_response(PR_META),
            _make_response(PR_FILES),
        ]

        profile = get_pr_diff_profile(OWNER, REPO, PR_NUMBER)

        required_keys = {
            "pr_number",
            "files_changed",
            "additions",
            "deletions",
            "modules_touched",
            "has_migration",
            "has_config_change",
            "has_dependency_change",
            "has_ci_change",
            "pr_description",
        }
        self.assertEqual(set(profile.keys()), required_keys)

    @patch("ingestion.github_pr.requests.get")
    def test_addition_deletion_sums(self, mock_get):
        mock_get.side_effect = [
            _make_response(PR_META),
            _make_response(PR_FILES),
        ]

        profile = get_pr_diff_profile(OWNER, REPO, PR_NUMBER)

        expected_additions = sum(f["additions"] for f in PR_FILES)
        expected_deletions = sum(f["deletions"] for f in PR_FILES)
        self.assertEqual(profile["additions"], expected_additions)
        self.assertEqual(profile["deletions"], expected_deletions)

    @patch("ingestion.github_pr.requests.get")
    def test_pr_description_from_body(self, mock_get):
        mock_get.side_effect = [
            _make_response(PR_META),
            _make_response(PR_FILES),
        ]

        profile = get_pr_diff_profile(OWNER, REPO, PR_NUMBER)

        self.assertEqual(profile["pr_description"], PR_META["body"])

    @patch("ingestion.github_pr.requests.get")
    def test_null_body_becomes_empty_string(self, mock_get):
        meta_no_body = {**PR_META, "body": None}
        mock_get.side_effect = [
            _make_response(meta_no_body),
            _make_response(PR_FILES),
        ]

        profile = get_pr_diff_profile(OWNER, REPO, PR_NUMBER)

        self.assertEqual(profile["pr_description"], "")

    @patch("ingestion.github_pr.requests.get")
    def test_pr_number_in_profile(self, mock_get):
        mock_get.side_effect = [
            _make_response(PR_META),
            _make_response(PR_FILES),
        ]

        profile = get_pr_diff_profile(OWNER, REPO, PR_NUMBER)
        self.assertEqual(profile["pr_number"], PR_NUMBER)

    @patch("ingestion.github_pr.requests.get")
    def test_classifiers_propagated(self, mock_get):
        mock_get.side_effect = [
            _make_response(PR_META),
            _make_response(PR_FILES),
        ]

        profile = get_pr_diff_profile(OWNER, REPO, PR_NUMBER)

        self.assertTrue(profile["has_migration"])
        self.assertTrue(profile["has_dependency_change"])
        self.assertTrue(profile["has_ci_change"])
        # config/settings.yaml (path contains "config/") → True
        self.assertTrue(profile["has_config_change"])

    @patch("ingestion.github_pr.requests.get")
    def test_ha_dependency_bump_no_config_change(self, mock_get):
        """requirements_all.txt + manifest.json must set dep=True, config=False."""
        ha_dep_files = [
            {"filename": "requirements_all.txt", "additions": 1, "deletions": 1},
            {"filename": "homeassistant/components/hue/manifest.json",
             "additions": 1, "deletions": 1},
        ]
        mock_get.side_effect = [
            _make_response(PR_META),
            _make_response(ha_dep_files),
        ]

        profile = get_pr_diff_profile(OWNER, REPO, PR_NUMBER)

        self.assertTrue(profile["has_dependency_change"])
        self.assertFalse(profile["has_config_change"])

    @patch("ingestion.github_pr.requests.get")
    def test_ha_modules_touched_uses_component_path(self, mock_get):
        """Files under homeassistant/components/<name>/ get two-segment module key."""
        ha_files = [
            {"filename": "homeassistant/components/motion_blinds/sensor.py",
             "additions": 5, "deletions": 0},
            {"filename": "tests/components/motion_blinds/test_sensor.py",
             "additions": 10, "deletions": 0},
        ]
        mock_get.side_effect = [
            _make_response(PR_META),
            _make_response(ha_files),
        ]

        profile = get_pr_diff_profile(OWNER, REPO, PR_NUMBER)

        self.assertIn("homeassistant/components/motion_blinds", profile["modules_touched"])
        self.assertIn("tests", profile["modules_touched"])


# ---------------------------------------------------------------------------
# Tests: rate-limit retry logic
# ---------------------------------------------------------------------------

class TestRateLimitRetry(unittest.TestCase):
    @patch("ingestion.github_pr.time.sleep")
    @patch("ingestion.github_pr.requests.get")
    def test_retries_on_403_then_succeeds(self, mock_get, mock_sleep):
        rate_limit_resp = _make_response(
            {"message": "rate limit exceeded"},
            status_code=403,
            headers={"Retry-After": "2"},
        )
        # raise_for_status should NOT raise on the rate-limit response (we handle it)
        rate_limit_resp.raise_for_status = MagicMock()

        success_resp = _make_response(PR_LIST_PAGE1, status_code=200)

        mock_get.side_effect = [rate_limit_resp, success_resp]

        result = _request("https://api.github.com/repos/acme/backend/pulls")

        self.assertEqual(result, PR_LIST_PAGE1)
        mock_sleep.assert_called_once_with(2)

    @patch("ingestion.github_pr.time.sleep")
    @patch("ingestion.github_pr.requests.get")
    def test_retries_on_429_with_retry_after(self, mock_get, mock_sleep):
        rate_limit_resp = _make_response(
            {"message": "too many requests"},
            status_code=429,
            headers={"Retry-After": "5"},
        )
        rate_limit_resp.raise_for_status = MagicMock()

        success_resp = _make_response(PR_FILES, status_code=200)

        mock_get.side_effect = [rate_limit_resp, success_resp]

        result = _request("https://api.github.com/repos/acme/backend/pulls/42/files")

        self.assertEqual(result, PR_FILES)
        mock_sleep.assert_called_once_with(5)

    @patch("ingestion.github_pr.time.sleep")
    @patch("ingestion.github_pr.requests.get")
    def test_raises_after_max_retries(self, mock_get, mock_sleep):
        rate_limit_resp = _make_response(
            {"message": "rate limit exceeded"},
            status_code=403,
            headers={"Retry-After": "1"},
        )

        mock_get.return_value = rate_limit_resp

        with self.assertRaises(requests.HTTPError):
            _request("https://api.github.com/repos/acme/backend/pulls")

        # sleep should have been called for each retry (max_retries - 1 = 2 times)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("ingestion.github_pr.time.sleep")
    @patch("ingestion.github_pr.time.time", return_value=1000)
    @patch("ingestion.github_pr.requests.get")
    def test_uses_ratelimit_reset_header_when_no_retry_after(
        self, mock_get, mock_time, mock_sleep
    ):
        rate_limit_resp = _make_response(
            {"message": "rate limit exceeded"},
            status_code=403,
            headers={"x-ratelimit-reset": "1060"},  # 60 seconds from now
        )
        rate_limit_resp.raise_for_status = MagicMock()
        success_resp = _make_response(PR_LIST_PAGE1)

        mock_get.side_effect = [rate_limit_resp, success_resp]

        _request("https://api.github.com/repos/acme/backend/pulls")

        mock_sleep.assert_called_once_with(60)

    @patch("ingestion.github_pr.requests.get")
    def test_raises_on_non_rate_limit_http_error(self, mock_get):
        not_found = _make_response({"message": "Not Found"}, status_code=404)
        mock_get.return_value = not_found

        with self.assertRaises(requests.HTTPError):
            _request("https://api.github.com/repos/acme/missing/pulls")

    @patch("ingestion.github_pr.requests.get")
    def test_raises_on_timeout(self, mock_get):
        mock_get.side_effect = requests.Timeout()

        with self.assertRaises(requests.Timeout):
            _request("https://api.github.com/repos/acme/backend/pulls")


if __name__ == "__main__":
    unittest.main()
