# AGENTS.md — Codex configuration for ShopQ (Nov 2025)

## 0) Purpose
Keep Codex aligned with the ShopQ dev guardrails in `/claude.md`
and technical references in `/SHOPQ_REFERENCE.md`.

## 1) Initialization
On startup or reload, Codex should:
1. Read `/claude.md` (do not modify).
2. Restate the **North Star** and confirm the plan → diff → approve → run loop.
3. Reference:
   - Architecture → `/SHOPQ_REFERENCE.md`
   - Runtime policy → `/config/shopq_policy.yaml`
   - Workflow guide → `/DEVELOPER_GUIDE.md`
4. Output a brief “session checklist” confirming compliance.

## 2) Approval Rules
| Action | Needs approval | Notes |
|--------|----------------|------|
| Generate PLAN | ✅ Yes | Always confirm before diffs |
| Write/edit files | ✅ Yes | Apply only after explicit `APPROVED` |
| Run commands | ✅ Yes | All start as DRY_RUN |
| Read docs/config files | ❌ No | Safe |
| Lint/tests | ✅ Yes | DRY_RUN first |

## 3) Session Commands
- `/context` → Re-read `claude.md` and output North Star summary.
- `/verify` → Audit session against `claude.md` (check DRY_RUN, diff size, etc.).
- `/approve` → Apply pending diff after review.

## 4) Diff Rules
- ≤ 200 lines per commit
- Tests updated first
- Docstrings for non-obvious logic
- Never touch `.env` or secrets directories

## 5) Testing
- Require tests that would fail pre-change
- Coverage ≥ 80% for touched modules
- Golden HTML snapshot tests for digest output

## 6) Escalation / Audit
If Codex detects ambiguous instructions or policy conflicts:
> “Request @human review — possible policy violation per claude.md”

---

### 3️⃣ Grant baseline approvals
Run:
