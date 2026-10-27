"""Reproducibility Packaging Script for Session-Persistent Repository Memory.

Packages:
1. Executable source code (memory_pilot/, scripts/)
2. Task inventories and configuration files (inventory.json, swebench.yaml)
3. Raw experimental results and benchmarks (results/*.json)
4. Per-task execution logs, patches, and evaluation reports (logs/run_evaluation/, results/recurrent_cluster_experiment/)
5. Reproducible verification scripts (scripts/run_statistical_tests.py)
6. Comprehensive replication guide (README_REPRODUCIBILITY.md)

Addresses Reviewer Weakness G and Required Improvement 8.
"""

from pathlib import Path
import shutil
import tarfile
import json


def create_reproducibility_package():
    root = Path(".")
    bundle_dir = root / "reproducibility_package"
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    print("Copying source code...")
    shutil.copytree(root / "memory_pilot", bundle_dir / "memory_pilot")
    
    scripts_dest = bundle_dir / "scripts"
    scripts_dest.mkdir(parents=True, exist_ok=True)
    for s in (root / "scripts").glob("*.py"):
        shutil.copy2(s, scripts_dest / s.name)
    for s in (root / "scripts").glob("*.sh"):
        shutil.copy2(s, scripts_dest / s.name)

    print("Copying configurations and inventory...")
    shutil.copy2(root / "inventory.json", bundle_dir / "inventory.json")
    if (root / "swebench.yaml").exists():
        shutil.copy2(root / "swebench.yaml", bundle_dir / "swebench.yaml")
    
    # Create safe .env.template (without real credentials)
    (bundle_dir / ".env.template").write_text(
        "GEMINI_API_KEY=your_key_here\nMSWEA_COST_TRACKING=ignore_errors\n", encoding="utf-8"
    )

    print("Copying raw experimental benchmark JSONs...")
    results_dest = bundle_dir / "results"
    results_dest.mkdir(parents=True, exist_ok=True)
    for j in (root / "results").glob("*.json"):
        shutil.copy2(j, results_dest / j.name)

    # Copy recurrent cluster results
    if (root / "results" / "recurrent_cluster_experiment").exists():
        shutil.copytree(
            root / "results" / "recurrent_cluster_experiment",
            results_dest / "recurrent_cluster_experiment"
        )

    # Copy chronological benchmark results
    if (root / "results" / "chronological_benchmark").exists():
        shutil.copytree(
            root / "results" / "chronological_benchmark",
            results_dest / "chronological_benchmark"
        )

    # Copy eval reports
    if (root / "results" / "eval_reports").exists():
        shutil.copytree(
            root / "results" / "eval_reports",
            results_dest / "eval_reports"
        )

    print("Copying execution logs, patches, and test outcomes...")
    if (root / "logs" / "run_evaluation").exists():
        shutil.copytree(
            root / "logs" / "run_evaluation",
            bundle_dir / "logs" / "run_evaluation"
        )

    # Copy top-level eval json reports
    for j in root.glob("gemini__gemini-3.5-flash-lite.*.json"):
        shutil.copy2(j, results_dest / j.name)

    print("Writing README_REPRODUCIBILITY.md...")
    readme_content = """# Reproducibility Package: Session-Persistent Repository Memory Architecture

**Manuscript**: Persistent Repository Memory for Autonomous Software Engineering Agents: Architectural Foundations, Empirical Retrieval, and Downstream Resolution Limits  
**Authors**: Abhinav Pant, Abhiram Anil, A Anjana Nair  
**Target Venue**: IEEE Conference on Software Engineering / Artificial Intelligence  

---

## 1. Package Directory Structure
```
reproducibility_package/
├── README_REPRODUCIBILITY.md          # Complete replication instructions
├── inventory.json                     # Metadata and base commits for SWE-bench Verified Mini (50 tasks)
├── swebench.yaml                      # SWE-bench configuration
├── .env.template                      # Environment variables template
├── memory_pilot/                      # Complete executable memory module source code
│   ├── interface.py                   # BaseMemory abstraction & data schemas
│   ├── condition_a.py                 # Stateless baseline
│   ├── condition_b.py                 # Snapshot lexical (TF-IDF)
│   ├── condition_c.py                 # Naive concatenation combo
│   └── condition_d.py                 # Structural AST symbol graph + Hybrid RRF + Staleness
├── scripts/                           # Reproducible experimental scripts
│   ├── run_statistical_tests.py       # 1-command statistical verification (Wilcoxon, McNemar, Wilson CIs)
│   ├── run_multi_repo_benchmark.py    # Cross-repository benchmark (Django + Sphinx, N=50)
│   ├── eval_component_ablations.py    # Architectural component-wise ablations & cache profiling
│   └── eval_drift_and_staleness.py    # 4 drift scenarios & lambda sensitivity analysis
├── results/                           # Raw machine-readable experimental output JSONs
│   ├── multi_repo_n50_benchmark.json
│   ├── comprehensive_retrieval_benchmark.json
│   ├── component_wise_ablations.json
│   ├── systematic_drift_and_staleness_study.json
│   ├── recurrent_cluster_summary.json
│   ├── eval_reports/                  # SWE-bench Docker harness evaluation reports
│   └── recurrent_cluster_experiment/  # Step-by-step trajectories and token usage logs
└── logs/
    └── run_evaluation/                # Raw execution traces, patches (patch.diff), test_output.txt
```

---

## 2. Fast 1-Command Statistical Verification
To instantly verify all manuscript statistics, confidence intervals, and Wilcoxon p-values without re-running long evaluations:
```bash
python scripts/run_statistical_tests.py
```

Expected output:
- Django (N=25): RRF MRR=0.5773 (+57.4% vs Lexical at 0.3667), R@1=44.0%, R@5=80.0%, Wilcoxon W=13.5, p=0.0077.
- Sphinx (N=25): RRF R@5=44.0% vs Lexical at 40.0% and Pure AST at 16.0%.
- Combined (N=50): RRF MRR=0.4110 (+22.7% vs Lexical at 0.3350), R@5=62.0% (31/50 hits).

---

## 3. Re-Running Empirical Benchmarks from Scratch

### Prerequisites
- Python 3.11+
- Virtual environment with dependencies:
```bash
pip install -r requirements.txt
# Dependencies: tree-sitter==0.26.0 tree-sitter-python==0.25.0 scikit-learn==1.9.1 scipy==1.17.1 datasets==5.1.0 unidiff==1.0.1
```

### Benchmarks
1. **Multi-Repository Benchmark (Django & Sphinx, N=50)**:
   ```bash
   python scripts/run_multi_repo_benchmark.py
   ```
2. **Component-Wise Ablations & Incremental Cache Profiling**:
   ```bash
   python scripts/eval_component_ablations.py
   ```
3. **Repository Drift Scenarios & Staleness Sensitivity Sweep**:
   ```bash
   python scripts/eval_drift_and_staleness.py
   ```
"""
    (bundle_dir / "README_REPRODUCIBILITY.md").write_text(readme_content, encoding="utf-8")

    # Generate requirements.txt
    reqs = (
        "tree-sitter>=0.26.0\n"
        "tree-sitter-python>=0.25.0\n"
        "scikit-learn>=1.9.1\n"
        "scipy>=1.17.1\n"
        "numpy>=2.4.6\n"
        "datasets>=5.1.0\n"
        "unidiff>=1.0.1\n"
        "mini-swe-agent>=2.4.6\n"
        "swebench>=4.1.0\n"
    )
    (bundle_dir / "requirements.txt").write_text(reqs, encoding="utf-8")

    print("Archiving into reproducibility_package.tar.gz...")
    tar_path = root / "reproducibility_package.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(bundle_dir, arcname="reproducibility_package")

    print(f"Archive successfully generated at {tar_path} ({tar_path.stat().st_size / (1024*1024):.2f} MB)")


if __name__ == "__main__":
    create_reproducibility_package()
