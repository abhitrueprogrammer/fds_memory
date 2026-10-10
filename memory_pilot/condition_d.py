from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import re
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from tree_sitter import Language, Parser
import tree_sitter_python as tspython

from memory_pilot.condition_b import get_repo_python_files, build_file_text_index
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
    2. Hybrid Reciprocal Rank Fusion (RRF): Fuses lexical keyword matches with
       AST structural symbols for optimal file retrieval.
    3. Episodic Log: Earlier task outcomes, weighted by harness test results.
    4. Staleness Tracking: Detects when earlier files have changed and marks
       outdated entries as STALE or down-weights them.
    """

    def __init__(
        self,
        token_budget: int = 1200,
        top_files_k: int = 5,
        use_ast: bool = True,
        use_episodic: bool = True,
        use_staleness: bool = True,
        use_hybrid_rrf: bool = True,
    ):
        super().__init__(name="D_structural_episodic_staleness", token_budget=token_budget)
        self.top_files_k = top_files_k
        self.use_ast = use_ast
        self.use_episodic = use_episodic
        self.use_staleness = use_staleness
        self.use_hybrid_rrf = use_hybrid_rrf

        self.parser = Parser(PY_LANGUAGE)
        # Structural cache: rel_path -> FileSymbols
        self.symbol_cache: dict[str, FileSymbols] = {}
        # Lexical cache: (vectorizer, tfidf_mat, paths)
        self.lexical_cache: tuple[Any, Any, list[str]] | None = None
        # Episodic log
        self.episodes: list[EpisodicEntry] = []

    def reset(self) -> None:
        self.symbol_cache = {}
        self.lexical_cache = None
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
        """Incrementally update AST symbols for repository files.
        
        Performs an O(Total_Repo_Bytes) = O(M) disk read and SHA-256 computation
        across repository files to detect modifications, followed by O(1) in-memory
        cache hit lookups for unchanged files. Only files with modified hashes are reparsed.
        """
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

    def _get_lexical_ranking(self, query: str, repo_dir: Path) -> dict[str, int]:
        """Compute lexical TF-IDF ranking over repository python files."""
        if self.lexical_cache is None:
            py_files = get_repo_python_files(repo_dir)
            paths, docs = build_file_text_index(py_files, repo_dir)
            vectorizer = TfidfVectorizer(max_features=30000, stop_words="english", sublinear_tf=True)
            tfidf_mat = vectorizer.fit_transform(docs)
            self.lexical_cache = (vectorizer, tfidf_mat, paths)

        vectorizer, tfidf_mat, paths = self.lexical_cache
        q_vec = vectorizer.transform([query])
        sims = cosine_similarity(q_vec, tfidf_mat).flatten()
        lex_order = sims.argsort()[::-1][:50]
        return {paths[i]: rank for rank, i in enumerate(lex_order)}

    def _get_ast_ranking(self, query: str) -> dict[str, int]:
        """Compute structural AST symbol ranking with subtoken splitting."""
        raw_tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", query)
        stopwords = {
            "the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "by", "for", "to", "from",
            "with", "without", "and", "or", "not", "this", "that", "it", "as", "be", "if", "when", "into",
            "than", "then", "also", "about", "https", "http", "com", "org", "github", "issue", "description",
            "regression", "django", "render", "__init__", "__repr__", "save", "get", "clean", "delete"
        }
        symbols = [w for w in raw_tokens if len(w) >= 3 and w.lower() not in stopwords]
        symbols_lower = {s.lower() for s in symbols}

        # Subtoken splitting: CamelCase, snake_case (underscores act as delimiters), and uppercase acronyms
        q_subtokens = set()
        for s in symbols:
            parts = re.findall(r"[A-Z]+(?=[A-Z][a-z0-9]|\b)|[A-Z][a-z0-9]*|[a-z0-9]+", s)
            q_subtokens.update([p.lower() for p in parts if len(p) >= 3])

        ast_scores: dict[str, float] = {}
        for rel_path, sym in self.symbol_cache.items():
            score = 0.0
            unique_classes = set(sym.classes)
            unique_functions = set(sym.functions) - {"render", "__init__", "__repr__", "save", "get", "clean", "delete"}
            unique_calls = set(sym.calls)

            # Class matches & subtoken matches
            for c in unique_classes:
                if c in symbols:
                    score += 150.0
                elif c.lower() in symbols_lower:
                    score += 40.0
                else:
                    c_parts = [p.lower() for p in re.findall(r"[A-Z]+(?=[A-Z][a-z0-9]|\b)|[A-Z][a-z0-9]*|[a-z0-9]+", c) if len(p) >= 3]
                    matching_parts = q_subtokens.intersection(c_parts)
                    score += len(matching_parts) * 25.0

            # Function matches & subtoken matches
            for fn in unique_functions:
                if fn in symbols:
                    score += 150.0
                elif fn.lower() in symbols_lower:
                    score += 40.0
                else:
                    fn_parts = [p.lower() for p in re.findall(r"[a-z0-9]+", fn.lower()) if len(p) >= 3]
                    matching_parts = q_subtokens.intersection(fn_parts)
                    score += len(matching_parts) * 20.0

            # Outgoing calls
            for call in unique_calls:
                call_base = call.split(".")[-1]
                if call_base in symbols:
                    score += 20.0

            # Path matches
            path_words = set(re.findall(r"[A-Za-z0-9_]+", rel_path.lower()))
            common_path = path_words.intersection(symbols_lower)
            score += len(common_path) * 30.0

            if score > 0:
                ast_scores[rel_path] = score

        ranked = sorted(ast_scores.items(), key=lambda x: x[1], reverse=True)[:50]
        return {r[0]: rank for rank, r in enumerate(ranked)}

    def get_memory_context(
        self,
        task: dict[str, Any],
        repo_dir: Path,
    ) -> MemoryOutput:
        char_budget = self.token_budget * 4

        # 1. Update structural index incrementally
        stats = self.update_structural_index(repo_dir)
        query = task.get("problem_statement", "")

        # 2. Determine file ranks based on ablation configuration
        if self.use_hybrid_rrf and self.use_ast:
            lex_ranks = self._get_lexical_ranking(query, repo_dir)
            ast_ranks = self._get_ast_ranking(query)
            all_cands = set(list(lex_ranks.keys())[:25]) | set(list(ast_ranks.keys())[:25])
            fused_scores = {}
            for c in all_cands:
                r_lex = lex_ranks.get(c, 100)
                r_ast = ast_ranks.get(c, 100)
                fused_scores[c] = (1.0 / (60.0 + r_lex)) + (1.0 / (60.0 + r_ast))
            retrieved_files = [x[0] for x in sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)[: self.top_files_k]]
        elif self.use_ast:
            ast_ranks = self._get_ast_ranking(query)
            retrieved_files = list(ast_ranks.keys())[: self.top_files_k]
        else:  # Lexical only (Ablation without AST)
            lex_ranks = self._get_lexical_ranking(query, repo_dir)
            retrieved_files = list(lex_ranks.keys())[: self.top_files_k]

        blocks = []
        blocks.append("[Structural Symbol & Call Graph]")
        blocks.append(f"Repository structural AST index: {stats['reparsed']} reparsed, {stats['cached']} cached.")
        blocks.append("Top relevant files and AST symbols:")

        for rel_path in retrieved_files:
            sym = self.symbol_cache.get(rel_path)
            if sym:
                class_str = ", ".join(sym.classes[:5]) if sym.classes else "(none)"
                fn_str = ", ".join(sym.functions[:8]) if sym.functions else "(none)"
                call_str = ", ".join(sym.calls[:6]) if sym.calls else "(none)"
                blocks.append(
                    f"- Module: {rel_path}\n"
                    f"  Classes: {class_str}\n"
                    f"  Functions: {fn_str}\n"
                    f"  Calls: {call_str}"
                )
            else:
                blocks.append(f"- Module: {rel_path}")

        # 3. Episodic Log & Staleness Verification
        if self.use_episodic:
            blocks.append("\n[Episodic Memory & Staleness Check]")
            if not self.episodes:
                blocks.append("No prior episodic experience in memory.")
            else:
                for ep in self.episodes:
                    is_stale, changed = self.check_staleness(ep, repo_dir) if self.use_staleness else (False, [])
                    status = "PASSED" if ep.harness_passed else "FAILED"
                    weight = ep.weight if not (is_stale and self.use_staleness) else ep.weight * 0.2

                    if is_stale and self.use_staleness:
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
                "ablation_ast": self.use_ast,
                "ablation_episodic": self.use_episodic,
                "ablation_staleness": self.use_staleness,
                "ablation_hybrid_rrf": self.use_hybrid_rrf,
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
