# Running Notes - Persistent Repository Memory Experiment

## Environment & Pins
- **OS**: Linux fedora-lappy 7.2.8-200.fc44.x86_64
- **CPU**: AMD Ryzen 7 7730U (16 logical cores)
- **RAM**: 13 GiB (approx 10 GiB available, 8 GiB swap)
- **Disk**: 175 GiB free on `/home`
- **Docker**: Version 29.8.2
- **Python**: 3.11.16 (managed via `uv`) in `.venv`
- **mini-swe-agent**: pinned to `2.4.6`
- **swebench**: pinned to `4.1.0`

## Decisions & Deviations
- Virtual environment created using Python 3.11.16 via `uv` because system Python is 3.14 (which is too new for several compiled C-extensions in ML/benchmarking dependencies).

## Dataset Inventory (MariusHobbhahn/swe-bench-verified-mini)
Total tasks: 50
- `django/django`: 25 tasks (chronological span: 2017-10-27T11:10:04Z to 2020-04-22T11:02:30Z)
- `sphinx-doc/sphinx`: 25 tasks (chronological span: 2020-05-01T18:29:11Z to 2023-07-24T22:46:12Z)

## Phase 0: Setup and Smoke Test Results
- Pinned packages: `mini-swe-agent==2.4.6`, `swebench==4.1.0`, Python 3.11.16 in `.venv`.
- Model: `gemini/gemini-3.5-flash-lite` (temperature=0.0).
- API Key: Saved in `.env` (gitignored).
- Smoke task: `django__django-11790`.
- Agent run: mini-swe-agent executed 30 bash turns inside Docker, generated trajectory and `preds.json`.
- Harness run: `swebench.harness.run_evaluation` scored `preds.json` cleanly, output report to `gemini__gemini-3.5-flash-lite.smoke_test_agent.json`.
- Time per task: ~5 min 39 s.
- Cost per task: $0.0615 (30 API calls).
## Approved Sequence Plan (Phase 1 Checkpoint Approved)
- **Repository**: `django/django`
- **Subset**: 3 tasks in strict chronological order:
  1. `django__django-11790` (2019-09-17) - Touches `django/contrib/auth/forms.py`
  2. `django__django-11815` (2019-09-24) - Touches `django/db/migrations/serializer.py`
  3. `django__django-11848` (2019-09-28) - Touches `django/utils/http.py`
- **Budget**: 3 tasks × 4 conditions = 12 runs (~300-360 requests, ~$0.72).
- **Disk / Cache Policy**: All downloaded Docker images (`django-11790`, `django-11815`, `django-11848`) are permanently preserved (no deletion).

## Phase 2: Offline Retrieval Evaluation (Recall@K)
Evaluated before running any agents on C or D.
- **Task 1: `django__django-11790`** (Gold: `django/contrib/auth/forms.py`)
  - B (Snapshot RAG): Recall@1: 0.0, Recall@3: 1.0, Recall@5: 1.0 (Rank 3)
  - C (Naive Combo): Recall@1: 0.0, Recall@3: 1.0, Recall@5: 1.0 (Rank 3)
  - D (Structural AST): Recall@1: 0.0, Recall@3: 1.0, Recall@5: 1.0 (Rank 2)
- **Task 2: `django__django-11815`** (Gold: `django/db/migrations/serializer.py`)
  - B (Snapshot RAG): Recall@1: 0.0, Recall@3: 0.0, Recall@5: 0.0
  - C (Naive Combo): Recall@1: 0.0, Recall@3: 0.0, Recall@5: 0.0
  - D (Structural AST): Recall@1: 0.0, Recall@3: 0.0, Recall@5: 0.0
- **Task 3: `django__django-11848`** (Gold: `django/utils/http.py`)
  - B (Snapshot RAG): Recall@1: 0.0, Recall@3: 1.0, Recall@5: 1.0 (Rank 3)
  - C (Naive Combo): Recall@1: 0.0, Recall@3: 1.0, Recall@5: 1.0 (Rank 3)
  - D (Structural AST): Recall@1: 0.0, Recall@3: 0.0, Recall@5: 0.0
- **Sequence Average Recall@5**:
  - Condition B: 66.7% (2/3)
  - Condition C: 66.7% (2/3)
  - Condition D: 33.3% (1/3)




