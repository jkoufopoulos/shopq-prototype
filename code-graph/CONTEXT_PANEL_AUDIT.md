# Context Panel Content & Design Audit

**Date:** 2025-11-03
**Auditor:** Content Design Expert
**Scope:** All 6 diagram HTML pages (system_architecture, classification_flow, learning_loop, digest_learning, cost_performance, auto_organize_sequence)

---

## Executive Summary

The context panels serve as architectural companion documentation but suffer from **inconsistent voice, redundant content, and poor information hierarchy**. They oscillate between tutorial-style explanations and reference documentation without a clear purpose.

**Overall Grade: C+**

---

## 1. Content Strategy Issues

### 1.1 Unclear Purpose
**Problem:** Context panels try to be three things at once:
- Quick reference for experienced developers
- Tutorial for new developers
- Technical specification

**Example from System Architecture:**
```
Extension Components
• Auto-Organize Engine — Docs · Source · Tests: network.test.js
• Background Service Worker — Docs · Source · Tests: network.test.js
...
```

Then immediately followed by:
```
Core Flow
Email → Rules Engine → [Match?] → Cache result (T0 cost: free)
...
```

**Impact:** Users don't know if they should read sequentially or scan for specific information.

**Recommendation:** Pick ONE purpose per diagram:
- **System Architecture** → Quick reference (just links)
- **Classification Flow** → Process walkthrough (narrative)
- **Learning Loop** → Conceptual explanation (how it works)

---

### 1.2 Redundant "Tip" Section
**Problem:** Every single panel ends with:
```
💡 Tip: Edit prompts in shopq/prompts/ - no code changes needed!
```

**Issues:**
1. Only relevant to 2 of 6 diagrams (classification_flow, learning_loop)
2. Appears on ALL pages even when irrelevant
3. Same exact wording = banner blindness

**Recommendation:** Remove global tip. Add context-specific tips only where relevant.

---

### 1.3 Inconsistent Detail Levels
**Problem:** Some sections are extremely detailed, others are surface-level.

**System Architecture:**
- 9 Extension components listed (good)
- 10 Backend components listed (good)
- But then: "Key Components" duplicates the same info with file paths

**Classification Flow:**
- Confidence thresholds: Precise numbers (0.85, 0.75)
- Verifier triggers: Vague bullets ("contradictions detected")

**Recommendation:** Establish detail level per diagram type:
- Overview diagrams (system): High-level only
- Process diagrams (flow): Step-by-step detail
- Concept diagrams (learning): Principles + examples

---

## 2. Content Quality Issues

### 2.1 Passive Voice & Weak Verbs
**Examples:**
- ❌ "Deduplicates threads, checks cache, calls the backend"
- ✅ "Removes duplicate emails, verifies cache, then requests classification"

- ❌ "Used by summary-email and diagnostics"
- ✅ "Powers the daily digest and debug dashboards"

**Recommendation:** Use active voice. Start with strong verbs.

---

### 2.2 Jargon Without Context
**Problem:** Technical terms used without definition.

**Examples:**
- "T0 cost" (what does T0 mean?)
- "MV3 service worker" (Manifest V3 not explained)
- "Span-Aware Entity Linker" (what's a span?)
- "Confidence delta threshold: 0.15" (delta of what?)

**Recommendation:** Either:
1. Define on first use: "T0 (tier 0, free tier)"
2. Link to glossary
3. Use plain language: "free tier" instead of "T0"

---

### 2.3 Inconsistent Formatting
**Problem:** Mix of styles makes scanning difficult.

**System Architecture:**
```
Extension Components
• Component — Docs · Source · Tests: file.js
```

**Classification Flow:**
```
Verifier Triggers
• Low/medium confidence (0.50-0.90)
• Multi-purpose senders (Amazon, Google, banks)
```

**Learning Loop:**
```
How Learning Works
1. User removes/adds label → content.js detects
2. POST /api/feedback with correction
```

**Recommendation:** Pick ONE format per content type:
- **Lists:** Use • for features, 1-2-3 for steps, → for flows
- **Key-value pairs:** Use consistent separator (`:` not `—`)
- **Code:** Always use `<code>` tags or `<pre>` blocks

---

## 3. Information Architecture Issues

### 3.1 Poor Hierarchy
**Problem:** Flat structure makes scanning hard.

**Current (System Architecture):**
```
Architecture Sources
Extension Components (9 items)
Backend Components (10 items)
Core Flow
Classification Dimensions
Key Components
```

**Issues:**
- No clear priority
- Can't quickly find "what does this component do?"
- Too much text for a "quick reference"

**Recommendation:** Use progressive disclosure:
```
At a Glance
├─ Purpose: AI-powered Gmail classifier
├─ Stack: Python + Chrome Extension + Vertex AI
└─ Flow: Email → Rules → LLM → Labels

Components (19) [expandable]
├─ Extension (9)
└─ Backend (10)

Deep Dive
├─ Architecture Overview →
└─ Component Index →
```

---

### 3.2 Missing "Why" Information
**Problem:** Explains "what" and "how" but not "why" decisions were made.

**Example (Classification Flow):**
```
MIN_TYPE_CONF = 0.85 (type must be 85%+ confident)
MIN_LABEL_CONF = 0.75 (labels must be 75%+ confident)
```

**Questions not answered:**
- Why 85% and not 90%?
- What happens to the 15% that fall below?
- How were these numbers chosen?

**Recommendation:** Add "Design Decisions" section:
```
Why These Thresholds?
• 85% for type: Balances accuracy vs coverage
  - Higher = fewer classifications but more accurate
  - Lower = more classifications but more errors
• Tuned based on 1,000-email validation set
• Can adjust in api_organize.py:42
```

---

## 4. Visual Design Issues

### 4.1 Typography Problems
**Current:**
```css
.context-section h4 {
    font-size: 14px;
    color: #667eea;
    text-transform: uppercase;
}
```

**Issues:**
1. All-caps headings are harder to read
2. 14px is too small for headings
3. Purple color (#667eea) has low contrast

**Recommendation:**
```css
.context-section h4 {
    font-size: 16px;
    font-weight: 600;
    color: #4a5568; /* Better contrast */
    text-transform: none;
    margin-bottom: 12px;
}
```

---

### 4.2 List Formatting
**Problem:** Bullets run together, hard to scan.

**Current:**
```html
<ul>
    <li><strong>Auto-Organize Engine</strong> — Docs · Source · Tests: network.test.js</li>
    <li><strong>Background Service Worker</strong> — Docs · Source · Tests: network.test.js</li>
</ul>
```

**Issues:**
- No spacing between items
- Links squished together
- Hard to find specific component

**Recommendation:**
```html
<ul class="component-list">
    <li class="component-item">
        <div class="component-name">Auto-Organize Engine</div>
        <div class="component-links">
            <a href="...">Docs</a> ·
            <a href="...">Source</a> ·
            <a href="...">Tests</a>
        </div>
    </li>
</ul>
```

With CSS:
```css
.component-item {
    padding: 8px 0;
    border-bottom: 1px solid #e5e7eb;
}
.component-name {
    font-weight: 600;
    margin-bottom: 4px;
}
.component-links {
    font-size: 12px;
    color: #6b7280;
}
```

---

### 4.3 Code Block Inconsistency
**Problem:** Some code uses `<pre><code>`, some uses inline `<code>`, some uses plain text.

**Recommendation:** Standardize:
- **Single values:** Inline code `<code>shopq.db</code>`
- **Multiple lines:** Pre block with syntax highlighting
- **Flows/ASCII art:** Pre block with monospace

---

## 5. Specific Diagram Recommendations

### System Architecture
**Current Focus:** Exhaustive component listing
**Suggested Focus:** High-level map with drill-down

**New Structure:**
```
Overview
├─ 3 main systems: Extension, Backend, External
└─ Click diagram nodes to see component details

Quick Navigation
├─ Extension (20 files) →
├─ Backend (53 files) →
└─ External (3 services) →

Architecture Docs
└─ Full component index →
```

---

### Classification Flow
**Current Focus:** Technical thresholds
**Suggested Focus:** Decision tree walkthrough

**New Structure:**
```
The Journey of an Email
1. Rules Check (Free)
   ├─ If match found → Apply cached classification
   └─ If not found → Continue to LLM

2. AI Classification ($0.0001)
   ├─ Gemini analyzes email
   ├─ Returns: type, domain, attention level
   └─ Confidence check...

Why This Flow?
• Rules-first saves 60% of LLM costs
• Two-pass verification reduces errors by 25%
```

---

### Learning Loop
**Current Focus:** Steps 1-2-3-4
**Suggested Focus:** Concept explanation

**New Structure:**
```
The Learning Cycle

User corrects label ─→ System learns ─→ Auto-applies to similar emails
       ↑                                            │
       └──────────── Feedback loop ←───────────────┘

How It Works
• Your corrections become rules (95% confidence)
• Each confirmation increases confidence (+5%)
• After 2 confirmations → permanent rule

Impact
• 500 corrections → 500 free classifications/day
• Accuracy improves from 85% → 95% over time
```

---

## 6. Accessibility Issues

### 6.1 Link Text
**Problem:** Links say "Docs" "Source" "Tests" without context.

**Current:**
```html
<a href="...">Docs</a>
```

**Screen reader reads:** "Link: Docs"
**User thinks:** "Docs for what?"

**Recommendation:**
```html
<a href="..." aria-label="Auto-Organize Engine documentation">Docs</a>
```

Or better:
```html
<a href="...">Auto-Organize Engine docs</a>
```

---

### 6.2 Color Contrast
**Problem:** Purple headings (#667eea) have insufficient contrast on white (3.8:1, needs 4.5:1).

**Recommendation:** Use #5568d3 (contrast 4.6:1) or darker.

---

## 7. Prioritized Recommendations

### High Priority (Do First)
1. **Remove redundant "Tip" section** from all pages
2. **Fix heading contrast** (#667eea → #4a5568)
3. **Standardize code formatting** (pre vs inline)
4. **Add spacing between list items** (currently squished)

### Medium Priority
5. **Define jargon on first use** (T0, MV3, span-aware, etc.)
6. **Restructure System Architecture** panel (too much text)
7. **Add "why" explanations** for key decisions
8. **Use active voice** throughout

### Low Priority
9. **Add visual hierarchy** with expandable sections
10. **Create component quick-find** (search/filter)
11. **Add glossary page** for common terms

---

## 8. Template Recommendation

Create 3 standard templates:

**Template A: Overview Diagrams** (System Architecture)
```
At a Glance
├─ One-sentence purpose
├─ Key statistics
└─ Main components (3-5 max)

Navigation
└─ Links to subsystem diagrams

Resources
└─ Full documentation link
```

**Template B: Process Diagrams** (Classification Flow, Auto-Organize)
```
Process Overview
└─ Narrative walkthrough (numbered steps)

Key Decision Points
└─ Why this approach? (design rationale)

Configuration
└─ How to tune (with defaults shown)
```

**Template C: Concept Diagrams** (Learning Loop, Digest Learning)
```
The Big Idea
└─ Conceptual model (with visual)

How It Works
└─ Simplified steps (3-5 max)

Real-World Impact
└─ Metrics/examples showing value
```

---

## 9. Before/After Example

### BEFORE (System Architecture - Backend Components)
```
Backend Components
• Classification Domain Logic — Docs · Source · Tests: test_fallback.py
• Context Digest Engine — Docs · Source
• Digest Card Renderer — Docs · Source
• FastAPI Gateway — Docs · Source · Tests: test_e2e_pipeline.py
[...7 more items...]
```

### AFTER
```
Backend (53 files)

Core API
├─ FastAPI Gateway
│  └─ Routes requests to classification, feedback, and digest handlers
│  └─ Docs · Source · Tests

Classification Engine
├─ Rules Engine (free tier)
├─ Gemini Classifier ($0.0001/email)
└─ Verifier (selective 2nd pass)

[+] Show all 53 components →
```

**Improvements:**
- Grouped by function (not alphabetical)
- Shows relationship hierarchy
- Progressive disclosure (expandable)
- Clearer descriptions
- More scannable

---

## 10. Conclusion

The context panels contain valuable information but present it poorly. The core issues are:

1. **Mixed purpose** - trying to be reference + tutorial + spec
2. **Poor hierarchy** - flat lists instead of grouped concepts
3. **Inconsistent detail** - too much in some areas, too little in others
4. **Weak typography** - hard to scan, low contrast
5. **Missing "why"** - explains how but not rationale

**Recommended Action:** Implement High Priority fixes (1-4) immediately, then redesign one diagram panel as a prototype for the new template system.

**Estimated Effort:**
- High Priority fixes: 2-3 hours
- Template redesign: 4-6 hours
- Apply to all 6 diagrams: 3-4 hours

**Total: 9-13 hours** for comprehensive improvement.
