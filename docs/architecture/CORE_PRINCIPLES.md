# ShopQ Core Principles

**Purpose:** Canonical architectural and coding principles that guide all feature work, migrations, and refactoring decisions.

**Last Updated:** 2025-11-13

---

## The Five Core Principles

### 1. **Concepts Are Rooms, Not Hallways**
> *"Every feature should live in one conceptual home, not scattered across layers"*

**What It Means:**
- A "concept" (Feedback, Digest, Classification, etc.) should be understandable by reading **one module**, not hunting through 4+ files
- Related state, actions, invariants, and business logic live together
- Cross-cutting concerns (DB, HTTP, LLM) are adapters injected into the concept, not tangled within it

**Examples:**

✅ **GOOD - Consolidated Concept:**
```python
# concepts/feedback_learning.py
class FeedbackLearning:
    """User Feedback → Pattern Learning → Rule Creation

    Everything about feedback in ONE place:
    - Recording corrections (state)
    - Learning patterns (action)
    - Creating rules (action)
    - Applying rules (action)
    - Invariants (e.g., max 200 rules/user)
    """

    def record_correction(self, ...): ...
    def learn_patterns(self, ...): ...
    def create_rule(self, ...): ...
```

❌ **BAD - Fragmented Concept:**
```python
# api_feedback.py - HTTP endpoint
# feedback_manager.py - Recording logic
# rules_manager.py - Rule CRUD
# rules_engine.py - Rule matching
# To understand feedback: read 4 files, trace hidden calls
```

**When to Apply:**
- Adding a new feature: Create `concepts/{feature_name}.py` as the canonical home
- Refactoring: If understanding a feature requires >2 files, consolidate into a concept module
- Code review: Ask "Is this feature's logic scattered or concentrated?"

**Why It Matters:**
- **Onboarding:** New developers find features in 5 minutes, not 2 hours
- **Maintenance:** Changes touch 1 file, not 4
- **Debugging:** Clear ownership of behavior

**Architecture Audit Impact:** +2 points (Concept Coherence), +1 point (Feature Locality)

---

### 2. **Side Effects Are Loud, Not Sneaky**
> *"Functions that modify state, call APIs, or trigger actions must declare this explicitly"*

**What It Means:**
- Function **names** reveal side effects (e.g., `record_and_learn` not just `record`)
- **Docstrings** list all side effects (DB writes, API calls, state changes)
- **Prefer explicit over implicit:** Split functions that do "one thing + secret thing" into two functions
- **Immutability by default:** Return new objects rather than mutating inputs (use `dataclasses.replace()`)

**Examples:**

✅ **GOOD - Explicit Side Effects:**
```python
def record_and_learn_from_correction(self, ...):
    """
    Record user correction and learn patterns.

    Side Effects:
    - Writes to `corrections` table
    - Writes to `learned_patterns` table
    - Creates rule in `rules` table
    - Modifies future classification behavior
    """
    correction_id = self.record_correction(...)
    self.learn_patterns(correction_id)
    return correction_id
```

❌ **BAD - Hidden Side Effects:**
```python
def record_correction(self, ...):
    """Record user correction."""
    # Hidden surprise: Also triggers learning!
    self._learn_from_correction(...)  # Not in docstring, not in name
```

✅ **GOOD - Immutable Transformation:**
```python
def enrich_entity(entity: Entity) -> EnrichedEntity:
    """Returns NEW enriched entity (does not mutate input)."""
    return EnrichedEntity(
        **entity.__dict__,
        resolved_importance="critical",
        enriched_at=datetime.now()
    )
```

❌ **BAD - Hidden Mutation:**
```python
def enrich_entity(entity: Entity) -> Entity:
    """Enriches entity."""
    entity.resolved_importance = "critical"  # Surprise mutation!
    return entity
```

**When to Apply:**
- Naming functions: If it writes to DB/API, name reflects that (`save_`, `update_`, `trigger_`)
- Writing docstrings: Always include `Side Effects:` section if applicable
- Code review: Ask "Are there hidden side effects not visible in the signature?"

**Why It Matters:**
- **Debugging:** No surprises in production ("Why did this function modify the rules table?")
- **Testing:** Clear which functions need mocking
- **Refactoring:** Safe to move/rename functions without breaking hidden dependencies

**Architecture Audit Impact:** +2 points (Side Effect Visibility), +1 point (Synchronization Verifiability)

---

### 3. **The Compiler Is Your Senior Engineer**
> *"Use types and validation to catch bugs at dev time, not production"*

**What It Means:**
- **Type everything:** Function signatures, return types, intermediate values
- **Validate at boundaries:** API inputs, LLM outputs, database reads
- **Make illegal states unrepresentable:** Use types to enforce ordering (e.g., `ExtractedEntity → ClassifiedEntity → EnrichedEntity`)
- **Fail fast:** Runtime checks should fail loudly at startup or dev time, not silently in production

**Examples:**

✅ **GOOD - Types Enforce Ordering:**
```python
def extract_entities(emails: list[Email]) -> list[ExtractedEntity]:
    """Returns entities with source metadata."""
    ...

def classify_importance(entities: list[ExtractedEntity]) -> list[ClassifiedEntity]:
    """Returns entities with .importance field. Requires ExtractedEntity."""
    ...

def enrich_temporal(entities: list[ClassifiedEntity]) -> list[EnrichedEntity]:
    """Returns entities with .resolved_importance. Requires ClassifiedEntity."""
    ...

# Compiler enforces: extract → classify → enrich
enriched = enrich_temporal(classify_importance(extract_entities(emails)))  # ✅ Type checks
enriched = enrich_temporal(extract_entities(emails))  # ❌ Type error at compile time!
```

❌ **BAD - Hope and Pray:**
```python
def extract_entities(emails) -> list:  # Any list, who knows?
    ...

def enrich_temporal(entities) -> list:  # Needs .importance but no type enforcement
    for e in entities:
        if hasattr(e, 'importance'):  # Runtime check, too late
            e.resolved_importance = ...
```

✅ **GOOD - Validate at Boundaries:**
```python
from pydantic import BaseModel, ValidationError

class LLMClassification(BaseModel):
    category: str
    confidence: float
    reasoning: str

def classify_with_llm(email: Email) -> ClassifiedEmail:
    """Classify email using LLM with validation."""
    raw_response = llm.call(prompt)

    try:
        validated = LLMClassification.model_validate(raw_response)
    except ValidationError as e:
        logger.error(f"LLM output invalid: {e}")
        counter("llm.schema_validation_failures")
        # Fall back to rules
        return classify_with_rules(email)

    return ClassifiedEmail(category=validated.category, ...)
```

❌ **BAD - No Validation:**
```python
def classify_with_llm(email):
    raw_response = llm.call(prompt)
    # Assume it's valid, hope for the best
    return ClassifiedEmail(category=raw_response['category'], ...)  # KeyError in production!
```

**When to Apply:**
- Writing new code: Add type hints to all functions
- Refactoring: Add types to untangled code (especially pipeline stages)
- Code review: Ask "What could go wrong if the input is invalid?"
- Integration points: Always validate external inputs (API, LLM, DB)

**Why It Matters:**
- **Catch bugs early:** Type errors at compile time vs runtime errors in production
- **Refactoring confidence:** Types tell you what breaks when you change things
- **Documentation:** Types are executable documentation
- **Onboarding:** New developers see what each function expects/returns

**Architecture Audit Impact:** +2 points (Synchronization Verifiability), +3 points (Type Safety)

---

### 4. **Synchronizations Are Explicit Contracts, Not Hidden Magic**
> *"If Feature A depends on Feature B, make that dependency visible and verifiable"*

**What It Means:**
- **Dependencies are declared:** Use explicit imports, dependency injection, or pipeline DSL
- **Ordering matters:** If Stage A must run before Stage B, enforce this with types or runtime checks
- **State contracts:** If Stage B expects Stage A to set field X, validate this explicitly
- **No action-at-a-distance:** Avoid global state, hidden callbacks, or implicit couplings

**Examples:**

✅ **GOOD - Explicit Pipeline Dependencies:**
```python
# Declarative: Dependencies are visible
digest_pipeline = Pipeline([
    Stage("extract", EntityExtractor()),
    Stage("classify", ImportanceClassifier(), depends_on=["extract"]),
    Stage("enrich", TemporalEnricher(), depends_on=["classify"]),
    Stage("categorize", DigestCategorizer(), depends_on=["enrich"]),
])

# Runtime validation at startup
digest_pipeline.validate()  # Fails if dependency graph is invalid

# Type validation at runtime
result = digest_pipeline.run(emails)  # Validates inputs/outputs between stages
```

❌ **BAD - Implicit Ordering:**
```python
# Imperative: Dependencies hidden in implementation
def generate_digest(emails):
    entities = extract_entities(emails)
    classified = classify_importance(emails)  # Needs entities but doesn't say so
    enriched = enrich_temporal(classified)    # Needs .importance but no validation
    # If you reorder these, silent breakage in production
```

✅ **GOOD - Validated State Contracts:**
```python
def categorize_entity(entity: EnrichedEntity) -> str:
    """
    Categorize entity into digest section.

    Requires: entity.resolved_importance (from TemporalEnricher)
    """
    if not hasattr(entity, 'resolved_importance'):
        raise ValueError(
            f"Entity missing 'resolved_importance'. "
            f"Did you forget to call TemporalEnricher? "
            f"Entity: {entity.source_subject}"
        )

    if entity.resolved_importance == "critical":
        return "critical"
    ...
```

❌ **BAD - Hope It's There:**
```python
def categorize_entity(entity):
    # Assumes .resolved_importance exists, no validation
    if entity.resolved_importance == "critical":  # AttributeError in production!
        return "critical"
```

✅ **GOOD - Dependency Injection:**
```python
class DigestGenerator:
    def __init__(self, extractor: EntityExtractor, classifier: ImportanceClassifier):
        self.extractor = extractor
        self.classifier = classifier

    def generate(self, emails):
        entities = self.extractor.extract(emails)
        classified = self.classifier.classify(entities)
        # Dependencies are explicit, testable, swappable
```

❌ **BAD - Hidden Global Dependencies:**
```python
class DigestGenerator:
    def generate(self, emails):
        entities = GLOBAL_EXTRACTOR.extract(emails)  # Where did this come from?
        classified = ImportanceClassifier().classify(entities)  # Hidden instantiation
```

**When to Apply:**
- Adding pipeline stages: Declare dependencies explicitly
- Cross-module calls: Use dependency injection, not global imports
- State expectations: Validate required fields at stage boundaries
- Code review: Ask "If I reorder these calls, will it break silently?"

**Why It Matters:**
- **Integration bugs:** Caught at dev time via validation, not production
- **Refactoring:** Clear what depends on what
- **Testing:** Easy to mock dependencies
- **Visualization:** Can generate dependency graphs automatically

**Architecture Audit Impact:** +2 points (Explicit Synchronizations), +3 points (Declarative Composition)

---

### 5. **Production Complexity Is Tuning, Architecture Debt Is Rewrites**
> *"Distinguish between 'needs indexes' (tuning) and 'tangled spaghetti' (debt)"*

**What It Means:**
- **Production complexity** = Normal scaling issues addressable through **configuration/tuning** (indexes, caching, connection pooling)
- **Architecture debt** = Structural problems requiring **rewrites** (God objects, tangled dependencies, no layer separation)
- **Bias toward tuning:** Don't prematurely optimize. Add complexity only when pain is real.
- **Measure first:** Use observability to identify bottlenecks before optimizing

**Examples:**

✅ **GOOD - Production Complexity (Addressable):**
```python
# Problem: Slow query on corrections table
# Solution: Add index (configuration change, not rewrite)
CREATE INDEX idx_corrections_from ON corrections(from_field);

# Problem: LLM calls are slow
# Solution: Add caching (infrastructure change, not rewrite)
@lru_cache(maxsize=1000)
def classify_with_llm(email_hash: str) -> Classification:
    ...

# Problem: Database locked under load
# Solution: Add connection pooling (tuning, not rewrite)
pool = DatabaseConnectionPool(pool_size=10)
```

❌ **BAD - Architecture Debt (Requires Rewrite):**
```python
# Problem: God object mixes HTTP + DB + business logic
class MegaController:
    def handle_request(self, request):
        # Validates input (HTTP concern)
        # Queries database directly (data concern)
        # Runs classification logic (business concern)
        # Formats response (HTTP concern)
        # All tangled together, can't optimize one without touching all

# Problem: Circular dependencies
# classification.py imports rules.py
# rules.py imports feedback.py
# feedback.py imports classification.py
# Can't change one without breaking others
```

✅ **GOOD - Clear Separation (Scales Through Tuning):**
```python
# Layered architecture: Can optimize each layer independently

# Layer 1: HTTP (can add rate limiting, caching headers)
@app.post("/api/classify")
def classify_endpoint(request: ClassifyRequest):
    return classifier.classify(request.emails)

# Layer 2: Business Logic (pure, no I/O, can optimize algorithms)
class EmailClassifier:
    def classify(self, emails: list[Email]) -> list[Classification]:
        ...

# Layer 3: Data Access (can add indexes, connection pooling, read replicas)
class ClassificationRepository:
    def save_classifications(self, classifications):
        ...
```

**Decision Framework:**

| Symptom | Diagnosis | Solution |
|---------|-----------|----------|
| Slow queries | Production Complexity | Add indexes, analyze query plans |
| High latency | Production Complexity | Add caching, connection pooling |
| Hard to understand flow | Architecture Debt | Consolidate concepts, explicit dependencies |
| Changes touch 4+ files | Architecture Debt | Consolidate related logic |
| Can't test in isolation | Architecture Debt | Dependency injection, clearer layers |
| Circular dependencies | Architecture Debt | Refactor module structure |

**When to Apply:**
- Performance issues: Measure first (profiling, logs), then tune (indexes, caching)
- Complexity issues: If "just adding an index" doesn't help, it's architecture debt
- New features: If adding feature requires touching 5+ modules, consider refactoring first
- Code review: Ask "Is this complexity inherent (tuning) or structural (debt)?"

**Why It Matters:**
- **Avoid premature optimization:** Don't add Redis before you need it
- **Avoid technical bankruptcy:** Don't let architecture debt compound
- **Clear prioritization:** Tune for performance, refactor for maintainability
- **Scale confidently:** Clean architecture can handle 100x through tuning alone

**ShopQ Example:**
- ✅ Missing database indexes = Production complexity (add indexes, 1 day)
- ✅ In-memory cache limiting scale = Production complexity (add Redis, 2 days)
- ⚠️ Feedback fragmented across 4 files = Architecture debt (consolidate, 5-7 days)
- ⚠️ Pipeline orchestration is imperative = Architecture debt (add DSL, 10-14 days)

**Architecture Audit Impact:** Foundational - enables correct categorization of all other issues

---

## How to Use These Principles

### In Feature Development
**Before starting:**
1. **Concept check:** Where does this feature live? Create `concepts/{feature}.py` if needed.
2. **Side effect check:** Will this modify state? Name and document it explicitly.
3. **Type check:** What are the inputs/outputs? Add type hints.
4. **Dependency check:** What does this depend on? Make it explicit (injection or declaration).
5. **Complexity check:** Is this tuning or debt? If debt, refactor first.

**During code review:**
- "Is this concept consolidated or fragmented?" (Principle 1)
- "Are side effects explicit?" (Principle 2)
- "Could types catch this bug?" (Principle 3)
- "Are dependencies visible?" (Principle 4)
- "Is this production complexity or architecture debt?" (Principle 5)

### In Architecture Decisions
**Use as tie-breaker:**
- Option A violates Principle 1 (fragments concept) → Choose Option B
- Option A requires rewrite (Principle 5) but Option B is tuning → Choose Option B
- Both options viable → Choose the one that makes dependencies explicit (Principle 4)

**Use for refactoring prioritization:**
1. High debt, high impact → Refactor now (e.g., consolidate feedback)
2. High debt, low impact → Defer (e.g., dependency injection)
3. Production complexity → Tune when pain is real (e.g., add indexes at scale)

### In Migrations
**Validate against principles:**
- Database migration: Does it maintain concept boundaries? (Principle 1)
- Schema change: Are side effects documented? (Principle 2)
- Data transformation: Are types enforced? (Principle 3)
- Service split: Are dependencies explicit? (Principle 4)
- Performance issue: Is it tuning or debt? (Principle 5)

---

## Canonical Examples

### Example 1: Adding a New Feature (Spam Detection)

**Question:** Where should spam detection logic live?

**Apply Principles:**
1. **Principle 1:** Create `concepts/spam_detection.py` - don't scatter across classifier, rules, feedback
2. **Principle 2:** `mark_as_spam_and_learn()` - name reveals it both marks AND learns
3. **Principle 3:** `def detect_spam(email: Email) -> SpamResult` - typed
4. **Principle 4:** Add to pipeline: `Stage("spam", SpamDetector(), depends_on=["classify"])`
5. **Principle 5:** Start simple (rules-based), tune to LLM only if needed

**Result:** Self-contained module, clear dependencies, type-safe, tunable

---

### Example 2: Performance Issue (Slow Corrections Query)

**Question:** Corrections query is slow. Refactor or optimize?

**Apply Principles:**
1. **Principle 5:** Is this production complexity or architecture debt?
   - Query is focused (single table, simple WHERE clause)
   - Code structure is clean (corrections in one module)
   - **Diagnosis:** Production complexity (missing index)

**Solution:** Add index, not refactor
```sql
CREATE INDEX idx_corrections_from_timestamp ON corrections(from_field, timestamp);
```

**Result:** 1 day to fix vs 5 days to refactor unnecessarily

---

### Example 3: Integration Bug (Digest Fails in Production)

**Question:** Categorizer fails with "Entity missing resolved_importance"

**Apply Principles:**
1. **Principle 3:** Type system didn't catch this? Add types.
2. **Principle 4:** Dependencies weren't explicit. Add validation.

**Solution:**
```python
# Before: No validation
def categorize(entity: Entity) -> str:
    return entity.resolved_importance  # Fails if missing

# After: Explicit validation + types
def categorize(entity: EnrichedEntity) -> str:
    """Requires EnrichedEntity (has resolved_importance)."""
    if not hasattr(entity, 'resolved_importance'):
        raise ValueError(f"Entity not enriched: {entity.source_subject}")
    return entity.resolved_importance
```

**Result:** Bug caught at dev time, not production

---

## The Principles Hierarchy

```
Principle 5 (Debt vs Complexity)
    ↓ Determines whether to refactor
    ↓
Principle 1 (Concepts as Rooms)
    ↓ Guides where code lives
    ↓
Principle 4 (Explicit Dependencies)
    ↓ Guides how concepts interact
    ↓
Principle 2 (Explicit Side Effects)
    ↓ Guides how actions are named/documented
    ↓
Principle 3 (Compiler as Senior Engineer)
    ↓ Enforces correctness at dev time
```

**Start with Principle 5** to decide if action is needed, then apply 1-4 to guide implementation.

---

## Success Metrics

**You're following these principles if:**
- ✅ New features take 2-4 hours to understand (not 2-4 days)
- ✅ Integration bugs are caught at dev time (not production)
- ✅ Onboarding takes 1 week (not 3 weeks)
- ✅ Performance issues are solved with tuning (not rewrites)
- ✅ Code reviews focus on business logic (not "where does this go?")

**You're violating these principles if:**
- ❌ "Where does this feature live?" takes >5 minutes to answer
- ❌ Production bugs from hidden side effects happen monthly
- ❌ Adding a pipeline stage takes 2-4 hours of debugging
- ❌ Every performance issue requires architectural changes
- ❌ Code review discussions are about structure, not logic

---

## Automated Validation

**Validation Script:** `scripts/validate_principles.py`

The validation script automatically checks P2 and P3 compliance:

```bash
# Validate entire codebase
python scripts/validate_principles.py

# Validate specific files
python scripts/validate_principles.py shopq/rules_manager.py

# Show detailed violations
python scripts/validate_principles.py --verbose

# Only show errors (not warnings)
python scripts/validate_principles.py --errors-only
```

**What It Checks:**

**P2: Side Effects Are Loud, Not Sneaky**
- Functions with DB writes must document them in docstrings
- Functions with API calls must declare side effects
- Functions that mutate external state must document this
- Function names should reflect side effects (e.g., `save_`, `update_`, `record_`)

**P3: The Compiler Is Your Senior Engineer**
- All function parameters must have type hints (except `self`, `cls`)
- All functions must have return type annotations
- Return types must be specific (e.g., `dict[str, Any]` not `dict`)
- List types must be parameterized (e.g., `list[Entity]` not `list`)

**Pre-commit Integration:**

The validation script runs automatically on commit via pre-commit hook:

```bash
# Install pre-commit hooks
pre-commit install

# Run all hooks manually
pre-commit run --all-files

# Run just principle validation
pre-commit run validate-principles --all-files
```

**Current Status:**

As of 2025-11-13:
- 98 Python files validated
- P2 violations: 9 errors, 166 warnings
- P3 violations: 213 errors, 0 warnings

**Addressing Violations:**

**P2 (Side Effects):**
- Add `Side Effects:` section to docstrings
- List all state modifications (DB writes, API calls, mutations)
- Example:
  ```python
  def record_and_learn(self, correction):
      """
      Record correction and learn patterns.

      Side Effects:
      - Writes to corrections table
      - Writes to learned_patterns table
      - May create rule in rules table
      """
  ```

**P3 (Type Hints):**
- Add type hints to all parameters and return values
- Use specific types (e.g., `dict[str, Any]` not `dict`)
- Example:
  ```python
  def get_rules(user_id: str = "default") -> list[dict[str, Any]]:
      ...
  ```

---

## Maintenance

**Review these principles:**
- **Weekly:** During sprint planning (guide feature decisions)
- **Monthly:** During architecture reviews (assess adherence)
- **Quarterly:** Update with lessons learned

**Last Review:** 2025-11-13
**Next Review Due:** 2025-12-13

**Canonical Reference:** This document (`docs/CORE_PRINCIPLES.md`) is the source of truth for ShopQ architectural philosophy.

---

**Remember:** These aren't rules to slow you down - they're guardrails to help you move fast **sustainably**. When in doubt, ask: "Does this make the code easier to understand, safer to change, and faster to debug?"

If yes, you're following the principles. If no, reconsider the approach.
