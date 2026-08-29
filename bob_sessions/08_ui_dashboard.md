<!-- Excerpt from full session (bob_sessions/00_full_session_raw.md), lines 7077-7253 -->
<!-- Modules built in this segment: ui/app.py -->

"Buatkan ui/app.py (Flask sederhana) dengan satu route '/' yang membaca output/explained_priority_queue.json dan menampilkan tabel HTML: PR number, blast-radius label, priority_score, priority_label, explanation (kolom lebar, teks lengkap), disortir dari priority_score tertinggi. Style minimal pakai CSS inline, fokus ke keterbacaan. Tambahkan warna badge merah (Critical), oranye (High), kuning (Medium), hijau (Low) sesuai priority_label. Tambahkan indikator kecil (ikon atau teks 'guardrail') di baris yang merge_blocker=true."

---

### 🤖 Assistant

> 🔧 called: read_file, list_files, list_files, read_file

Let me first inspect the data shape to know every field available:

> 🔧 **list_files** — .

> 🔧 **read_file** — output/explained_priority_queue.json

> 🔧 **list_files** — ui

> 🔧 **read_file** — output/explained_priority_queue.json

### 🤖 Assistant

> 🔧 called: write_file

Good. I have the full schema. Now I'll write the Flask app:

> 🔧 **write_file** — ui/app.py

### 🤖 Assistant

> 🔧 called: execute_command

Now check Flask is available and do a quick smoke test to confirm the route renders without error:

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && source .venv/bin/activate && python -c "
from ui.app import app
with app.test_client() as c:
    resp = c.get('/')
    assert resp.status_code == 200, f'got {resp.status_code}'
    body = resp.data.decode()
    assert 'Priority Queue' in body
    assert 'guardrail' in body
    assert 'Critical' in body
    assert 'multi module' in body or 'multi_module' in body
    print('OK — status 200, key strings present')
    # spot-check counts
    count_blocker = body.count('guardrail-badge') + body.count('⛔ guardrail')
    print(f'  guardrail badges rendered: {count_blocker}')
" 2>&1

### 🤖 Assistant

> 🔧 called: execute_command

30 merge-blocker rows render correctly. Let me also verify the label badges and reviewer cells look right:

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && source .venv/bin/activate && python -c "
from ui.app import app
with app.test_client() as c:
    body = c.get('/').data.decode()
    # colour palette present
    for colour in ['#dc2626','#ea580c','#ca8a04','#16a34a']:
        assert colour in body, f'missing colour {colour}'
    # all four labels
    for label in ['Critical','High','Medium','Low']:
        assert label in body, f'missing label {label}'
    # reviewer column
    assert 'dependency-review' in body
    assert 'platform-team' in body
    # summary counts line
    import re
    m = re.search(r'(\d+)</strong> merge-blocker guardrails active', body)
    print(f'Summary counts line — merge-blockers: {m.group(1) if m else \"NOT FOUND\"}')
    m2 = re.search(r'(\d+) pull requests', body)
    print(f'Total PRs in table: {m2.group(1) if m2 else \"NOT FOUND\"}')
    print('All assertions passed')
" 2>&1

### 🤖 Assistant

> 🔧 called: execute_command

The Jinja template uses `|` inside HTML `style=` attributes which can be tricky with raw rendering. Let me check how Flask renders the colour:

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && source .venv/bin/activate && python -c "
from ui.app import app
with app.test_client() as c:
    body = c.get('/').data.decode()
    import re
    styles = re.findall(r'background:[^;\"]+', body)
    print(set(styles))
" 2>&1

### 🤖 Assistant

> 🔧 called: execute_command

`#ea580c` (High/orange) is missing because there are no `High` entries in the current 100-PR dataset. The data simply has no High-label rows — the assertion was wrong, not the code. Let me verify:

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && source .venv/bin/activate && python -c "
import json
data = json.load(open('output/explained_priority_queue.json'))
from collections import Counter
c = Counter(r['priority_label'] for r in data)
print(dict(c))
print('merge_blockers:', sum(1 for r in data if r.get('merge_blocker')))
" 2>&1

### 🤖 Assistant

> 🔧 called: execute_command

No High-label PRs in the dataset — that's a data distribution fact, not a bug. All 4 colours are correctly defined in the code; High just doesn't appear in this run. Re-run the assertion with the actual labels:

> 🔧 **execute_command** — cd /home/steven/projects/tech-xchange-2026-ibm/bob-risk-triage-reviewer && source .venv/bin/activate && python -c "
from ui.app import app
with app.test_client() as c:
    body = c.get('/').data.decode()
    # colours present for labels that actually exist in dataset
    for colour in ['#dc2626','#ca8a04','#16a34a']:   # Critical, Medium, Low
        assert colour in body, f'missing colour {colour}'
    # High colour defined in Python dict even if no rows use it — code is correct
    from ui.app import _LABEL_STYLES
    assert _LABEL_STYLES['High']['bg'] == '#ea580c'
    # all four labels in the palette
    for label in ['Critical','Medium','Low']:
        assert label in body
    # reviewer column
    assert 'dependency-review' in body
    assert 'platform-team' in body
    # summary counts line
    import re
    m = re.search(r'<strong>(\d+)</strong> merge-blocker guardrails', body)
    print(f'Merge-blocker count in page: {m.group(1)}')
    m2 = re.search(r'(\d+) pull requests', body)
    print(f'Total PRs in table: {m2.group(1)}')
    # guardrail badges
    badges = body.count('\u26d4 guardrail')
    print(f'Guardrail badge rows: {badges}')
    print('All assertions passed')
" 2>&1

### 🤖 Assistant

Everything checks out. [`ui/app.py`](ui/app.py) is complete and working.

---

### What was built

**[`ui/app.py`](ui/app.py)** — a self-contained Flask app (~180 lines, zero external CSS/JS).

#### Route `GET /`
1. Reads [`output/explained_priority_queue.json`](output/explained_priority_queue.json) and sorts by `priority_score` descending (guaranteed, even if the file order shifts).
2. Injects per-row `label_bg` / `label_fg` from the palette dict and passes everything to `render_template_string`.

#### Table columns
| Column | Detail |
|---|---|
| **PR #** | Monospace, blue |
| **Blast Radius** | Pill badge — blue tint for `multi_module`, grey for `small_or_local` |
| **Score** | Bold number (0–100) |
| **Label** | Colour-coded badge: 🔴 Critical `#dc2626` · 🟠 High `#ea580c` · 🟡 Medium `#ca8a04` · 🟢 Low `#16a34a` |
| **Explanation** | Full text, readable line-height, word-wrap |

#### Guardrail indicator
Rows where `merge_blocker=true` get:
- Light amber row background (`#fff8f0`)
- `⛔ guardrail` pill badge next to the label, with a tooltip title
- `👤 <reviewer>` sub-label below the badge

#### Summary bar
Shows Critical / High / Medium / Low counts + total merge-blocker guardrails active — verified: **30 Critical, 30 blockers, 100 PRs total**.

#### Run
```bash
source .venv/bin/activate
flask --app ui.app run
# → http://127.0.0.1:5000/
