# claude.md — MailQ development guardrails (Nov 2025)

> Purpose: make Claude Code (Pro) a reliable pair‑programmer for MailQ by encoding rules, workflows, and safety rails it must follow. Keep this file at repo root. Claude must read this file before acting and re‑state the "North Star" at the top of each plan.

## 0) Reality check

* **Known from docs:** Claude Code supports VS Code integration (context from editor, inline diffs, terminal with approval) and long-context Sonnet models; it can plan → propose diffs → run commands with explicit user approval.
* **Likely but verify in your environment (⚠️):** features like Rewind, 1M‑token context, Plan Mode names/shortcuts, weekly/rolling usage caps, and model default (Sonnet 4.5). If tooling behaves differently, adapt the prompts below.

## 1) North Star (repeat every plan)

* **Goal:** shipping a stable, privacy‑respecting Gmail AI assistant (MailQ) with high precision classification and low incident risk.
* **Invariant Rules:**

  1. Propose a plan before editing. Wait for approval.
  2. Produce **minimal, atomic diffs** with tests updated first.
  3. Never run commands or write files without explicit "APPROVED" in the last user message.
  4. Prefer **surgical edits** over large refactors; if refactor is required, generate a migration plan + backout steps.
  5. For ambiguous instructions, ask 1 targeted question with your best default.

## 2) Project context

* **Stack:** Python FastAPI backend (+ SQLite or Postgres), Chrome Extension (TypeScript), Gemini‑first classification + rules, digest HTML templates, evaluation scripts.
* **Deployment flow:** Local development → Production (Cloud Run). No staging environment. Use feature flags for safe deployments.
* **Critical directories (keep tidy):**

  * `mailq/` (Python backend with subdirectories: api/, classification/, digest/, gmail/, infrastructure/, llm/, observability/, runtime/, shared/, storage/, utils/)
  * `extension/` (Chrome extension: background, content scripts, options, UI)
  * `config/` (mailq_policy.yaml, mapper rules, confidence settings)
  * `scripts/` (ETL, evals, cleanup)
  * `tests/`
  * `docs/` (architecture, development guides, analysis)
* **Critical artifacts:** `mailq/llm/prompts/`, `mailq/digest/templates/`, `mailq/data/mailq.db`, `config/mailq_policy.yaml`, `.env.example`.
* **Runtime policy knobs:** See `config/mailq_policy.yaml` for classification thresholds, verifier triggers, and quality monitor settings.

For architecture, file paths, environment variables, quality monitoring, and debugging, see [MAILQ_REFERENCE.md](MAILQ_REFERENCE.md).

## 2a) Core Architectural Principles (ALWAYS APPLY)

**Before writing ANY code, validate against these 5 principles** from [docs/CORE_PRINCIPLES.md](docs/CORE_PRINCIPLES.md):

### P1: Concepts Are Rooms, Not Hallways
* Each feature lives in ONE conceptual home (e.g., `mailq/classification/feedback_learning.py`)
* Don't scatter related logic across 4+ files
* **Check:** "Can I understand this feature by reading 1-2 files max?"

### P2: Side Effects Are Loud, Not Sneaky
* Functions that write to DB/API must declare this in name + docstring
* Use `record_and_learn()` not `record()` if it triggers learning
* Add `Side Effects:` section to docstrings for all state-modifying functions
* **Check:** "Are there hidden side effects not visible in the signature?"

### P3: The Compiler Is Your Senior Engineer
* Type everything: function signatures, return types, intermediate values
* Use typed pipeline stages: `ExtractedEntity → ClassifiedEntity → EnrichedEntity`
* Validate at boundaries (API inputs, LLM outputs, DB reads)
* **Check:** "Could types catch this bug at compile time?"

### P4: Synchronizations Are Explicit Contracts
* Pipeline dependencies declared: `Stage("enrich", depends_on=["classify"])`
* Validate state contracts: fail fast if required fields missing
* No global state or hidden callbacks
* **Check:** "Are dependencies visible? Would reordering break silently?"

### P5: Production Complexity Is Tuning, Debt Is Rewrites
* **Production complexity** = fixable with indexes, caching, pooling (1-2 days)
* **Architecture debt** = requires refactoring tangled code (5-14 days)
* Bias toward tuning; only refactor when structure blocks progress
* **Check:** "Is this a missing index (tune) or tangled logic (refactor)?"

**Application in Plans:**
* When proposing changes, state which principles apply
* If violating a principle, explain why and propose mitigation
* In code review context, flag principle violations

**Full reference:** [docs/CORE_PRINCIPLES.md](docs/CORE_PRINCIPLES.md) (read before major refactors)

## 3) Roles & scope Claude may take

* **Editor:** propose diffs for specific files.
* **Planner:** generate task graph with estimates and unknowns.
* **Test author:** add/repair unit/integration tests.
* **Refactorer:** only after plan + backout steps.
* **Evaluator:** run eval scripts; compute precision/recall and cost; write markdown report.

## 4) Command policy

Claude may *suggest* commands but must not execute until approved. Use `DRY_RUN` blocks.

```bash
# DRY_RUN — propose only, do not execute
uv run pytest -q
ruff check .
node --version && python -V
make digest
```

Upon approval, execute in this order: **lint → typecheck → unit tests → integration/e2e → run service**.

## 5) Planning template (Claude must use)

```
PLAN
1) Intent: <what we're changing and why>
2) Impacted files: <list>
3) Risks & mitigations: <list>
4) Tests to add/update: <list>
5) Commands (dry‑run): <ordered list>
6) Rollback: <how to revert>
7) Diffs (one atomic commit per bullet): <titles only>
END PLAN
```

## 6) Diff rules

* Keep patches ≤ 200 lines per commit when possible.
* Include **docstring + comments** for non‑obvious logic.
* Update **mappers** so Gmail policy stays decoupled from prompts.
* Refuse to touch secrets; use `.env` and `secrets/` placeholders.

## 7) Test rules

* For each feature edit, require tests that would fail pre‑change.
* Maintain `scripts/evals/` for classifier accuracy and cost evaluation scripts.
* Add a **golden digest** snapshot test for HTML output.
* Coverage target: **statements ≥ 80%** for touched modules.

## 8) MailQ‑specific guardrails

* **Classification:** rules → LLM fallback; log `decider` (rule|gemini|detector), confidences, and reasons.
* **Digest:** deterministic structure; tolerate missing fields; never leak PII.
* **Gmail policy:** `gmail_labels` computed in mappers, not LLM outputs.
* **Privacy:** no uploading user emails or secrets to third‑party APIs beyond configured LLM provider.
* **Thresholds:** All runtime classification/verifier thresholds are in `config/mailq_policy.yaml`, not hard-coded.
* **Database Policy:** MailQ uses ONE SQLite database: `mailq/data/mailq.db`
  * All new tables MUST be added to this database via `mailq/infrastructure/database.py`
  * Creating new `.db` files is **FORBIDDEN** without explicit architectural review
  * All code MUST use `get_db_connection()` from `mailq/infrastructure/database.py`
  * Scripts MUST connect to central database, not create their own
  * Pre-commit hook will reject commits with new `.db` files
* **Evaluation Output Policy:** All eval script outputs go to `reports/experiments/`
  * Source data (GDS, golden digests) lives in `data/evals/`
  * Generated outputs (JSON, CSV, MD reports) go to `reports/experiments/`
  * Never create new output directories under `data/evals/`
  * The `reports/` directory has `.gitignore` for generated files

## 9) Known Claude Code pitfalls & mitigations (Nov 2025)

* **Instruction drift / ignores plan (⚠️ observed):**

  * Always restate the **North Star** and this file's key rules in your plan preamble.
  * Use **plan→diff→approve→run** loop; if you detect divergence, stop and ask.
* **Over‑broad edits / file creation outside scope:**

  * Require an explicit file list; edits restricted to that list unless user adds "/allow‑expand".
* **Unauthorized commands / risky ops:**

  * All commands start as **DRY_RUN**; look for words like `rm -rf`, network calls, migrations; if found, require double‑confirmation (`CONFIRM DANGEROUS`).
* **Context loss or short memory:**

  * Re‑ingest `claude.md`, `MAILQ_REFERENCE.md`, and the touched files each session; summarize them in the plan.
* **Rate limits / weekly caps (⚠️ may apply):**

  * Batch diffs; prefer smaller, higher‑signal conversations; export long logs to `reports/`.
* **Long diffs get truncated:**

  * Split by module; use a series of atomic commits.
* **Monorepo path confusion:**

  * Echo full absolute paths in plan; show `tree` of impacted dirs.
* **"It works on my machine" test drift:**

  * Pin Python/node versions; include lockfiles; run CI matrix.

## 10) Prompts Claude should use (copyable snippets)

**A) Small feature edit**

```
You are operating under repo root and must follow /claude.md rules. Propose a PLAN only. Do not write any files or run commands.
Task: <describe>
Constraints: atomic diffs; update tests first; DRY_RUN commands only.
Output format: use the PLAN template from /claude.md.
```

**B) Apply a reviewed diff**

```
Apply the following approved diff as a single atomic commit titled: "<title>". Do not change any other files. Then output a DRY_RUN command list to lint and test.
```

**C) Dead/unused code cleanup (safe)**

```
Goal: identify and remove dead code with zero behavior change.
Steps:
1) Static scan (ripgrep/ts-prune/vulture/ruff‑dead‑code) → candidate list.
2) Cross‑ref test coverage; require zero references in repo.
3) Propose diff that only deletes files/symbols with evidence lines.
4) DRY_RUN: ruff, mypy/pyright, tests. If green, proceed.
```

**D) Refactor with backout**

```
Propose a two‑phase refactor plan with backout. Phase 1 introduces adapters behind feature flags; Phase 2 flips the flag after tests pass. Include rollback steps and migration notes.
```

**E) Eval run**

```
Run the classifier evals and produce report markdown with precision/recall, cost/email, top error patterns, and suggested rules to add.
```

## 11) Tooling expectations

* **Editor integration:** use VS Code inline diffs; prefer `@file` mentions over whole‑repo dumps.
* **Terminal:** request permission per command; never run shells that mutate env without approval.
* **Artifacts:** dump generated analysis, eval outputs, and temp docs to `reports/`. Delete freely—git history preserves if needed.

## 12) CI gates (define or align to these)

* Lint & typecheck pass.
* Tests pass; snapshots updated intentionally (require `SNAPSHOT_OK=1`).
* No secrets detected (pre‑commit hook or CI step).
* Bundle size limits for extension unchanged ±5% unless noted.

## 13) File hygiene

* Keep **schemas** versioned (`mvp.v1.json` → `mvp.v2.json`); mappers adapt without breaking clients.
* Move prompts to `prompts/` with small, composable fragments.
* Keep digests HTML deterministic; use template tests.

## 14) Checklists

**PR checklist**

* [ ] Why now / user impact stated
* [ ] Tests updated/added and failing before change
* [ ] Security & privacy review completed
* [ ] Rollback documented
* [ ] Screenshots or sample digest attached

**Release checklist**

* [ ] Version bumped; changelog updated
* [ ] Evals run; accuracy not regressed >1pp
* [ ] Canary digest test email verified

## 15) Glossary for Claude

* **Mapper:** code that maps internal classification → Gmail labels. Not LLM output.
* **Decider:** (rule|gemini|detector) source of classification.
* **Digest:** daily HTML summary; strict schema; deterministic.

---

**Maintenance:** review this file monthly; append observed issues + mitigations. If Claude deviates from these rules, instruct it to re‑read `/claude.md` and restate the North Star before continuing.
