# importance_deciders.md — Where “importance” Is Written (Nov 2025)

This audit enumerates every production code path that sets or mutates the `importance` field (critical | time_sensitive | routine). Line numbers use repo-relative paths.

## 1. Assignment Sites

| # | Path:Line | Writer | Notes / Downstream Consumers |
|---|-----------|--------|------------------------------|
| 0 | `shopq/bridge/mapper.py` ⚠️ *Path may be outdated* | `BridgeImportanceMapper.map_email` (feature gate `bridge_mode`) assigns importance using guardrails + `config/mapper_rules.yaml`. | Bridge Mode path (ContextDigest stage) that consumes extension LLM records; runs guardrails first, then deterministic mapper, logging comparisons against legacy patterns. |
| 1 | `shopq/classification/importance_classifier.py:500-525` | `ImportanceClassifier.classify_batch` mutates each email dict with `email["importance"] = importance` after running the pattern matcher. | Primary classification gate for context digest and noise summaries; feeds `ContextDigestGenerator`, tracking DB, and any downstream analytics. |
| 2 | `shopq/entity_extractor.py:197-219` | `RulesExtractor.extract_flight` calls `ImportanceClassifier.classify(...)` and copies the result into `FlightEntity.importance`. | Entities built from critical/time-sensitive emails retain their classification for timeline/ranking. |
| 3 | `shopq/entity_extractor.py:296-312` | `extract_event` sets `EventEntity.importance` via `ImportanceClassifier`. | Ensures event entities honor urgency when `TimelineSynthesizer` and `DigestCategorizer` place them. |
| 4 | `shopq/entity_extractor.py:331-347` | `extract_deadline` classifies bill/payment emails before building `DeadlineEntity`. | Critical for bills showing up in 🚨 Critical digest sections; also influences `timeline.calculate_priority`. |
| 5 | `shopq/entity_extractor.py:373-387` | `extract_reminder` propagates classifier output to `ReminderEntity`. | Keeps reminders in routine vs. time-sensitive buckets for narrative generation. |
| 6 | `shopq/entity_extractor.py:409-419` | `extract_promo` hard-codes `importance = "routine"` for promotional entities. | Guarantees promos never escalate; only affects digest noise summaries. |
| 7 | `shopq/entity_extractor.py:484-519` | `extract_notification` classifies fraud/delivery/job notifications and stores the result on `NotificationEntity`. | Used by `TimelineSynthesizer` to mix notifications with other featured entities. |
| 8 | `shopq/context_digest.py:852-864` | `_fallback_email_summary.MockTimeline` fabricates featured entries with explicit `importance` (critical/time_sensitive) when entity extraction fails. | Supplies `NaturalOpeningGenerator` and fallback HTML with deterministic ordering even without extracted entities. |
| 9 | `shopq/natural_opening.py:240-298` | `_extract_entity_metadata` defaults missing values to `"routine"` and the module’s example timeline seeds explicit importance strings. | Ensures narrative intros never crash on absent data and reflect the correct tone in sample/fallback output. |
|10 | `shopq/importance/learning.py:168-191` | `DigestFeedbackLearner.extract_patterns` persists inferred patterns with `importance` tags derived from `predicted_importance`. | Provides source-of-truth for future guardrail config (`digest_patterns` table) and feeds few-shot prompts. |
|11 | `shopq/importance/learning.py:376-381` | `_update_patterns` writes `importance` back when storing/updating guardrail patterns. | Keeps guardrail precedence accurate when digest feedback promotes/demotes senders or subject motifs. |

> Tests, docs, and debug-only scaffolding (e.g., `tests/test_debug_endpoints.py`, `archive/*`) are excluded because they do not influence runtime state.

## 2. Call Graph (Source → Importance → Consumer)

```
Chrome Extension (gmail.js → modules/classifier.js)
  └─ POST /api/organize → shopq/api_organize.py
       ├─ Legacy path: shopq/memory_classifier.MemoryClassifier
       │     ├─ shopq/rules_engine.RulesEngine (rules-first)
       │     └─ shopq/vertex_gemini_classifier.VertexGeminiClassifier (LLM fallback)
       └─ Refactored path: shopq/digest/pipeline_wrapper.classify_batch_refactored
             └─ domain/classify.classify_email (LLM + rules fallback)
                 └─ Outputs Gmail labels (no importance yet)

Chrome Extension (context-digest.js) / CLI
  └─ POST /api/context-digest → shopq/context_digest.ContextDigestGenerator
       ├─ Stage 1:
           - (feature gate `bridge_mode`) shopq/bridge/mapper.BridgeImportanceMapper → guardrails + mapper_rules
           - Legacy path: shopq/classification/importance_classifier.ImportanceClassifier.classify_batch
       │     └─ Writes `email["importance"]`, logs via shopq/observability + shopq/email_tracker
       ├─ Stage 2: shopq/entity_extractor.HybridExtractor.extract_from_emails
       │     └─ Each entity copies the assigned importance (Rows 2‑7 above)
       ├─ Stage 3: shopq/timeline_synthesizer.TimelineSynthesizer.build
       │     └─ Importance drives priority scores and featured ordering
       ├─ Stage 4: shopq/digest_categorizer.DigestCategorizer.categorize
       │     └─ Importance determines critical vs. today/coming_up fallback
       └─ Render: shopq/digest_renderer + shopq/natural_opening + shopq/card_renderer
             └─ Fallback path uses `_fallback_email_summary` (Row 8) when extraction fails

Feedback Loop:
  Digest HTML → Users click "Why is this here?" / provide feedback
    └─ shopq/api_feedback.py → shopq/feedback_manager.FeedbackManager
         └─ shopq/importance/learning.DigestFeedbackLearner (Rows 10‑11) records importance-tagged patterns
              └─ Patterns feed prompts (shopq/vertex_gemini_classifier) + future guardrail configs
```

Keeping future changes constrained to these lines ensures CI can diff new importance writers against this canon as required by the migration plan.
