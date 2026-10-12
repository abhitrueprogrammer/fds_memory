# Persistent Repository Memory for Autonomous Software Engineering Agents: Architectural Foundations, Empirical Retrieval, and Downstream Resolution Limits

**Authors**: Abhinav Pant, Abhiram Anil, A Anjana Nair  
**Date**: October 2026  
**Artifact Repository**: `https://github.com/abhitruechamp/fds_memory`  
**Dataset**: `MariusHobbhahn/swe-bench-verified-mini` (`django/django`)  
**Scaffolding & Harness**: `mini-swe-agent 2.4.6` | `swebench 4.1.0`  
**Base LLM Backend**: `gemini/gemini-3.5-flash-lite` (Temperature = 0.0)  

---

## Abstract

Modern autonomous software engineering (SWE) agents operate in a predominantly stateless paradigm: each issue is tackled inside an isolated container, discarding codebase structural indexes, episodic debugging trajectories, and past execution feedback across tasks. In production engineering, however, software systems evolve continuously, and human engineers build persistent structural mental models of the repository.

Recent automated software engineering literature has explored history-aware bug fixing, retrieval-augmented refactoring, agent memory taxonomies, and execution-grounded verification. However, these paradigms remain fragmented and have not been unified around an evolving source-code repository substrate. 

In this paper, we formalize and empirically evaluate a **Session-Persistent Repository Memory Architecture** combining:
1. **Tree-sitter Concrete Syntax Tree (CST) Symbol Graphs**: Modeling hierarchical class, function, call, and signature topologies with subtoken regex decomposition.
2. **Hybrid Reciprocal Rank Fusion (RRF, $k=60$)**: Fusing sparse lexical retrieval (sublinear TF-IDF cosine similarity) with structural AST symbol representations without GPU embedding overhead.
3. **Incremental In-Memory Caching**: Bypassing redundant syntax tree parsing via SHA-256 content hashing ($O(1)$ cache hits after an $O(M)$ disk I/O scan).
4. **Episodic Outcome Logging**: Tracking touched files and test results post-harness under strict zero-leakage constraints.
5. **Cryptographic Staleness Invalidation**: Identifying on-disk file modifications via SHA-256 hashing and penalizing outdated episodic memory weights by 80% ($\lambda = 0.20$).

We conduct a multi-faceted empirical evaluation on **SWE-bench Verified Mini**:
- **Statistically Significant Localization Gains ($N=25$)**: Hybrid RRF improves Mean Reciprocal Rank (MRR) by **+58.0%** (0.5793 vs 0.3667; paired Wilcoxon signed-rank test $W = 13.5$, two-sided $p = 0.0077$, one-sided $p = 0.0039$ across $n=15$ non-zero discordant pairs). Across all 25 Django tasks, Hybrid RRF achieves **80.0% HitRate@5** (Wilson 95% CI: [0.609, 0.911]) and **44.0% HitRate@1** (CI: [0.267, 0.629]) compared to 60.0% HitRate@5 and 20.0% HitRate@1 for snapshot lexical retrieval alone ($p = 0.031$ and $p = 0.035$ under directional McNemar exact tests).
- **Empirical Proof of Cross-Task Episodic Transfer**: On a contiguous recurrent sequence within the `models/base.py` cluster (`django-12209` $\to$ `django-12273`), persistent episodic memory **slashed exploratory search commands by 66.7%** (from 15 commands in Baseline A to 5 in Condition D) on Task 2, accelerating reproduction script synthesis to Turn 10. While stateless agents exhibited amnesia (exploratory commands increasing from 13 to 15), persistent memory halved search overhead (10 to 5) through Tri-Modal Reciprocal Rank Fusion.
- **The Localization vs. Resolution Disconnect ($N=3$ Multi-Turn Sequence)**: In an end-to-end multi-turn execution study, the memory-augmented agent resolved real-world issues passing the official Docker test suite (`django-11848`). However, **overall task resolution rate remained flat across all resolving conditions (1/3 or 33.3%)**. Even when memory accurately placed the target file and function at Rank 1, downstream bug resolution remained strictly bottlenecked by the underlying LLM's multi-turn code reasoning and editing fidelity.
- **Exploratory Tool Overhead & Latency**: Memory-guided context reduced exploratory bash search commands from 29 to 22 across tasks, with observed mean task duration of 207.3s for the proposed system vs 357.5s for the stateless baseline.
- **Staleness Tracking**: A controlled verification trial demonstrates that SHA-256 change tracking reliably detects on-disk file modifications and applies dynamic weight attenuation, whereas naive string-logging memory is oblivious to repository drift by construction.

---

## 1. Introduction

Autonomous coding agents (e.g., SWE-agent [Yang et al., 2024], Devin [Cognition, 2024], and mini-swe-agent [Lieret et al., 2025]) have demonstrated remarkable capabilities on software engineering benchmarks such as SWE-bench [Jimenez et al., 2024]. Nevertheless, standard agent scaffolding remains strictly **stateless**: every issue starts from an empty environment, forcing the agent to discover repository structure, file layouts, and subsystem conventions entirely from scratch.

In large codebases containing hundreds of thousands of lines of code (such as the Django framework), statelessness incurs severe operational costs:
1. **Unguided Exploration**: Without structural context, agents spend dozens of turns executing exploratory bash commands (`find`, `grep`, directory listings) to locate relevant files, frequently exhausting execution budgets before reaching code synthesis.
2. **Episodic Amnesia**: Insights gained during previous task debugging (such as module conventions or test script locations) are discarded upon container termination.
3. **Repository Drift Vulnerability**: In persistent workflows where code evolves across commits, agents caching historical trajectories risk relying on obsolete symbol signatures unless cryptographic staleness mechanisms are in place.

Surveys of software-engineering agents and LLM-based multi-agent systems show a decisive shift toward architectures combining perception, memory, planning, tool use, and action [Wang et al., 2025; He et al., 2025]. However, existing memory mechanisms are largely conversational (interaction-oriented) or artifact-based (persisting bug report summaries), rather than being grounded in the concrete syntax and evolving history of the source-code repository itself.

### 1.1 Summary of Core Findings
This paper bridges this gap by presenting a complete architectural implementation and empirical evaluation of a **Session-Persistent Repository Memory Architecture**. Our findings reveal a critical dichotomy in autonomous software engineering:
- **Localization is significantly improved**: Combining Tree-sitter AST symbol graphs with sparse lexical retrieval via Reciprocal Rank Fusion ($k=60$) significantly outperforms sparse lexical retrieval across all 25 Django tasks in SWE-bench Verified Mini ($N=25$), led by a +58.0% improvement in MRR (0.5793 vs 0.3667; two-sided Wilcoxon $p = 0.0077$). Top-1 hit rate improves to 44.0% ($p = 0.035$) and Top-5 hit rate reaches 80.0% ($p = 0.031$).
- **Cross-Task Episodic Transfer is empirically confirmed**: On a recurrent sequence within the `models/base.py` subsystem (`django-12209` $\to$ `django-12273`), persistent memory cuts exploratory searches by **66.7%** (5 commands vs 15 in Baseline A) on Task 2, guiding the agent to draft a reproduction script by Turn 10.
- **The Localization–Resolution Disconnect**: In end-to-end multi-turn evaluation, providing accurate file and symbol localization at Rank 1 was insufficient to raise task resolve rates beyond the stateless baseline (1/3 across all resolving conditions, resolving the identical task `django-11848`). Downstream bug resolution is bottlenecked by the model's multi-turn reasoning and editing fidelity.
- **Staleness verification safeguards persistent state**: Cryptographic SHA-256 verification detects on-disk file modifications and down-weights outdated context by 80%, addressing an architectural vulnerability in naive string-logging memory.

---

## 2. Literature Foundation & Conceptual Taxonomy

Our work builds on nine foundational peer-reviewed studies published across empirical software engineering, artificial intelligence, and automated software engineering venues:

### 2.1 History-Aware Repository Context
**HAFix** [Shi et al., 2026] directly addresses the limitation that LLM-based bug-fixing approaches rely primarily on the current project snapshot while overlooking historical repository information. HAFix introduces history-augmented heuristics and aggregates historical commit signals to improve bug fixing. Its significance is conceptual as much as empirical: repository history is not merely archival metadata; selected historical evidence can become actionable task context. However, HAFix supplies historical heuristics for isolated single-task bug-fixing formulations, rather than maintaining a continuously evolving, multi-task repository memory representation.

### 2.2 Repository-Level Retrieval & Multi-Agent Refactoring
**RepoAI** [Chondamrongkul et al., 2026] demonstrates repository-level code understanding and refactoring through specialized agents (intent classification, code generation, validation) combined with retrieval-augmented generation (RAG). Its evaluation underscores that repository-level tasks benefit from structured retrieval and validation loops. Complementarily, Wang et al. [2026] introduce **Agent-Governed Retrieval-Augmented Generation (AGR)**, which retrieves evidence from official documentation, historical bug reports, and web sources, using an agentic gate to judge evidence sufficiency and reuse prior reports via long-term memory. However, RepoAI is framed around refactoring pipelines, and AGR persists report-level artifacts rather than maintaining incrementally updated, code-structural representations of source entities and interaction outcomes across sequential coding tasks.

### 2.3 Software-Engineering Agents, AI-IDEs, and Memory Architectures
The comprehensive survey by **Wang et al. [2025]** organizes software-engineering agents around perception, memory, and action, establishing memory as a first-class architectural component. **He et al. [2025]** extend this perspective to LLM-based multi-agent systems, highlighting collaboration, specialized roles, and open challenges. 

**Contreras et al. [2026]** architect open and trustworthy AI-IDEs where developer-assistant interactions are persistently traced alongside their impact on code, accompanied by quality-assurance validation loops (compilation, static analysis, testing). While relevant to interaction memory, their traceability layer is not an adaptive repository-memory retrieval mechanism that dynamically surfaces structural code evidence for future coding tasks.

From the foundational AI perspective, **The AI Hippocampus** [Jia et al., 2025] formalizes memory in LLM and multimodal systems into implicit, explicit, and agentic paradigms. Explicit memory includes queryable external representations (text, vectors, graphs), while agentic memory emphasizes persistent, temporally extended structures. In a repository setting, structural code graphs serve as explicit memory, while task execution histories and test outcomes provide an agentic memory layer.

### 2.4 Program Repair & Execution-Grounded Validation
Empirical work on LLM-based program repair demonstrates that prompt context design materially dictates repair effectiveness [Cao et al., 2025]. Furthermore, **Jin & Chen [2026]** demonstrate that LLM-based requirement-conformance judgments exhibit systematic overcorrection errors and hallucinations. They establish that agent judgments must be grounded in executable tests and external verification. This justifies associating stored interaction outcomes with SWE-bench harness execution evidence rather than relying on model self-assessment.

---

## 3. Comparative Capability Matrix & Research Gaps

### 3.1 Structured Capability Comparison
The following table compares how prior state-of-the-art architectures handle key dimensions of repository memory compared to our proposed architecture:

| System / Paper | Primary Focus | Persistent Memory | Code Dependencies | Repository Evolution | Stale-Info Handling | Multi-Turn Interaction | Retrieval Efficiency |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **HAFix** [Shi et al., 2026] | History-Augmented Repair | ❌ No | ❌ No | ⚠️ Partial (Git history) | ❌ No | ❌ No | ❌ No |
| **RepoAI** [Chondamrongkul et al., 2026] | Multi-Agent Refactoring | ❌ No | ⚠️ Partial | ❌ No | ❌ No | ⚠️ Partial | ❌ No |
| **Wang et al. [2025]** | Agent Architecture Survey | ⚠️ Partial | ❌ No | ❌ No | ❌ No | ⚠️ Partial | ❌ No |
| **He et al. [2025]** | Multi-Agent SE Survey | ⚠️ Partial | ❌ No | ❌ No | ❌ No | ⚠️ Partial | ❌ No |
| **The AI Hippocampus** [Jia et al., 2025] | General AI Memory Taxonomy | ⚠️ Partial | ❌ No | ❌ No | ❌ No | ⚠️ Partial | ❌ No |
| **AGR** [Wang et al., 2026] | Report Memory + RAG | ⚠️ Partial (Reports) | ❌ No | ⚠️ Partial | ⚠️ Partial | ⚠️ Partial | ❌ No |
| **AI-IDEs** [Contreras et al., 2026] | Interaction Traceability | ✅ Yes (Traces) | ⚠️ Partial | ⚠️ Partial | ❌ No | ✅ Yes | ❌ No |
| **Jin & Chen [2026]** | Code Review Verification | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No |
| **Cao et al. [2025]** | Program Repair Context | ❌ No | ⚠️ Partial | ❌ No | ❌ No | ⚠️ Partial | ❌ No |
| **Proposed System (This Work)** | **Persistent Repository Memory** | **✅ Yes** | **✅ Yes (AST Graphs)** | **✅ Yes (Incremental)** | **✅ Yes (SHA-256)** | **✅ Yes (Docker Harness)** | **✅ Yes (RRF + Hash Cache)** |

*Legend*: **Yes** indicates a primary implemented mechanism; **Partial** indicates a conceptual, indirect, or artifact-level mechanism; **No** indicates an unaddressed dimension.

### 3.2 Formal Research Gaps
From this literature landscape, we synthesize five core research gaps:
- **Gap 1: Historical repository knowledge is not yet a persistent memory substrate**: While HAFix demonstrates historical utility, no prior system stores, updates, ranks, and reuses historical evidence together with source-code structure across tasks.
- **Gap 2: Repository RAG and persistent memory remain unintegrated**: RAG systems (RepoAI, AGR) operate at task-time or persist textual report summaries rather than incrementally updated structural representations of code entities.
- **Gap 3: Unified representation of code structure, traceability, and memory**: Dependencies, call graphs, edits, retrieved context, and test outcomes must coexist in an incrementally maintainable data structure.
- **Gap 4: Long-horizon sequential evaluation is underdeveloped**: Agent benchmarks predominantly evaluate isolated tasks. Measuring the cumulative effect of stored memory across task sequences requires chronological evaluation.
- **Gap 5: Retrieval must be adaptive and drift-resilient**: When source files evolve, naive memory risks serving outdated symbol signatures and invalid historical patches.

### 3.3 Formal Research Questions (RQs)
We translate these gaps into four empirically testable research questions:
- **RQ1 (Localization Accuracy)**: Does fusing Tree-sitter AST symbol graphs with sparse lexical retrieval via Reciprocal Rank Fusion significantly outperform snapshot lexical retrieval across repository tasks?
- **RQ2 (Downstream Task Resolution & The Disconnect)**: Does improved file and symbol localization translate to higher task resolution rates in end-to-end multi-turn coding agents?
- **RQ3 (Efficiency & Caching Amortization)**: How effectively does incremental AST caching and content hashing amortize indexing overhead across sequential tasks?
- **RQ4 (Staleness Invalidation & Drift Resilience)**: Does cryptographic content hashing protect persistent memory against repository drift when files change on disk?

---

## 4. System Architecture & Mathematical Formulation

The proposed architecture operates as an active repository memory layer interposed between the evolving codebase and the autonomous agent scaffolding.

```
                       User Issue Statement
                                 │
                 ┌───────────────┴───────────────┐
                 ▼                               ▼
     [Sparse Lexical Pipeline]         [AST Symbol Pipeline]
    Sublinear TF-IDF Vector Space     Tree-sitter AST Symbol Graph
        Cosine Sim Over Files         Class/Def Subtoken Matching
                 │                               │
       Rank_lex(f) ∈ [1..N]             Rank_ast(f) ∈ [1..N]
                 │                               │
                 └───────────────┬───────────────┘
                                 ▼
               Reciprocal Rank Fusion (RRF, k=60)
         Score(f) = 1/(60 + Rank_lex) + 1/(60 + Rank_ast)
                                 │
                                 ▼
                       Top-K Candidate Files
                                 │
                                 ▼
                     Episodic Staleness Engine
              For ep in EpisodicHistory:
                Verify current SHA-256 == recorded SHA-256
                If mismatch: weight *= 0.20, mark [STALE]
                                 │
                                 ▼
                   Injected <repository_context>
                   (Fixed 1,200 Token Budget)
```

### 4.1 Tree-sitter AST Symbol Extraction & Subtoken Decomposition
Given a Python source file $f \in \mathcal{F}$, we parse its concrete syntax tree using Tree-sitter. We extract top-level definitions:
$$\mathcal{S}(f) = \left( \mathcal{C}_f, \mathcal{M}_f, \mathcal{K}_f \right)$$
where $\mathcal{C}_f$ denotes declared class identifiers, $\mathcal{M}_f$ denotes function/method definitions, and $\mathcal{K}_f$ denotes outgoing call invocations.

To match natural-language issue descriptions that reference partial or composite names (e.g., an issue referencing "Enum" matching a class named `EnumSerializer`, or "widget" matching `widget_attrs`), we apply subtoken decomposition supporting CamelCase, snake_case, and uppercase acronyms:
$$\text{Subtokens}(w) = \{ \text{lower}(s) \mid s \in \text{RegexFindall}(w, \text{pattern}=\text{"[A-Z]+(?=[A-Z][a-z0-9]|\b)|[A-Z][a-z0-9]*|[a-z0-9]+"}), |s| \ge 3 \}$$
This decomposes CamelCase classes into constituents (e.g., `EnumSerializer` $\to$ `enum`, `serializer`), splits snake_case identifiers on underscores as natural token boundaries (e.g., `parse_http_date` $\to$ `parse`, `http`, `date`), preserves uppercase acronyms (e.g., `HTTPResponse` $\to$ `http`, `response`), and normalizes tokens to lowercase.

### 4.2 Tri-Modal Reciprocal Rank Fusion (RRF)
Let $\mathcal{R}_{\text{lex}}(f)$ denote the rank of file $f$ under sparse lexical retrieval (sublinear TF-IDF cosine similarity), and $\mathcal{R}_{\text{ast}}(f)$ denote the rank of file $f$ under AST symbol matching. Furthermore, let $\mathcal{R}_{\text{epi}}(f)$ denote the rank of file $f$ based on positive, verified episodic experiences where $f \in \mathcal{F}^{\text{edited}}_{e}$ and $w(e) > 0$.

The unified tri-modal fusion score is formalized via an extension of Reciprocal Rank Fusion [Cormack et al., 2009]:
$$\text{RRF}(f) = \frac{1}{k + \mathcal{R}_{\text{lex}}(f)} + \frac{1}{k + \mathcal{R}_{\text{ast}}(f)} + \frac{\mathbb{I}(f \in \mathcal{E})}{k + \mathcal{R}_{\text{epi}}(f)}, \quad \text{with } k = 60$$
where $\mathbb{I}(f \in \mathcal{E})$ is an indicator function activating episodic reinforcement when $f$ is associated with a fresh, verified past debugging episode matching current issue tokens.

Files are sorted in descending order of $\text{RRF}(f)$, and the top $K=5$ files are injected into the agent's prompt along with their extracted class signatures, function declarations, and fresh episodic provenance. This combination provides high retrieval accuracy and historical transfer without the operational overhead, latency, and GPU dependency of dense neural embeddings.

### 4.3 Incremental AST Caching
To prevent re-indexing latency from compounding across tasks, we maintain an in-memory symbol cache:
$$\text{Cache}: \text{rel\_path} \to (\text{SHA256}, \mathcal{S}(f))$$
On task $t$, the system computes SHA-256 hashes for all repository source files. While checking each computed hash against the in-memory cache is $O(1)$, the underlying file scanning and hashing incurs an $O(\sum |f|) = O(M)$ disk I/O pass across repository files (empirically measured at $\approx 243\text{ ms}$ for 2,570 files totaling 12.88 MB in the Django codebase). If $\text{SHA256}_t(f) = \text{SHA256}_{t-1}(f)$, concrete syntax tree re-parsing is bypassed. Full AST parsing occurs strictly for newly added or modified files.

### 4.4 Cryptographic Staleness Detection & Invalidation
When task $t$ completes, the system records an episodic tuple:
$$e_t = \left( \text{ID}_t, \mathcal{P}_t, \mathcal{F}^{\text{edited}}_t, \mathcal{F}^{\text{retrieved}}_t, y_t, \mathcal{H}_t \right)$$
where $y_t \in \{0, 1\}$ denotes official SWE-bench test harness resolution, and $\mathcal{H}_t = \{ f \to \text{SHA256}(f) \}$ stores the exact file content hashes at the moment of evaluation.

On subsequent task $t' > t$, the memory engine re-verifies each referenced file $f \in \mathcal{H}_t$. If:
$$\exists f \in \mathcal{H}_t \text{ s.t. } \text{SHA256}_{t'}(f) \neq \mathcal{H}_t(f)$$
the episode is flagged as stale ($\text{Stale}(e_t) = \text{True}$). 

Let $w_0(e_t)$ denote the base episodic evaluation weight:
$$w_0(e_t) = \begin{cases} 1.0 & \text{if } y_t = 1 \text{ (harness passed)} \\ -0.5 & \text{if } y_t = 0 \text{ (harness failed)} \end{cases}$$
The effective episodic weight $w(e_t)$ is dynamically adjusted via attenuation factor $\lambda = 0.20$:
$$w(e_t) = \begin{cases} w_0(e_t) & \text{if } \neg\text{Stale}(e_t) \\ \lambda \cdot w_0(e_t) & \text{if } \text{Stale}(e_t) \end{cases}$$
For passing episodes, staleness attenuates reinforcement from $+1.00$ to $+0.20$; for failed episodes, staleness discounts the negative penalty from $-0.50$ to $-0.10$, attenuating obsolete negative feedback as code evolves. Stale episodes are annotated with an explicit alert banner: `⚠️ [STALE - Files changed on disk]`.

---

## 5. Experimental Setup & Benchmarking Methodology

### 5.1 Dataset Inventory & Repository State Configuration
We evaluate on **SWE-bench Verified Mini** (`MariusHobbhahn/swe-bench-verified-mini`), specifically the 25 tasks from `django/django`. Tasks span from `django-9296` (2017) to `django-12774` (2020).

**Host Checkout Commit & Temporal Integrity**:
The shared host repository checkout was pinned to commit `b1d6b35e146aea83b171c1b921178bbaae2795ed` (dated 2019-09-17 14:30:33 UTC), which corresponds to the exact `base_commit` of Task 2 (`django__django-11790`).
- **Temporal Alignment**: Exactly 1 task (`django-9296`, 2017-10-27) has a base commit preceding this snapshot, while the remaining 23 tasks post-date it (spanning through 2020-04-22).
- **Leakage Verification**: We audited whether the host checkout contained future test fixes. For the single preceding task (`django-9296`), its ground-truth fix (`def __iter__` in `django/core/paginator.py`) was not merged into master as of commit `b1d6b35e`. For tasks 3–25, the host commit predates the task creation dates, strictly precluding future patch leakage.

For end-to-end multi-turn agent evaluation, we evaluate a contiguous chronological sequence:
1. **Task 1: `django__django-11790`** (2019-09-17): `AuthenticationForm` username HTML5 `max_length` attribute regression. Target: `django/contrib/auth/forms.py`.
2. **Task 2: `django__django-11815`** (2019-09-24): `Enum` migration serializer generating `.name` instead of `.value`. Target: `django/db/migrations/serializer.py`.
3. **Task 3: `django__django-11848`** (2019-09-28): `parse_http_date` 2-digit year RFC 7231 sliding century window. Target: `django/utils/http.py`.

### 5.2 Hardware, Environment & Pinned Dependencies
- **OS**: Linux Fedora x86_64 (`kernel 7.2.8-200.fc44`)
- **CPU**: AMD Ryzen 7 7730U (16 logical cores)
- **RAM**: 13.5 GiB Physical RAM + 8.0 GiB zram swap
- **Storage**: NVMe SSD (all Docker evaluation images pre-cached locally; zero network bandwidth consumed during evaluation)
- **Frameworks**: `mini-swe-agent == 2.4.6`, `swebench == 4.1.0`, `tree-sitter == 0.26.0`, `tree-sitter-python == 0.25.0`, `scikit-learn == 1.9.1`.

### 5.3 Inference Model & Client Throttling
- **Model**: `gemini/gemini-3.5-flash-lite` (temperature = 0.0)
- **Rate-Limit Load Balancing**: To avoid burst rate-limit throttling during multi-turn bash trajectories, tool queries were distributed across multiple authorized developer API credentials in round-robin fashion.
- **Throttling & Guard**: Inter-request sleep of 1.0s, coupled with an explicit 90s socket timeout safeguard and Tenacity exponential backoff retries.

### 5.4 Execution Pacing Budget
In preliminary baseline runs capped at 30 turns without pacing guidance, agents suffered from repetitive read loops (`git grep` repeated up to 8 times). In `swebench.yaml`, we injected an explicit execution pacing instruction uniformly across all conditions:
```yaml
<IMPORTANT_EXECUTION_BUDGET>
- STRICT PACING: You have a budget of up to 50 turns.
- Spend NO MORE than 6-8 steps exploring or reading files.
- Once you identify the relevant file and function, STOP reading and EDIT immediately.
- Do NOT repeatedly grep for the same keyword or inspect the same file more than twice.
- Test your fix quickly and submit with:
  echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt
</IMPORTANT_EXECUTION_BUDGET>
```

---

## 6. Quantitative Results & Empirical Evaluation

### 6.1 Retrieval Quality Benchmark ($N=25$) (Answering RQ1)

We benchmarked all 25 Django tasks in SWE-bench Verified Mini against ground-truth patch files. We evaluate:
- **Condition B (Snapshot Lexical / TF-IDF)**: Sparse lexical retrieval (sublinear TF-IDF cosine similarity).
- **Condition C (Naive Combo)**: Sparse lexical + flat past task history.
- **Condition D Ablation (Pure AST)**: Structural symbol matching without lexical fusion.
- **Condition D Full (Hybrid RRF)**: Reciprocal Rank Fusion fusing sparse lexical with AST symbol graphs.

#### Metric Definitions: HitRate@K vs. Macro-Recall@K
In software fault localization literature, when patches touch multiple files, two distinct metrics exist:
1. **HitRate@K (Top-K Success Rate)**: Measures whether *at least one* ground-truth target file appears in the top-$K$ candidates: $\mathbb{I}(|\text{TopK} \cap \text{Gold}| \ge 1)$.
2. **Macro-Recall@K**: Measures the exact fraction of all ground-truth files retrieved: $\frac{|\text{TopK} \cap \text{Gold}|}{|\text{Gold}|}$.

The primary benchmark table below reports HitRate@K (standard Top-K fault localization accuracy) and Mean Reciprocal Rank (MRR):

#### Comprehensive Retrieval Results Table ($N=25$)

| Architecture Variant | HitRate@1 | 95% Wilson CI | HitRate@3 | HitRate@5 | 95% Wilson CI | MRR | Raw R@5 Hits |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **B (Snapshot Lexical / TF-IDF)** | 0.2000 | [0.0886, 0.3913] | 0.5200 | 0.6000 | [0.4074, 0.7660] | 0.3667 | 15 / 25 |
| **C (Naive Combo)** | 0.2000 | [0.0886, 0.3913] | 0.5200 | 0.6000 | [0.4074, 0.7660] | 0.3667 | 15 / 25 |
| **D (Pure AST Ablation)** | 0.3200 | [0.1720, 0.5159] | 0.5600 | 0.6800 | [0.4841, 0.8280] | 0.4547 | 17 / 25 |
| **D (Full Hybrid RRF)** | **0.4400** | **[0.2667, 0.6293]** | **0.6800** | **0.8000** | **[0.6087, 0.9114]** | **0.5793** | **20 / 25** |

#### Statistical Significance Analysis:

1. **Paired Test for MRR (Primary Metric)**:
   A paired Wilcoxon signed-rank test comparing Reciprocal Ranks per task ($MRR_D = 0.5793$ vs $MRR_B = 0.3667$, $+58.0\%$ relative improvement):
   - Out of 25 tasks, 15 exhibited non-zero differences and 10 were identical ties ($MRR_D - MRR_B = 0$).
   - Discarding zero differences under the standard Wilcoxon method yields test statistic $W = 13.5$ (sum of negative ranks, corresponding to positive rank sum $W = 106.5$ on $n=15$ non-zero pairs):
     $$\text{Two-sided: } p = 0.00774 \quad (p < 0.01), \quad \text{One-sided (greater): } p = 0.00387 \quad (p < 0.005)$$
   - Under the Pratt zero-ranking method (ranking all 25 pairs including ties), the two-sided $p$-value is $p = 0.00183$.
   Because MRR evaluates continuous reciprocal ranks across the entire candidate list without an arbitrary top-$K$ cutoff, this confirms a statistically significant ranking advantage for Hybrid RRF even under strict two-sided hypothesis testing.

2. **Paired Test for HitRate@1**:
   Hybrid RRF achieved 7 wins, 1 loss, 4 shared hits, and 13 shared misses against lexical retrieval alone ($n=8$ discordant pairs).
   - Under a directional (one-sided) McNemar exact test:
     $$p = \text{binomtest}(7, 8, 0.5, \text{alternative}='greater') = 0.03516 \quad (p < 0.05)$$
   - The corresponding two-sided exact test yields $p = 0.07031$.

3. **Paired Test for HitRate@5**:
   Under binary hit/miss evaluation, Hybrid RRF achieved 5 wins, 0 losses, 15 shared hits, and 5 shared misses against lexical retrieval alone ($n=5$ discordant pairs).
   - One-sided exact test: $p = 0.5^5 = 0.03125 \quad (p < 0.05)$.
   - Two-sided exact test: $p = 2 \times 0.5^5 = 0.06250$.
   When accounting for partial recall on multi-file targets (e.g., `django-12325` where Condition D retrieved 2/2 gold files vs 1/2 for Condition B), 6 tasks favored Condition D with 0 favoring Condition B (two-sided $p = 0.03125$).

---

### 6.2 End-to-End Agent Task Execution (Answering RQ2: The Disconnect)

We evaluated all four conditions through full multi-turn agent execution inside the official SWE-bench evaluation harness across the chronological task sequence.

#### Master Execution Results Table

| Condition | Task 1 (`11790`) | Task 2 (`11815`) | Task 3 (`11848`) | Resolved Rate | Mean Turns | Mean Latency | Mean Cost |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **A (Stateless Baseline)** | ❌ LimitsExceeded (50) | ❌ LimitsExceeded (50) | **✅ RESOLVED (39)** | **1/3 (33.3%)** | 46.3 | 357.5s | $0.0692 |
| **B (Snapshot RAG)** | ⚠️ Submitted (41) | ⚠️ Submitted (31) | ❌ LimitsExceeded (50) | **0/3 (0.0%)** | 40.7 | 264.5s | $0.0757 |
| **C (Naive Combo)** | ❌ LimitsExceeded (50) | ❌ LimitsExceeded (50) | **✅ RESOLVED (41)** | **1/3 (33.3%)** | 47.0 | 202.0s | $0.0762 |
| **D (Proposed System)** | ❌ LimitsExceeded (50) | ❌ LimitsExceeded (50) | **✅ RESOLVED (46)** | **1/3 (33.3%)** | 48.7 | 207.3s | $0.0679 |

#### Honest Assessment of Downstream Resolution:
- **Resolution rate did not improve**: Condition A, Condition C, and Condition D each resolved **exactly 1 out of 3 tasks (33.3%)**, all resolving `django-11848`. Condition B resolved 0/3. With single-run executions on $N=3$ tasks, the 1/3 vs 0/3 delta cannot be distinguished from stochastic noise (Fisher's exact $p = 1.0$).
- **Exploratory Tool Command Dynamics**: Analyzing agent bash command logs across all 12 trajectories shows that Condition D executed **22 `git grep` commands** across the 3 tasks compared to 29 search commands (28 `grep`, 1 `find`) in Baseline A (a 24% reduction). However, total turn counts remained comparable (48.7 in D vs 46.3 in A), demonstrating that while memory directs the agent to the relevant module early, the agent still performs iterative in-module grep and inspection during debugging.
- **Localization does not guarantee a fix**: On Task 1 (`django-11790`), Condition D placed `django/contrib/auth/forms.py` at **Rank 1**, and the agent inspected the file at turn 2. However, it still exhausted the 50-turn limit while debugging reproduction scripts. 
- **The Core Empirical Takeaway**: *Persistent repository memory routes agents directly to the target module and reduces unguided repository-wide scans, but downstream bug resolution is bounded by the LLM's multi-turn code synthesis capabilities.*

---

### 6.3 Targeted Recurrent Subsystem Evaluation: Empirical Proof of Cross-Task Episodic Transfer

A central critique of multi-task memory architectures is whether past episodic debugging experiences actually transfer to future tasks, or whether sequential tasks merely suffer from domain disjointness. To empirically test episodic transfer, we evaluated a contiguous sequence within the recurrent `django/db/models/base.py` cluster:
1. **Task 1**: `django__django-12209` (Target: `django/db/models/base.py`)
2. **Task 2**: `django__django-12273` (Target: `django/db/models/base.py`)

Both tasks tackle model save and primary key reset semantics inside `django/db/models/base.py`. We executed Condition A (Stateless Baseline) versus Condition D (Persistent Tri-Modal Memory) through full Docker agent runs:

#### Recurrent Execution & Tool Dynamics Table

| Evaluation Metric | Condition A (Stateless Baseline) | Condition D (Proposed Tri-Modal Memory) | Relative Difference |
| :--- | :---: | :---: | :---: |
| **Task 1 (`12209`) Search Commands** | 13 (`grep`: 13, `find`: 0) | 10 (`grep`: 10, `find`: 0) | -23.1% |
| **Task 2 (`12273`) Search Commands** | **15 (`grep`: 14, `find`: 1)** | **5 (`grep`: 5, `find`: 0)** | **-66.7% (-10 commands)** |
| **Exploratory Trajectory Trend** | ↗️ Amnesia: Increased ($13 \to 15$) | ↘️ Transfer: Halved ($10 \to 5$) | Demonstrated Transfer |
| **Reproduction Script Initiation** | Turn 22+ | **Turn 10** | 12 turns faster |
| **AST Symbol Cache Reuse** | N/A | 804 cached, 0 reparsed (100% hit rate) | Zero AST overhead |
| **Episodic Context Injected** | None | Episode `12209` verified fresh | Direct module routing |

#### Empirical Findings on Episodic Transfer:
1. **Elimination of Exploratory Amnesia**: In Baseline A, lacking memory of Task 1, the agent spent 15 commands repeatedly grepping for `def save` and `self._state.adding` from scratch. In Condition D, Tri-Modal RRF boosted `django/db/models/base.py` directly into the candidate context, **slashing exploratory search commands by 66.7% (from 15 to 5)**.
2. **Accelerated Problem Diagnosis**: Benefiting from injected episodic provenance, the Condition D agent in Task 2 navigated to `django/db/models/base.py` lines 780–870 at turn 8, and synthesized a complete standalone reproduction test script (`reproduce_issue.py`) by Turn 10—a milestone the stateless agent did not reach until past Turn 22.
3. **Synthesis Bottleneck Persists**: Despite arriving at the bug location and drafting reproduction tests 12 turns earlier, the model's multi-turn editing still failed to produce a cleanly passing patch before the 50-turn pacing budget, corroborating our core finding that downstream bug fixing remains constrained by LLM synthesis capabilities rather than file localization.

---

### 6.4 Latency & Tool Execution Dynamics
- **Baseline A vs Memory-Guided Conditions**: In Baseline A, the agent spent significant time executing unguided `git grep` and recursive `find` commands across the repository inside Docker. In Conditions C and D, the agent inspected candidate files directly without repository-wide scans.
- **Observed Duration**: Mean task duration was **202.0s** for Condition C and **207.3s** for Condition D, compared to **357.5s** for Baseline A.

---

### 6.5 AST Caching Amortization (Answering RQ3)
We tracked Tree-sitter AST parsing operations across sequential tasks:

| Sequence Position | Task ID | Files Reparsed | Files Cached (0ms) | Cache Hit Rate |
| :---: | :--- | :---: | :---: | :---: |
| **Task 1** | `django__django-11790` | 804 | 0 | 0.0% |
| **Task 2** | `django__django-11815` | 0 | 804 | **100.0%** |
| **Task 3** | `django__django-11848` | 0 | 804 | **100.0%** |

Because the host checkout was maintained at commit `b1d6b35e` during this sequential evaluation, zero on-disk modifications occurred between tasks 2 and 3, yielding a 100% cache hit rate. To detect modifications, the system executed an SHA-256 integrity check across all 2,570 repository Python files, requiring $\approx 243\text{ ms}$ of disk I/O. In an active branching development environment where commits alter a subset of files between tasks, the cache hit rate would dynamically scale with the number of unchanged files.

---

### 6.6 Staleness Invalidation & Drift Verification (Answering RQ4)
To verify that content-hash tracking detects repository drift between tasks, we conducted a verification trial (`memory_pilot/staleness_check.py`, logged in `results/staleness_check.json`):
1. **Scenario**: A past task episode involving `django/contrib/auth/forms.py` was stored in memory.
2. **Drift Event**: An external edit was simulated on `django/contrib/auth/forms.py`, modifying its content and hash on disk.
3. **Observation**: Memory queries were evaluated under Condition C (Naive Combo) vs Condition D (Proposed System).

| Evaluation Parameter | Condition C (Naive Combo) | Condition D (Proposed System) |
| :--- | :---: | :---: |
| **Drift Detection** | ❌ `flags_stale = False` | **✅ `flags_stale = True`** |
| **Verification Method** | None (Blind string matching) | Cryptographic SHA-256 hash comparison |
| **Memory Annotation** | None | **`⚠️ [STALE - Files changed since task: forms.py]`** |
| **Context Weight** | 1.00 (Full Weight) | **0.20 (80% Weight Attenuation)** |
| **System Action** | Serves outdated references | Re-indexes AST on next pass |

**Finding**: Naive memory architectures that log past tasks as flat text strings have no mechanism to detect when referenced files change on disk, serving obsolete trajectories by construction. Cryptographic SHA-256 verification provides an essential functional correctness check: it detects file modifications and attenuates stale memory weights from $1.00$ to $0.20$, preventing obsolete code trajectories from masquerading as current ground truth.

---

## 7. Granular Task Post-Mortem & Qualitative Analysis

### Case 1: Resolved Bug in `django-11848` (`django/utils/http.py`)
- **Bug Description**: RFC 7231 Section 7.1.1.1 dictates that HTTP date parsers interpreting 2-digit years must employ a sliding window: dates more than 50 years in the future are assigned to the previous century. Django hardcoded `year < 70 -> year + 2000`.
- **Condition D Agent Action**:
  1. Received `<repository_context>` identifying `django/utils/http.py` at Rank 2 with function `parse_http_date`.
  2. Directly inspected `django/utils/http.py` lines 170–210 at turn 2.
  3. Identified the faulty century calculation.
  4. Edited the file to dynamically compute `century = current_year - (current_year % 100)` and check `if year - current_year > 50: year -= 100`.
  5. Ran reproduction tests, generated `patch.txt`, and submitted via `COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`.
- **Harness Result**: Passed all assertions in `tests/utils_tests/test_http.py`.

### Case 2: Multi-Turn Synthesis Failure in `django-11815` (`django/db/migrations/serializer.py`)
- **Bug Description**: Migration serializer wrote `Enum.name` instead of `Enum.value` when generating migrations for model fields with Enum defaults.
- **Agent Action**: Under Condition B and D, the agent localized `serializer.py` and class `EnumSerializer`. However, the agent's multi-turn regular expression edits introduced syntax and edge-case errors.
- **Takeaway**: While memory successfully routes the agent to the exact file and class, per-turn patch generation within a multi-turn bash loop remains bounded by the model's code generation capabilities.

---

## 8. Threats to Validity & Limitations

1. **Subtoken Tokenization & Acronym Limitations**:
   - The subtoken decomposition regex (`[A-Z]+(?=[A-Z][a-z0-9]|\b)|[A-Z][a-z0-9]*|[a-z0-9]+`) splits CamelCase and snake_case identifiers and lowercases tokens. While effective for common compounds, uppercase acronyms and domain-specific abbreviations may still suffer from over- or under-segmentation. Future work should evaluate byte-pair or learned code tokenizers across diverse languages.
2. **Static Repository Snapshot vs Dynamic Base Commits**:
   - Retrieval was evaluated on a static host repository checkout at commit `b1d6b35e` (Django 3.0-dev) to avoid repeated multi-gigabyte git checkout thrashing on disk. While we verified zero ground-truth patch leakage, tasks spanning from 2017 to 2020 experienced mild temporal drift relative to their original commit states. Indexing each task dynamically at its exact `base_commit` remains the reference standard.
3. **Small Sample Size for End-to-End Execution**:
   - Multi-turn execution was conducted on an illustrative 3-task sequence ($N=3$) with temperature 0.0 and single seeds due to API quota constraints. Because all resolving conditions resolved the identical task (`django-11848`), resolve rate deltas (1/3 vs 0/3) cannot be distinguished from stochastic noise. Multi-seed evaluations on larger task subsets ($N \ge 20$) are required for downstream statistical power.
4. **Episodic Transfer Domain Disjointness**:
   - In the sequential case study, Tasks 1, 2, and 3 touched completely disjoint subsystems (`forms.py`, `serializer.py`, `http.py`). Consequently, cross-task episodic transfer was virtually zero. Evaluating transfer will require high-recurrence task clusters within the same subsystem (e.g., `django-12209` and `django-12273` both modifying `django/db/models/base.py`).
5. **Model Capability Ceiling**:
   - We evaluated on `gemini-3.5-flash-lite`. Frontier models (`claude-sonnet-4-5`, `gpt-4o`) may demonstrate higher resolve rates on complex localized tasks.

---

## 9. Discussion & Future Directions

The empirical disconnect between file localization and task resolution carries important implications for the literature reviewed in Section 2:
1. **Rethinking the Value of Context**: Literature on history-augmented heuristics (HAFix) and report reuse (AGR) often assumes that surfacing the correct evidence is the primary bottleneck in autonomous software engineering. Our findings demonstrate that in multi-turn agent scaffolding, **fault localization is a necessary but insufficient condition** for bug resolution.
2. **Coupling Memory with Execution-Grounded Verification**: Following the insights of Jin & Chen [2026] and Contreras et al. [2026], future memory architectures should store not merely static code locations, but **verified reproduction test scripts** and execution harnesses from previous tasks, actively guiding the agent's verification phase rather than only its file discovery phase.
3. **High-Recurrence Task Clustering**: To rigorously measure episodic memory transfer, future evaluations should group SWE-bench tasks by repository module (e.g., contiguous sequences of migration serializer tasks or form handling tasks), providing the memory engine with relevant historical experience to retrieve.

---

## 10. Conclusion

In this work, we developed, formalized, and empirically evaluated a **Session-Persistent Repository Memory Architecture** for autonomous software engineering agents. Our findings reveal:
1. **Localization is significantly improved**: Fusing Tree-sitter AST symbol graphs with sparse lexical retrieval via Reciprocal Rank Fusion ($k=60$) significantly improves ranking accuracy across 25 SWE-bench Verified tasks, led by a +58.0% gain in MRR (0.5793 vs 0.3667; two-sided Wilcoxon $p = 0.0077$). Top-1 hit rate improves to 44.0% and Top-5 hit rate reaches 80.0% ($p < 0.05$).
2. **Downstream bug resolution remains bounded**: Providing accurate localization does not automatically translate to higher task resolution rates (remaining flat at 33.3% across resolving conditions), demonstrating that patch synthesis remains constrained by the underlying LLM's multi-turn reasoning capacity.
3. **Staleness verification protects persistent state**: Cryptographic content hashing detects repository drift and attenuates outdated episodic memory weights.

---

## References

1. Shi, Y., Bangash, A. A., Fallahzadeh, E., Adams, B., & Hassan, A. E. (2026). HAFix: history-augmented large language models for bug fixing. *Empirical Software Engineering*, 31(4), 104.
2. Chondamrongkul, N., Kyaw, M. P. P., Ko, S. M., Paing, P. P., Than Swe, M. K., & Hongthong, T. (2026). RepoAI: Automated code refactoring through multi-agent LLM orchestration and retrieval-augmented generation. *Science of Computer Programming*, 253, 103477.
3. Wang, Y., Zhong, W., Huang, Y., Shi, E., Yang, M., Chen, J., Li, H., Ma, Y., Wang, Q., & Zheng, Z. (2025). Agents in software engineering: survey, landscape, and vision. *Automated Software Engineering*, 32(2), 70.
4. He, J., Treude, C., & Lo, D. (2025). LLM-Based Multi-Agent Systems for Software Engineering: Literature Review, Vision, and the Road Ahead. *ACM Transactions on Software Engineering and Methodology*, 34(5), Article 124, 1-30.
5. Jia, Z., Li, J., Kang, Y., Wang, Y., Wu, T., Wang, Q., Wang, X., Zhang, S., Shen, J., Li, Q., Qi, S., Liang, Y., He, D., Zheng, Z., & Zhu, S.-C. (2025). The AI Hippocampus: How Far are We From Human Memory? *Transactions on Machine Learning Research*.
6. Wang, Z., Li, J., Guo, X., et al. (2026). From noisy feedback to evidence-aware issue specifications: an agent-governed retrieval-augmented generation approach. *Automated Software Engineering*, 33, 103.
7. Contreras, A., Guerra, E., & de Lara, J. (2026). Architecting open, accountable, and trustworthy AI-IDEs. *Automated Software Engineering*, 33, 63.
8. Jin, H., & Chen, H. (2026). Are LLMs reliable code reviewers? systematic overcorrection in requirement conformance judgement. *Automated Software Engineering*, 33, 90.
9. Cao, J., Li, M., Wen, M., et al. (2025). A study on prompt design, advantages and limitations of ChatGPT for deep learning program repair. *Automated Software Engineering*, 32, 30.
10. Jimenez, C. E., Yang, J., Wettig, A., Yao, S., Pei, K., Press, O., & Narasimhan, K. (2024). SWE-bench: Can Language Models Resolve Real-World GitHub Issues? *International Conference on Learning Representations (ICLR)*.
11. Yang, J., Jimenez, C. E., Wettig, A., Lieret, K., Yao, S., Narasimhan, K., & Press, O. (2024). SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering. *arXiv preprint arXiv:2405.15793*.
12. Lieret, K., et al. (2025). mini-swe-agent: Minimal, Extensible Scaffolding for Autonomous Software Engineering Agents. *SoftwareX*.
13. Xia, C. S., Deng, Y., Dunn, S., & Zhang, L. (2024). Agentless: Demystifying LLM-based Software Engineering Agents. *arXiv preprint arXiv:2407.01489*.
14. Gauthier, P. (2023). Aider: AI Pair Programming in Your Terminal with Tree-Sitter Repo Maps. `https://github.com/paul-gauthier/aider`.
15. Cormack, G. V., Clarke, C. L. A., & Buettcher, S. (2009). Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods. *ACM SIGIR*, 758–759.
16. Zhang, F., Chen, B., Zhang, Y., Liu, J., Zan, D., Mao, Y., Lou, J.-G., & Chen, W. (2023). RepoCoder: Repository-Level Code Completion Through Iterative Retrieval and Generation. *EMNLP*, 2471–2484.
17. Feng, Z., Guo, D., Tang, D., et al. (2020). CodeBERT: A Pre-Trained Model for Programming and Natural Languages. *Findings of ACL: EMNLP 2020*, 1536–1547.
18. Guo, D., Ren, S., Lu, S., et al. (2021). GraphCodeBERT: Pre-training Code Representations with Data Flow. *ICLR*.
