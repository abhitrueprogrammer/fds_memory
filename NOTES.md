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
## Phase 3 & 4: Experimental Runs, Logging & Analysis

### Execution Summary
- Model: `gemini/gemini-3.5-flash-lite` (temperature=0.0)
- Sequence: 3 tasks in chronological order: `django-11790` -> `django-11815` -> `django-11848`
- Total runs: 12 runs (4 conditions × 3 tasks). Single-run evaluation due to daily API quotas.
- Total cost: ~$0.52 total across all 12 runs.
- Total Docker disk used: ~12.5 GB (all 3 images preserved locally, 0 internet bandwidth wasted after download).

### Resolve Rates by Condition & Position
| Condition | Task 1 (`11790`) | Task 2 (`11815`) | Task 3 (`11848`) | Overall Resolve Rate |
|---|---|---|---|---|
| **A (No Memory)** | Unresolved (0/1) | Unresolved (0/1) | Unresolved (0/1) | **0/3 (0.0%)** |
| **B (Snapshot RAG)** | Unresolved (0/1) | Unresolved (0/1) | Unresolved (0/1) | **0/3 (0.0%)** |
| **C (Naive Combo)** | Unresolved (0/1) | Unresolved (0/1) | Unresolved (0/1) | **0/3 (0.0%)** |
| **D (Proposed System)** | Unresolved (0/1) | Unresolved (0/1) | Unresolved (0/1) | **0/3 (0.0%)** |

*Note*: On Task 3 under Condition B, the agent successfully reached the submission command (`exit_status: Submitted` in 20 steps), though the resulting patch did not resolve the test suite. All other instances exited with `LimitsExceeded` (capped at 30 steps to protect API quotas).

### Offline Retrieval Recall@5
- Condition B (Snapshot RAG): **66.7%** (2/3 hits: Rank 3 on Task 1 and Task 3)
- Condition C (Naive Combo): **66.7%** (2/3 hits: Rank 3 on Task 1 and Task 3)
- Condition D (Structural AST): **33.3%** (1/3 hits: Rank 2 on Task 1)

### Token, Cost, and Latency Overhead
| Condition | Total Cost | Avg Cost / Task | Total Latency | Avg Latency / Task | Incremental Cache Stats |
|---|---|---|---|---|---|
| **A (Baseline)** | $0.1339 | $0.0446 | 561.8s | 187.3s | N/A |
| **B (Snapshot RAG)** | $0.1269 | $0.0423 | 911.5s | 303.8s | N/A |
| **C (Naive Combo)** | $0.1350 | $0.0450 | 649.9s | 216.6s | Past tasks: 0 -> 1 -> 2 |
| **D (Proposed System)** | $0.1244 | $0.0415 | 675.2s | 225.1s | Task 1: 804 parsed / 0 cached<br>Task 2 & 3: 0 parsed / 804 cached |

### Staleness Check Verification
- Target file: `django/contrib/auth/forms.py` (modified after Task 1 entered memory)
- **Condition C (Naive Combo)**: Completely oblivious to file modification (`flags_stale = False`). Continued serving outdated task history.
- **Condition D (Proposed System)**: Detected SHA-256 hash mismatch (`flags_stale = True`), flagged `⚠️ [STALE - Files changed since task: django/contrib/auth/forms.py (modified)]`, and penalized memory weight from 1.0 to 0.20.





