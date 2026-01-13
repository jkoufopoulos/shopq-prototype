# Where LLMs Sit in the Digest Pipeline

**Date**: 2025-11-01 17:14

---

## Full Digest Pipeline

```
98 Emails from Gmail
    ↓
┌─────────────────────────────────────────────────────────────┐
│ STAGE 1: Phase 1 Filters (Rule-based, NO LLM)             │
│ - Time-decay filter (expired events)                       │
│ - Self-email filter (ShopQ digest recursion)              │
│ Result: 95 emails (3 filtered)                            │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ STAGE 2: Importance Classification (Rule-based, NO LLM)    │
│ File: shopq/importance_classifier.py                       │
│ - Pattern matching on subject + snippet                    │
│ - Categorizes: critical / time_sensitive / routine         │
│ Result: 8 critical, 28 time_sensitive, 59 routine         │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ STAGE 3: Entity Extraction (🤖 LLM #1 - Gemini 2.0)       │
│ File: shopq/entity_extractor.py                            │
│ - Extracts structured data from critical + time_sensitive  │
│ - Creates: NotificationEntity, EventEntity, etc.           │
│ - LLM call for EACH email that needs extraction            │
│ Result: 36 entities extracted from 36 emails              │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ STAGE 4: Deduplication (Rule-based, NO LLM)               │
│ - Merges similar entities                                  │
│ Result: 31 entities (5 duplicates removed)                │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ STAGE 5: Timeline Building (Rule-based, NO LLM)           │
│ File: shopq/timeline_synthesizer.py                        │
│ - Sorts entities by priority score                         │
│ - Groups: critical vs time_sensitive                       │
│ - NOW: Shows ALL entities (no limits)                      │
│ Result: 31 entities to feature                            │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ STAGE 6: Weather Enrichment (🤖 LLM call to Weather API)  │
│ - Gets local weather for greeting                          │
│ Result: "52°, Clear in New York"                          │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ STAGE 7: Narrative Generation (Template OR LLM)            │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐   │
│ │ NEW: Template-Based (digest_template_based = TRUE)  │   │
│ │ File: shopq/digest_formatter.py                     │   │
│ │ - Programmatically categorize entities              │   │
│ │ - Build HTML sections (🚨📦📅💼)                  │   │
│ │ - NO LLM CALL                                       │   │
│ │ Result: Structured HTML digest                      │   │
│ └─────────────────────────────────────────────────────┘   │
│                                                             │
│ OR                                                          │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐   │
│ │ OLD: LLM-Based (🤖 LLM #2 - Gemini 2.0)            │   │
│ │ File: shopq/narrative_generator.py                  │   │
│ │ - Sends entities + prompt to LLM                    │   │
│ │ - LLM generates natural language digest             │   │
│ │ - Problem: LLM ignores HTML formatting              │   │
│ │ Result: Plain text list                             │   │
│ └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ STAGE 8: Fact Verification (Rule-based, NO LLM)           │
│ - Validates numbered references (1)...(N)                  │
│ - Ensures all entities referenced                          │
│ Result: Validation pass/fail                              │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ STAGE 9: HTML Rendering (Rule-based, NO LLM)              │
│ File: shopq/card_renderer.py                               │
│ - Wraps digest in card template                            │
│ - Adds deep links to Gmail                                 │
│ - Adds noise summary footer                                │
│ Result: Final HTML email                                   │
└─────────────────────────────────────────────────────────────┘
    ↓
Final Digest Email Sent
```

---

## Current LLM Usage Summary

### LLM Call #1: Entity Extraction (Required)
**File**: `shopq/entity_extractor.py`
**Model**: Gemini 2.0 Flash
**Purpose**: Extract structured data from emails
**Input**: Email subject + snippet
**Output**: Entity object (NotificationEntity, EventEntity, etc.)
**Call volume**: 1 call per critical/time-sensitive email (~36 calls per digest)
**Cost**: ~$0.0001 per call

**Why needed**: Pattern matching can't extract structured data like:
- Flight number, departure time, destination
- Event title, time, location
- Bill amount, due date
- Delivery item name, tracking number

**Example**:
```
Input: "Delivered: Vintage Mesh Top Hat"
Output: NotificationEntity(
    category='delivery',
    message='Delivered: Vintage Mesh Top Hat',
    source_subject='Delivered: Vintage Mesh Top Hat'
)
```

---

### LLM Call #2: Narrative Generation (NOW OPTIONAL)

#### NEW: Template-Based (NO LLM) ✅ ACTIVE
**File**: `shopq/digest_formatter.py`
**Feature gate**: `digest_template_based = True`
**Purpose**: Format entities into structured HTML digest
**Method**: Programmatic categorization + templating
**Cost**: $0 (no LLM call)

**How it works**:
```python
# Categorize each entity
if entity.importance == 'critical':
    section = 'critical'
elif 'delivered:' in subject:
    section = 'today'
elif 'appointment' in subject and future_date:
    section = 'coming_up'
else:
    section = 'worth_knowing'

# Build HTML
html = """
<p>Hey! It's 52° in New York 🌙</p>

<p style="font-weight: 600; color: #d32f2f;">🚨 CRITICAL</p>
<ul>
  <li>Security alert (1)</li>
  <li>Your Con Edison bill is ready (2)</li>
</ul>
...
"""
```

**Pros**:
- ✅ Consistent formatting every time
- ✅ No LLM hallucination/ignoring instructions
- ✅ Fast (no API call)
- ✅ Free (no LLM cost)
- ✅ Reliable structure

**Cons**:
- ❌ Less natural language (more template-y)
- ❌ No contextual variation in tone
- ❌ Harder to add narrative flow between sections

---

#### OLD: LLM-Based (🤖 Gemini 2.0)
**File**: `shopq/narrative_generator.py`
**Feature gate**: `digest_template_based = False`
**Model**: Gemini 2.0 Flash
**Purpose**: Generate conversational digest from entities
**Input**: List of entities + prompt template
**Output**: Natural language digest text
**Call volume**: 1 call per digest
**Cost**: ~$0.0001 per digest

**Why we disabled it**:
- ❌ LLM kept ignoring HTML formatting instructions
- ❌ Returned flat bulleted list instead of structured sections
- ❌ Included noise items (vote requests, past events)
- ❌ Unpredictable output quality

**What we tried**:
1. V1: Original chronological prompt
2. V2: Urgency-grouped prompt
3. V3: Structured HTML with examples
4. V4: Simplified with explicit rules
5. **All failed** - LLM wouldn't follow HTML structure

**Conclusion**: Template-based is more reliable for structure

---

## Email Classification Pipeline (Separate from Digest)

When emails first arrive, there's also classification:

```
New Email Arrives
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Rules Engine (T0 - Rule-based, NO LLM)                    │
│ - Exact sender match in rules DB                           │
│ - If found: Return cached classification                   │
│ - Hit rate: ~50-70% of emails                             │
└─────────────────────────────────────────────────────────────┘
    ↓ (if no rule match)
┌─────────────────────────────────────────────────────────────┐
│ Gemini Classifier (T3 - 🤖 LLM #3)                        │
│ File: shopq/vertex_gemini_classifier.py                    │
│ - Classifies: type, domains, attention, relationship       │
│ - Uses few-shot examples                                   │
│ - Cost: ~$0.0001 per email                                │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Verifier (T3 - 🤖 LLM #4 - Selective)                     │
│ File: shopq/api_verify.py                                  │
│ - Only runs on ~10-20% of suspicious emails                │
│ - Challenges first classification                          │
│ - Can confirm or reject + provide correction               │
│ - Cost: ~$0.0001 per verified email                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Total LLM Usage Per Digest

### With Template-Based Formatting (Current)
- **Entity Extraction**: ~36 LLM calls (one per entity)
- **Narrative Generation**: 0 LLM calls (template-based)
- **Weather**: 1 API call (OpenWeather, not LLM)
- **Total cost**: ~$0.0036 per digest

### With LLM-Based Formatting (Old)
- **Entity Extraction**: ~36 LLM calls
- **Narrative Generation**: 1 LLM call
- **Total cost**: ~$0.0037 per digest

**Savings**: Minimal (~$0.0001 per digest), but reliability is much better

---

## Why Template-Based is Better for Structure

**LLM is great for**:
- Extracting structured data from unstructured text ✅
- Understanding context and intent ✅
- Handling edge cases ✅

**LLM is bad for**:
- Following strict formatting rules ❌
- Consistent HTML structure ❌
- Deterministic categorization ❌

**Templates are great for**:
- Consistent formatting every time ✅
- Predictable structure ✅
- Fast execution ✅
- Zero hallucination ✅

**Templates are bad for**:
- Natural language variation ❌
- Contextual tone adjustment ❌
- Narrative flow ❌

---

## Hybrid Approach (Current)

We use **LLMs where they excel** (entity extraction) and **templates where consistency matters** (formatting).

```
┌─────────────────────────────────────────────────────────┐
│ LLM: Extract structured data from messy emails         │
│ "Delivered: Vintage Hat" → NotificationEntity          │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ Template: Organize entities into consistent structure  │
│ NotificationEntity → 📦 TODAY section                  │
└─────────────────────────────────────────────────────────┘
```

**Result**: Best of both worlds
- Intelligent extraction (LLM)
- Reliable formatting (Template)

---

## Future: Could Add LLM for Section Summaries

Instead of using LLM for the whole digest, we could use it for **section summaries**:

```html
<p>Hey! It's 52° in New York 🌙</p>

<p style="font-weight: 600;">🚨 CRITICAL</p>
<p style="font-style: italic; color: #666;">
  <!-- LLM-generated summary of critical section -->
  You have 8 financial items that need attention: bills, statements, and account activity.
</p>
<ul>
  <li>Security alert (1)</li>
  <li>Your Con Edison bill is ready (2)</li>
  ...
</ul>
```

This would add:
- Natural language context
- Better scanning ("Oh, mostly bills")
- Still preserve structure

**Not implemented yet** - but could be a good middle ground.

---

## Summary

**Where LLMs sit NOW**:
1. ✅ Entity Extraction (required, works well)
2. ❌ Narrative Generation (disabled, unreliable)
3. ✅ Email Classification (separate pipeline, works well)

**Template-based formatting** replaced LLM narrative generation for reliability.

**The digest is now**:
- 90% rule-based + templates
- 10% LLM-based (entity extraction only)
