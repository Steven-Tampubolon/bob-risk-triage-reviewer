<!-- Excerpt from full session (bob_sessions/00_full_session_raw.md), lines 4726-5766 -->
<!-- Modules built in this segment: scripts/build_priority_queue.py + scripts/test_explainer_live.py -->

Buatkan script scripts/build_priority_queue.py yang membaca data/home_assistant_100prs.json, menjalankan pipeline score_blast_radius → score_security_policy → combine_priority untuk setiap PR, lalu simpan hasilnya sebagai list JSON ke output/priority_queue.json dengan field: pr_number, blast_radius_label, priority_score, priority_label, merge_blocker, required_reviewer." Jalankan: python scripts/build_priority_queue.py

---

### 🤖 Assistant

> 🔧 called: write_file, execute_command



> 🔧 **write_file** — """
scripts/build_priority_queue.py

Reads data/home_assistant_100prs.json, runs the full scoring pipeline
(score_blast_radius → score_security_policy → combine_priority) for every PR,
and writes the prioritised queue to output/priority_queue.json.

Output schema per PR:
    {
        "pr_number":          int,
        "blast_radius_label": str,   # "multi_module" | "small_or_local"
        "priority_score":     int,   # 0-100
        "priority_label":     str,   # "Low" | "Medium" | "High" | "Critical"
        "merge_blocker":      bool,
        "required_reviewer":  str | null
    }

The list is sorted by priority_score descending so the most urgent PRs
appear at the top.

Usage:
    python scripts/build_priority_queue.py
"""

import json
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scoring.blast_radius import score_blast_radius
from scoring.security_policy import score_security_policy
from priority.combine import combine_priority

INPUT_PATH  = Path(__file__).resolve().parent.parent / "data"  / "home_assistant_100prs.json"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "output" / "priority_queue.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    if not INPUT_PATH.exists():
        logger.error("Input file not found: %s", INPUT_PATH)
        sys.exit(1)

    profiles = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    logger.info("Loaded %d PR profiles from %s", len(profiles), INPUT_PATH.name)

    queue = []
    for p in profiles:
        br_result  = score_blast_radius(p)
        sec_result = score_security_policy(p)
        pri_score, pri_label = combine_priority(br_result, sec_result)

        queue.append({
            "pr_number":         p["pr_number"],
            "blast_radius_label": br_result[1],
            "priority_score":    pri_score,
            "priority_label":    pri_label,
            "merge_blocker":     sec_result[1],
            "required_reviewer": sec_result[0],
        })

    # Sort by priority_score descending; tie-break on pr_number ascending
    queue.sort(key=lambda r: (-r["priority_score"], r["pr_number"]))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(queue, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Priority queue saved to %s  (%d entries)", OUTPUT_PATH, len(queue))

    # Quick summary to console
    from collections import Counter
    label_dist = Counter(r["priority_label"] for r in queue)
    blockers   = sum(1 for r in queue if r["merge_blocker"])
    print()
    for lbl in ("Critical", "High", "Medium", "Low"):
        print(f"  {lbl:<10} {label_dist[lbl]:>3} PR")
    print(f"  {'merge_blocker':.<10} {blockers:>3} PR")
    print()


if __name__ == "__main__":
    main()


> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && .venv/bin/python scripts/build_priority_queue.py 2>&1

### 🤖 Assistant

> 🔧 called: execute_command

Selesai. Verifikasi isi output:

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && .venv/bin/python -c "
import json
q = json.load(open('output/priority_queue.json'))
print(f'Total entries : {len(q)}')
print()
print('Top 10 (highest priority_score):')
print(f'  {\"PR #\":<8} {\"score\":>5}  {\"label\":<10}  {\"blast\":<14}  {\"blocker\":<8}  reviewer')
print(f'  {\"-\"*8}  {\"-\"*5}  {\"-\"*10}  {\"-\"*14}  {\"-\"*8}  {\"-\"*20}')
for r in q[:10]:
    print(f'  #{r[\"pr_number\"]:<7} {r[\"priority_score\"]:>5}  {r[\"priority_label\"]:<10}  {r[\"blast_radius_label\"]:<14}  {str(r[\"merge_blocker\"]):<8}  {r[\"required_reviewer\"] or \"-\"}')
print()
print('Bottom 5 (lowest priority_score):')
for r in q[-5:]:
    print(f'  #{r[\"pr_number\"]:<7} {r[\"priority_score\"]:>5}  {r[\"priority_label\"]:<10}  {r[\"blast_radius_label\"]:<14}  {str(r[\"merge_blocker\"]):<8}  {r[\"required_reviewer\"] or \"-\"}')
"


### 🤖 Assistant

**100 entries tersimpan ke [`output/priority_queue.json`](output/priority_queue.json)**, diurutkan dari skor tertinggi ke terendah.

Distribusi hasil pipeline:

| Label | Count | Keterangan |
|---|---|---|
| **Critical** | 30 PR | Semua karena `merge_blocker=True` (security policy override) |
| High | 0 PR | — |
| Medium | 20 PR | `multi_module` tanpa security block |
| Low | 50 PR | `small_or_local`, bersih |

**Top scorer** (skor 75): PR yang sekaligus `multi_module` + `merge_blocker=True` + dependency-review required — kombinasi blast-radius tinggi dan security flag aktif. Ini adalah PR dengan risiko tertinggi yang memerlukan perhatian reviewer pertama.

Schema setiap entry di [`output/priority_queue.json`](output/priority_queue.json):
```json
{
  "pr_number": 176825,
  "blast_radius_label": "multi_module",
  "priority_score": 75,
  "priority_label": "Critical",
  "merge_blocker": true,
  "required_reviewer": "dependency-review"
}
```

---

### 👤 User

Buatkan script scripts/test_explainer_live.py yang ambil 3 PR dari output/priority_queue.json (yang skor tertinggi, sedang, terendah), cari data profile lengkapnya di data/home_assistant_100prs.json berdasarkan pr_number, jalankan ulang score_blast_radius dan score_security_policy untuk dapat objek result yang lengkap, lalu panggil call_explainer() untuk tiap PR dan print hasil penjelasannya ke console dengan format jelas per PR." Jalankan: python scripts/test_explainer_live.py — INI PANGGILAN API ASLI, bukan mock

---

### 🤖 Assistant

> 🔧 called: write_file, execute_command



> 🔧 **write_file** — """
scripts/test_explainer_live.py

Picks 3 PRs from output/priority_queue.json (highest, median, lowest score),
looks up their full diff profiles in data/home_assistant_100prs.json, re-runs
the scoring pipeline, and calls call_explainer() — a LIVE watsonx.ai API call.

This script is intentionally NOT mocked.  Requires .env with:
    WATSONX_API_KEY=...
    WATSONX_URL=...
    WATSONX_PROJECT_ID=...

Usage:
    python scripts/test_explainer_live.py
"""

import json
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from scoring.blast_radius import score_blast_radius
from scoring.security_policy import score_security_policy
from priority.combine import combine_priority
from ai_layer.explainer import call_explainer

QUEUE_PATH   = Path(__file__).resolve().parent.parent / "output" / "priority_queue.json"
PROFILE_PATH = Path(__file__).resolve().parent.parent / "data"   / "home_assistant_100prs.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DIVIDER = "=" * 68


def pick_three(queue: list[dict]) -> list[dict]:
    """Return [highest-score, median-score, lowest-score] entries."""
    sorted_q = sorted(queue, key=lambda r: (-r["priority_score"], r["pr_number"]))
    high   = sorted_q[0]
    low    = sorted_q[-1]
    mid    = sorted_q[len(sorted_q) // 2]
    return [high, mid, low]


def main() -> None:
    for path in (QUEUE_PATH, PROFILE_PATH):
        if not path.exists():
            logger.error("Required file not found: %s", path)
            sys.exit(1)

    queue    = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    profiles = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))

    # Build a lookup by pr_number for O(1) access
    profile_by_number = {p["pr_number"]: p for p in profiles}

    selected = pick_three(queue)
    labels   = ["HIGHEST SCORE", "MEDIAN SCORE", "LOWEST SCORE"]

    print()
    print(DIVIDER)
    print("  Live Explainer Test — home-assistant/core × watsonx.ai (Granite)")
    print(DIVIDER)
    print()

    for rank_label, entry in zip(labels, selected):
        pr_number = entry["pr_number"]
        pr_data   = profile_by_number.get(pr_number)

        if pr_data is None:
            logger.warning("PR #%d not found in profiles — skipping.", pr_number)
            continue

        # Re-run pipeline to get full result tuples
        br_result  = score_blast_radius(pr_data)
        sec_result = score_security_policy(pr_data)
        pri_score, pri_label = combine_priority(br_result, sec_result)

        print(f"{'─' * 68}")
        print(f"  [{rank_label}]  PR #{pr_number}")
        print(f"{'─' * 68}")
        print(f"  priority_score   : {pri_score}")
        print(f"  priority_label   : {pri_label}")
        print(f"  blast_radius     : {br_result[1]}  (score {br_result[0]})")
        print(f"  merge_blocker    : {sec_result[1]}")
        print(f"  required_reviewer: {sec_result[0] or '–'}")
        print(f"  modules_touched  : {', '.join(pr_data.get('modules_touched', [])[:4])}")
        print()

        logger.info("Calling watsonx.ai for PR #%d ...", pr_number)
        explanation = call_explainer(
            pr_data        = pr_data,
            priority_result = (pri_score, pri_label),
            blast_radius_result = br_result,
            security_result     = sec_result,
        )

        print("  Penjelasan AI:")
        print()
        # Indent each line of the explanation for readability
        for line in explanation.strip().splitlines():
            print(f"    {line}")
        print()

    print(DIVIDER)
    print("  Done.")
    print(DIVIDER)
    print()


if __name__ == "__main__":
    main()


> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && .venv/bin/python scripts/test_explainer_live.py 2>&1

### 🤖 Assistant

> 🔧 called: execute_command

API terhubung sukses (HTTP 200) tapi penjelasan AI kosong — model mengembalikan string kosong. Ada dua kemungkinan: deprecated endpoint `/ml/v1/text/generation` atau model `ibm/granite-4-h-small` tidak tersedia. Mari debug dan fix:

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && .venv/bin/python -c "
import os; from dotenv import load_dotenv; load_dotenv()
from ibm_watsonx_ai import Credentials
from ibm_watsonx_ai.foundation_models import ModelInference

creds = Credentials(url=os.getenv('WATSONX_URL'), api_key=os.getenv('WATSONX_API_KEY'))
m = ModelInference(model_id='ibm/granite-4-h-small', credentials=creds,
    project_id=os.getenv('WATSONX_PROJECT_ID'), params={'max_new_tokens': 50})
raw = m.generate_text('Jawab satu kalimat: apa itu pull request?')
print(repr(raw))
print(type(raw))
" 2>&1 | tail -20

### 🤖 Assistant

> 🔧 called: execute_command

Model mengembalikan string kosong `''` — ini berarti `ibm/granite-4-h-small` tidak support `generate_text`. Perlu pakai `generate` (full response) atau switch ke `generate_text` with the chat API. Cek model yang tersedia dan coba `generate()`:

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && .venv/bin/python -c "
import os; from dotenv import load_dotenv; load_dotenv()
from ibm_watsonx_ai import Credentials
from ibm_watsonx_ai.foundation_models import ModelInference

creds = Credentials(url=os.getenv('WATSONX_URL'), api_key=os.getenv('WATSONX_API_KEY'))
m = ModelInference(model_id='ibm/granite-4-h-small', credentials=creds,
    project_id=os.getenv('WATSONX_PROJECT_ID'), params={'max_new_tokens': 80})
raw = m.generate('Jawab satu kalimat: apa itu pull request?')
import json; print(json.dumps(raw, indent=2)[:800])
" 2>&1 | grep -v WatsonxAPIWarning | grep -v 'warn(cls' | grep -v 'ID: api'

### 🤖 Assistant

> 🔧 called: grep, grep, read_file, apply_diff

`generate()` bekerja — teks ada di `results[0]["generated_text"]`. Masalahnya adalah `generate_text()` (alias lama) mengembalikan `''` untuk model ini. Update [`ai_layer/explainer.py`](ai_layer/explainer.py) untuk pakai `generate()` dengan ekstraksi manual:

> 🔧 **grep** — ai_layer/explainer.py

> 🔧 **grep** — ai_layer/explainer.py

> 🔧 **read_file** — ai_layer/explainer.py

> 🔧 **apply_diff** — <<<<<<< SEARCH
:start_line:326
-------
    last_explanation: str = ""
    for attempt in range(1, MAX_RETRIES + 2):  # attempts: 1, 2, 3 (= 1 + MAX_RETRIES)
        try:
            raw = model.generate_text(full_prompt)
            explanation = raw.strip() if isinstance(raw, str) else str(raw).strip()
        except Exception as exc:
=======
    last_explanation: str = ""
    for attempt in range(1, MAX_RETRIES + 2):  # attempts: 1, 2, 3 (= 1 + MAX_RETRIES)
        try:
            raw = model.generate(full_prompt)
            # generate() returns a dict: {"results": [{"generated_text": "..."}], ...}
            if isinstance(raw, dict):
                results = raw.get("results") or []
                explanation = (results[0].get("generated_text", "") if results else "").strip()
            else:
                explanation = str(raw).strip()
        except Exception as exc:
>>>>>>> REPLACE


### 🤖 Assistant

> 🔧 called: execute_command

Now re-run the tests to make sure the mock change doesn't break anything, then run the live script:

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && .venv/bin/python -m pytest tests/test_explainer.py -v --tb=short 2>&1 | tail -20

### 🤖 Assistant

> 🔧 called: apply_diff, execute_command

The mocks were built for `generate_text` — need to update them to mock `generate` and return the proper dict format:

> 🔧 **apply_diff** — <<<<<<< SEARCH
:start_line:76
-------
def _make_model_mock(return_values: list[str]) -> MagicMock:
    """Build a mock ModelInference whose generate_text returns values in order."""
    mock_model = MagicMock()
    mock_model.generate_text.side_effect = return_values
    return mock_model
=======
def _wrap_as_generate_response(text: str | Exception) -> dict | Exception:
    """Wrap a plain string into the generate() response dict, or pass through exceptions."""
    if isinstance(text, Exception):
        return text
    return {"results": [{"generated_text": text, "stop_reason": "eos_token"}]}


def _make_model_mock(return_values: list) -> MagicMock:
    """Build a mock ModelInference whose generate() returns proper response dicts."""
    mock_model = MagicMock()
    wrapped = [_wrap_as_generate_response(v) for v in return_values]
    # side_effect: if item is an exception instance, raise it; otherwise return it
    def _side_effect(*args, **kwargs):
        item = wrapped.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
    mock_model.generate.side_effect = _side_effect
    return mock_model
>>>>>>> REPLACE

<<<<<<< SEARCH
:start_line:99
-------
def _patch_watsonx(model_mock: MagicMock):
    """
    Return a context manager that patches both Credentials and ModelInference
    inside ai_layer.explainer.
    """
    cred_patch  = patch("ai_layer.explainer.Credentials", return_value=MagicMock())
    model_patch = patch(
        "ai_layer.explainer.ModelInference",
        return_value=model_mock,
    )
    return cred_patch, model_patch
=======
def _patch_watsonx(model_mock: MagicMock):
    """
    Return two context managers that patch Credentials and ModelInference
    inside ai_layer.explainer.
    """
    cred_patch  = patch("ai_layer.explainer.Credentials", return_value=MagicMock())
    model_patch = patch("ai_layer.explainer.ModelInference", return_value=model_mock)
    return cred_patch, model_patch
>>>>>>> REPLACE

<<<<<<< SEARCH
:start_line:232
-------
    def test_generate_text_called_exactly_once(self):
        model_mock = _make_model_mock([_CONSISTENT_RESPONSE])
        cred_p, model_p = _patch_watsonx(model_mock)
        with cred_p, model_p:
            call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        model_mock.generate_text.assert_called_once()
=======
    def test_generate_called_exactly_once(self):
        model_mock = _make_model_mock([_CONSISTENT_RESPONSE])
        cred_p, model_p = _patch_watsonx(model_mock)
        with cred_p, model_p:
            call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertEqual(model_mock.generate.call_count, 1)
>>>>>>> REPLACE

<<<<<<< SEARCH
:start_line:305
-------
    def test_generate_text_called_max_retries_plus_one(self):
        """generate_text must be called exactly MAX_RETRIES+1 times then stop."""
        model_mock = _make_model_mock(self._exhausted_responses())
        cred_p, model_p = _patch_watsonx(model_mock)
        with cred_p, model_p:
            call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertEqual(
            model_mock.generate_text.call_count,
            MAX_RETRIES + 1,
        )
=======
    def test_generate_called_max_retries_plus_one(self):
        """generate() must be called exactly MAX_RETRIES+1 times then stop."""
        model_mock = _make_model_mock(self._exhausted_responses())
        cred_p, model_p = _patch_watsonx(model_mock)
        with cred_p, model_p:
            call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertEqual(model_mock.generate.call_count, MAX_RETRIES + 1)
>>>>>>> REPLACE

<<<<<<< SEARCH
:start_line:383
-------
class TestCallExplainerSDKException(unittest.TestCase):

    def test_sdk_exception_returns_fallback(self):
        model_mock = MagicMock()
        model_mock.generate_text.side_effect = RuntimeError("connection refused")
        cred_p, model_p = _patch_watsonx(model_mock)
        with cred_p, model_p:
            result = call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertIn("42", result)
        self.assertIn("Medium", result)

    def test_sdk_exception_does_not_propagate(self):
        model_mock = MagicMock()
        model_mock.generate_text.side_effect = Exception("unexpected")
        cred_p, model_p = _patch_watsonx(model_mock)
        with cred_p, model_p:
            # Must not raise
            result = call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertIsInstance(result, str)
=======
class TestCallExplainerSDKException(unittest.TestCase):

    def test_sdk_exception_returns_fallback(self):
        model_mock = _make_model_mock([RuntimeError("connection refused")])
        cred_p, model_p = _patch_watsonx(model_mock)
        with cred_p, model_p:
            result = call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertIn("42", result)
        self.assertIn("Medium", result)

    def test_sdk_exception_does_not_propagate(self):
        model_mock = _make_model_mock([Exception("unexpected")])
        cred_p, model_p = _patch_watsonx(model_mock)
        with cred_p, model_p:
            # Must not raise
            result = call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertIsInstance(result, str)
>>>>>>> REPLACE

<<<<<<< SEARCH
:start_line:410
-------
class TestNoRealAPICallMade(unittest.TestCase):
    """
    Verifies that ibm_watsonx_ai.foundation_models.ModelInference is never
    instantiated with real credentials — all tests use mock objects.
    """

    def test_model_inference_is_mocked_not_real(self):
        model_mock = _make_model_mock([_CONSISTENT_RESPONSE])
        cred_p, model_p = _patch_watsonx(model_mock)
        with cred_p, model_p as mock_mi:
            call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
            # ModelInference constructor was called with our mock, not real SDK
            mock_mi.assert_called_once()
            # The instance returned is our mock, not a live ModelInference
            instance = mock_mi.return_value
            self.assertIsInstance(instance, MagicMock)

    def test_credentials_object_is_mocked(self):
        model_mock = _make_model_mock([_CONSISTENT_RESPONSE])
        cred_p, model_p = _patch_watsonx(model_mock)
        with cred_p as mock_cred, model_p:
            call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
            mock_cred.assert_called_once()
            cred_instance = mock_cred.return_value
            self.assertIsInstance(cred_instance, MagicMock)
=======
class TestNoRealAPICallMade(unittest.TestCase):
    """
    Verifies that ibm_watsonx_ai.foundation_models.ModelInference is never
    instantiated with real credentials — all tests use mock objects.
    """

    def test_model_inference_is_mocked_not_real(self):
        model_mock = _make_model_mock([_CONSISTENT_RESPONSE])
        cred_p, model_p = _patch_watsonx(model_mock)
        with cred_p, model_p as mock_mi:
            call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
            # ModelInference constructor was called — instance is our mock
            mock_mi.assert_called_once()
            # generate() was called on the mock instance, not a real HTTP call
            model_mock.generate.assert_called_once()

    def test_credentials_object_is_mocked(self):
        model_mock = _make_model_mock([_CONSISTENT_RESPONSE])
        cred_p, model_p = _patch_watsonx(model_mock)
        with cred_p as mock_cred, model_p:
            call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
            mock_cred.assert_called_once()
            cred_instance = mock_cred.return_value
            self.assertIsInstance(cred_instance, MagicMock)
>>>>>>> REPLACE


> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && .venv/bin/python -m pytest tests/test_explainer.py -v --tb=short 2>&1 | tail -15

### 🤖 Assistant

> 🔧 called: apply_diff, execute_command

3 tests still referencing `generate_text.call_count` in the retry tests. Let me fix those:

> 🔧 **apply_diff** — <<<<<<< SEARCH
:start_line:260
-------
    def test_no_numbers_response_accepted_without_retry(self):
        model_mock = _make_model_mock([_NO_NUMBER_RESPONSE])
        cred_p, model_p = _patch_watsonx(model_mock)
        with cred_p, model_p:
            result = call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertEqual(result, _NO_NUMBER_RESPONSE)
        model_mock.generate_text.assert_called_once()
=======
    def test_no_numbers_response_accepted_without_retry(self):
        model_mock = _make_model_mock([_NO_NUMBER_RESPONSE])
        cred_p, model_p = _patch_watsonx(model_mock)
        with cred_p, model_p:
            result = call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertEqual(result, _NO_NUMBER_RESPONSE)
        self.assertEqual(model_mock.generate.call_count, 1)
>>>>>>> REPLACE

<<<<<<< SEARCH
:start_line:277
-------
    def test_retries_on_wrong_score_then_returns_consistent(self):
        """First call returns wrong score, second call returns consistent."""
        model_mock = _make_model_mock([_WRONG_SCORE_RESPONSE, _CONSISTENT_RESPONSE])
        cred_p, model_p = _patch_watsonx(model_mock)
        with cred_p, model_p:
            result = call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertEqual(result, _CONSISTENT_RESPONSE)
        self.assertEqual(model_mock.generate_text.call_count, 2)

    def test_retries_on_wrong_label_then_returns_consistent(self):
        model_mock = _make_model_mock([_WRONG_LABEL_RESPONSE, _CONSISTENT_RESPONSE])
        cred_p, model_p = _patch_watsonx(model_mock)
        with cred_p, model_p:
            result = call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertEqual(result, _CONSISTENT_RESPONSE)
        self.assertEqual(model_mock.generate_text.call_count, 2)
=======
    def test_retries_on_wrong_score_then_returns_consistent(self):
        """First call returns wrong score, second call returns consistent."""
        model_mock = _make_model_mock([_WRONG_SCORE_RESPONSE, _CONSISTENT_RESPONSE])
        cred_p, model_p = _patch_watsonx(model_mock)
        with cred_p, model_p:
            result = call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertEqual(result, _CONSISTENT_RESPONSE)
        self.assertEqual(model_mock.generate.call_count, 2)

    def test_retries_on_wrong_label_then_returns_consistent(self):
        model_mock = _make_model_mock([_WRONG_LABEL_RESPONSE, _CONSISTENT_RESPONSE])
        cred_p, model_p = _patch_watsonx(model_mock)
        with cred_p, model_p:
            result = call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertEqual(result, _CONSISTENT_RESPONSE)
        self.assertEqual(model_mock.generate.call_count, 2)
>>>>>>> REPLACE


> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && .venv/bin/python -m pytest tests/test_explainer.py -v --tb=short 2>&1 | tail -8

### 🤖 Assistant

> 🔧 called: execute_command

**36/36 mock tests pass.** Sekarang jalankan live script:

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && .venv/bin/python scripts/test_explainer_live.py 2>&1 | grep -v "HTTP Request\|Client successfully\|Successfully finished\|WatsonxAPIWarning\|warn(cls\|ID: api"

### 🤖 Assistant

> 🔧 called: execute_command

API sukses (HTTP 200) tetapi penjelasan tetap kosong — `generate()` mengembalikan dict tapi `generated_text` mungkin kosong untuk prompt ini. Cek raw response langsung:

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && .venv/bin/python -c "
import os, json; from dotenv import load_dotenv; load_dotenv()
from ibm_watsonx_ai import Credentials
from ibm_watsonx_ai.foundation_models import ModelInference

creds = Credentials(url=os.getenv('WATSONX_URL'), api_key=os.getenv('WATSONX_API_KEY'))
m = ModelInference(model_id='ibm/granite-4-h-small', credentials=creds,
    project_id=os.getenv('WATSONX_PROJECT_ID'), params={'max_new_tokens': 200, 'temperature': 0.2})
prompt = 'Jelaskan dalam satu paragraf mengapa PR yang mengubah dependency harus di-review dengan hati-hati.'
raw = m.generate(prompt)
print(json.dumps(raw, indent=2, ensure_ascii=False)[:1000])
" 2>&1 | grep -v "HTTP\|Client\|Successfully\|Warning\|warn\|ID:"

### 🤖 Assistant

> 🔧 called: execute_command

Model berjalan baik dengan prompt pendek. Masalahnya pada prompt panjang — mungkin melebihi `input_token_count` limit atau ada karakter yang menyebabkan masalah. Cek dengan prompt explainer yang sebenarnya:

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && .venv/bin/python -c "
import os, json; from dotenv import load_dotenv; load_dotenv()
from ibm_watsonx_ai import Credentials
from ibm_watsonx_ai.foundation_models import ModelInference
from ai_layer.explainer import _SYSTEM_PROMPT, _build_user_prompt
from scoring.blast_radius import score_blast_radius
from scoring.security_policy import score_security_policy
from priority.combine import combine_priority

# Load PR #176825
profiles = json.load(open('data/home_assistant_100prs.json'))
p = next(x for x in profiles if x['pr_number'] == 176825)
br = score_blast_radius(p)
sec = score_security_policy(p)
pri = combine_priority(br, sec)

user_prompt = _build_user_prompt(p, pri, br, sec)
full_prompt = f'{_SYSTEM_PROMPT}\n\n{user_prompt}'
print('Prompt length (chars):', len(full_prompt))
print('---')
print(full_prompt[:500])
print('...')

creds = Credentials(url=os.getenv('WATSONX_URL'), api_key=os.getenv('WATSONX_API_KEY'))
m = ModelInference(model_id='ibm/granite-4-h-small', credentials=creds,
    project_id=os.getenv('WATSONX_PROJECT_ID'), params={'max_new_tokens': 300, 'temperature': 0.2})
raw = m.generate(full_prompt)
results = raw.get('results', [])
print('generated_text:', repr(results[0]['generated_text'] if results else ''))
print('input_tokens:', results[0].get('input_token_count') if results else 'N/A')
print('stop_reason:', results[0].get('stop_reason') if results else 'N/A')
" 2>&1 | grep -v "HTTP\|Client\|Successfully\|Warning\|warn\|ID:"

### 🤖 Assistant

> 🔧 called: execute_command

`stop_reason: eos_token` dengan `generated_text: ''` — model menerima prompt (339 token) tapi langsung berhenti tanpa generate. Ini adalah perilaku `ibm/granite-4-h-small` dengan `generate()` endpoint yang deprecated. Perlu switch ke **chat API** (`generate_text` dengan format messages, atau `chat()`):

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && .venv/bin/python -c "
import os, json; from dotenv import load_dotenv; load_dotenv()
from ibm_watsonx_ai import Credentials
from ibm_watsonx_ai.foundation_models import ModelInference
from ai_layer.explainer import _SYSTEM_PROMPT, _build_user_prompt
from scoring.blast_radius import score_blast_radius
from scoring.security_policy import score_security_policy
from priority.combine import combine_priority

profiles = json.load(open('data/home_assistant_100prs.json'))
p = next(x for x in profiles if x['pr_number'] == 176825)
br = score_blast_radius(p); sec = score_security_policy(p); pri = combine_priority(br, sec)
user_prompt = _build_user_prompt(p, pri, br, sec)

creds = Credentials(url=os.getenv('WATSONX_URL'), api_key=os.getenv('WATSONX_API_KEY'))
m = ModelInference(model_id='ibm/granite-4-h-small', credentials=creds,
    project_id=os.getenv('WATSONX_PROJECT_ID'))

messages = [
    {'role': 'system', 'content': _SYSTEM_PROMPT},
    {'role': 'user',   'content': user_prompt},
]
raw = m.chat(messages=messages, params={'max_new_tokens': 300, 'temperature': 0.2})
print(json.dumps(raw, indent=2, ensure_ascii=False)[:1200])
" 2>&1 | grep -v "HTTP\|Client\|Successfully\|Warning\|warn\|ID:"

### 🤖 Assistant

> 🔧 called: apply_diff

Chat API bekerja sempurna. Update [`ai_layer/explainer.py`](ai_layer/explainer.py) untuk pakai `model.chat()`:

> 🔧 **apply_diff** — <<<<<<< SEARCH
:start_line:90
-------
GENERATE_PARAMS = {
    "max_new_tokens": MAX_NEW_TOKENS,
    "temperature": 0.2,  # low temperature → deterministic, factual output
}
=======
GENERATE_PARAMS = {
    "max_new_tokens": MAX_NEW_TOKENS,
    "temperature": 0.2,  # low temperature → deterministic, factual output
}

# Chat params use slightly different key names for the chat endpoint
_CHAT_PARAMS = {
    "max_tokens": MAX_NEW_TOKENS,
    "temperature": 0.2,
}
>>>>>>> REPLACE

<<<<<<< SEARCH
:start_line:299
-------
    user_prompt = _build_user_prompt(
        pr_data, priority_result, blast_radius_result, security_result
    )
    full_prompt = f"{_SYSTEM_PROMPT}\n\n{user_prompt}"

    credentials = Credentials(url=url, api_key=api_key)
    model = ModelInference(
        model_id=MODEL_ID,
        credentials=credentials,
        project_id=project_id,
        params=GENERATE_PARAMS,
    )

    last_explanation: str = ""
    for attempt in range(1, MAX_RETRIES + 2):  # attempts: 1, 2, 3 (= 1 + MAX_RETRIES)
        try:
            raw = model.generate(full_prompt)
            # generate() returns a dict: {"results": [{"generated_text": "..."}], ...}
            if isinstance(raw, dict):
                results = raw.get("results") or []
                explanation = (results[0].get("generated_text", "") if results else "").strip()
            else:
                explanation = str(raw).strip()
        except Exception as exc:
=======
    user_prompt = _build_user_prompt(
        pr_data, priority_result, blast_radius_result, security_result
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
>>>>>>> REPLACE


### 🤖 Assistant

> 🔧 called: apply_diff, execute_command

Now update the mock helper in tests to use `chat` instead of `generate`:

> 🔧 **apply_diff** — <<<<<<< SEARCH
:start_line:78
-------
def _wrap_as_generate_response(text: str | Exception) -> dict | Exception:
    """Wrap a plain string into the generate() response dict, or pass through exceptions."""
    if isinstance(text, Exception):
        return text
    return {"results": [{"generated_text": text, "stop_reason": "eos_token"}]}


def _make_model_mock(return_values: list) -> MagicMock:
    """Build a mock ModelInference whose generate() returns proper response dicts."""
    mock_model = MagicMock()
    wrapped = [_wrap_as_generate_response(v) for v in return_values]
    # side_effect: if item is an exception instance, raise it; otherwise return it
    def _side_effect(*args, **kwargs):
        item = wrapped.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
    mock_model.generate.side_effect = _side_effect
    return mock_model
=======
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
>>>>>>> REPLACE

<<<<<<< SEARCH
:start_line:254
-------
    def test_generate_called_exactly_once(self):
        model_mock = _make_model_mock([_CONSISTENT_RESPONSE])
        cred_p, model_p = _patch_watsonx(model_mock)
        with cred_p, model_p:
            call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertEqual(model_mock.generate.call_count, 1)

    def test_no_numbers_response_accepted_without_retry(self):
        model_mock = _make_model_mock([_NO_NUMBER_RESPONSE])
        cred_p, model_p = _patch_watsonx(model_mock)
        with cred_p, model_p:
            result = call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertEqual(result, _NO_NUMBER_RESPONSE)
        self.assertEqual(model_mock.generate.call_count, 1)
=======
    def test_chat_called_exactly_once(self):
        model_mock = _make_model_mock([_CONSISTENT_RESPONSE])
        cred_p, model_p = _patch_watsonx(model_mock)
        with cred_p, model_p:
            call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertEqual(model_mock.chat.call_count, 1)

    def test_no_numbers_response_accepted_without_retry(self):
        model_mock = _make_model_mock([_NO_NUMBER_RESPONSE])
        cred_p, model_p = _patch_watsonx(model_mock)
        with cred_p, model_p:
            result = call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertEqual(result, _NO_NUMBER_RESPONSE)
        self.assertEqual(model_mock.chat.call_count, 1)
>>>>>>> REPLACE

<<<<<<< SEARCH
:start_line:282
-------
        self.assertEqual(model_mock.generate.call_count, 2)

    def test_retries_on_wrong_label_then_returns_consistent(self):
        model_mock = _make_model_mock([_WRONG_LABEL_RESPONSE, _CONSISTENT_RESPONSE])
        cred_p, model_p = _patch_watsonx(model_mock)
        with cred_p, model_p:
            result = call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertEqual(result, _CONSISTENT_RESPONSE)
        self.assertEqual(model_mock.generate.call_count, 2)
=======
        self.assertEqual(model_mock.chat.call_count, 2)

    def test_retries_on_wrong_label_then_returns_consistent(self):
        model_mock = _make_model_mock([_WRONG_LABEL_RESPONSE, _CONSISTENT_RESPONSE])
        cred_p, model_p = _patch_watsonx(model_mock)
        with cred_p, model_p:
            result = call_explainer(
                _PR_DATA, _PRIORITY_RESULT, _BLAST_RESULT, _SECURITY_RESULT
            )
        self.assertEqual(result, _CONSISTENT_RESPONSE)
        self.assertEqual(model_mock.chat.call_count, 2)
>>>>>>> REPLACE

<<<<<<< SEARCH
:start_line:319
-------
        self.assertEqual(model_mock.generate.call_count, MAX_RETRIES + 1)
=======
        self.assertEqual(model_mock.chat.call_count, MAX_RETRIES + 1)
>>>>>>> REPLACE

<<<<<<< SEARCH
:start_line:434
-------
            # generate() was called on the mock instance, not a real HTTP call
            model_mock.generate.assert_called_once()
=======
            # chat() was called on the mock instance, not a real HTTP call
            model_mock.chat.assert_called_once()
>>>>>>> REPLACE


> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && .venv/bin/python -m pytest tests/test_explainer.py -q 2>&1 | tail -5

### 🤖 Assistant

> 🔧 called: execute_command

**36/36 mock tests pass.** Sekarang jalankan live script:

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && .venv/bin/python scripts/test_explainer_live.py 2>&1 | grep -v "HTTP Request\|Client successfully\|Successfully finished\|WatsonxAPIWarning\|warn(cls\|ID: api\|warn("

### 🤖 Assistant

**Pipeline end-to-end berjalan sempurna dengan API asli.** Berikut ringkasan hasil:

---

## Hasil live call ke watsonx.ai (Granite 4h-small)

### PR #176825 — HIGHEST (score 75, Critical)
> *"PR ini mendapat label "Critical" karena memiliki priority_score 75 yang menunjukkan dampak besar pada sistem. PR ini menyinggung banyak modul dan mengubah konfigurasi serta dependensi, sehingga perlu perhatian khusus. Reviewer yang disarankan adalah **dependency-review** untuk memastikan perubahan dependensi aman."*

### PR #157062 — MEDIAN (score 25, Low)
> *"PR ini mendapat label "Low" karena hanya mempengaruhi modul `homeassistant/components/twitch` dengan perubahan kecil (29 additions, 0 deletions) dan tidak menyinggung konfigurasi, migrasi, atau dependensi. Score 25 menunjukkan prioritas rendah."*

### PR #180392 — LOWEST (score 25, Low)
> *"PR ini mendapat label "Low" karena hanya mempengaruhi modul lokal (`homeassistant/components/sofar`) tanpa perubahan konfigurasi, dependensi, atau CI, serta tidak mempengaruhi blast radius secara signifikan."*

---

**Yang diperbaiki selama proses:**
1. `generate_text()` deprecated dan mengembalikan `''` untuk Granite → diganti ke **`chat()`** dengan format messages `[{role: system}, {role: user}]`
2. Mock tests diupdate: `_wrap_as_chat_response()` menghasilkan format `{"choices": [{"message": {"content": "..."}}]}` yang sesuai chat API
3. **36/36 mock tests tetap hijau** setelah perubahan

---

### 👤 User

