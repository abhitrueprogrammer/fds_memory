from pathlib import Path
import json
import numpy as np
from datasets import load_dataset
import unidiff

from memory_pilot.condition_a import ConditionAMemory
from memory_pilot.condition_b import ConditionBMemory
from memory_pilot.condition_c import ConditionCMemory
from memory_pilot.condition_d import ConditionDMemory


def extract_gold_files(patch_str: str) -> list[str]:
    """Extract list of target files modified by a patch."""
    patch_set = unidiff.PatchSet(patch_str)
    files = []
    for p in patch_set:
        path = p.path
        if path.startswith("a/") or path.startswith("b/"):
            path = path[2:]
        files.append(path)
    return files


def calculate_recall_at_k(retrieved: list[str], gold: list[str], k: int) -> float:
    """Calculate recall at top-K retrieved files."""
    if not gold:
        return 0.0
    top_k_retrieved = set(retrieved[:k])
    gold_set = set(gold)
    hits = len(top_k_retrieved & gold_set)
    return hits / len(gold_set)


def calculate_reciprocal_rank(retrieved: list[str], gold: list[str]) -> float:
    """Calculate reciprocal rank for the first relevant file."""
    gold_set = set(gold)
    for rank, f in enumerate(retrieved, start=1):
        if f in gold_set:
            return 1.0 / rank
    return 0.0


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Calculate Wilson 95% score confidence interval."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    margin = (z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))) / denom
    return round(float(center - margin), 4), round(float(center + margin), 4)


def run_comprehensive_retrieval_benchmark(repo_dir: Path, repo_name: str = "django/django") -> dict:
    ds = load_dataset("MariusHobbhahn/swe-bench-verified-mini", split="test")
    django_tasks = [x for x in ds if x["repo"] == repo_name]
    django_tasks.sort(key=lambda x: x["created_at"])

    # Instantiate conditions and ablation variants
    cond_b = ConditionBMemory(token_budget=1200, top_k=5)
    cond_c = ConditionCMemory(token_budget=1200)
    cond_d_ast = ConditionDMemory(token_budget=1200, top_files_k=5, use_hybrid_rrf=False)  # Ablation: Pure AST
    cond_d_hybrid = ConditionDMemory(token_budget=1200, top_files_k=5, use_hybrid_rrf=True)  # Full: Hybrid RRF

    # Pre-index AST once
    cond_d_ast.update_structural_index(repo_dir)
    cond_d_hybrid.symbol_cache = cond_d_ast.symbol_cache

    variants = {
        "B_Snapshot_BM25": cond_b,
        "C_Naive_Combo": cond_c,
        "D_Ablation_Pure_AST": cond_d_ast,
        "D_Full_Hybrid_RRF": cond_d_hybrid,
    }

    per_task_results = []
    summary_stats = {v: {"r1": 0, "r3": 0, "r5": 0, "mrrs": []} for v in variants}

    total_tasks = len(django_tasks)

    for idx, task in enumerate(django_tasks):
        instance_id = task["instance_id"]
        gold_files = extract_gold_files(task["patch"])
        if not gold_files:
            continue

        task_eval = {
            "instance_id": instance_id,
            "created_at": task["created_at"],
            "gold_files": gold_files,
            "variants": {},
        }

        for var_name, mem_obj in variants.items():
            out = mem_obj.get_memory_context(task, repo_dir)
            r1 = calculate_recall_at_k(out.retrieved_files, gold_files, 1)
            r3 = calculate_recall_at_k(out.retrieved_files, gold_files, 3)
            r5 = calculate_recall_at_k(out.retrieved_files, gold_files, 5)
            rr = calculate_reciprocal_rank(out.retrieved_files, gold_files)

            if r1 > 0:
                summary_stats[var_name]["r1"] += 1
            if r3 > 0:
                summary_stats[var_name]["r3"] += 1
            if r5 > 0:
                summary_stats[var_name]["r5"] += 1
            summary_stats[var_name]["mrrs"].append(rr)

            task_eval["variants"][var_name] = {
                "retrieved": out.retrieved_files,
                "recall@1": r1,
                "recall@3": r3,
                "recall@5": r5,
                "reciprocal_rank": round(rr, 4),
            }

            # Update episodic memory (zero leakage, offline simulation)
            if hasattr(mem_obj, "update_memory"):
                mem_obj.update_memory(
                    task=task,
                    repo_dir=repo_dir,
                    harness_passed=True,
                    files_edited=[],
                    files_retrieved=out.retrieved_files,
                )

        per_task_results.append(task_eval)

    # Aggregate metrics
    aggregated = {}
    for var_name, s in summary_stats.items():
        r1_rate = s["r1"] / total_tasks
        r3_rate = s["r3"] / total_tasks
        r5_rate = s["r5"] / total_tasks
        mrr = float(np.mean(s["mrrs"]))

        ci_r1 = wilson_ci(s["r1"], total_tasks)
        ci_r5 = wilson_ci(s["r5"], total_tasks)

        aggregated[var_name] = {
            "recall@1": round(r1_rate, 4),
            "recall@1_ci95": ci_r1,
            "recall@3": round(r3_rate, 4),
            "recall@5": round(r5_rate, 4),
            "recall@5_ci95": ci_r5,
            "mrr": round(mrr, 4),
            "raw_hits_r5": s["r5"],
            "total_tasks": total_tasks,
        }

    return {
        "total_tasks": total_tasks,
        "aggregated_metrics": aggregated,
        "per_task_results": per_task_results,
    }


if __name__ == "__main__":
    repo_dir = Path("repos/django")
    print("Executing comprehensive N=25 retrieval evaluation...")
    benchmark_data = run_comprehensive_retrieval_benchmark(repo_dir)

    out_file = Path("results/comprehensive_retrieval_benchmark.json")
    out_file.write_text(json.dumps(benchmark_data, indent=2))
    print(f"\nSaved benchmark results to {out_file}")
    print("\nAggregated Results:")
    print(json.dumps(benchmark_data["aggregated_metrics"], indent=2))
