# Task-Flow Lens: Daily Digest Generation

> **Manually maintained** - Last updated: 2025-12-04

## Purpose

Answer: **"What happens when a daily digest is generated?"**

V2 7-stage pipeline from trigger to Gmail inbox.

```mermaid
sequenceDiagram
    autonumber
    participant Trigger as Alarm/Manual Trigger
    participant API as /api/context-digest
    participant Extract as Entity Extractor<br/>entity_extractor.py
    participant Import as Importance Classifier<br/>importance_mapping/
    participant Temporal as Temporal Decay<br/>temporal.py
    participant Section as Section Assignment<br/>section_assignment.py
    participant Narrative as Narrative Builder<br/>narrative.py
    participant Render as Hybrid Renderer<br/>hybrid_digest_renderer.py
    participant Verify as Narrative Verifier<br/>narrative_verifier.py
    participant Gmail as Gmail API

    Trigger->>API: POST /api/context-digest

    Note over API,Extract: Stage 1: Extraction
    API->>Extract: extract_entities(emails)
    Extract-->>API: entities (flights, events, deadlines)

    Note over API,Import: Stage 2: Importance
    API->>Import: classify_importance(entities)
    Import-->>API: critical/time_sensitive/routine

    Note over API,Temporal: Stage 3: Temporal Decay
    API->>Temporal: apply_decay(importance, time_distance)
    Temporal-->>API: decayed importance scores

    Note over API,Section: Stage 4: Section Assignment
    API->>Section: assign_sections(entities)
    Section-->>API: NOW/COMING_UP/WORTH_KNOWING

    Note over API,Narrative: Stage 5: Narrative
    API->>Narrative: build_narrative(sections)
    Narrative-->>API: natural language summaries

    Note over API,Render: Stage 6: Rendering
    API->>Render: render_digest(sections, narrative)
    Render-->>API: HTML digest

    Note over API,Verify: Stage 7: Verification
    API->>Verify: verify_narrative(html, sources)
    Verify-->>API: verified HTML (hallucinations flagged)

    API->>Gmail: Send email (to: user, html: ...)
    Gmail-->>API: Message ID
    API-->>Trigger: {success: true, message_id}
```

## V2 Pipeline Stages

| Stage | Component | Purpose |
|-------|-----------|---------|
| 1. Extraction | `entity_extractor.py` | Extract structured entities from emails |
| 2. Importance | `importance_mapping/` | Classify as critical/time_sensitive/routine |
| 3. Temporal | `temporal.py` | Apply time-based decay to importance |
| 4. Section | `section_assignment.py` | Assign to NOW/COMING_UP/WORTH_KNOWING |
| 5. Narrative | `narrative.py` | Generate natural language summaries |
| 6. Rendering | `hybrid_digest_renderer.py` | Create HTML digest with cards |
| 7. Verification | `narrative_verifier.py` | Check for hallucinations |

## Key Files

| Component | File Path |
|-----------|-----------|
| API Route | `shopq/api/routes/digest.py` |
| Context Builder | `shopq/digest/context_digest.py` |
| Entity Extractor | `shopq/digest/entity_extractor.py` |
| Importance Mapper | `shopq/classification/importance_mapping/mapper.py` |
| Temporal Decay | `shopq/classification/temporal.py` |
| Section Assignment | `shopq/digest/section_assignment.py` |
| Narrative Builder | `shopq/digest/narrative.py` |
| Hybrid Renderer | `shopq/digest/hybrid_digest_renderer.py` |
| Narrative Verifier | `shopq/digest/narrative_verifier.py` |
| Template | `shopq/digest/templates/digest_v2.html.j2` |

## Metrics

- **Latency**: ~2-5s (depends on email volume)
- **LLM Cost**: ~$0.01/digest (narrative + verification)
- **Frequency**: Daily or on-demand

---

**See also**: [CLASSIFICATION_FLOW.md](CLASSIFICATION_FLOW.md) for classification before digest
