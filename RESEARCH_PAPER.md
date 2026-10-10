# Persistent Repository Memory for Autonomous Software Engineering Agents: An Empirical Study on SWE-bench Verified

**Authors**: Abhinav Pant, Abhiram Anil, A Anjana Nair  
**Date**: October 2026  
**Artifact Repository**: `https://github.com/abhitruechamp/fds_memory`  
**Dataset**: `MariusHobbhahn/swe-bench-verified-mini` (`django/django`)  
**Scaffolding & Harness**: `mini-swe-agent 2.4.6` | `swebench 4.1.0`  
**Base LLM Backend**: `gemini/gemini-3.5-flash-lite`  

---

## Abstract

Modern autonomous software engineering (SWE) agents operate in a predominantly stateless paradigm: each issue is tackled inside an isolated container, discarding codebase structural indexes, episodic debugging trajectories, and past execution feedback across tasks. In production engineering, however, software systems evolve continuously, and human engineers build persistent structural mental models of the repository.

In this paper, we explore the design, localization efficacy, and limitations of a **Persistent Repository Memory Architecture** combining:
1. **Tree-sitter Structural AST Symbol Graphs**: Parsing hierarchical class, function, call, and signature topologies with subtoken decomposition.
2. **Hybrid Reciprocal Rank Fusion (RRF)**: Fusing sparse lexical retrieval (sublinear TF-IDF) with AST symbol representations.
3. **Incremental In-Memory Caching**: Content-hash tracking avoiding redundant parsing of unchanged files across tasks.
4. **Episodic Outcome Logging**: Tracking touched files and test results post-harness under strict zero-leakage constraints.
5. **Cryptographic Staleness Invalidation**: Identifying on-disk file modifications via SHA-256 hashing and penalizing outdated memory weights.

We conduct an empirical evaluation on **SWE-bench Verified Mini**:
- **Significant Localization Gains ($N=25$)**: Hybrid RRF improves Mean Reciprocal Rank (MRR) by **+58.0%** (0.5793 vs 0.3667; paired Wilcoxon signed-rank test $W = 13.5$, two-sided $p = 0.0077$, one-sided $p = 0.0039$ across $n=15$ non-zero discordant pairs). Across all 25 Django tasks, Hybrid RRF achieves **80.0% Recall@5** (Wilson 95% CI: [0.609, 0.911]) and **44.0% Recall@1** (CI: [0.267, 0.629]) compared to 60.0% Recall@5 and 20.0% Recall@1 for sparse lexical retrieval alone. Under directional (one-sided) paired McNemar tests motivated by the a priori non-inferiority hypothesis, these gains are significant ($p = 0.035$ for Recall@1, $p = 0.031$ for Recall@5); two-sided exact values are $p = 0.070$ and $p = 0.063$, reflecting statistical power limits at $N=25$.
- **Downstream Task Resolution Remains Bounded by Model Reasoning**: In an illustrative multi-turn sequential case study ($N=3$ tasks), the proposed system resolves target bugs passing the official Docker test suite (`django-11848`), but **overall resolution rate did not improve over the stateless baseline (1/3 or 33.3% across all resolving conditions)**. Even when memory accurately placed the target file at Rank 1, complex patch synthesis remained bounded by the underlying model's multi-turn code generation capacity.
- **Latency & Tool Overhead**: In our multi-turn runs, memory-guided context reduced exploratory search commands from 29 to 22 across tasks, with observed mean task duration of 207.3s for Condition D vs 357.5s for Baseline A (comparable to Naive Combo at 202.0s), though mean turns remained comparable (48.7 in D vs 46.3 in A).
- **Staleness Tracking**: A verification check demonstrates that SHA-256 change tracking detects on-disk file modifications and applies an 80% weight attenuation, whereas naive string-logging is oblivious to repository drift by construction.

---

## 1. Introduction

Autonomous coding agents (e.g., SWE-agent, Devin, mini-swe-agent) have demonstrated impressive capability on benchmarks such as SWE-bench. Nevertheless, standard scaffolding remains strictly **stateless**: every issue starts from an empty environment, forcing the agent to discover repository structure, file layouts, and subsystem conventions entirely from scratch.

In large codebases containing hundreds of thousands of lines of code (such as the Django framework), statelessness incurs significant operational costs:
1. **Unguided Exploration**: Without structural context, agents spend dozens of turns executing exploratory bash commands (`find`, `grep`, directory listings) to locate relevant files.
2. **Episodic Amnesia**: Insights gained during previous task debugging (such as module conventions or test script locations) are discarded upon container termination.
3. **Repository Drift Vulnerability**: In persistent workflows where code evolves across commits, agents caching historical trajectories risk relying on obsolete symbol signatures unless cryptographic staleness mechanisms are in place.

However, bridging repository memory with agent scaffolding presents an open question: **Does providing structural repository memory actually improve bug resolution, or does it merely solve file localization?** 

### 1.1 Summary of Findings
- **Localization is significantly improved**: Combining Tree-sitter AST symbol graphs with lexical retrieval via Reciprocal Rank Fusion ($k=60$) significantly outperforms sparse lexical retrieval across all 25 Django tasks in SWE-bench Verified Mini ($N=25$), led by a +58.0% improvement in MRR (0.5793 vs 0.3667; two-sided Wilcoxon $p = 0.0077$). Recall@1 improves to 44.0% (directional McNemar $p = 0.035$, two-sided $p = 0.070$), and Recall@5 reaches 80.0% (directional $p = 0.031$, two-sided $p = 0.063$).
- **Downstream resolution does not automatically follow**: In end-to-end multi-turn evaluation, providing accurate file localization at Rank 1 was insufficient to raise task resolve rates beyond the stateless baseline (1/3 across all resolving conditions, resolving the identical task `django-11848`). Downstream bug resolution is bottlenecked by the model's multi-turn reasoning and editing fidelity.
- **Episodic transfer is domain-dependent**: When sequential tasks touch disjoint subsystems (`auth/forms`, `db/migrations`, `utils/http`), cross-task episodic transfer is negligible.
- **Staleness verification protects persistent state**: Cryptographic SHA-256 verification detects file modifications and down-weights outdated context, addressing an architectural vulnerability in naive string-logging memory.

---

## 2. System Architecture & Mathematical Formulation

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

### 2.1 Tree-sitter AST Symbol Extraction & Subtoken Decomposition
Given a Python source file $f \in \mathcal{F}$, we parse its concrete syntax tree using Tree-sitter. We extract top-level definitions:
$$\mathcal{S}(f) = \left( \mathcal{C}_f, \mathcal{M}_f, \mathcal{K}_f \right)$$
where $\mathcal{C}_f$ denotes declared class identifiers, $\mathcal{M}_f$ denotes function/method definitions, and $\mathcal{K}_f$ denotes outgoing call invocations.

To match natural-language descriptions that reference partial or composite names (e.g., an issue referencing "Enum" matching a class named `EnumSerializer`, or "widget" matching `widget_attrs`), we apply subtoken decomposition supporting CamelCase, snake_case, and uppercase acronyms:
$$\text{Subtokens}(w) = \{ \text{lower}(s) \mid s \in \text{RegexFindall}(w, \text{pattern}=\text{"[A-Z]+(?=[A-Z][a-z0-9]|\b)|[A-Z][a-z0-9]*|[a-z0-9]+"}), |s| \ge 3 \}$$
This decomposes CamelCase classes into constituents (e.g., `EnumSerializer` $\to$ `enum`, `serializer`), splits snake_case identifiers on underscores as natural token boundaries (e.g., `parse_http_date` $\to$ `parse`, `http`, `date`), preserves uppercase acronyms (e.g., `HTTPResponse` $\to$ `http`, `response`), and normalizes tokens to lowercase.

### 2.2 Hybrid Reciprocal Rank Fusion (RRF)
Let $\mathcal{R}_{\text{lex}}(f)$ denote the rank of file $f$ under sparse lexical retrieval (sublinear TF-IDF cosine similarity), and $\mathcal{R}_{\text{ast}}(f)$ denote the rank of file $f$ under AST symbol matching. The unified fusion score is defined as:
$$\text{RRF}(f) = \frac{1}{k + \mathcal{R}_{\text{lex}}(f)} + \frac{1}{k + \mathcal{R}_{\text{ast}}(f)}, \quad \text{with } k = 60$$

Files are sorted in descending order of $\text{RRF}(f)$, and the top $K=5$ files are injected into the agent's prompt along with their extracted class signatures and function declarations.

### 2.3 Incremental AST Caching
To prevent re-indexing latency from compounding across tasks, we maintain an in-memory symbol cache:
$$\text{Cache}: \text{rel\_path} \to (\text{SHA256}, \mathcal{S}(f))$$
On task $t$, the system computes SHA-256 hashes for all repository source files. While checking each computed hash against the in-memory cache is $O(1)$, the underlying file scanning and hashing incurs an $O(\sum |f|) = O(M)$ disk I/O pass across repository files (empirically measured at $\approx 243\text{ ms}$ for 2,570 files totaling 12.88 MB in the Django codebase). If $\text{SHA256}_t(f) = \text{SHA256}_{t-1}(f)$, concrete syntax tree re-parsing is bypassed. Full AST parsing occurs strictly for newly added or modified files.

### 2.4 Cryptographic Staleness Detection & Invalidation
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

## 3. Experimental Setup & Benchmarking Methodology

### 3.1 Dataset Inventory & Repository State Configuration
We evaluate on **SWE-bench Verified Mini** (`MariusHobbhahn/swe-bench-verified-mini`), specifically the 25 tasks from `django/django`. Tasks span from `django-9296` (2017) to `django-12774` (2020).

**Host Checkout Commit & Temporal Integrity**:
The shared host repository checkout was pinned to commit `b1d6b35e146aea83b171c1b921178bbaae2795ed` (dated 2019-09-17 14:30:33 UTC), which corresponds to the exact `base_commit` of Task 2 (`django__django-11790`).
- **Temporal Alignment**: Exactly 1 task (`django-9296`, 2017-10-27) has a base commit preceding this snapshot, while the remaining 23 tasks post-date it (spanning through 2020-04-22).
- **Leakage Verification**: We audited whether the host checkout contained future test fixes. For the single preceding task (`django-9296`), its ground-truth fix (`def __iter__` in `django/core/paginator.py`) was not merged into master as of commit `b1d6b35e`. For tasks 3–25, the host commit predates the task creation dates, strictly precluding future patch leakage.
- **Static Snapshot vs Dynamic Base Commits**: Because the host checkout was static, the index represents Django 3.0-dev. While evaluating static retrieval against a single checkout avoids repeated multi-gigabyte git checkout overhead on disk, checking out each task at its own `base_commit` represents the ideal reference architecture and is discussed as a methodological consideration in Section 6.

For end-to-end multi-turn agent evaluation, we select a contiguous chronological sequence:
1. **Task 1: `django__django-11790`** (2019-09-17): `AuthenticationForm` username HTML5 `max_length` attribute regression. Target: `django/contrib/auth/forms.py`.
2. **Task 2: `django__django-11815`** (2019-09-24): `Enum` migration serializer generating `.name` instead of `.value`. Target: `django/db/migrations/serializer.py`.
3. **Task 3: `django__django-11848`** (2019-09-28): `parse_http_date` 2-digit year RFC 7231 sliding century window. Target: `django/utils/http.py`.

### 3.2 Hardware, Environment & Pinned Dependencies
- **OS**: Linux Fedora x86_64 (`kernel 7.2.8-200.fc44`)
- **CPU**: AMD Ryzen 7 7730U (16 logical cores)
- **RAM**: 13.5 GiB Physical RAM + 8.0 GiB zram swap
- **Storage**: NVMe SSD (all Docker images pre-cached locally; zero network bandwidth consumed during evaluation)
- **Frameworks**:
  - `mini-swe-agent == 2.4.6`
  - `swebench == 4.1.0`
  - `tree-sitter == 0.26.0`
  - `tree-sitter-python == 0.25.0`
  - `scikit-learn == 1.9.1`

### 3.3 Inference Model & Client Throttling
- **Model**: `gemini/gemini-3.5-flash-lite` (temperature = 0.0)
- **Rate-Limit Load Balancing**: To avoid burst rate-limit throttling during multi-turn bash trajectories on developer accounts, tool queries were distributed across multiple authorized developer API credentials in round-robin fashion.
- **Throttling & Guard**: Inter-request sleep of 1.0s, coupled with an explicit 90s socket timeout safeguard and Tenacity exponential backoff retries.

### 3.4 Pacing Budget Prompt Injection
In baseline runs capped at 30 turns without pacing guidance, agents suffered from repetitive read loops (`git grep "widget_attrs"` repeated up to 8 times). In `swebench.yaml`, we injected an explicit execution pacing instruction:
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
*Note*: This identical pacing prompt configuration was applied uniformly across all four experimental conditions.

---

## 4. Quantitative Results & Empirical Evaluation

### 4.1 Retrieval Quality Benchmark ($N=25$)

We benchmarked all 25 Django tasks in SWE-bench Verified Mini against ground-truth patch files. We compare:
- **Condition B (Snapshot Lexical / TF-IDF)**: Sparse lexical retrieval (sublinear TF-IDF cosine similarity).
- **Condition C (Naive Combo)**: Sparse lexical + flat past task history.
- **Condition D Ablation (Pure AST)**: Structural symbol matching without lexical fusion.
- **Condition D Full (Hybrid RRF)**: Reciprocal Rank Fusion fusing sparse lexical with AST symbol graphs.

#### Comprehensive Retrieval Results Table ($N=25$)

| Architecture Variant | Recall@1 | 95% Wilson CI | Recall@3 | Recall@5 | 95% Wilson CI | MRR | Raw R@5 Hits |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **B (Snapshot Lexical / TF-IDF)** | 0.2000 | [0.0886, 0.3913] | 0.5200 | 0.6000 | [0.4074, 0.7660] | 0.3667 | 15 / 25 |
| **C (Naive Combo)** | 0.2000 | [0.0886, 0.3913] | 0.5200 | 0.6000 | [0.4074, 0.7660] | 0.3667 | 15 / 25 |
| **D (Pure AST Ablation)** | 0.3200 | [0.1720, 0.5159] | 0.5600 | 0.6800 | [0.4841, 0.8280] | 0.4547 | 17 / 25 |
| **D (Full Hybrid RRF)** | **0.4400** | **[0.2667, 0.6293]** | **0.6800** | **0.8000** | **[0.6087, 0.9114]** | **0.5793** | **20 / 25** |

#### Statistical Significance Analysis:

1. **Paired Test for MRR (Primary Statistical Metric)**:
   A paired Wilcoxon signed-rank test comparing Reciprocal Ranks per task ($MRR_D = 0.5793$ vs $MRR_B = 0.3667$, $+58.0\%$ relative improvement):
   - Out of 25 tasks, 15 exhibited non-zero differences and 10 were identical ties ($MRR_D - MRR_B = 0$).
   - Discarding zero differences under the standard Wilcoxon method yields test statistic $W = 13.5$ (sum of negative ranks, corresponding to positive rank sum $W = 106.5$ on $n=15$ non-zero pairs):
     $$\text{Two-sided: } p = 0.00774 \quad (p < 0.01), \quad \text{One-sided (greater): } p = 0.00387 \quad (p < 0.005)$$
   - Under the Pratt zero-ranking method (ranking all 25 pairs including ties), the two-sided $p$-value is $p = 0.00183$.
   Because MRR evaluates continuous reciprocal ranks across the entire candidate list without an arbitrary top-$K$ threshold, this confirms a statistically significant ranking advantage for Hybrid RRF even under strict two-sided hypothesis testing.

2. **Paired Test for Recall@1**:
   Hybrid RRF achieved 7 wins, 1 loss, 4 shared hits, and 13 shared misses against lexical retrieval alone ($n=8$ discordant pairs).
   - Under a directional (one-sided) McNemar exact test reflecting our a priori hypothesis ($H_1: \text{Recall}_D > \text{Recall}_B$):
     $$p = \text{binomtest}(7, 8, 0.5, \text{alternative}='greater') = 0.03516 \quad (p < 0.05)$$
   - The corresponding two-sided exact test yields:
     $$p = \text{binomtest}(7, 8, 0.5, \text{alternative}='two-sided') = 0.07031$$
   While the directional test supports top-1 improvement, the two-sided value crosses $\alpha=0.05$ due to finite sample size ($N=25$).

3. **Paired Test for Recall@5**:
   Under binary hit/miss evaluation (at least 1 gold file retrieved in top 5), Hybrid RRF achieved 5 wins, 0 losses, 15 shared hits, and 5 shared misses against lexical retrieval alone ($n=5$ discordant pairs).
   - One-sided exact test:
     $$p = 0.5^5 = 0.03125 \quad (p < 0.05)$$
   - Two-sided exact test:
     $$p = 2 \times 0.5^5 = 0.06250$$
   When accounting for partial recall on multi-file targets (e.g., `django-12325` where Condition D retrieved 2/2 gold files vs 1/2 for Condition B), 6 tasks favored Condition D with 0 favoring Condition B (two-sided $p = 0.03125$).

---

### 4.2 End-to-End Agent Task Execution (Sequential Case Study, $N=3$)

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

### 4.3 Latency & Tool Execution Dynamics

- **Baseline A vs Memory-Guided Conditions**: In Baseline A, the agent spent significant time executing unguided `git grep` and recursive `find` commands across the repository inside Docker. In Conditions C and D, the agent inspected candidate files directly without repository-wide scans.
- **Condition C vs Condition D**: Observed mean execution duration was **202.0s** for Condition C and **207.3s** for Condition D. 
- *Methodological Caveat*: Wall-clock latency was measured on single runs subject to external Google API network variance, round-robin key rotation, and client-side throttle settings. These measurements represent observed operational characteristics rather than formal statistical guarantees.

---

### 4.4 AST Caching Amortization

We tracked Tree-sitter AST parsing operations across sequential tasks:

| Sequence Position | Task ID | Files Reparsed | Files Cached (0ms) | Cache Hit Rate |
| :---: | :--- | :---: | :---: | :---: |
| **Task 1** | `django__django-11790` | 804 | 0 | 0.0% |
| **Task 2** | `django__django-11815` | 0 | 804 | **100.0%** |
| **Task 3** | `django__django-11848` | 0 | 804 | **100.0%** |

*Note on Repository State & Hashing Cost*:
Because the host repository checkout was maintained at a static commit (`b1d6b35e`) during this sequential evaluation, zero on-disk modifications occurred between tasks 2 and 3, yielding an expected 100% cache hit rate. To detect modifications, the system executed an SHA-256 integrity check across all 2,570 repository Python files, requiring $\approx 243\text{ ms}$ of disk I/O. In an active branching development environment where commits alter a subset of files between tasks, the cache hit rate would dynamically scale with the number of unchanged files.

---

### 4.5 Staleness Invalidation & Drift Verification

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

## 5. Granular Task Post-Mortem & Qualitative Analysis

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

## 6. Threats to Validity & Limitations

1. **Subtoken Tokenization & Acronym Limitations**:
   - The subtoken decomposition regex (`[A-Z]+(?=[A-Z][a-z0-9]|\b)|[A-Z][a-z0-9]*|[a-z0-9]+`) splits CamelCase and snake_case identifiers and lowercases tokens. While effective for common compounds, uppercase acronyms and domain-specific abbreviations may still suffer from over- or under-segmentation. Future work should evaluate byte-pair or learned code tokenizers across diverse languages.
2. **Static Repository Snapshot vs Dynamic Base Commits**:
   - Retrieval was evaluated on a static host repository checkout at commit `b1d6b35e` (Django 3.0-dev) to avoid repeated multi-gigabyte git checkout thrashing on disk. While we verified zero ground-truth patch leakage, tasks spanning from 2017 to 2020 experienced mild temporal drift relative to their original commit states. Indexing each task dynamically at its exact `base_commit` remains the reference standard.
3. **Small Sample Size for End-to-End Execution**:
   - Multi-turn execution was conducted on an illustrative 3-task sequence ($N=3$) with temperature 0.0 and single seeds due to API quota constraints. Because all resolving conditions resolved the identical task (`django-11848`), resolve rate deltas (1/3 vs 0/3) cannot be distinguished from stochastic noise. Multi-seed evaluations on larger task subsets ($N \ge 20$) are required for downstream statistical power.
4. **Episodic Transfer Domain Disjointness**:
   - In the sequential case study, Tasks 1, 2, and 3 touched completely disjoint subsystems (`forms.py`, `serializer.py`, `http.py`). Consequently, cross-task episodic transfer was virtually zero. Evaluating transfer will require high-recurrence task clusters within the same subsystem.
5. **Model Capability Ceiling**:
   - We evaluated on `gemini-3.5-flash-lite`. Frontier models (`claude-sonnet-4-5`, `gpt-4o`) may demonstrate higher resolve rates on complex localized tasks.

---

## 7. Related Work

- **Autonomous Coding Scaffolding**: SWE-agent (Yang et al., 2024), Devin (Cognition, 2024), and mini-swe-agent (Klieret et al., 2025) pioneered bash-driven tool interaction for software engineering. These scaffolds operate statelessly.
- **Codebase Localization & Repo-Maps**: Aider (Gauthier, 2023) introduced repository mapping using Tree-sitter symbol graphs and PageRank. Agentless (Xia et al., 2024) demonstrated two-stage localize-then-repair pipelines using lexical and semantic search. Our work integrates structural AST graphs with multi-task episodic logging and cryptographic staleness verification.
- **Dense & Graph Code Retrieval**: CodeBERT (Feng et al., 2020) and GraphCodeBERT (Guo et al., 2021) explore semantic code embeddings. Our findings show that sparse lexical retrieval combined with AST symbol topologies via Reciprocal Rank Fusion ($k=60$) achieves competitive performance without GPU embedding overhead.

---

## 8. Conclusion

Statelessness in autonomous coding agents imposes an unnecessary exploratory burden. In this work, we developed and evaluated a Persistent Repository Memory Architecture. Our findings reveal:
1. **Localization is significantly improved**: Fusing Tree-sitter AST symbol graphs with sparse lexical retrieval via Reciprocal Rank Fusion significantly improves ranking accuracy across 25 SWE-bench Verified tasks, led by a +58.0% gain in MRR (0.5793 vs 0.3667; two-sided Wilcoxon $p = 0.0077$). Recall@1 improves to 44.0% and Recall@5 reaches 80.0% (directional McNemar $p < 0.05$).
2. **Downstream bug resolution remains bounded**: Providing accurate localization does not automatically translate to higher task resolution rates (remaining flat at 33.3% across resolving conditions), demonstrating that patch synthesis remains constrained by the underlying LLM's multi-turn reasoning capacity.
3. **Staleness verification protects persistent state**: Cryptographic content hashing detects repository drift and attenuates outdated episodic memory weights.

---

## BibTeX Citation

```bibtex
@misc{pant2026repositorymemory,
  title={Persistent Repository Memory for Autonomous Software Engineering Agents: An Empirical Study on SWE-bench Verified},
  author={Pant, Abhinav and Anil, Abhiram and Nair, A Anjana},
  year={2026},
  howpublished={\url{https://github.com/abhitruechamp/fds_memory}},
  note={arXiv preprint}
}
```
