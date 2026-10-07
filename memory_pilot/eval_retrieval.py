from pathlib import Path
import json
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
        # p.path or p.target_file, stripped of a/ or b/
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


def run_offline_retrieval_evaluation(
    instance_ids: list[str],
    repo_dir: Path,
) -> dict:
    ds = load_dataset("MariusHobbhahn/swe-bench-verified-mini", split="test")
    tasks_by_id = {x["instance_id"]: x for x in ds}

    cond_b = ConditionBMemory(token_budget=1200, top_k=5)
    cond_c = ConditionCMemory(token_budget=1200)
    cond_d = ConditionDMemory(token_budget=1200, top_files_k=5)

    results = []

    for idx, instance_id in enumerate(instance_ids):
        task = tasks_by_id[instance_id]
        gold_files = extract_gold_files(task["patch"])

        # Retrieval for B
        out_b = cond_b.get_memory_context(task, repo_dir)
        # Retrieval for C
        out_c = cond_c.get_memory_context(task, repo_dir)
        # Retrieval for D
        out_d = cond_d.get_memory_context(task, repo_dir)

        task_eval = {
            "instance_id": instance_id,
            "created_at": task["created_at"],
            "gold_files": gold_files,
            "B": {
                "retrieved": out_b.retrieved_files,
                "recall@1": calculate_recall_at_k(out_b.retrieved_files, gold_files, 1),
                "recall@3": calculate_recall_at_k(out_b.retrieved_files, gold_files, 3),
                "recall@5": calculate_recall_at_k(out_b.retrieved_files, gold_files, 5),
            },
            "C": {
                "retrieved": out_c.retrieved_files,
                "recall@1": calculate_recall_at_k(out_c.retrieved_files, gold_files, 1),
                "recall@3": calculate_recall_at_k(out_c.retrieved_files, gold_files, 3),
                "recall@5": calculate_recall_at_k(out_c.retrieved_files, gold_files, 5),
            },
            "D": {
                "retrieved": out_d.retrieved_files,
                "recall@1": calculate_recall_at_k(out_d.retrieved_files, gold_files, 1),
                "recall@3": calculate_recall_at_k(out_d.retrieved_files, gold_files, 3),
                "recall@5": calculate_recall_at_k(out_d.retrieved_files, gold_files, 5),
            },
        }
        results.append(task_eval)

        # Update episodic memories in C and D simulating sequential progression
        # (with non-leaking earlier task data)
        dummy_harness_pass = True  # offline simulation for sequential context build
        cond_c.update_memory(task, repo_dir, dummy_harness_pass, files_edited=[], files_retrieved=out_c.retrieved_files)
        cond_d.update_memory(task, repo_dir, dummy_harness_pass, files_edited=[], files_retrieved=out_d.retrieved_files)

    return results


if __name__ == "__main__":
    sequence = [
        "django__django-11790",
        "django__django-11815",
        "django__django-11848",
    ]
    repo_dir = Path("repos/django")
    print(f"Evaluating offline retrieval for sequence: {sequence}...")
    res = run_offline_retrieval_evaluation(sequence, repo_dir)
    print(json.dumps(res, indent=2))
