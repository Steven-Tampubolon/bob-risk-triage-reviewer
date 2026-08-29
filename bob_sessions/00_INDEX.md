# Bob 2.0 Session — Index & Highlights

This project was built in **one continuous Bob 2.0 Agent Mode session** (23 user turns, 110 assistant tool-use turns, 7,253 lines total). Rather than asking judges to read all 7,253 lines, this index summarizes what was built, links to each module's segment, and highlights the three most evidentiary moments. **The complete, unedited transcript is preserved at `01_setup_and_ingestion.md` through `08_ui_dashboard.md` (split by module for readability) and as a single file at `../bob-task-f87e49e5f7d2c401177c45beaa12b6c4-2026-08-29.md` (original export, unmodified).**

No content was altered when splitting — each file below is a verbatim, contiguous slice of the original export.

## Table of Contents

| File | What was built | Approx. lines |
|---|---|---|
| `01_setup_and_ingestion.md` | Project scaffolding + `ingestion/github_pr.py` (GitHub PR fetching, mocked tests) | 1,114 |
| `02_blast_radius.md` | `scripts/fetch_ha_core_100.py` + `scoring/blast_radius.py`, **including a mid-session correction** (see Highlight 2) | 965 |
| `03_security_policy_and_priority.md` | `scoring/security_policy.py` + `priority/combine.py` (guardrail logic) | 887 |
| `04_explainer.md` | `scripts/validate_cross_repo.py` + `ai_layer/explainer.py`, **including an autonomous test-fail-fix loop** (see Highlight 1) | 1,759 |
| `05_priority_queue_and_live_test.md` | `scripts/build_priority_queue.py` + `scripts/test_explainer_live.py` | 1,041 |
| `06_build_explained_queue.md` | `scripts/build_explained_queue.py` (100-PR live watsonx.ai run) | 250 |
| `07_document_understanding.md` | `ai_layer/document_understanding.py` | 1,060 |
| `08_ui_dashboard.md` | `ui/app.py` (Flask dashboard) | 177 |

---

## Highlight 1 — Autonomous test-fail → diagnose → fix loop (no user turn in between)

*Full context: `04_explainer.md`, search for `pytest tests/test_explainer.py -v`.*

Bob ran the test suite for `ai_layer/explainer.py`, and — **without any message from us in between** — diagnosed two distinct bugs and fixed both in the same turn:

> Dua masalah yang harus diperbaiki:
> 1. **`Credentials` / `ModelInference` bukan module-level attributes** — karena diimport di dalam fungsi dengan `from ... import`, patch harus menargetkan `ibm_watsonx_ai.Credentials` dan `ibm_watsonx_ai.foundation_models.ModelInference`...
> 2. **Validator terlalu ketat** — `_CONSISTENT_RESPONSE` menyebut `#42` (PR number) dan `3` (files), tapi validator menganggap itu "score foreign"...
>
> Solusi bersih: pindahkan import SDK ke module-level dengan try/except..., dan perbaiki validator agar hanya flag angka yang muncul di konteks "skor/poin" bukan angka PR arbitrer.

This is the generate → test → diagnose → fix → retest loop referenced in our Written Statement on Technology — Bob identified the root cause of two independent failures and patched both without us re-prompting.

## Highlight 2 — Human-reviewed correction (honest disclosure, not autonomous)

*Full context: `02_blast_radius.md`, search for "Perbaiki scoring/blast_radius.py".*

Not every fix in this session was autonomous. After Bob's first pass on `blast_radius.py`, **we** reviewed its output and caught a logic flaw: the `tests` folder was being counted as its own "module," inflating the multi-module rate:

> Perbaiki scoring/blast_radius.py. Saat ini kriteria breadth (len(modules_touched) > 1) menghitung 'tests' sebagai module terpisah, padahal PR yang menyertakan test untuk komponen yang sama seharusnya tidak dianggap multi-module. Ubah logika: buat variabel substantive_modules = modules_touched dikurangi entri yang bernilai persis 'tests' atau file non-kode seperti 'requirements_all.txt'...

Bob then applied this via `apply_diff` across the scoring logic, its tests, and the validation script consistently. We disclose this as human-in-the-loop review, not an autonomous fix, to keep our "how Bob was used" claim accurate.

## Highlight 3 — Test suite growing across the session

Individual `pytest` runs within the session (not the final combined suite) show tests accumulating as each module was added: 25 passed (ingestion) → 30 passed (blast-radius, post-correction) → 57 passed (security/policy + priority) → 36 passed (explainer) → 77 passed (document understanding, cumulative for that file). These are per-file run counts captured live in the transcript, not a single monotonic total.

**Independently of this transcript**, we re-ran the full delivered test suite ourselves and confirmed **248/248 tests pass** — see `README.md` in the repo root for how to reproduce this.

---

## A note on the SmartBear/Cisco reference inside this transcript

Early in `02_blast_radius.md`, Bob's own summary text cites "riset SmartBear/Cisco" as the source for the 150-line threshold. We later determined this citation was not accurate (see `written_statement.md`, Methodological Honesty section) and corrected it in the shipped code (`scoring/blast_radius.py`) and documentation. **We have left it uncorrected here**, since this file is a historical transcript, not a claim we are making today — editing an exported session record would misrepresent what actually happened during development.
