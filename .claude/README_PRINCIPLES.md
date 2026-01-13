# How Core Principles Are Codified for Claude Code

**Created:** 2025-11-13

---

## Three-Tier Strategy

We use a **three-tier documentation strategy** to ensure Claude Code always references the core principles:

### **Tier 1: CLAUDE.md (Root) - Always Read**
**Location:** `/CLAUDE.md` (section 2a)

**What's there:**
- Summary of 5 core principles (1-2 sentences each)
- Quick checks for each principle
- Instruction to validate against principles before writing code

**Why here:**
- Claude Code automatically reads `CLAUDE.md` at the start of every session
- It's part of the "project instructions" that override default behavior
- Provides immediate context without requiring navigation

**When Claude sees this:**
- Every time it starts a new conversation
- When explicitly reminded about project guidelines
- During plan generation (section 1 says "restate North Star")

---

### **Tier 2: .claude/PRINCIPLES_CHECKLIST.md - Quick Reference**
**Location:** `/.claude/PRINCIPLES_CHECKLIST.md`

**What's there:**
- Checkbox-style checklist for each principle
- Code snippet examples
- Decision tree for quick decisions
- Red flags that should trigger principle review

**Why here:**
- Quick reference during active coding
- Checklist format makes it actionable
- Easy to reference: "Check `.claude/PRINCIPLES_CHECKLIST.md`"

**When to use:**
- During feature development (quick validation)
- During code review (systematic checks)
- When unsure about architecture decision

---

### **Tier 3: docs/CORE_PRINCIPLES.md - Deep Dive**
**Location:** `/docs/CORE_PRINCIPLES.md`

**What's there:**
- Full explanation of each principle (2-3 pages each)
- Detailed examples (good vs bad code)
- Canonical examples of applying principles
- Success metrics and anti-patterns

**Why here:**
- Comprehensive reference for complex decisions
- Referenced from CLAUDE.md for "read before major refactors"
- Source of truth for architectural philosophy

**When to use:**
- Before major refactoring
- When adding new concepts
- When architectural decisions affect multiple modules
- During onboarding (for humans and AI)

---

## How Claude Code Will Use This

### **Automatic (Every Session):**
1. Claude reads `CLAUDE.md` → sees section 2a with principles summary
2. Before proposing code, Claude validates against 5 principles
3. In plans, Claude states which principles apply

### **On Request:**
- "Check the principles" → Claude reads `.claude/PRINCIPLES_CHECKLIST.md`
- "Full principle context" → Claude reads `docs/CORE_PRINCIPLES.md`

### **In Code Reviews:**
- Claude can systematically check each principle
- Flag violations with reference to specific principle
- Suggest fixes aligned with principles

---

## Example Workflow

### **User:** "Add spam detection feature"

**Claude's Internal Process:**
1. ✅ Reads `CLAUDE.md` section 2a (automatic)
2. ✅ Checks P1: "Where should this live?" → `concepts/spam_detection.py`
3. ✅ Checks P2: "Does it modify state?" → Yes, name it `detect_and_mark_spam()`
4. ✅ Checks P3: "Add types" → `def detect_spam(email: Email) -> SpamResult`
5. ✅ Checks P4: "Dependencies?" → `Stage("spam", depends_on=["classify"])`
6. ✅ Checks P5: "Tune or refactor?" → New feature, not tuning

**Claude's Response:**
```
I'll add spam detection following core principles:

P1 (Concepts as Rooms): Create `concepts/spam_detection.py`
P2 (Explicit Side Effects): Name function `detect_and_mark_spam()`
P3 (Types): `def detect_spam(email: Email) -> SpamResult`
P4 (Explicit Dependencies): Add to pipeline with `depends_on=["classify"]`
P5 (Debt vs Complexity): This is a new feature, not addressing existing complexity

[Proposes plan with principle-aligned code]
```

---

## Maintenance

### **Update Strategy:**
When principles evolve:

1. **Update Tier 3 first** (`docs/CORE_PRINCIPLES.md`) - source of truth
2. **Update Tier 1** (`CLAUDE.md` section 2a) - summary + checks
3. **Update Tier 2** (`.claude/PRINCIPLES_CHECKLIST.md`) - checklist items

### **Review Cadence:**
- **Weekly:** Validate code against principles (sprint retro)
- **Monthly:** Review if principles need updates (architecture review)
- **Quarterly:** Deep review with lessons learned

---

## Why This Works

### **For Claude Code:**
- ✅ Always sees principles (Tier 1 auto-loaded)
- ✅ Can reference quickly (Tier 2 checklist)
- ✅ Can deep-dive when needed (Tier 3 full docs)

### **For Human Developers:**
- ✅ Single source of truth (`docs/CORE_PRINCIPLES.md`)
- ✅ Quick validation (`.claude/PRINCIPLES_CHECKLIST.md`)
- ✅ Claude enforces principles in code review

### **For Consistency:**
- ✅ Principles are embedded in workflow (not optional)
- ✅ Same checks for humans and AI
- ✅ Clear escalation path (checklist → full docs)

---

## Testing the Setup

### **Verify Claude Reads Principles:**
1. Start new Claude Code session
2. Ask: "What are ShopQ's core architectural principles?"
3. Claude should list all 5 from `CLAUDE.md` section 2a

### **Verify Claude Applies Principles:**
1. Ask: "I want to add user notifications. Where should this code live?"
2. Claude should reference P1 and suggest `concepts/notifications.py`

### **Verify Checklist Access:**
1. Ask: "Check the principles checklist"
2. Claude should read `.claude/PRINCIPLES_CHECKLIST.md`

---

## File Locations Summary

```
/CLAUDE.md
  └─ Section 2a: Core Principles (summary + checks)
     ↓ References
     ↓
/.claude/PRINCIPLES_CHECKLIST.md
  └─ Quick reference checklist
     ↓ References
     ↓
/docs/CORE_PRINCIPLES.md
  └─ Full canonical reference (source of truth)
```

---

## What Changed

**Before:** Principles only in `docs/CORE_PRINCIPLES.md` (Claude might not read)

**After:**
- ✅ Principles summary in `CLAUDE.md` (always read)
- ✅ Quick checklist in `.claude/` (easy reference)
- ✅ Full docs in `docs/` (deep dive)

**Impact:** Claude Code will now validate against principles **automatically** in every session, not just when explicitly asked.

---

**Next Steps:**
1. Test with next feature request (verify Claude references principles)
2. Refine checklist based on usage patterns
3. Add to onboarding docs for new developers

**Canonical Reference:** This strategy is documented here for future reference when updating principles or adding new guidelines.
