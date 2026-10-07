from pathlib import Path
from typing import Any

from memory_pilot.interface import BaseMemory, MemoryOutput


class ConditionAMemory(BaseMemory):
    """Condition A: No memory.
    
    Injects nothing into the task prompt.
    Nothing is stored or updated between tasks.
    """

    def __init__(self, token_budget: int = 1200):
        super().__init__(name="A_no_memory", token_budget=token_budget)

    def get_memory_context(
        self,
        task: dict[str, Any],
        repo_dir: Path,
    ) -> MemoryOutput:
        return MemoryOutput(
            context_str="",
            retrieved_files=[],
            metadata={"condition": "A", "items_included": []},
        )

    def update_memory(
        self,
        task: dict[str, Any],
        repo_dir: Path,
        harness_passed: bool,
        files_edited: list[str],
        files_retrieved: list[str],
    ) -> None:
        # No-op: nothing carried across tasks
        pass
