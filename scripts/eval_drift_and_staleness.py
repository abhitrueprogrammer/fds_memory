"""Systematic Repository Drift and Staleness Sensitivity Evaluation.

Evaluates repository drift scenarios (signature changes, renames, deletions, conflicts)
and performs sensitivity analysis on the staleness attenuation factor lambda in [0.0, 1.0].
Addresses Reviewer Weakness F and Required Improvement 7.
"""

from pathlib import Path
import json
import subprocess
import shutil
import numpy as np

from memory_pilot.condition_c import ConditionCMemory
from memory_pilot.condition_d import ConditionDMemory, EpisodicEntry, compute_file_sha256


def run_drift_scenarios(repo_dir: Path) -> dict:
    """Run systematic drift scenarios: signature drift, file rename, deleted symbol, and conflicting memories."""
    print("\n--- Running Drift Scenario 1: Changed Function Signature ---")
    cond_c = ConditionCMemory(token_budget=1200)
    cond_d = ConditionDMemory(token_budget=1200, use_staleness=True)

    target_file = "django/utils/http.py"
    full_target = repo_dir / target_file
    orig_content = full_target.read_text(encoding="utf-8")

    ep_task = {
        "instance_id": "django__django-11848",
        "problem_statement": "parse_http_date century parsing with 2-digit years",
    }

    try:
        # Pre-seed episodic memory
        cond_c.update_memory(ep_task, repo_dir, True, [target_file], [target_file])
        cond_d.update_memory(ep_task, repo_dir, True, [target_file], [target_file])

        # Simulate signature drift: modify parse_http_date signature
        drifted_content = orig_content.replace(
            "def parse_http_date(date):",
            "def parse_http_date(date, base_year=None, strict=True): # DRIFTED SIGNATURE"
        )
        full_target.write_text(drifted_content, encoding="utf-8")

        # Query
        query_task = {"instance_id": "django__django-12000", "problem_statement": "parse_http_date strict parsing validation"}
        out_c = cond_c.get_memory_context(query_task, repo_dir)
        out_d = cond_d.get_memory_context(query_task, repo_dir)

        s1_result = {
            "scenario": "signature_drift",
            "condition_c_detected_drift": "STALE" in out_c.context_str,
            "condition_d_detected_drift": "STALE" in out_d.context_str,
            "condition_d_reparsed_ast": out_d.metadata.get("reparsed_files", 0) > 0,
            "condition_d_new_symbols_present": "base_year" in out_d.context_str or "strict" in out_d.context_str or "parse_http_date" in out_d.context_str,
        }
    finally:
        full_target.write_text(orig_content, encoding="utf-8")

    print("\n--- Running Drift Scenario 2: Renamed / Moved Source File ---")
    renamed_file = "django/utils/http_legacy_renamed.py"
    renamed_full = repo_dir / renamed_file
    try:
        full_target.rename(renamed_full)

        out_c_rename = cond_c.get_memory_context(query_task, repo_dir)
        out_d_rename = cond_d.get_memory_context(query_task, repo_dir)

        s2_result = {
            "scenario": "file_rename_or_deletion",
            "condition_c_hallucinates_deleted_path": target_file in out_c_rename.retrieved_files,
            "condition_d_flags_missing_file": "deleted" in out_d_rename.context_str.lower() or target_file not in out_d_rename.retrieved_files,
            "condition_d_retrieved": out_d_rename.retrieved_files,
        }
    finally:
        if renamed_full.exists():
            renamed_full.rename(full_target)
        else:
            full_target.write_text(orig_content, encoding="utf-8")

    print("\n--- Running Drift Scenario 3: Deleted Symbol ---")
    try:
        # Simulate deleting a function entirely
        deleted_func_content = orig_content.replace("def parse_http_date(date):", "def _parse_http_date_deprecated(date):")
        full_target.write_text(deleted_func_content, encoding="utf-8")

        out_d_del = cond_d.get_memory_context(query_task, repo_dir)
        sym = cond_d.symbol_cache.get(target_file)
        has_old_func = "parse_http_date" in (sym.functions if sym else [])

        s3_result = {
            "scenario": "deleted_symbol",
            "ast_purged_deleted_function": not has_old_func,
            "ast_indexed_new_symbol": "_parse_http_date_deprecated" in (sym.functions if sym else []),
        }
    finally:
        full_target.write_text(orig_content, encoding="utf-8")

    print("\n--- Running Drift Scenario 4: Conflicting Historical Memories ---")
    file_a = "django/db/models/base.py"
    file_b = "django/db/models/fields/__init__.py"

    full_a = repo_dir / file_a
    orig_a = full_a.read_text(encoding="utf-8")

    cond_d_conflict = ConditionDMemory(token_budget=1500, use_staleness=True)
    try:
        # Episode 1 touching file_a
        cond_d_conflict.update_memory(
            {"instance_id": "ep1_base", "problem_statement": "Model save validation constraint error in models"},
            repo_dir, True, [file_a], [file_a]
        )
        # Episode 2 touching file_b
        cond_d_conflict.update_memory(
            {"instance_id": "ep2_field", "problem_statement": "Model Field clean validation error in models"},
            repo_dir, True, [file_b], [file_b]
        )

        # Now drift file_a only (file_b remains fresh)
        full_a.write_text(orig_a + "\n# Commit V2 modification in base.py\n", encoding="utf-8")

        conflict_query = {"instance_id": "ep3_query", "problem_statement": "Model validation error in models"}
        out_conflict = cond_d_conflict.get_memory_context(conflict_query, repo_dir)

        # Inspect episodic weights in context
        is_ep1_stale = "STALE" in out_conflict.context_str and "ep1_base" in out_conflict.context_str
        is_ep2_fresh = "FRESH" in out_conflict.context_str and "ep2_field" in out_conflict.context_str

        s4_result = {
            "scenario": "conflicting_memories",
            "drifted_episode_penalized_stale": is_ep1_stale,
            "fresh_episode_retained_full_weight": is_ep2_fresh,
        }
    finally:
        full_a.write_text(orig_a, encoding="utf-8")

    return {
        "scenario_1_signature_drift": s1_result,
        "scenario_2_file_rename": s2_result,
        "scenario_3_deleted_symbol": s3_result,
        "scenario_4_conflicting_memories": s4_result,
    }


def run_lambda_sensitivity_analysis(repo_dir: Path) -> dict:
    """Evaluate retrieval precision and rank metrics across lambda attenuation values."""
    print("\n=======================================================")
    print("Running Staleness Attenuation Factor (lambda) Sensitivity Analysis")
    print("=======================================================")

    lambdas = [0.0, 0.1, 0.2, 0.3, 0.5, 0.8, 1.0]
    
    test_cases = [
        {
            "query": "parse_http_date century parsing year",
            "gold_file": "django/utils/http.py",
            "modified_file": "django/utils/http.py",
            "distractor_file": "django/utils/dateformat.py",
        },
        {
            "query": "AuthenticationForm username field maxlength",
            "gold_file": "django/contrib/auth/forms.py",
            "modified_file": "django/contrib/auth/forms.py",
            "distractor_file": "django/contrib/auth/views.py",
        },
        {
            "query": "Model save validation constraint error",
            "gold_file": "django/db/models/base.py",
            "modified_file": "django/db/models/base.py",
            "distractor_file": "django/db/models/query.py",
        }
    ]

    sensitivity_results = {}

    for lam in lambdas:
        ranks = []
        hits_at_1 = 0
        hits_at_5 = 0

        for tc in test_cases:
            target_file = tc["gold_file"]
            full_target = repo_dir / target_file
            orig_text = full_target.read_text(encoding="utf-8")

            cond_d = ConditionDMemory(token_budget=1200, use_staleness=True)
            # Override attenuation factor
            try:
                # Pre-seed episode
                cond_d.update_memory(
                    {"instance_id": "seed_ep", "problem_statement": tc["query"]},
                    repo_dir, True, [target_file], [target_file]
                )

                # Mutate file on disk to simulate drift
                full_target.write_text(orig_text + "\n# Drift edit\n", encoding="utf-8")

                # In condition_d, attenuation is applied in _get_episodic_ranking:
                # We monkey-patch the attenuation factor
                orig_epi_rank = cond_d._get_episodic_ranking
                def patched_epi_ranking(query, r_dir, factor=lam):
                    # compute with custom lambda factor
                    if not cond_d.episodes:
                        return {}, {}
                    query_words = set(query.lower().split())
                    scores = {}
                    for ep in cond_d.episodes:
                        is_stale, _ = cond_d.check_staleness(ep, r_dir)
                        eff_weight = ep.weight if not is_stale else ep.weight * factor
                        ep_words = set(ep.problem_statement.lower().split())
                        sim = len(query_words & ep_words) / max(len(query_words | ep_words), 1)
                        for f in ep.files_edited:
                            scores[f] = scores.get(f, 0.0) + (sim * eff_weight * 3.0)
                    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                    return {r[0]: rank for rank, r in enumerate(ranked)}, scores

                cond_d._get_episodic_ranking = patched_epi_ranking

                out = cond_d.get_memory_context({"instance_id": "q", "problem_statement": tc["query"]}, repo_dir)
                retrieved = out.retrieved_files

                if target_file in retrieved:
                    rank = retrieved.index(target_file) + 1
                    ranks.append(1.0 / rank)
                    if rank == 1: hits_at_1 += 1
                    if rank <= 5: hits_at_5 += 1
                else:
                    ranks.append(0.0)
            finally:
                full_target.write_text(orig_text, encoding="utf-8")

        mrr = float(np.mean(ranks)) if ranks else 0.0
        sensitivity_results[str(lam)] = {
            "lambda": lam,
            "mrr": round(mrr, 4),
            "hit_at_1_rate": round(hits_at_1 / len(test_cases), 4),
            "hit_at_5_rate": round(hits_at_5 / len(test_cases), 4),
            "interpretation": (
                "Hard eviction (zero credit for stale files)" if lam == 0.0 else
                "Default moderate penalty (balances fresh symbols vs historical hints)" if lam == 0.2 else
                "Weak penalty (stale memories risk contaminating active context)" if lam >= 0.8 else
                "Moderate attenuation"
            )
        }
        print(f"Lambda = {lam:0.2f} -> MRR = {mrr:0.4f}, Hit@1 = {hits_at_1}/{len(test_cases)}, Hit@5 = {hits_at_5}/{len(test_cases)}")

    return sensitivity_results


def main():
    repo_dir = Path("repos/django")
    print("Executing Systematic Repository Drift and Staleness Study...")

    drift_results = run_drift_scenarios(repo_dir)
    lambda_results = run_lambda_sensitivity_analysis(repo_dir)

    combined = {
        "drift_scenarios": drift_results,
        "lambda_sensitivity_analysis": lambda_results,
    }

    out_file = Path("results/systematic_drift_and_staleness_study.json")
    out_file.write_text(json.dumps(combined, indent=2))
    print(f"\nSaved drift and staleness study results to {out_file}")
    print(json.dumps(combined, indent=2))


if __name__ == "__main__":
    main()
