# Task-Flow Lens: Feedback Learning Loop

> **Manually maintained** - Last updated: 2025-12-04

## Purpose

Answer: **"What happens when a user corrects a label?"**

Max 8 steps, showing how feedback becomes a rule.

```mermaid
sequenceDiagram
    autonumber
    participant User as User in Gmail
    participant Content as Content Script<br/>content.js
    participant API as /api/feedback
    participant FeedMgr as Feedback Learning<br/>feedback_learning.py
    participant RulesMgr as Rules Engine<br/>rules_engine.py
    participant DB as mailq.db

    User->>User: Changes label (Critical → Routine)
    Content->>Content: Detect label change (MutationObserver)
    Content->>API: POST {thread_id, old_label, new_label}

    API->>FeedMgr: process_feedback(...)
    FeedMgr->>DB: Log feedback event
    FeedMgr->>FeedMgr: Check if pattern warrants rule

    alt High-confidence pattern (3+ corrections)
        FeedMgr->>RulesMgr: create_rule(pattern, label)
        RulesMgr->>DB: INSERT INTO rules
        RulesMgr-->>FeedMgr: Rule created (ID)
        FeedMgr-->>API: {rule_created: true}
    else Isolated correction
        FeedMgr-->>API: {logged: true, rule_created: false}
    end

    API-->>Content: {success: true}
    Content-->>User: Silent (no UI change)
```

## Key Contracts

1. **Content → API**: `FeedbackEvent` with label change
2. **API → Feedback Manager**: Process correction
3. **Feedback → Rules Manager**: Create rule if warranted
4. **Rules Manager → DB**: Persist new rule

## Learning Thresholds

- **Min corrections for rule**: 3 similar patterns
- **Rule confidence**: 0.95 (highest)
- **Rule precedence**: User rules override LLM

---

**See also**: [CLASSIFICATION_FLOW.md](CLASSIFICATION_FLOW.md) for full classification pipeline

**Key files**:
- `mailq/api/routes/feedback.py` - API endpoint
- `mailq/classification/feedback_learning.py` - Feedback processing
- `mailq/classification/rules_engine.py` - Rule management
