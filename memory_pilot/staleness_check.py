"""Staleness check demonstration between Condition C (naive) and Condition D (staleness-aware)."""

from pathlib import Path
import subprocess

from memory_pilot.condition_c import ConditionCMemory
from memory_pilot.condition_d import ConditionDMemory


def run_staleness_experiment(repo_dir: Path):
    cond_c = ConditionCMemory(token_budget=1200)
    cond_d = ConditionDMemory(token_budget=1200)

    sample_task = {
        "instance_id": "django__django-11790",
        "problem_statement": "AuthenticationForm username field maxlength attribute",
    }
    target_file = "django/contrib/auth/forms.py"

    print("=== Step 1: Record initial task in memory for C and D ===")
    cond_c.update_memory(
        task=sample_task,
        repo_dir=repo_dir,
        harness_passed=True,
        files_edited=[target_file],
        files_retrieved=[target_file],
    )
    cond_d.update_memory(
        task=sample_task,
        repo_dir=repo_dir,
        harness_passed=True,
        files_edited=[target_file],
        files_retrieved=[target_file],
    )

    query_task = {
        "instance_id": "django__django-11880",
        "problem_statement": "Form Field deepcopy and error messages in forms",
    }

    print("\n=== Step 2: Query memory BEFORE file modification ===")
    out_c_before = cond_c.get_memory_context(query_task, repo_dir)
    out_d_before = cond_d.get_memory_context(query_task, repo_dir)
    print("Condition C context contains target file:", target_file in out_c_before.context_str)
    print("Condition D flags stale before mod:", "STALE" in out_d_before.context_str)
    print("Condition D flags fresh before mod:", "FRESH" in out_d_before.context_str)

    print("\n=== Step 3: Modify source file in repository ===")
    file_path = repo_dir / target_file
    orig_content = file_path.read_text(encoding="utf-8")
    try:
        # Append simulated edit
        file_path.write_text(orig_content + "\n# Simulated modification in repository\n", encoding="utf-8")

        print("\n=== Step 4: Query memory AFTER file modification ===")
        out_c_after = cond_c.get_memory_context(query_task, repo_dir)
        out_d_after = cond_d.get_memory_context(query_task, repo_dir)

        c_flags_stale = "STALE" in out_c_after.context_str or "stale" in out_c_after.context_str.lower()
        d_flags_stale = "STALE" in out_d_after.context_str

        print("Condition C flags stale after modification:", c_flags_stale)
        print("Condition D flags stale after modification:", d_flags_stale)

        # Extract Condition D snippet
        for line in out_d_after.context_str.splitlines():
            if "STALE" in line or "Episode django__django-11790" in line:
                print("Condition D banner:", line)

        return {
            "target_file": target_file,
            "condition_c_flags_stale": c_flags_stale,
            "condition_d_flags_stale": d_flags_stale,
            "condition_d_snippet": [l for l in out_d_after.context_str.splitlines() if "STALE" in l],
        }
    finally:
        # Restore original file via git
        subprocess.run(["git", "checkout", "--", target_file], cwd=str(repo_dir), check=True)
        print("Restored file successfully via git checkout.")


if __name__ == "__main__":
    repo_dir = Path("repos/django")
    res = run_staleness_experiment(repo_dir)
    import json
    Path("results/staleness_check.json").write_text(json.dumps(res, indent=2))
