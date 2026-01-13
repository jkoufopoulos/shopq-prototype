# MailQ User Stories

**Purpose**: Formal user stories with acceptance criteria for MailQ features, extracted from roadmaps and organized by priority.

**Last Updated**: 2025-11-10

---

## NOW (MVP - 20-40 users)

### US-001: Calendar Events Never Misclassified

**Priority**: P0
**Status**: ✅ DONE (2025-11-10)
**Effort**: 2 days
**Owner**: Claude + Justin

**User Story**:
> As a busy professional,
> I want calendar invitations always classified as type=event,
> So that I never miss important meetings due to classification errors.

**Acceptance Criteria**:
- [x] Google Calendar invites → type=event (≥95% accuracy)
- [x] Outlook calendar invites → type=event (≥95% accuracy)
- [x] Yahoo/Apple calendar invites → type=event (≥95% accuracy)
- [x] Type mapper processes <1ms per email
- [x] Zero additional LLM calls for calendar events
- [x] Tests: 36/36 passing (unit + regression)
- [x] False positive rate ≤1% (actual: 0.45%)

**Out of Scope**:
- Receipts, shipping notifications (Phase 2)
- User overrides for type mapper rules (P5)
- Non-calendar event types

**Technical Implementation**:
- Module: `mailq/type_mapper.py`
- Config: `config/type_mapper_rules.yaml`
- Integration: `mailq/memory_classifier.py:60-83`
- Tests: `tests/test_type_mapper*.py`

**Reference**: `docs/TYPE_MAPPER_IMPLEMENTATION_SUMMARY.md`

---

### US-002: Temporal Decay for Events

**Priority**: P0
**Status**: ✅ DONE (2025-11-10)
**Effort**: 3 days
**Owner**: Claude + Justin

**User Story**:
> As a user reviewing my daily digest,
> I want past events to automatically disappear from my digest,
> So that I only see relevant upcoming events and don't waste time on expired items.

**Acceptance Criteria**:
- [x] Events with end_time in the past are hidden from digest
- [x] Events without end_time expire based on start_time
- [x] Imminent events (±1h) escalated to CRITICAL section
- [x] Upcoming events (≤7 days) → COMING UP section
- [x] Distant events (>7 days) → WORTH KNOWING section
- [x] Tests: 49/49 passing (unit + integration + e2e)
- [x] Timezone handling correct
- [x] Grace period (1 hour) applied consistently

**Out of Scope**:
- User-specific timezone preferences (future)
- Holiday/weekend awareness (future)
- Recurring event handling (future)
- Custom grace periods per user (future)

**Technical Implementation**:
- Module: `mailq/temporal_enrichment.py`, `mailq/temporal_decay.py`
- Config: `config/mailq_policy.yaml` (grace_period_hours, active_window_hours, etc.)
- Integration: `mailq/digest_formatter.py:64-80`
- Tests: `tests/test_temporal*.py`

**Reference**: `docs/TESTING_COMPLETE_SUMMARY.md`

---

### US-003: Deterministic Digest Rendering

**Priority**: P0
**Status**: IN PROGRESS
**Effort**: 2 days

**User Story**:
> As a MailQ user,
> I want my digest to look the same every time I view it for the same set of emails,
> So that I can trust the digest won't randomly change or show different information.

**Acceptance Criteria**:
- [ ] Pydantic `Classification` contract enforced at API boundaries (≥99.5%)
- [ ] Digest renders from versioned DTO (`digest_dto_v3`) only
- [ ] Snapshot tests ensure byte-identical HTML for same inputs
- [ ] All Gmail deep-links generated via centralized link builder
- [ ] No LLM prose in digest body (template-based only)
- [ ] Contract validation tests pass

**Out of Scope**:
- LLM-generated summaries (Agent v3, LATER)
- Dynamic content based on user preferences
- Personalized greeting messages

**Technical Implementation**:
- Module: `mailq/digest_formatter.py`, `mailq/card_renderer.py`
- Schema: `shared/schemas/classification.json`
- Tests: TBD (snapshot tests)

**Reference**: `docs/MVP_ROADMAP.md` (Section 1)

---

### US-004: Bridge Mode LLM Classification with Mapper Rules

**Priority**: P0
**Status**: NOT STARTED
**Effort**: 3 days

**User Story**:
> As a MailQ operator,
> I want to use LLM classification with deterministic type mapper overrides,
> So that I get the best of both worlds: LLM flexibility and rule-based consistency.

**Acceptance Criteria**:
- [ ] Extension's LLM output mapped to importance via ≤20 `mapper_rules.yaml` rules
- [ ] 3-day shadow period logs `{llm_mapped vs patterns}` with model/prompt versions
- [ ] LLM-mapped beats patterns on critical precision without recall collapse
- [ ] OTP in CRITICAL == 0
- [ ] Event-newsletter noise ≤2%
- [ ] Weekday/weekend drift monitored and within acceptable range

**Out of Scope**:
- User-specific mapper rules (P5)
- Dynamic rule generation (Agent v1)
- Confidence-based routing (P4)

**Technical Implementation**:
- Module: `mailq/mapper.py`
- Config: `config/mapper_rules.yaml` (to be created)
- Integration: `mailq/memory_classifier.py`
- Tests: TBD

**Reference**: `docs/MVP_ROADMAP.md` (Section 2)

---

### US-005: Centralized Guardrails with Precedence

**Priority**: P0
**Status**: NOT STARTED
**Effort**: 2 days

**User Story**:
> As a MailQ user,
> I want sensitive emails (OTP codes, verification emails) to never appear in my digest,
> So that I can feel confident my security isn't compromised by the digest.

**Acceptance Criteria**:
- [ ] `guardrails.yaml` created with:
  - `never_surface` list (OTP, verification codes)
  - `force_critical` list (fraud, phishing, password-reset)
  - `force_non_critical` list (calendar auto-responses, event newsletters)
- [ ] Precedence enforced: `never > force_critical > force_non_critical`
- [ ] Zero behavior drift on golden set (all tests pass)
- [ ] Table tests for all rules pass
- [ ] CI guard enabled and passing

**Out of Scope**:
- User-specific guardrails (P5)
- ML-based guardrail detection
- Confidence-based filtering

**Technical Implementation**:
- Config: `config/guardrails.yaml` (to be created)
- Module: TBD (new guardrails module or refactor prefilter)
- Tests: TBD (table tests + CI guard)

**Reference**: `docs/MVP_ROADMAP.md` (Section 3), `docs/CLASSIFICATION_REFACTOR_PLAN.md` (Phase 1)

---

### US-006: Monotonic Post-Processing (No Surprises)

**Priority**: P0
**Status**: NOT STARTED
**Effort**: 2 days

**User Story**:
> As a MailQ developer,
> I want importance to only be up-ranked by deterministic rules or down-ranked by confidence,
> So that classification behavior is predictable and doesn't drift over time.

**Acceptance Criteria**:
- [ ] Deterministic up-ranks implemented:
  - Deadline ≤48h → `time_sensitive`
  - Event ≤7d → `time_sensitive`
  - Fraud/phishing → `critical`
- [ ] Confidence-based down-ranks implemented:
  - If `confidence < route_threshold` → down-rank to Everything Else
- [ ] No other importance mutations allowed
- [ ] CI mutation guard test passes
- [ ] Importance distribution stays within ±5pp of baseline
- [ ] No heuristic "feels urgent" logic

**Out of Scope**:
- ML-based importance adjustment
- User-specific importance thresholds (P5)
- Dynamic thresholds based on user behavior

**Technical Implementation**:
- Module: TBD (post-processor or mapper refactor)
- Config: `config/mailq_policy.yaml` (route_threshold)
- Tests: TBD (mutation guard + distribution tests)

**Reference**: `docs/MVP_ROADMAP.md` (Section 4)

---

### US-007: Model/Prompt Versioning & Rollback

**Priority**: P0
**Status**: NOT STARTED
**Effort**: 1 day

**User Story**:
> As a MailQ operator,
> I want every classification to be logged with model and prompt versions,
> So that I can rollback to previous versions if classification quality degrades.

**Acceptance Criteria**:
- [ ] `model_name`, `model_version`, `prompt_version` logged in 100% of classifications
- [ ] Shadow + replay triggered on any model/prompt change
- [ ] Rollback triggers defined:
  - FP budget exceeded
  - Latency/cost spike
  - Critical precision drop
- [ ] Rollback runbook documented
- [ ] Canary thresholds defined

**Out of Scope**:
- Automatic rollback (manual for MVP)
- A/B testing framework
- Multi-model comparison

**Technical Implementation**:
- Module: `mailq/vertex_gemini_classifier.py` (add version logging)
- Config: `config/rollback_conditions.yaml` (to be created or update existing)
- Documentation: `docs/ROLLBACK_CONDITIONS.md`

**Reference**: `docs/MVP_ROADMAP.md` (Section 5)

---

### US-008: User Overrides with Explainability

**Priority**: P0
**Status**: NOT STARTED
**Effort**: 3 days

**User Story**:
> As a MailQ user,
> I want to override incorrect classifications and see why each email was categorized,
> So that I can quickly fix mistakes and understand MailQ's reasoning.

**Acceptance Criteria**:
- [ ] User Overrides (P5) apply after LLM/mapper/guardrails and before digest sectioning
- [ ] Cap to ≤200 overrides/user with expiry
- [ ] "Why is this here?" explainer shown for every card with `{importance, reason, source}`
- [ ] Overrides stored in `user_overrides` table (thread-level)
- [ ] Overrides apply in ≤100ms
- [ ] Override count enforced per user
- [ ] Expiry logic works correctly (e.g., 30 days)

**Out of Scope**:
- Sender-level overrides (future)
- Bulk override operations
- Override sharing between users
- Machine learning from overrides (Agent v1)

**Technical Implementation**:
- Database: `user_overrides` table (thread_id, user_id, importance, type, expires_at)
- Module: TBD (overrides processor)
- Integration: Apply before `digest_formatter.py:categorize()`
- Tests: TBD (override application + expiry + cap)

**Reference**: `docs/MVP_ROADMAP.md` (Section 6)

---

### US-009: Multi-User Tenancy

**Priority**: P0
**Status**: NOT STARTED
**Effort**: 2 days

**User Story**:
> As a MailQ user,
> I want my data completely isolated from other users,
> So that I can trust no one else can see my emails or rules.

**Acceptance Criteria**:
- [ ] `user_id` column added to all relevant tables (NOT NULL):
  - `rules`, `feedback`, `corrections`, `fewshot`, `tracking`, `user_overrides`
- [ ] Composite keys created: `(user_id, thread_id)`, `(user_id, rule_id)`, etc.
- [ ] Backfill existing rows with owner user ID
- [ ] Migration script created and tested
- [ ] Tenancy guards in every query (no cross-user leakage)
- [ ] Unit tests for cross-tenant leakage pass
- [ ] Index created: `(user_id, updated_at)` for fast per-user scans

**Out of Scope**:
- Shared rules between users
- Admin access to all users' data (security feature)
- Team/organization accounts

**Technical Implementation**:
- Database: Migration script to add `user_id` columns
- Module: All database queries updated to filter by `user_id`
- Tests: TBD (cross-tenant leakage tests)

**Reference**: `docs/LONGTERM_ROADMAP.md` (NOW section)

---

### US-010: Digest QA Privacy & Retention

**Priority**: P0
**Status**: NOT STARTED
**Effort**: 1 day

**User Story**:
> As a MailQ user,
> I want my digest artifacts to be automatically deleted after 14 days,
> So that my email data isn't stored indefinitely.

**Acceptance Criteria**:
- [ ] Anonymize/truncate artifacts for non-owner users (mask sender/subject, drop bodies)
- [ ] Retention policy defined (e.g., 14 days)
- [ ] Cleanup job created and scheduled
- [ ] Cleanup job tested (deletes old artifacts correctly)
- [ ] Privacy switches documented

**Out of Scope**:
- User-configurable retention periods
- Export before deletion
- Long-term analytics storage

**Technical Implementation**:
- Database: Add `created_at` to digest artifacts tables
- Module: Cleanup job script (scheduled via cron or Cloud Scheduler)
- Tests: TBD (retention + anonymization tests)

**Reference**: `docs/LONGTERM_ROADMAP.md` (NOW section)

---

### US-011: Granular OAuth Scopes

**Priority**: P0
**Status**: NOT STARTED
**Effort**: 1 day

**User Story**:
> As a privacy-conscious user,
> I want to use MailQ with read-only access by default,
> So that I can trust MailQ won't modify my emails without my explicit permission.

**Acceptance Criteria**:
- [ ] MVP ships `gmail.readonly` only
- [ ] `gmail.modify` is opt-in for Smart labels feature
- [ ] `gmail.send` is NOT requested (no sending emails on user's behalf)
- [ ] Onboarding modal explains scopes and storage clearly
- [ ] Scope upgrade flow documented
- [ ] Tests verify only readonly operations work without modify scope

**Out of Scope**:
- Draft creation (`gmail.send` scope)
- Calendar write access (Agent v2)
- Contacts access

**Technical Implementation**:
- Chrome Extension: OAuth scope request flow
- Backend: Scope validation middleware
- Documentation: Onboarding copy + trust narrative

**Reference**: `docs/MVP_ROADMAP.md` (User-Trust & Permission Model), `docs/TRUST_THREATS_AND_MITIGATIONS.md`

---

### US-012: Rollback Conditions Documentation

**Priority**: P0
**Status**: NOT STARTED
**Effort**: 1 day

**User Story**:
> As a MailQ operator,
> I want clear documented thresholds for when to rollback,
> So that I can act quickly when classification quality degrades.

**Acceptance Criteria**:
- [ ] Document exact thresholds:
  - OTP in CRITICAL > 0
  - Critical precision drop ≥5pp
  - P95 latency spike >2x baseline
  - P95 cost spike >2x baseline
  - Invalid JSON rate >1%
- [ ] Runbook created with steps:
  - Which feature flags to flip
  - How to revert model/prompt versions
  - How to re-enable once green
- [ ] Rollback procedure tested (dry run)
- [ ] Monitoring alerts configured

**Out of Scope**:
- Automatic rollback (manual for MVP)
- Gradual rollback (instant for MVP)

**Technical Implementation**:
- Documentation: `docs/ROLLBACK_CONDITIONS.md` (update)
- Monitoring: Cloud Logging alerts + dashboards
- Runbook: Step-by-step rollback instructions

**Reference**: `docs/LONGTERM_ROADMAP.md` (NOW section)

---

## NEXT (Stabilize Cohort, Scale to Few Hundred Users)

### US-013: Thread-Level Overrides (P5)

**Priority**: P1
**Status**: NOT STARTED
**Effort**: 3 days
**Depends On**: US-008 (User Overrides MVP)

**User Story**:
> As a MailQ user,
> I want to override the importance/type for specific email threads,
> So that future emails in that thread are classified correctly.

**Acceptance Criteria**:
- [ ] Thread-level overrides stored in `user_overrides` table
- [ ] Overrides apply to all messages in thread (not just one message)
- [ ] Override UI in Chrome extension (right-click → override)
- [ ] Overrides sync between devices
- [ ] Tests for thread-level application

**Out of Scope**:
- Sender-level overrides
- Pattern-based overrides
- Bulk operations

**Technical Implementation**:
- Database: `user_overrides` table with `thread_id` column
- Chrome Extension: UI for override creation
- Backend API: `/overrides/` endpoints

**Reference**: `docs/LONGTERM_ROADMAP.md` (NEXT section)

---

### US-014: Exponential Backoff & Jitter

**Priority**: P1
**Status**: NOT STARTED
**Effort**: 1 day

**User Story**:
> As a MailQ system,
> I want to gracefully handle Gmail API rate limits with exponential backoff,
> So that I don't bombard Gmail with requests when throttled.

**Acceptance Criteria**:
- [ ] Exponential backoff implemented for Gmail API calls
- [ ] Jitter added to prevent thundering herd
- [ ] Max retry count: 3
- [ ] Base delay: 1s, max delay: 16s
- [ ] Tests for backoff behavior

**Out of Scope**:
- Circuit breaker pattern (future)
- Request queuing (US-015)

**Technical Implementation**:
- Module: Gmail API client wrapper
- Library: Use `backoff` or implement custom
- Tests: Mock Gmail API errors + verify retry behavior

**Reference**: `docs/LONGTERM_ROADMAP.md` (NEXT section)

---

### US-015: LLM Extraction Back-Pressure & Queue

**Priority**: P1
**Status**: NOT STARTED
**Effort**: 2 days

**User Story**:
> As a MailQ system,
> I want to queue LLM classification requests when under load,
> So that I don't drop requests or timeout during traffic spikes.

**Acceptance Criteria**:
- [ ] Small queue implemented (e.g., 100 items)
- [ ] Back-pressure signals when queue is full
- [ ] FIFO ordering (or priority-based)
- [ ] Queue metrics logged (depth, wait time)
- [ ] Tests for queue behavior under load

**Out of Scope**:
- Distributed queue (RabbitMQ, Redis)
- Persistent queue (in-memory for MVP)
- Priority scheduling

**Technical Implementation**:
- Module: Queue manager (in-memory Python queue)
- Integration: LLM classifier wrapper
- Tests: Load testing + queue behavior

**Reference**: `docs/LONGTERM_ROADMAP.md` (NEXT section)

---

### US-016: SQLite to Postgres Migration

**Priority**: P1
**Status**: NOT STARTED
**Effort**: 3 days

**User Story**:
> As a MailQ operator,
> I want to migrate from SQLite to Postgres when we hit scaling limits,
> So that we can support hundreds of concurrent users.

**Acceptance Criteria**:
- [ ] Flip point threshold defined (e.g., >50 users, >10k emails/day)
- [ ] Migration script created (schema + data)
- [ ] Postgres schema matches SQLite schema
- [ ] All queries tested against Postgres
- [ ] Rollback plan documented
- [ ] Zero downtime migration (read replica cutover)

**Out of Scope**:
- NoSQL databases
- Sharding
- Read replicas (initial deployment)

**Technical Implementation**:
- Database: Postgres (Cloud SQL or self-hosted)
- Migration: Alembic or custom script
- Testing: Dual-write + verification

**Reference**: `docs/LONGTERM_ROADMAP.md` (NEXT section)

---

### US-017: Nightly Golden Set Replay

**Priority**: P1
**Status**: NOT STARTED
**Effort**: 2 days

**User Story**:
> As a MailQ operator,
> I want to automatically run golden set validation every night,
> So that I catch classification drift before it affects users.

**Acceptance Criteria**:
- [ ] Nightly job runs golden set replay
- [ ] Drift alarms trigger if importance distribution changes ±5pp
- [ ] CI fails if Gmail labels aren't actually applied (Gmail reality test)
- [ ] Results logged and dashboarded
- [ ] Alert sent to team if drift detected

**Out of Scope**:
- Real-time drift detection
- User-specific golden sets
- Automatic remediation

**Technical Implementation**:
- Script: `scripts/nightly_golden_set_replay.sh`
- Scheduler: Cron or Cloud Scheduler
- Monitoring: Cloud Logging + alerting

**Reference**: `docs/LONGTERM_ROADMAP.md` (NEXT section), `docs/MVP_ROADMAP.md` (Operationalize the Loop)

---

### US-018: Agent v0 - Suggested Next Steps

**Priority**: P2
**Status**: NOT STARTED
**Effort**: 5 days

**User Story**:
> As a MailQ user,
> I want to see suggested next steps based on my emails and calendar,
> So that I can act on important tasks without manually reviewing everything.

**Acceptance Criteria**:
- [ ] Advice-only mode (no writes)
- [ ] Suggestions based on:
  - Extracted entities (deadlines, events, tasks)
  - Calendar events (read-only)
  - Email content (context-aware)
- [ ] "Suggested Next Steps" section in digest
- [ ] 3-5 suggestions per digest
- [ ] Each suggestion has clear CTA (what to do)
- [ ] No hallucinations (all suggestions grounded in email data)

**Out of Scope**:
- Automatic actions (Agent v1)
- Calendar write access (Agent v2)
- Draft email creation

**Technical Implementation**:
- Module: Agent planner (LLM-based)
- Integration: Digest formatter (new section)
- Tests: Suggestion quality + grounding tests

**Reference**: `docs/LONGTERM_ROADMAP.md` (NEXT section)

---

## LATER (Scale, Canary, Agentization)

### US-019: Canary Rollout with Auto-Rollback

**Priority**: P2
**Status**: NOT STARTED
**Effort**: 4 days

**User Story**:
> As a MailQ operator,
> I want to gradually roll out new features with automatic rollback,
> So that I can catch issues before they affect all users.

**Acceptance Criteria**:
- [ ] Canary rollout: 10% → 50% → 100%
- [ ] Auto-rollback triggers:
  - Error rate >5%
  - Latency spike >2x
  - Critical precision drop >5pp
- [ ] Rollback happens automatically within 5 minutes
- [ ] Rollback notification sent to team
- [ ] Feature flags control rollout percentage

**Out of Scope**:
- Blue/green deployment
- A/B testing framework
- User-level targeting (random assignment for MVP)

**Technical Implementation**:
- Module: Feature flag system (LaunchDarkly or custom)
- Monitoring: Real-time metrics + auto-rollback logic
- Tests: Rollback simulation

**Reference**: `docs/LONGTERM_ROADMAP.md` (LATER section)

---

### US-020: Postgres + Worker Tier

**Priority**: P2
**Status**: NOT STARTED
**Effort**: 5 days
**Depends On**: US-016 (Postgres migration)

**User Story**:
> As a MailQ system,
> I want to scale horizontally with worker processes,
> So that I can handle thousands of concurrent users.

**Acceptance Criteria**:
- [ ] Postgres as primary database
- [ ] Worker tier for LLM classification (background jobs)
- [ ] Job queue (Redis or Cloud Tasks)
- [ ] Horizontal scaling (N workers)
- [ ] Load balancer distributes traffic
- [ ] Health checks for workers

**Out of Scope**:
- Auto-scaling (manual scaling for MVP)
- Multi-region deployment
- CDN for static assets

**Technical Implementation**:
- Database: Postgres (Cloud SQL)
- Workers: Cloud Run or Kubernetes
- Queue: Cloud Tasks or Redis

**Reference**: `docs/LONGTERM_ROADMAP.md` (LATER section)

---

### US-021: Agent v1 - Follow-ups & Bumps

**Priority**: P2
**Status**: NOT STARTED
**Effort**: 7 days
**Depends On**: US-018 (Agent v0)

**User Story**:
> As a MailQ user,
> I want MailQ to suggest bumping emails I haven't responded to,
> So that I don't forget to follow up on important conversations.

**Acceptance Criteria**:
- [ ] Detect threads with no response from user after N days
- [ ] Suggest bump with draft message
- [ ] User approves/edits before sending (no auto-send)
- [ ] Track bump suggestions and success rate
- [ ] Smart timing (don't suggest bumps on weekends)

**Out of Scope**:
- Auto-send (requires gmail.send scope)
- Draft creation (Agent v2)
- Multi-party thread analysis

**Technical Implementation**:
- Module: Follow-up detector (LLM-based)
- Integration: Digest formatter (new section)
- Tests: Follow-up detection accuracy

**Reference**: `docs/LONGTERM_ROADMAP.md` (LATER section)

---

### US-022: Agent v2 - Opt-in Write Scopes

**Priority**: P3
**Status**: NOT STARTED
**Effort**: 10 days
**Depends On**: US-021 (Agent v1)

**User Story**:
> As a MailQ power user,
> I want MailQ to create calendar events and draft emails on my behalf,
> So that I can save time on repetitive tasks.

**Acceptance Criteria**:
- [ ] Opt-in flow for `gmail.send` scope (explicit consent)
- [ ] Calendar write access for event creation
- [ ] Draft email creation (not sending)
- [ ] User approval required for all writes
- [ ] Audit log for all write operations
- [ ] Revoke write access anytime

**Out of Scope**:
- Auto-send emails (always require approval)
- Calendar event deletion
- Email deletion/archiving

**Technical Implementation**:
- Chrome Extension: Scope upgrade flow
- Backend: Write operation logging
- Tests: Write operation safety tests

**Reference**: `docs/LONGTERM_ROADMAP.md` (LATER section)

---

### US-023: Cleanup & Documentation

**Priority**: P3
**Status**: NOT STARTED
**Effort**: 3 days

**User Story**:
> As a MailQ developer,
> I want comprehensive documentation for all features,
> So that new contributors can onboard quickly.

**Acceptance Criteria**:
- [ ] API documentation (OpenAPI/Swagger)
- [ ] Architecture diagrams updated
- [ ] User guide for Chrome extension
- [ ] Developer setup guide
- [ ] Troubleshooting guide
- [ ] Code comments for complex logic

**Out of Scope**:
- Video tutorials
- Interactive demos
- Localization (English only for MVP)

**Technical Implementation**:
- Documentation: Markdown in `docs/`
- API docs: FastAPI auto-generated
- Diagrams: Mermaid or draw.io

**Reference**: `docs/LONGTERM_ROADMAP.md` (LATER section)

---

### US-024: Agent v3 - Human-Feeling JARVIS Layer

**Priority**: P3
**Status**: NOT STARTED
**Effort**: 14 days
**Depends On**: US-022 (Agent v2)

**User Story**:
> As a MailQ user,
> I want MailQ to feel like a helpful assistant,
> So that interacting with my email feels natural and conversational.

**Acceptance Criteria**:
- [ ] Micro-enrichment: 1-sentence rewrite inside cards (more human-friendly)
- [ ] Digest opening line: contextual top-of-digest sentence
- [ ] Conversational surface: "what should I do next?" queries
- [ ] Tone: friendly but professional
- [ ] No hallucinations (all content grounded in emails)
- [ ] User can disable JARVIS layer (fallback to deterministic)

**Out of Scope**:
- Full conversation mode
- Multi-turn dialogue
- Voice interface

**Technical Implementation**:
- Module: JARVIS layer (LLM-based enrichment)
- Integration: Digest formatter + card renderer
- Tests: Content quality + grounding tests

**Reference**: `docs/LONGTERM_ROADMAP.md` (LATER section)

---

## Template for New User Stories

When adding new user stories, use this template:

```markdown
### US-XXX: [Feature Name]

**Priority**: P0 | P1 | P2 | P3
**Status**: NOT STARTED | IN PROGRESS | DONE
**Effort**: X days
**Owner**: Unassigned | Name
**Depends On**: US-XXX (if applicable)

**User Story**:
> As a [user type],
> I want [goal],
> So that [benefit].

**Acceptance Criteria**:
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

**Out of Scope**:
- Item 1
- Item 2

**Technical Implementation**:
- Module: [file path]
- Config: [config file]
- Integration: [integration points]
- Tests: [test files]

**Reference**: [link to relevant doc]
```

---

## How to Use This File

### For Product Managers
- Review user stories before sprint planning
- Prioritize stories based on user feedback and metrics
- Ensure acceptance criteria are measurable
- Track story completion in sprints

### For Developers
- Use stories as implementation guide
- Check acceptance criteria before marking story done
- Link commits/PRs to user stories
- Update status as work progresses

### For QA
- Use acceptance criteria as test plan
- Verify all criteria met before story completion
- Report issues referencing story ID

---

## Maintenance

**Review Cadence**: Weekly sprint planning
**Update Triggers**:
- New feature requests
- User feedback
- Roadmap changes
- Completed stories (move to archive)

**Archive Old Stories**: Keep last 6 months of completed stories

---

*Last Review*: 2025-11-10
*Next Review Due*: 2025-11-17
