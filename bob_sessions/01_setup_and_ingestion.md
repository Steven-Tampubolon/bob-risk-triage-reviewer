<!-- Excerpt from full session (bob_sessions/00_full_session_raw.md), lines 1-1114 -->
<!-- Modules built in this segment: Setup Project + ingestion/github_pr.py -->

# bob risk triager reviewer

---

**Status:** active  **Date:** 2026-08-28

---

### 👤 User

Buatkan module ingestion/github_pr.py dengan fungsi fetch_pr_list(owner, repo, since, until) dan fetch_pr_files(owner, repo, pr_number) yang memanggil GitHub REST API (https://api.github.com/repos/{owner}/{repo}/pulls). Gabungkan ke get_pr_diff_profile(owner, repo, pr_number) yang mengembalikan JSON sesuai schema berikut: {pr_number, files_changed, additions, deletions, modules_touched, has_migration, has_config_change, has_dependency_change, has_ci_change, pr_description}. Baca GITHUB_TOKEN dari environment variable pakai python-dotenv, kirim sebagai header Authorization Bearer. Tambahkan error handling untuk rate limit GitHub API (HTTP 403) dengan retry-after, dan timeout. Buat unit test di tests/test_ingestion.py dengan mock response (pakai responses atau unittest.mock), jangan panggil API asli saat test.

---

### 🤖 Assistant

> 🔧 called: list_files, list_files, list_files, read_file, read_file, update_todo_list, read_file



> 🔧 **list_files** — .

> 🔧 **list_files** — ingestion

> 🔧 **list_files** — tests

> 🔧 **read_file** — .env

> 🔧 **read_file** — requirements.txt

> 🔧 **update_todo_list** — 
[-] Create ingestion/github_pr.py with fetch_pr_list, fetch_pr_files, and get_pr_diff_profile
[ ] Add responses library to requirements.txt for test mocking
[ ] Create tests/test_ingestion.py with mock-based unit tests
[ ] Validate with pytest


> 🔧 **read_file** — ingestion/__init__.py

### 🤖 Assistant

> 🔧 called: write_file, write_file

Good — `requests` and `python-dotenv` are already in [`requirements.txt`](requirements.txt). I need to add `responses` for test mocking. Let me build everything now.

> 🔧 **write_file** — ingestion/github_pr.py

> 🔧 **write_file** — """
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
# Tests: _classify_files
# ---------------------------------------------------------------------------

class TestClassifyFiles(unittest.TestCase):
    def test_migration_detected(self):
        result = _classify_files(PR_FILES)
        self.assertTrue(result["has_migration"])

    def test_config_change_detected(self):
        result = _classify_files(PR_FILES)
        self.assertTrue(result["has_config_change"])

    def test_dependency_change_detected(self):
        result = _classify_files(PR_FILES)
        self.assertTrue(result["has_dependency_change"])

    def test_ci_change_detected(self):
        result = _classify_files(PR_FILES)
        self.assertTrue(result["has_ci_change"])

    def test_modules_touched(self):
        result = _classify_files(PR_FILES)
        self.assertIn("src", result["modules_touched"])
        self.assertIn("migrations", result["modules_touched"])
        self.assertIn("config", result["modules_touched"])

    def test_no_special_files(self):
        plain = [{"filename": "src/utils.py", "additions": 1, "deletions": 0}]
        result = _classify_files(plain)
        self.assertFalse(result["has_migration"])
        self.assertFalse(result["has_ci_change"])
        self.assertFalse(result["has_dependency_change"])


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
        self.assertTrue(profile["has_config_change"])


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


### 🤖 Assistant

> 🔧 called: apply_diff, execute_command, execute_command, execute_command

Now add `responses` to requirements.txt (useful for future tests) and run the tests:

> 🔧 **apply_diff** — requirements.txt

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && pip install responses --quiet && python -m pytest tests/test_ingestion.py -v 2>&1

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && python -m pytest tests/test_ingestion.py -v 2>&1

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && python3 -m pytest tests/test_ingestion.py -v 2>&1

### 🤖 Assistant

> 🔧 called: execute_command, execute_command, execute_command

There's a virtual environment to discover:

> 🔧 **execute_command** — find /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer -name "python*" -path "*/bin/*" 2>/dev/null | head -10; find /home/steven/projects/tech-xchange-2026-ibm -maxdepth 3 -name "activate" 2>/dev/null | head -10

> 🔧 **execute_command** — find /home/steven -maxdepth 5 -name "activate" 2>/dev/null | head -10; which python3; ls /home/steven/projects/tech-xchange-2026-ibm/

> 🔧 **execute_command** — python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt && .venv/bin/python -m pytest tests/test_ingestion.py -v 2>&1

### 🤖 Assistant

> 🔧 called: update_todo_list

**25/25 passed.** Let me update the todo list.

> 🔧 **update_todo_list** — 
[x] Create ingestion/github_pr.py with fetch_pr_list, fetch_pr_files, and get_pr_diff_profile
[x] Add responses library to requirements.txt for test mocking
[x] Create tests/test_ingestion.py with mock-based unit tests
[x] Validate with pytest


### 🤖 Assistant

All 25 tests pass. Here's a summary of what was built:

---

## What was created

### [`ingestion/github_pr.py`](ingestion/github_pr.py)

**Three public functions:**

| Function | Description |
|---|---|
| [`fetch_pr_list(owner, repo, since, until)`](ingestion/github_pr.py:103) | Paginates `GET /repos/{owner}/{repo}/pulls`. Client-side filters by `since`/`until` (ISO-8601 strings). Early-exits pagination once results pass the `since` boundary. |
| [`fetch_pr_files(owner, repo, pr_number)`](ingestion/github_pr.py:142) | Calls `GET /repos/{owner}/{repo}/pulls/{pr_number}/files` and returns the file list. |
| [`get_pr_diff_profile(owner, repo, pr_number)`](ingestion/github_pr.py:158) | Combines PR metadata + file list into the target JSON schema below. |

**Returned schema from `get_pr_diff_profile`:**
```json
{
  "pr_number": 42,
  "files_changed": 5,
  "additions": 55,
  "deletions": 12,
  "modules_touched": ["config", "migrations", "src"],
  "has_migration": true,
  "has_config_change": true,
  "has_dependency_change": true,
  "has_ci_change": true,
  "pr_description": "Fix the login flow and update dependencies."
}
```

**Rate-limit handling** in [`_request()`](ingestion/github_pr.py:55):
- Catches HTTP **403** and **429**
- Reads `Retry-After` header first, then `x-ratelimit-reset`, falls back to 60 s
- Retries up to **3 attempts** with `time.sleep()`, then raises `HTTPError` if exhausted
- Also propagates `requests.Timeout` unchanged

**Auth:** `GITHUB_TOKEN` loaded from `.env` via `python-dotenv`, sent as `Authorization: Bearer <token>`.

---

### [`tests/test_ingestion.py`](tests/test_ingestion.py)

25 tests across 5 test classes, all using `unittest.mock.patch` — zero real HTTP calls:

| Class | What it covers |
|---|---|
| `TestClassifyFiles` | Migration, config, dependency, CI detection; modules list; plain files |
| `TestFetchPrList` | Pagination, `since`/`until` filtering, empty repo, auth header presence |
| `TestFetchPrFiles` | Return value, correct URL construction |
| `TestGetPrDiffProfile` | Full schema shape, addition/deletion sums, description, null body, classifiers |
| `TestRateLimitRetry` | 403 retry→success, 429 retry→success, max retries exhausted, `x-ratelimit-reset` fallback, non-rate-limit 4xx, timeout |

---

### 👤 User

jalankan test untuk ingestion Semua test harus lulus TANPA memanggil API GitHub asli (cek tidak ada network call di test, harusnya full mock

---

### 🤖 Assistant

> 🔧 called: execute_command



> 🔧 **execute_command** — .venv/bin/python -m pytest tests/test_ingestion.py -v --tb=short 2>&1

### 🤖 Assistant

> 🔧 called: execute_command, execute_command

Sekarang verifikasi bahwa tidak ada network call asli — cek semua test menggunakan `@patch("ingestion.github_pr.requests.get")` dan tidak ada `requests.get` yang tidak di-mock:

> 🔧 **execute_command** — grep -n "@patch" tests/test_ingestion.py 2>&1

> 🔧 **execute_command** — grep -n "requests\." tests/test_ingestion.py | grep -v "mock\|patch\|MagicMock\|HTTPError\|Timeout\|spec=" 2>&1

### 🤖 Assistant

**25/25 PASSED ✅ — zero network calls.**

Hasil verifikasi lengkap:

| Pemeriksaan | Hasil |
|---|---|
| Semua 25 test lulus | ✅ |
| Waktu eksekusi | 0.15 detik (tidak ada I/O jaringan) |
| Setiap test yang memanggil HTTP di-cover `@patch` | ✅ — 19 `@patch("ingestion.github_pr.requests.get")` dekorator ditemukan |
| `requests.get` yang tidak di-mock | ✅ — tidak ada (grep exit 1 = 0 baris ditemukan) |
| `TestClassifyFiles` (6 test) | Murni logic — tidak ada HTTP sama sekali |
| `TestRateLimitRetry` (6 test) | `time.sleep` juga di-mock → tidak ada sleep nyata |

Semua call ke `requests.get` di-patch pada namespace `ingestion.github_pr.requests.get` (bukan `requests.get` global), sehingga mock terisolasi tepat di module yang diuji dan tidak ada celah network call bocor keluar.

---

### 👤 User

Buatkan script scripts/fetch_ha_core_sample.py yang memanggil get_pr_diff_profile() dari ingestion/github_pr.py untuk mengambil 5 PR nyata dari repo home-assistant/core yang di-merge antara 2026-03-01 dan 2026-08-27. Gunakan fetch_pr_list() dulu untuk dapat daftar PR di periode itu, ambil 5 PR pertama, lalu panggil get_pr_diff_profile() untuk masing-masing. Cetak hasilnya ke console dalam format JSON yang rapi (pakai json.dumps dengan indent=2), dan simpan juga ke file data/sample_5_prs.json. Baca GITHUB_TOKEN dari .env

---

### 🤖 Assistant

> 🔧 called: list_files, list_files, write_file



> 🔧 **list_files** — scripts

> 🔧 **list_files** — data

> 🔧 **write_file** — scripts/fetch_ha_core_sample.py

### 🤖 Assistant

> 🔧 called: execute_command

Script dibuat. Sekarang jalankan:

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && .venv/bin/python scripts/fetch_ha_core_sample.py 2>&1

### 🤖 Assistant

> 🔧 called: execute_command

Script berjalan sukses dan [`data/sample_5_prs.json`](data/sample_5_prs.json) sudah tersimpan. Verifikasi file output:

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && .venv/bin/python -c "
import json; data = json.load(open('data/sample_5_prs.json'))
print(f'PRs saved: {len(data)}')
for p in data:
    print(f'  PR #{p[\"pr_number\"]:>6} | files={p[\"files_changed\"]:>3} | +{p[\"additions\"]:>4}/-{p[\"deletions\"]:>3} | migration={p[\"has_migration\"]} ci={p[\"has_ci_change\"]} dep={p[\"has_dependency_change\"]} cfg={p[\"has_config_change\"]} | modules={p[\"modules_touched\"]}')
"

### 🤖 Assistant

Berhasil. Ringkasan hasil:

---

## Hasil eksekusi [`scripts/fetch_ha_core_sample.py`](scripts/fetch_ha_core_sample.py)

**10.538 PR** ditemukan di window `2026-03-01 → 2026-08-27` di repo `home-assistant/core`. 5 PR pertama diambil profilnya:

| PR # | Files | +/- | Config | Dep | CI | Migration | Modules |
|---|---|---|---|---|---|---|---|
| `#180428` | 2 | +2/-2 | ✅ | ❌ | ❌ | ❌ | `homeassistant`, `requirements_all.txt` |
| `#162240` | 1 | +6/-2 | ❌ | ❌ | ❌ | ❌ | `homeassistant` |
| `#178027` | 4 | +558/-0 | ✅ | ❌ | ❌ | ❌ | `homeassistant`, `tests` |
| `#180342` | 4 | +4/-1 | ❌ | ❌ | ❌ | ❌ | `homeassistant` |
| `#169704` | 3 | +55/-95 | ❌ | ❌ | ❌ | ❌ | `homeassistant`, `tests` |

**Output disimpan ke** [`data/sample_5_prs.json`](data/sample_5_prs.json) ✅

**Catatan performa:** `fetch_pr_list()` perlu memindai semua halaman API dari ujung terbaru ke batas `since` — untuk repo sebesar `home-assistant/core` dengan 10.000+ PR ini memakan ~5 menit. Untuk penggunaan produksi, bisa dioptimasi dengan parameter `page` langsung atau binary search pada nomor PR.

---

### 👤 User

Perbaiki ingestion/github_pr.py. Dua masalah: (1) modules_touched saat ini cuma mengambil segmen path pertama (level-1), sehingga hampir semua PR di home-assistant/core keliatan sebagai module tunggal homeassistant. Ubah supaya mengambil dua segmen path pertama untuk file di dalam homeassistant/components/ (contoh: homeassistant/components/motion_blinds), tapi tetap kembalikan tests atau nama top-level lain apa adanya untuk file di luar components/. (2) Logika deteksi has_config_change dan has_dependency_change salah kaprah — file requirements_all.txt, requirements.txt, manifest.json yang isinya bump versi dependency, package.json, go.mod harus set has_dependency_change=true, BUKAN has_config_change. has_config_change hanya untuk file configuration.yaml, const.py yang isinya default config, atau path yang eksplisit mengandung kata config. Perbaiki unit test di tests/test_ingestion.py untuk cover kedua kasus ini (PR yang bump dependency harus lulus assert has_dependency_change=True dan has_config_change=False).

---

### 🤖 Assistant

> 🔧 called: read_file, read_file

Let me read the current implementation before making changes.

> 🔧 **read_file** — ingestion/github_pr.py

> 🔧 **read_file** — tests/test_ingestion.py

### 🤖 Assistant

> 🔧 called: apply_diff

Sudah jelas masalahnya. Dua perubahan di [`ingestion/github_pr.py`](ingestion/github_pr.py) dan update test yang sesuai:

> 🔧 **apply_diff** — ingestion/github_pr.py

### 🤖 Assistant

> 🔧 called: apply_diff, execute_command

Now update the tests. The key changes needed:
1. `PR_FILES` fixture has `requirements.txt` → must assert `has_dependency_change=True` **and** `has_config_change=False` for that file
2. `config/settings.yaml` → this still triggers `has_config_change` (path contains `config/`) ✓
3. `test_config_change_detected` in the old fixture is still valid (because `config/settings.yaml` passes the new `config/` keyword)
4. Add new test class for `modules_touched` with HA component paths, and dependency-vs-config disambiguation

> 🔧 **apply_diff** — <<<<<<< SEARCH
:start_line:1
-------
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
    _request,
)
=======
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
>>>>>>> REPLACE

<<<<<<< SEARCH
:start_line:95
-------
# ---------------------------------------------------------------------------
# Tests: _classify_files
# ---------------------------------------------------------------------------

class TestClassifyFiles(unittest.TestCase):
    def test_migration_detected(self):
        result = _classify_files(PR_FILES)
        self.assertTrue(result["has_migration"])

    def test_config_change_detected(self):
        result = _classify_files(PR_FILES)
        self.assertTrue(result["has_config_change"])

    def test_dependency_change_detected(self):
        result = _classify_files(PR_FILES)
        self.assertTrue(result["has_dependency_change"])

    def test_ci_change_detected(self):
        result = _classify_files(PR_FILES)
        self.assertTrue(result["has_ci_change"])

    def test_modules_touched(self):
        result = _classify_files(PR_FILES)
        self.assertIn("src", result["modules_touched"])
        self.assertIn("migrations", result["modules_touched"])
        self.assertIn("config", result["modules_touched"])

    def test_no_special_files(self):
        plain = [{"filename": "src/utils.py", "additions": 1, "deletions": 0}]
        result = _classify_files(plain)
        self.assertFalse(result["has_migration"])
        self.assertFalse(result["has_ci_change"])
        self.assertFalse(result["has_dependency_change"])
=======
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
>>>>>>> REPLACE

<<<<<<< SEARCH
:start_line:288
-------
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
        self.assertTrue(profile["has_config_change"])
=======
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
>>>>>>> REPLACE


> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && .venv/bin/python -m pytest tests/test_ingestion.py -v 2>&1

### 🤖 Assistant

**52/52 passed.** Berikut ringkasan perubahan yang dibuat:

---

## Perubahan yang dilakukan

### [`ingestion/github_pr.py`](ingestion/github_pr.py)

**Fix #1 — `modules_touched` (fungsi [`_module_key()`](ingestion/github_pr.py:213))**

| Path file | Sebelum | Sesudah |
|---|---|---|
| `homeassistant/components/motion_blinds/sensor.py` | `homeassistant` | `homeassistant/components/motion_blinds` |
| `homeassistant/components/zwave_js/__init__.py` | `homeassistant` | `homeassistant/components/zwave_js` |
| `homeassistant/helpers/entity.py` | `homeassistant` | `homeassistant` (tetap, bukan `components`) |
| `tests/components/...` | `tests` | `tests` (tetap) |

Aturan: hanya `homeassistant/components/<name>/` yang dapat dua segmen; semua path lain tetap segmen pertama.

**Fix #2 — Pemisahan dependency vs config**

Diganti dari regex substring `.yaml/.json` yang over-broad menjadi dua fungsi eksplisit:

- [`_is_dependency_file()`](ingestion/github_pr.py:228) — cocokkan berdasarkan **basename** terhadap `frozenset` nama file yang dikenal (`manifest.json`, `requirements_all.txt`, `package.json`, `go.mod`, dst.). Dependency dirs (`requirements/`) cocokkan via prefix.
- [`_is_config_file()`](ingestion/github_pr.py:236) — cocokkan **path keywords** eksplisit (`config/`, `configuration.yaml`, `const.py`, `.cfg`, `.ini`, dll.), **setelah** memastikan file tersebut bukan dependency (sehingga `manifest.json` tidak bisa flip `has_config_change`).

### [`tests/test_ingestion.py`](tests/test_ingestion.py)

Dua test class baru ditambahkan:

- **`TestModuleKey`** (6 test) — unit test untuk `_module_key()` secara langsung
- **`TestDependencyVsConfigClassifiers`** (14 test) — verifikasi positif/negatif untuk `_is_dependency_file()` dan `_is_config_file()`, termasuk kasus kritis: `manifest.json` → dep ✅, bukan config ✅

Plus 3 test baru di class yang sudah ada:
- `TestClassifyFiles.test_ha_dependency_bump_pr` — `requirements_all.txt` + `manifest.json` → `dep=True, config=False`
- `TestClassifyFiles.test_modules_touched_ha_components` — verifikasi component path HA
- `TestGetPrDiffProfile.test_ha_dependency_bump_no_config_change` — integrasi end-to-end
- `TestGetPrDiffProfile.test_ha_modules_touched_uses_component_path` — integrasi end-to-end

---

### 👤 User

jalankan lagi scripts/fetch_ha_core_sample.py untuk 5 PR yang sama

---

### 🤖 Assistant

> 🔧 called: execute_command

Data di [`data/sample_5_prs.json`](data/sample_5_prs.json) sudah ada — saya perlu tahu PR number yang diambil sebelumnya supaya bisa di-hardcode untuk run cepat, atau langsung jalankan ulang script-nya. Mari jalankan langsung:

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && .venv/bin/python scripts/fetch_ha_core_sample.py 2>&1

### 🤖 Assistant

Berhasil. Perbedaan hasil sebelum vs sesudah perbaikan sangat terlihat jelas:

## Perbandingan hasil — fix classifier bekerja di data nyata

| PR # | Field | **Sebelum fix** | **Sesudah fix** |
|---|---|---|---|
| `#180428` | `modules_touched` | `["homeassistant", "requirements_all.txt"]` | `["homeassistant/components/neopool", "requirements_all.txt"]` ✅ |
| `#180428` | `has_dependency_change` | `false` | `true` ✅ (requirements_all.txt terdeteksi) |
| `#180428` | `has_config_change` | `true` ❌ | `false` ✅ |
| `#162240` | `modules_touched` | `["homeassistant"]` | `["homeassistant/components/apprise"]` ✅ |
| `#178027` | `modules_touched` | `["homeassistant", "tests"]` | `["homeassistant/components/monarch_money", "tests"]` ✅ |
| `#178027` | `has_config_change` | `true` ❌ | `false` ✅ |
| `#180342` | `modules_touched` | `["homeassistant"]` | `["homeassistant/components/nice_go"]` ✅ |
| `#169704` | `modules_touched` | `["homeassistant", "tests"]` | `["homeassistant/components/proxmoxve", "tests"]` ✅ |

Semua 5 PR sekarang menampilkan nama component spesifik di `modules_touched`, dan PR #180428 (dependency bump `neopool-modbus`) kini tepat mengset `has_dependency_change=true, has_config_change=false`.

---

### 👤 User

Buatkan script scripts/fetch_ha_core_100.py yang memanggil fetch_pr_list('home-assistant', 'core', since='2026-03-01', until='2026-08-27') dari ingestion/github_pr.py untuk dapat daftar PR merged di periode itu, ambil 100 PR pertama dari hasilnya, lalu panggil get_pr_diff_profile() untuk masing-masing PR. Simpan seluruh hasil sebagai list of JSON ke file data/home_assistant_100prs.json (pakai json.dump dengan indent=2). Tampilkan progress ke console setiap 10 PR selesai diproses (misal 'Processed 10/100 PRs...') supaya saya tahu prosesnya masih berjalan. Baca GITHUB_TOKEN dari .env. Tangani rate limit dengan retry-after seperti sebelumnya.

---

### 🤖 Assistant

