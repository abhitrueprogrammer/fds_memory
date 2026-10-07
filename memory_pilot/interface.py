from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, NamedTuple


class MemoryOutput(NamedTuple):
    context_str: str
    retrieved_files: list[str]
    metadata: dict[str, Any]


class BaseMemory(ABC):
    """Base interface for repository memory implementations."""

    def __init__(self, name: str, token_budget: int = 1200):
        self.name = name
        self.token_budget = token_budget

    @abstractmethod
    def get_memory_context(
        self,
        task: dict[str, Any],
        repo_dir: Path,
    ) -> MemoryOutput:
        """Get memory context to inject into task prompt before agent starts.
        
        Args:
            task: Task dictionary containing 'instance_id', 'problem_statement', 'base_commit', etc.
            repo_dir: Local path to repository snapshot at task base_commit.
            
        Returns:
            MemoryOutput namedtuple containing context_str, retrieved_files, and metadata.
        """
        pass

    @abstractmethod
    def update_memory(
        self,
        task: dict[str, Any],
        repo_dir: Path,
        harness_passed: bool,
        files_edited: list[str],
        files_retrieved: list[str],
    ) -> None:
        """Update memory state after task has been scored by SWE-bench harness.
        
        Args:
            task: Task dictionary.
            repo_dir: Path to repository snapshot.
            harness_passed: True if harness resolved the task, False otherwise.
            files_edited: Files modified by agent patch.
            files_retrieved: Files retrieved by memory for this task.
        """
        pass

    def reset(self) -> None:
        """Reset memory state between sequence runs."""
        pass
