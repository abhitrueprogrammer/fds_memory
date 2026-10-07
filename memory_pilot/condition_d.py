from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import re
from typing import Any

from tree_sitter import Language, Parser
import tree_sitter_python as tspython

from memory_pilot.condition_b import get_repo_python_files
from memory_pilot.interface import BaseMemory, MemoryOutput

PY_LANGUAGE = Language(tspython.language())


def compute_file_sha256(path: Path) -> str:
    """Compute sha256 hash of a file."""
    try:
        data = path.read_bytes()
        return hashlib.sha256(data).hexdigest()
    except Exception:
        return ""


@dataclass
class FileSymbols:
    rel_path: str
    sha256: str
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)


@dataclass
class EpisodicEntry:
    instance_id: str
    problem_statement: str
    files_retrieved: list[str]
    files_edited: list[str]
    harness_passed: bool
    file_hashes: dict[str, str] = field(default_factory=dict)
    weight: float = 1.0


class ConditionDMemory(BaseMemory):
    """Condition D: Structural + Episodic + Staleness.
    
    1. Structural Symbol & Call Graph: Tree-sitter parsed modules, classes,
       functions, and calls. Incremental: re-parses only files whose content hash changed.
    2. Episodic Log: Earlier task outcomes, weighted by harness test results.
    3. Staleness Tracking: Detects when earlier files have changed and marks
       outdated entries as STALE or down-weights them.
    """

    def __init__(self, token_budget: int = 1200, top_files_k: int = 4):
        super().__init__(name="D_structural_episodic_staleness", token_budget=token_budget)
        self.top_files_k = top_files_k
        self.parser = Parser(PY_LANGUAGE)
        # Structural cache: rel_path -> FileSymbols
        self.symbol_cache: dict[str, FileSymbols] = {}
        # Episodic log
        self.episodes: list[EpisodicEntry] = []

    def reset(self) -> None:
        self.symbol_cache = {}
        self.episodes = []

    def _parse_python_file(self, full_path: Path, rel_path: str) -> FileSymbols:
        """Parse Python file using tree-sitter, returning classes, functions, and calls."""
        try:
            content_bytes = full_path.read_bytes()
        except Exception:
            return FileSymbols(rel_path=rel_path, sha256="")

        sha256 = hashlib.sha256(content_bytes).hexdigest()
        tree = self.parser.parse(content_bytes)

        classes = []
        functions = []
        calls = set()

        def visit(node):
            if node.type == "class_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    classes.append(
                        content_bytes[name_node.start_byte : name_node.end_byte].decode("utf-8", "replace")
                    )
            elif node.type == "function_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    functions.append(
                        content_bytes[name_node.start_byte : name_node.end_byte].decode("utf-8", "replace")
                    )
            elif node.type == "call":
                func_node = node.child_by_field_name("function")
                if func_node:
                    call_name = content_bytes[func_node.start_byte : func_node.end_byte].decode("utf-8", "replace")
                    if len(call_name) < 40 and "\n" not in call_name:
                        calls.add(call_name)
            for child in node.children:
                visit(child)

        visit(tree.root_node)
        return FileSymbols(
            rel_path=rel_path,
            sha256=sha256,
            classes=classes,
            functions=functions,
            calls=sorted(calls)[:20],
        )

    def update_structural_index(self, repo_dir: Path) -> dict[str, int]:
        """Incrementally update AST symbols for repository files."""
        py_files = get_repo_python_files(repo_dir)
        reparsed = 0
        cached = 0

        for f in py_files:
            rel_path = str(f.relative_to(repo_dir))
            curr_sha = compute_file_sha256(f)

            if rel_path in self.symbol_cache and self.symbol_cache[rel_path].sha256 == curr_sha:
                cached += 1
                continue

            # File is new or changed: re-parse only this file
            symbols = self._parse_python_file(f, rel_path)
            self.symbol_cache[rel_path] = symbols
            reparsed += 1

        return {"reparsed": reparsed, "cached": cached, "total": len(py_files)}

    def check_staleness(self, episode: EpisodicEntry, repo_dir: Path) -> tuple[bool, list[str]]:
        """Check if any files from a past episode have changed in current repository."""
        changed_files = []
        for f, recorded_sha in episode.file_hashes.items():
            curr_path = repo_dir / f
            if not curr_path.exists():
                changed_files.append(f"{f} (deleted)")
            else:
                curr_sha = compute_file_sha256(curr_path)
                if curr_sha != recorded_sha:
                    changed_files.append(f"{f} (modified)")
        is_stale = len(changed_files) > 0
        return is_stale, changed_files

    def get_memory_context(
        self,
        task: dict[str, Any],
        repo_dir: Path,
    ) -> MemoryOutput:
        char_budget = self.token_budget * 4

        # 1. Update structural index incrementally
        stats = self.update_structural_index(repo_dir)

        query = task.get("problem_statement", "")
        raw_tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", query)
        stopwords = {
            "the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "by", "for", "to", "from",
            "with", "without", "and", "or", "not", "this", "that", "it", "as", "be", "if", "when", "into",
            "than", "then", "also", "about", "https", "http", "com", "org", "github", "issue", "description",
            "regression", "django", "render", "__init__", "__repr__", "save", "get", "clean", "delete"
        }
        symbols = [w for w in raw_tokens if len(w) >= 3 and w.lower() not in stopwords]
        symbols_lower = {s.lower() for s in symbols}

        # Score files based on symbol matches in classes/functions/calls/paths
        file_scores: dict[str, float] = {}
        for rel_path, sym in self.symbol_cache.items():
            score = 0.0
            unique_classes = set(sym.classes)
            unique_functions = set(sym.functions) - {"render", "__init__", "__repr__", "save", "get", "clean", "delete"}
            unique_calls = set(sym.calls)

            # Class matches (high confidence)
            for c in unique_classes:
                if c in symbols:
                    score += 150.0
                elif c.lower() in symbols_lower:
                    score += 30.0

            # Function matches (high confidence)
            for fn in unique_functions:
                if fn in symbols:
                    score += 150.0
                elif fn.lower() in symbols_lower:
                    score += 30.0

            # Outgoing calls
            for call in unique_calls:
                call_base = call.split(".")[-1]
                if call_base in symbols:
                    score += 20.0

            # Path matches (words in path)
            path_words = set(re.findall(r"[A-Za-z_]+", rel_path.lower()))
            for s in symbols_lower:
                if s in path_words:
                    score += 25.0

            if score > 0:
                file_scores[rel_path] = score

        # Top candidate files by structural symbol matching
        ranked_files = sorted(file_scores.items(), key=lambda x: x[1], reverse=True)[: self.top_files_k]
        retrieved_files = [rf[0] for rf in ranked_files]


        blocks = []
        blocks.append("[Structural Symbol & Call Graph]")
        blocks.append(f"Repository structural AST index: {stats['reparsed']} reparsed, {stats['cached']} cached.")
        blocks.append("Top relevant files and AST symbols:")

        for rel_path, score in ranked_files:
            sym = self.symbol_cache[rel_path]
            class_str = ", ".join(sym.classes[:5]) if sym.classes else "(none)"
            fn_str = ", ".join(sym.functions[:8]) if sym.functions else "(none)"
            call_str = ", ".join(sym.calls[:6]) if sym.calls else "(none)"
            blocks.append(
                f"- Module: {rel_path} (score: {score:.1f})\n"
                f"  Classes: {class_str}\n"
                f"  Functions: {fn_str}\n"
                f"  Calls: {call_str}"
            )

        # 2. Episodic Log & Staleness Verification
        blocks.append("\n[Episodic Memory & Staleness Check]")
        if not self.episodes:
            blocks.append("No prior episodic experience in memory.")
        else:
            for ep in self.episodes:
                is_stale, changed = self.check_staleness(ep, repo_dir)
                status = "PASSED" if ep.harness_passed else "FAILED"
                weight = ep.weight if not is_stale else ep.weight * 0.2

                if is_stale:
                    staleness_banner = f"⚠️ [STALE - Files changed since task: {', '.join(changed)}]"
                else:
                    staleness_banner = "✅ [FRESH - Verified against current repo state]"

                blocks.append(
                    f"- Episode {ep.instance_id} | Status: {status} (weight={weight:.2f}) | {staleness_banner}\n"
                    f"  Issue Summary: {ep.problem_statement[:120]}...\n"
                    f"  Files Edited: {ep.files_edited}\n"
                    f"  Files Retrieved: {ep.files_retrieved}"
                )

        full_context = "\n".join(blocks)
        if len(full_context) > char_budget:
            full_context = full_context[:char_budget] + "\n...[truncated to budget]"

        return MemoryOutput(
            context_str=full_context,
            retrieved_files=retrieved_files,
            metadata={
                "condition": "D",
                "items_included": retrieved_files,
                "reparsed_files": stats["reparsed"],
                "cached_files": stats["cached"],
                "episodes_count": len(self.episodes),
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
        """Update episodic memory after harness scoring with file hashes."""
        all_touched = set(files_edited) | set(files_retrieved)
        file_hashes = {}
        for f in all_touched:
            p = repo_dir / f
            if p.exists():
                file_hashes[f] = compute_file_sha256(p)

        # Weight: positive for passing patches (+1.0), negative for failures (-0.5)
        weight = 1.0 if harness_passed else -0.5

        entry = EpisodicEntry(
            instance_id=task.get("instance_id", "unknown"),
            problem_statement=task.get("problem_statement", "")[:400],
            files_retrieved=list(files_retrieved),
            files_edited=list(files_edited),
            harness_passed=harness_passed,
            file_hashes=file_hashes,
            weight=weight,
        )
        self.episodes.append(entry)
