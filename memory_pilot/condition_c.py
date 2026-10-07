from pathlib import Path
import subprocess
from typing import Any
import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from memory_pilot.interface import BaseMemory, MemoryOutput
from memory_pilot.condition_b import ConditionBMemory, get_repo_python_files


class ConditionCMemory(BaseMemory):
    """Condition C: Naive combo.
    
    Combines:
    1. Snapshot RAG (vector retrieval over current snapshot)
    2. Git history of likely files (recent commits touching top files)
    3. Similar past tasks (from earlier tasks in sequence)
    
    Simply concatenated and truncated to the same token budget, with no ranking logic.
    """

    def __init__(self, token_budget: int = 1200):
        super().__init__(name="C_naive_combo", token_budget=token_budget)
        self.rag_engine = ConditionBMemory(token_budget=token_budget // 2)
        self.past_tasks: list[dict[str, Any]] = []

    def reset(self) -> None:
        self.past_tasks = []

    def get_memory_context(
        self,
        task: dict[str, Any],
        repo_dir: Path,
    ) -> MemoryOutput:
        char_budget = self.token_budget * 4

        # 1. Snapshot RAG
        rag_out = self.rag_engine.get_memory_context(task, repo_dir)
        retrieved_files = rag_out.retrieved_files

        # 2. Git history of likely files
        git_history_blocks = ["[Git History of Candidate Files]"]
        for f in retrieved_files[:3]:
            try:
                res = subprocess.run(
                    ["git", "log", "-n", "3", "--oneline", "--", f],
                    cwd=str(repo_dir),
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                log_text = res.stdout.strip()
                if log_text:
                    git_history_blocks.append(f"History for {f}:\n  {log_text}")
            except Exception:
                pass
        git_history_str = "\n".join(git_history_blocks)

        # 3. Similar past tasks (from earlier sequence runs)
        past_tasks_blocks = ["[Past Tasks History]"]
        if not self.past_tasks:
            past_tasks_blocks.append("No previous tasks in history yet.")
        else:
            current_query = task.get("problem_statement", "")
            # Find past tasks with word overlap
            query_words = set(re.findall(r"\w+", current_query.lower()))
            for past in self.past_tasks:
                past_words = set(re.findall(r"\w+", past["problem_statement"].lower()))
                overlap = len(query_words & past_words)
                status_str = "PASSED" if past["harness_passed"] else "FAILED"
                past_tasks_blocks.append(
                    f"- Task: {past['instance_id']} (Status: {status_str}, Word overlap: {overlap})\n"
                    f"  Issue: {past['problem_statement'][:150]}...\n"
                    f"  Files edited: {past['files_edited']}\n"
                    f"  Files retrieved: {past['files_retrieved']}"
                )
        past_tasks_str = "\n".join(past_tasks_blocks)

        # Naive concatenation of all 3 blocks with no ranking logic
        full_context = (
            rag_out.context_str
            + "\n\n"
            + git_history_str
            + "\n\n"
            + past_tasks_str
        )

        # Truncate strictly to character budget
        if len(full_context) > char_budget:
            full_context = full_context[:char_budget] + "\n...[truncated to budget]"

        return MemoryOutput(
            context_str=full_context,
            retrieved_files=retrieved_files,
            metadata={
                "condition": "C",
                "items_included": retrieved_files,
                "past_tasks_count": len(self.past_tasks),
            },
        )

    def update_memory(
        self,
        task: dict[str, Any],
        repo_dir: Path,
        harness_passed: bool,
        files_edited: list[str],
        files_retrieved: list[str],
    ) -> None:
        """Record task into naive past tasks history."""
        self.past_tasks.append({
            "instance_id": task.get("instance_id", "unknown"),
            "problem_statement": task.get("problem_statement", "")[:400],
            "files_edited": list(files_edited),
            "files_retrieved": list(files_retrieved),
            "harness_passed": harness_passed,
        })
