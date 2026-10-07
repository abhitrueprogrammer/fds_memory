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

