# Architecture Principles Checklist

**Quick reference for Claude Code during feature work and code review**

---

## Before Writing Any Code

### ✅ P1: Concepts Are Rooms, Not Hallways
- [ ] Does this feature have ONE conceptual home?
- [ ] Can I understand it by reading 1-2 files max?
- [ ] Am I consolidating related logic, not scattering it?

**If NO:** Create `concepts/{feature_name}.py` as canonical home

---

### ✅ P2: Side Effects Are Loud, Not Sneaky
- [ ] Do function names reveal side effects? (`save_`, `update_`, `record_and_learn_`)
- [ ] Are side effects documented in docstrings?
- [ ] Am I using immutable transformations over mutations?

**Add to every state-modifying function:**
```python
"""
Side Effects:
- Writes to {table} table
- Calls {API}
- Modifies {state}
"""
```

---

### ✅ P3: The Compiler Is Your Senior Engineer
- [ ] Are all functions typed? (`def foo(x: Type) -> ReturnType`)
- [ ] Am I validating at boundaries? (API inputs, LLM outputs)
- [ ] Could types catch integration bugs at compile time?

**For pipelines, use typed stages:**
```python
ExtractedEntity → ClassifiedEntity → EnrichedEntity
```

---

### ✅ P4: Synchronizations Are Explicit Contracts
- [ ] Are dependencies declared explicitly?
- [ ] Do I validate state contracts (required fields)?
- [ ] Would reordering break silently or fail fast?

**For pipelines:**
```python
Stage("enrich", TemporalEnricher(), depends_on=["classify"])
```

**For required fields:**
```python
if not hasattr(entity, 'resolved_importance'):
    raise ValueError(f"Entity not enriched: {entity.source_subject}")
```

---

### ✅ P5: Production Complexity vs Architecture Debt
- [ ] Is this issue fixable with tuning (indexes, caching)?
- [ ] Or does it require refactoring (tangled logic)?
- [ ] Am I measuring before optimizing?

**Decision framework:**
- Slow query → Add index (production complexity)
- Fragmented concept → Consolidate module (architecture debt)
- Hard to test → Dependency injection (architecture debt)

---

## Code Review Checklist

When reviewing code (or having code reviewed):

1. **P1 Check:** "Where does this feature live? Is it consolidated?"
2. **P2 Check:** "Are side effects explicit in name and docs?"
3. **P3 Check:** "Could types catch this bug?"
4. **P4 Check:** "Are dependencies visible? Can I see the flow?"
5. **P5 Check:** "Is this production tuning or architecture debt?"

---

## When to Read Full Docs

**Read [`docs/CORE_PRINCIPLES.md`](../docs/CORE_PRINCIPLES.md) before:**
- Major refactoring (consolidating modules, changing architecture)
- Adding new concepts to the codebase
- Architectural decision that affects multiple modules
- Unclear whether to refactor or tune

**This checklist is for:** Quick validation during normal feature work

---

## Red Flags (Stop and Reconsider)

🚨 **If you see these, pause and apply principles:**

1. "To understand this, read these 4 files..." → Violates P1
2. "This function has hidden side effects..." → Violates P2
3. "This failed in production but types didn't catch it..." → Violates P3
4. "I have to trace through global state..." → Violates P4
5. "Every perf issue requires a rewrite..." → Violates P5

---

## Quick Decision Tree

```
Starting new work?
  ↓
WHERE does this live? (P1)
  ↓
Does it modify state? → Name it explicitly (P2)
  ↓
What are the types? → Add them (P3)
  ↓
What does it depend on? → Make explicit (P4)
  ↓
Performance issue? → Tune first, refactor only if needed (P5)
```

---

**Last Updated:** 2025-11-13
**Full Reference:** [`docs/CORE_PRINCIPLES.md`](../docs/CORE_PRINCIPLES.md)
