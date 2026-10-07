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
- Docker disk used: 4.18 GB (preserved on disk per user request, no images deleted).
- Total free disk: 173 GB.


