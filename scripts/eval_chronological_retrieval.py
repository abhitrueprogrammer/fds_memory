"""Chronological Task-Specific Checkout Evaluation Benchmark.

Evaluates retrieval on exact task-specific git checkouts (base_commit)
to strictly prevent future repository information from entering retrieval or memory.
Runs on both django/django (N=25) and sphinx-doc/sphinx (N=25).
"""

from pathlib import Path
import json
import subprocess
import numpy as np
from datasets import load_dataset
import unidiff
from memory_pilot.condition_b import ConditionBMemory
from memory_pilot.condition_c import ConditionCMemory
from memory_pilot.condition_d import ConditionDMemory
from memory_pilot.eval_retrieval import extract_gold_files, calculate_recall_at_k, calculate_reciprocal_rank, wilson_ci


def checkout_commit(repo_dir: Path, commit_sha: str) -> bool:
    """Checkout a specific git commit cleanly."""
    try:
        subprocess.run(["git", "reset", "--hard"], cwd=str(repo_dir), check=True, capture_output=True)
        subprocess.run(["git", "clean", "-fd"], cwd=str(repo_dir), check=True, capture_output=True)
        res = subprocess.run(["git", "checkout", commit_sha], cwd=str(repo_dir), check=True, capture_output=True)
        return res.returncode == 0
    except Exception as e:
        print(f"Error checking out {commit_sha}: {e}")
        return False


def run_chronological_benchmark(repo_name: str, repo_dir: Path) -> dict:
    ds = load_dataset("MariusHobbhahn/swe-bench-verified-mini", split="test")
    tasks = [x for x in ds if x["repo"] == repo_name]
    tasks.sort(key=lambda x: x["created_at"])

    # Track original HEAD to restore later
    orig_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo_dir), capture_output=True, text=True, check=True
    ).stdout.strip()

    print(f"\n=======================================================")
    print(f"Running Task-Specific Chronological Benchmark: {repo_name} (N={len(tasks)})")
    print(f"=======================================================")

    results = []
    variants = [
        "B_Snapshot_BM25",
        "C_Naive_Combo",
        "D_Pure_AST",
        "D_Static_Hybrid_RRF",
        "D_Episodic_Hybrid_RRF",
    ]
    stats = {v: {"r1": 0, "r3": 0, "r5": 0, "mrrs": []} for v in variants}

    # Static Hybrid RRF maintains persistent AST symbol cache across chronological commits
    mem_static_hybrid = ConditionDMemory(token_budget=1200, top_files_k=5, use_hybrid_rrf=True, use_episodic=False)
    # Episodic Hybrid RRF additionally accumulates past task episodes
    mem_episodic_hybrid = ConditionDMemory(token_budget=1200, top_files_k=5, use_hybrid_rrf=True, use_episodic=True)

    try:
        for idx, task in enumerate(tasks):
            instance_id = task["instance_id"]
            base_commit = task["base_commit"]
            gold_files = extract_gold_files(task["patch"])
            if not gold_files:
                continue

            # Task-specific checkout: ensure zero future code enters repository
            ok = checkout_commit(repo_dir, base_commit)
            if not ok:
                print(f"Skipping {instance_id}: checkout failed")
                continue

            # Condition instances for this checkout
            mem_b = ConditionBMemory(token_budget=1200, top_k=5)
            mem_c = ConditionCMemory(token_budget=1200)
            mem_ast = ConditionDMemory(token_budget=1200, top_files_k=5, use_hybrid_rrf=False, use_episodic=False)

            # Update structural index incrementally on the newly checked-out state
            stats_inc = mem_static_hybrid.update_structural_index(repo_dir)
            mem_episodic_hybrid.symbol_cache = mem_static_hybrid.symbol_cache
            mem_episodic_hybrid.lexical_cache = mem_static_hybrid.lexical_cache
            mem_ast.symbol_cache = mem_static_hybrid.symbol_cache

            var_map = {
                "B_Snapshot_BM25": mem_b,
                "C_Naive_Combo": mem_c,
                "D_Pure_AST": mem_ast,
                "D_Static_Hybrid_RRF": mem_static_hybrid,
                "D_Episodic_Hybrid_RRF": mem_episodic_hybrid,
            }

            task_res = {
                "instance_id": instance_id,
                "base_commit": base_commit,
                "created_at": task["created_at"],
                "gold_files": gold_files,
                "incremental_cache_stats": stats_inc,
                "variants": {},
            }

            for v_name, m_obj in var_map.items():
                out = m_obj.get_memory_context(task, repo_dir)
                r1 = calculate_recall_at_k(out.retrieved_files, gold_files, 1)
                r3 = calculate_recall_at_k(out.retrieved_files, gold_files, 3)
                r5 = calculate_recall_at_k(out.retrieved_files, gold_files, 5)
                rr = calculate_reciprocal_rank(out.retrieved_files, gold_files)

                if r1 > 0: stats[v_name]["r1"] += 1
                if r3 > 0: stats[v_name]["r3"] += 1
                if r5 > 0: stats[v_name]["r5"] += 1
                stats[v_name]["mrrs"].append(rr)

                task_res["variants"][v_name] = {
                    "retrieved": out.retrieved_files,
                    "recall@1": r1,
                    "recall@3": r3,
                    "recall@5": r5,
                    "reciprocal_rank": round(rr, 4),
                }

            # Update episodic memory on episodic hybrid condition (zero leakage post-task)
            mem_episodic_hybrid.update_memory(
                task=task,
                repo_dir=repo_dir,
                harness_passed=True,
                files_edited=[],
                files_retrieved=task_res["variants"]["D_Episodic_Hybrid_RRF"]["retrieved"],
            )

            results.append(task_res)
            print(f"[{idx+1}/{len(tasks)}] {instance_id}: Static RRF MRR={task_res['variants']['D_Static_Hybrid_RRF']['reciprocal_rank']}, Episodic MRR={task_res['variants']['D_Episodic_Hybrid_RRF']['reciprocal_rank']} | Reparsed={stats_inc['reparsed']}, Cached={stats_inc['cached']}")

    finally:
        # Restore original HEAD
        print(f"Restoring repository HEAD to {orig_head}...")
        checkout_commit(repo_dir, orig_head)

    # Compute aggregate summary
    n_tasks = len(results)
    aggregated = {}
    for v_name, s in stats.items():
        r1_rate = s["r1"] / n_tasks if n_tasks else 0.0
        r3_rate = s["r3"] / n_tasks if n_tasks else 0.0
        r5_rate = s["r5"] / n_tasks if n_tasks else 0.0
        mrr = float(np.mean(s["mrrs"])) if s["mrrs"] else 0.0

        ci_r1 = wilson_ci(s["r1"], n_tasks)
        ci_r5 = wilson_ci(s["r5"], n_tasks)

        aggregated[v_name] = {
            "recall@1": round(r1_rate, 4),
            "recall@1_ci95": ci_r1,
            "recall@3": round(r3_rate, 4),
            "recall@5": round(r5_rate, 4),
            "recall@5_ci95": ci_r5,
            "mrr": round(mrr, 4),
            "raw_hits_r1": s["r1"],
            "raw_hits_r5": s["r5"],
            "total_tasks": n_tasks,
            "mrrs_raw": s["mrrs"],
        }

    return {
        "repo": repo_name,
        "evaluation_type": "chronological_task_specific_checkout",
        "total_tasks": n_tasks,
        "aggregated_metrics": aggregated,
        "per_task_results": results,
    }


def compute_combined_chronological(django_res: dict, sphinx_res: dict) -> dict:
    from scipy.stats import wilcoxon

    combined_metrics = {}
    variants = list(django_res["aggregated_metrics"].keys())

    for var in variants:
        d_mrrs = django_res["aggregated_metrics"][var]["mrrs_raw"]
        s_mrrs = sphinx_res["aggregated_metrics"][var]["mrrs_raw"]
        comb_mrrs = d_mrrs + s_mrrs

        tot_r1 = django_res["aggregated_metrics"][var]["raw_hits_r1"] + sphinx_res["aggregated_metrics"][var]["raw_hits_r1"]
        tot_r5 = django_res["aggregated_metrics"][var]["raw_hits_r5"] + sphinx_res["aggregated_metrics"][var]["raw_hits_r5"]
        total_n = len(comb_mrrs)

        combined_metrics[var] = {
            "combined_mrr": round(float(np.mean(comb_mrrs)), 4),
            "combined_hit_at_1_rate": round(tot_r1 / total_n, 4),
            "combined_hit_at_1_ci95": wilson_ci(tot_r1, total_n),
            "combined_hit_at_5_rate": round(tot_r5 / total_n, 4),
            "combined_hit_at_5_ci95": wilson_ci(tot_r5, total_n),
            "raw_hits_r1": tot_r1,
            "raw_hits_r5": tot_r5,
            "total_tasks": total_n,
            "mrrs": comb_mrrs,
        }

    # Wilcoxon test: Static Hybrid RRF vs Snapshot Lexical (N=50 chronological)
    rrf_mrrs = combined_metrics["D_Static_Hybrid_RRF"]["mrrs"]
    lex_mrrs = combined_metrics["B_Snapshot_BM25"]["mrrs"]
    diff = np.array(rrf_mrrs) - np.array(lex_mrrs)
    non_zero = diff[diff != 0]

    if len(non_zero) > 0:
        w_res_two = wilcoxon(rrf_mrrs, lex_mrrs, alternative="two-sided")
        w_res_one = wilcoxon(rrf_mrrs, lex_mrrs, alternative="greater")
        wilc_summary = {
            "statistic": float(w_res_two.statistic),
            "two_sided_p": float(w_res_two.pvalue),
            "greater_p": float(w_res_one.pvalue),
            "discordant_pairs": int(len(non_zero)),
        }
    else:
        wilc_summary = {"statistic": 0.0, "two_sided_p": 1.0, "greater_p": 1.0, "discordant_pairs": 0}

    return {
        "combined_metrics": combined_metrics,
        "wilcoxon_rrf_vs_lexical_n50": wilc_summary,
    }


def main():
    out_dir = Path("results/chronological_benchmark")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Django Chronological
    django_res = run_chronological_benchmark("django/django", Path("repos/django"))
    (out_dir / "django_chronological.json").write_text(json.dumps(django_res, indent=2))

    # 2. Sphinx Chronological
    sphinx_res = run_chronological_benchmark("sphinx-doc/sphinx", Path("repos/sphinx"))
    (out_dir / "sphinx_chronological.json").write_text(json.dumps(sphinx_res, indent=2))

    # 3. Combined Chronological (N=50)
    combined_res = compute_combined_chronological(django_res, sphinx_res)
    (out_dir / "combined_chronological.json").write_text(json.dumps(combined_res, indent=2))

    # Overall artifact
    overall = {
        "django": django_res,
        "sphinx": sphinx_res,
        "combined_n50": combined_res,
    }
    Path("results/chronological_n50_benchmark.json").write_text(json.dumps(overall, indent=2))

    print("\n\n================ CHRONOLOGICAL BENCHMARK SUMMARY ================")
    print("DJANGO CHRONOLOGICAL:")
    print(json.dumps({k: {m: v[m] for m in ["recall@1", "recall@5", "mrr", "raw_hits_r5"]} for k, v in django_res["aggregated_metrics"].items()}, indent=2))
    print("\nSPHINX CHRONOLOGICAL:")
    print(json.dumps({k: {m: v[m] for m in ["recall@1", "recall@5", "mrr", "raw_hits_r5"]} for k, v in sphinx_res["aggregated_metrics"].items()}, indent=2))
    print("\nCOMBINED CHRONOLOGICAL (N=50):")
    print(json.dumps({k: {m: v[m] for m in ["combined_hit_at_1_rate", "combined_hit_at_5_rate", "combined_mrr", "raw_hits_r5"]} for k, v in combined_res["combined_metrics"].items()}, indent=2))
    print("Wilcoxon:", json.dumps(combined_res["wilcoxon_rrf_vs_lexical_n50"], indent=2))


if __name__ == "__main__":
    main()
