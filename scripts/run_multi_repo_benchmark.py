"""Multi-Repository Comprehensive Benchmark (N=50 SWE-bench Verified Mini Tasks).

Evaluates retrieval across two distinct repositories:
1. django/django (Web framework, ORM, deep inheritance hierarchies, N=25)
2. sphinx-doc/sphinx (Documentation engine, AST visitors, parser/builders, N=25)

Computes Recall@1, Recall@3, Recall@5, MRR, 95% Wilson CIs,
and paired Wilcoxon signed-rank tests across all 50 tasks.
Directly addresses Reviewer Weakness B and Required Improvement 2.
"""

from pathlib import Path
import json
import numpy as np
from datasets import load_dataset
from scipy.stats import wilcoxon

from memory_pilot.condition_b import ConditionBMemory
from memory_pilot.condition_c import ConditionCMemory
from memory_pilot.condition_d import ConditionDMemory
from memory_pilot.eval_retrieval import extract_gold_files, calculate_recall_at_k, calculate_reciprocal_rank, wilson_ci


def evaluate_repository_benchmarks(repo_name: str, repo_dir: Path) -> dict:
    ds = load_dataset("MariusHobbhahn/swe-bench-verified-mini", split="test")
    tasks = [x for x in ds if x["repo"] == repo_name]
    tasks.sort(key=lambda x: x["created_at"])

    print(f"\n=======================================================")
    print(f"Evaluating Repository: {repo_name} (N={len(tasks)}) in {repo_dir}")
    print(f"=======================================================")

    cond_b = ConditionBMemory(token_budget=1200, top_k=5)
    cond_c = ConditionCMemory(token_budget=1200)
    cond_d_ast = ConditionDMemory(token_budget=1200, top_files_k=5, use_hybrid_rrf=False, use_episodic=False)
    cond_d_hybrid = ConditionDMemory(token_budget=1200, top_files_k=5, use_hybrid_rrf=True, use_episodic=False)

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
    total_tasks = len(tasks)

    for idx, task in enumerate(tasks):
        instance_id = task["instance_id"]
        gold_files = extract_gold_files(task["patch"])
        if not gold_files:
            continue

        task_res = {
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

            if r1 > 0: summary_stats[var_name]["r1"] += 1
            if r3 > 0: summary_stats[var_name]["r3"] += 1
            if r5 > 0: summary_stats[var_name]["r5"] += 1
            summary_stats[var_name]["mrrs"].append(rr)

            task_res["variants"][var_name] = {
                "retrieved": out.retrieved_files,
                "recall@1": r1,
                "recall@3": r3,
                "recall@5": r5,
                "reciprocal_rank": round(rr, 4),
            }

        per_task_results.append(task_res)

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
            "raw_hits_r1": s["r1"],
            "raw_hits_r5": s["r5"],
            "mrrs_raw": s["mrrs"],
            "total_tasks": total_tasks,
        }

    return {
        "repo": repo_name,
        "total_tasks": total_tasks,
        "aggregated_metrics": aggregated,
        "per_task_results": per_task_results,
    }


def compute_combined_statistics(django_res: dict, sphinx_res: dict) -> dict:
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

    # Paired Wilcoxon Test: Hybrid RRF vs Snapshot Lexical (N=50)
    rrf_mrrs = combined_metrics["D_Full_Hybrid_RRF"]["mrrs"]
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
    django_benchmark = evaluate_repository_benchmarks("django/django", Path("repos/django"))
    sphinx_benchmark = evaluate_repository_benchmarks("sphinx-doc/sphinx", Path("repos/sphinx"))

    combined_stats = compute_combined_statistics(django_benchmark, sphinx_benchmark)

    result = {
        "django": django_benchmark,
        "sphinx": sphinx_benchmark,
        "combined_n50": combined_stats,
    }

    out_file = Path("results/multi_repo_n50_benchmark.json")
    out_file.write_text(json.dumps(result, indent=2))
    print(f"\nSaved Multi-Repository Benchmark to {out_file}")

    print("\n================== BENCHMARK SUMMARY ==================")
    print("DJANGO (N=25):")
    for k, v in django_benchmark["aggregated_metrics"].items():
        print(f"  {k:22s} | MRR: {v['mrr']:.4f} | R@1: {v['recall@1']:.4f} | R@5: {v['recall@5']:.4f}")

    print("\nSPHINX (N=25):")
    for k, v in sphinx_benchmark["aggregated_metrics"].items():
        print(f"  {k:22s} | MRR: {v['mrr']:.4f} | R@1: {v['recall@1']:.4f} | R@5: {v['recall@5']:.4f}")

    print("\nCOMBINED MULTI-REPO (N=50):")
    for k, v in combined_stats["combined_metrics"].items():
        print(f"  {k:22s} | MRR: {v['combined_mrr']:.4f} | R@1: {v['combined_hit_at_1_rate']:.4f} | R@5: {v['combined_hit_at_5_rate']:.4f}")

    print("\nWilcoxon Test (Hybrid RRF vs Snapshot Lexical N=50):")
    print(json.dumps(combined_stats["wilcoxon_rrf_vs_lexical_n50"], indent=2))


if __name__ == "__main__":
    main()
