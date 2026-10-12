"""Runner for Recurrent Subsystem Cluster Evaluation to Test Episodic Transfer."""

import json
from pathlib import Path
import time
from typing import Any

from memory_pilot.runner import run_condition_sequence


RECURRENT_SEQUENCE = [
    "django__django-12209",  # Target: django/db/models/base.py
    "django__django-12273",  # Target: django/db/models/base.py (Recurrent pair!)
]


def extract_trajectory_search_stats(cond_dir: Path, sequence: list[str]) -> dict[str, Any]:
    stats = {}
    for iid in sequence:
        traj_file = cond_dir / iid / iid / f"{iid}.traj.json"
        if not traj_file.exists():
            continue
        try:
            data = json.loads(traj_file.read_text())
            commands = []
            for m in data.get("messages", []):
                for tc in m.get("tool_calls", []):
                    func = tc.get("function", {})
                    args = func.get("arguments", "{}")
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            pass
                    cmd = args.get("command", "") if isinstance(args, dict) else str(args)
                    if cmd:
                        commands.append(cmd)

            grep_count = sum(1 for c in commands if "grep" in c)
            find_count = sum(1 for c in commands if "find" in c)
            read_count = sum(1 for c in commands if any(k in c for k in ["cat", "head", "tail", "sed"]))

            stats[iid] = {
                "grep_commands": grep_count,
                "find_commands": find_count,
                "total_search_commands": grep_count + find_count,
                "read_commands": read_count,
                "total_commands": len(commands),
            }
        except Exception as e:
            stats[iid] = {"error": str(e)}
    return stats


def main():
    repo_dir = Path("repos/django")
    output_dir = Path("results/recurrent_cluster_experiment")
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("STARTING RECURRENT CLUSTER EXPERIMENT")
    print(f"Sequence: {RECURRENT_SEQUENCE}")
    print("=" * 60)

    # 1. Run Baseline Condition A (Stateless)
    print("\n>>> Running Condition A (Stateless Baseline)...")
    res_a = run_condition_sequence("A", RECURRENT_SEQUENCE, repo_dir, output_dir, step_limit=50)
    stats_a = extract_trajectory_search_stats(output_dir / "condition_A", RECURRENT_SEQUENCE)

    # 2. Run Proposed Condition D (Persistent Memory with Episodic Transfer)
    print("\n>>> Running Condition D (Persistent Memory with Episodic Transfer)...")
    res_d = run_condition_sequence("D", RECURRENT_SEQUENCE, repo_dir, output_dir, step_limit=50)
    stats_d = extract_trajectory_search_stats(output_dir / "condition_D", RECURRENT_SEQUENCE)

    summary = {
        "sequence": RECURRENT_SEQUENCE,
        "shared_target": "django/db/models/base.py",
        "condition_A": {
            "results": res_a,
            "trajectory_search_stats": stats_a,
        },
        "condition_D": {
            "results": res_d,
            "trajectory_search_stats": stats_d,
        },
    }

    summary_file = output_dir / "recurrent_cluster_summary.json"
    summary_file.write_text(json.dumps(summary, indent=2))
    print("\n" + "=" * 60)
    print("RECURRENT CLUSTER EXPERIMENT COMPLETED")
    print(f"Summary saved to: {summary_file}")
    print("=" * 60)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
