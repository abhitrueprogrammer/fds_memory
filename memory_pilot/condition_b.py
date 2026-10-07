from pathlib import Path
from typing import Any
import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from memory_pilot.interface import BaseMemory, MemoryOutput


def get_repo_python_files(repo_dir: Path) -> list[Path]:
    """Find source python files in the repository, excluding tests and auto-generated migrations."""
    all_files = []
    for p in repo_dir.rglob("*.py"):
        rel_str = str(p.relative_to(repo_dir))
        # Skip test directories, virtualenvs, hidden folders, and auto-generated migration files
        if (
            "tests/" in rel_str
            or "test/" in rel_str
            or ".git/" in rel_str
            or ".venv/" in rel_str
            or "site-packages" in rel_str
            or bool(re.search(r"/\d{4}_[a-zA-Z0-9_]+\.py$", rel_str))
        ):
            continue
        all_files.append(p)
    return sorted(all_files)



def build_file_text_index(files: list[Path], repo_dir: Path) -> tuple[list[str], list[str]]:
    """Prepare document texts for vector indexing."""
    paths = []
    docs = []
    for f in files:
        rel_path = str(f.relative_to(repo_dir))
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        # Document text combines relative path (repeated for weight) and file content
        doc_text = f"{rel_path} {rel_path.replace('/', ' ').replace('_', ' ')}\n{content[:15000]}"
        paths.append(rel_path)
        docs.append(doc_text)
    return paths, docs


class ConditionBMemory(BaseMemory):
    """Condition B: Snapshot RAG.
    
    Vector retrieval over the current repository snapshot only.
    Nothing carried between tasks.
    """

    def __init__(self, token_budget: int = 1200, top_k: int = 5):
        super().__init__(name="B_snapshot_rag", token_budget=token_budget)
        self.top_k = top_k

    def get_memory_context(
        self,
        task: dict[str, Any],
        repo_dir: Path,
    ) -> MemoryOutput:
        py_files = get_repo_python_files(repo_dir)
        if not py_files:
            return MemoryOutput(
                context_str="",
                retrieved_files=[],
                metadata={"condition": "B", "items_included": []},
            )

        paths, docs = build_file_text_index(py_files, repo_dir)
        query = task.get("problem_statement", "")

        vectorizer = TfidfVectorizer(
            stop_words="english",
            max_features=25000,
            sublinear_tf=True,
            token_pattern=r"(?u)\b[A-Za-z_][A-Za-z0-9_]*\b",
        )
        try:
            doc_matrix = vectorizer.fit_transform(docs)
            query_vec = vectorizer.transform([query])
            sims = cosine_similarity(query_vec, doc_matrix)[0]
            top_indices = np.argsort(sims)[::-1][: self.top_k]
        except Exception:
            return MemoryOutput(
                context_str="",
                retrieved_files=[],
                metadata={"condition": "B", "items_included": []},
            )

        retrieved_files = []
        context_blocks = []
        context_blocks.append("[Repository Snapshot RAG Context]")
        context_blocks.append("Retrieved candidate files from the repository:")

        char_budget = self.token_budget * 4
        current_len = sum(len(b) for b in context_blocks)

        for idx in top_indices:
            file_path = paths[idx]
            score = float(sims[idx])
            if score <= 0.0:
                continue
            retrieved_files.append(file_path)

            # Read top symbols / excerpt from the file
            full_path = repo_dir / file_path
            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
                lines = content.splitlines()
                # Extract class and def headers
                signatures = [
                    line.strip()
                    for line in lines
                    if re.match(r"^\s*(class|def|async def)\s+[A-Za-z_]", line)
                ][:8]
                sig_str = "\n  ".join(signatures) if signatures else lines[0][:200]
            except Exception:
                sig_str = "(could not read file)"

            entry = f"- File: {file_path} (relevance score: {score:.3f})\n  Key symbols/headers:\n  {sig_str}\n"
            if current_len + len(entry) <= char_budget:
                context_blocks.append(entry)
                current_len += len(entry)
            else:
                remaining = char_budget - current_len
                if remaining > 100:
                    context_blocks.append(entry[:remaining] + "...\n")
                break

        context_str = "\n".join(context_blocks)
        return MemoryOutput(
            context_str=context_str,
            retrieved_files=retrieved_files,
            metadata={
                "condition": "B",
                "items_included": retrieved_files,
                "top_k": self.top_k,
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
        # Condition B does not carry anything between tasks
        pass
