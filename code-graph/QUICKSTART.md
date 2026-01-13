# MailQ Code-Graph: 3-Lens Quick Reference

**Problem**: A single "everything graph" turns into TV static. You can't answer targeted questions quickly.

**Solution**: Three complementary lenses. Pick the one you need in the moment.

---

## Quick Navigation

**I want to understand...**

- 🎯 **"How does X work?"** → [Task-Flow Lens](#1-task-flow-lens-sequence-first) (3 scenarios, ≤8 steps each)
- 🗺️ **"Where does Y belong?"** → [Layer Map Lens](#2-layer-map-lens-stable-topology) (categories only, no sprawl)
- 🔥 **"What needs attention now?"** → [Evidence Lens](#3-evidence-lens-whats-risky--hot) (top 12 by real signals)

---

## 1) Task-Flow Lens (Sequence-First)

**Purpose**: "What happens when X occurs?"

**Format**: Short sequence diagrams (≤8 boxes) showing:
- The contract at each hop (payload name + version)
- No file names unless directly involved
- One happy path + one error branch

**Available Scenarios**:

| Scenario | File | Answers |
|----------|------|---------|
| **Organize Request** | [TASK_FLOW_ORGANIZE.md](visuals/TASK_FLOW_ORGANIZE.md) | "What happens when `/api/organize` is called?" |
| **Digest Generation** | [TASK_FLOW_DIGEST.md](visuals/TASK_FLOW_DIGEST.md) | "How is the daily digest generated?" |
| **Feedback Learning** | [TASK_FLOW_FEEDBACK.md](visuals/TASK_FLOW_FEEDBACK.md) | "How does user feedback become a rule?" |

**Example Output**:
```
Extension → API → Rules Engine → LLM → Database
(≤8 steps, shows payloads, <30 seconds to understand)
```

**When to Use**:
- ✅ Onboarding new developers
- ✅ Debugging a specific flow
- ✅ Planning a feature change
- ❌ Don't use for: "Show me everything" (use System Diagram instead)

---

## 2) Layer Map Lens (Stable Topology)

**Purpose**: "Where does a thing belong?" (org chart for code)

**Format**: One layered map showing:
- Categories only (no leaf files)
- File counts in each box (e.g., "Rules Engine (7 files)")
- Arrows **only between layers**, never within
- Link out to file lists in docs

**Available Views**:

| View | File | Shows |
|------|------|-------|
| **Layer Map** | [LAYER_MAP.md](visuals/LAYER_MAP.md) | Extension • Gateway • Pipeline • Digest • Learning layers |

**Example Output**:
```
📱 Extension (21 files)
  ⚙️ Core (2)  📧 Gmail (1)  🤖 Classifier (3)  💾 Cache (1)  ✨ Features (3)  🔧 Utils (7)

↓

🐍 Backend (75 files)
  🌐 API (9)  ⚡ Pipeline (4)  📊 Digest (0)  📚 Learning (5)  🔧 Utils (3)
```

**When to Use**:
- ✅ "Where should I add this file?"
- ✅ "What layer handles X?"
- ✅ Understanding system boundaries
- ❌ Don't use for: How data flows (use Task-Flow instead)

---

## 3) Evidence Lens (What's Risky / Hot)

**Purpose**: "What should I pay attention to?" (directs focus with real signals)

**Format**: Heat-map graph showing:
- Top 12 nodes by composite score
- Node color = churn (git commits last 30 days)
- Border = incidents / TODOs
- Badge = test coverage %

**Available Views**:

| View | File | Shows |
|------|------|-------|
| **Evidence Heat-Map** | [EVIDENCE_HEATMAP.md](visuals/EVIDENCE_HEATMAP.md) | Top 12 components by activity score |

**Signals Used**:
- ✅ **Git churn**: Commits in last 30 days (from `git log`)
- ✅ **TODO count**: Open TODOs/FIXMEs in file
- ⚠️ **Test coverage**: Not yet implemented
- ⚠️ **Production incidents**: Not yet wired

**Example Output**:
```
🔥 api.py           - Score: 90 (45 commits, 0 TODOs)
🔥 background.js    - Score: 64 (32 commits, 0 TODOs)
⚠️ context_digest.py - Score: 47 (23 commits, 1 TODO)
```

**When to Use**:
- ✅ Planning refactoring priorities
- ✅ Code review focus
- ✅ Roadmap planning
- ❌ Don't use for: Static architecture (use Layer Map instead)

---

## Comparison: When to Use Each Lens

| Question | Lens | Example |
|----------|------|---------|
| "How does classification work?" | 🎯 Task-Flow | See TASK_FLOW_ORGANIZE.md |
| "Where do I add a new API endpoint?" | 🗺️ Layer Map | See LAYER_MAP.md → API Gateway category |
| "What file should I refactor next?" | 🔥 Evidence | See EVIDENCE_HEATMAP.md → top scoring files |
| "Show me everything" | Use System Diagram | See SYSTEM_DIAGRAM.md (comprehensive view) |

---

## Maintaining This System

### Auto-Generation

All diagrams are **100% auto-generated** from code. No manual updates needed.

**Regenerate everything**:
```bash
./code-graph/scripts/quick_regen.sh
```

**Or step-by-step**:
```bash
# 1. Generate markdown diagrams
python3 code-graph/scripts/generate_diagrams.py

# 2. Generate HTML interactive versions
python3 code-graph/scripts/generate_diagram_html.py

# 3. Open in browser
open code-graph/visuals/html/index.html
```

### Adding New Task-Flow Scenarios

To add a new scenario (e.g., "Auto-Organize Alarm Flow"):

1. Add method to `generate_diagrams.py`:
   ```python
   def generate_task_flow_alarm(self):
       """Task-flow lens: What happens during alarm trigger"""
       # ... sequence diagram code
   ```

2. Add to `generate_all()`:
   ```python
   ("Task-Flow: Alarm Trigger", "TASK_FLOW_ALARM", self.generate_task_flow_alarm()),
   ```

3. Add to HTML generator `diagrams` list:
   ```python
   {
       "file": "task_flow_alarm.html",
       "markdown": "TASK_FLOW_ALARM.md",
       "title": "Task-Flow: Alarm Trigger",
       "icon": "⏰",
       "category": "task-flow",
   }
   ```

4. Regenerate: `./code-graph/scripts/quick_regen.sh`

### Updating Evidence Signals

To add test coverage or incident tracking:

1. Update `_compute_evidence_scores()` in `generate_diagrams.py`
2. Add new signal detection (e.g., parse coverage reports)
3. Update scoring formula
4. Regenerate

---

## File Structure

```
code-graph/
├── QUICKSTART.md              ← You are here
├── scripts/
│   ├── generate_diagrams.py   ← Main generator (markdown)
│   ├── generate_diagram_html.py ← HTML converter
│   └── quick_regen.sh         ← One-command regenerate
└── visuals/
    ├── TASK_FLOW_*.md         ← Task-flow scenarios
    ├── LAYER_MAP.md           ← Layer topology
    ├── EVIDENCE_HEATMAP.md    ← Hot files
    ├── SYSTEM_DIAGRAM.md      ← Comprehensive (all files)
    ├── CORE_LAYERS.md         ← Layered comprehensive
    ├── CLASSIFICATION_FLOW.md ← Detailed flow
    └── html/
        ├── index.html         ← Interactive entry point
        └── *.html             ← Interactive diagrams
```

---

## FAQ

**Q: When should I use the comprehensive diagrams (SYSTEM_DIAGRAM.md)?**

A: When you need to see **everything at once** or are exploring broadly. But for targeted questions, use the 3 lenses instead.

**Q: Why are some diagrams so small (≤8 steps)?**

A: Cognitive load. Research shows humans can hold ~7 items in working memory. Small diagrams answer questions in <30 seconds.

**Q: How often should I regenerate?**

A: After significant architecture changes or weekly (if actively developing). The Evidence lens should be regenerated more frequently (daily) to track churn.

**Q: Can I customize the evidence scoring?**

A: Yes! Edit `_compute_evidence_scores()` in `generate_diagrams.py`. Current formula:
```python
score = (commits * 2) + (todos * 1.5) + (incidents * 5)
```

**Q: What if I want a different task-flow scenario?**

A: Follow the "Adding New Task-Flow Scenarios" guide above. Keep it ≤8 steps!

---

## Credits

**Design Philosophy**: Based on cognitive load research and "information scent" principles. A system should answer "what/where/why now" questions in <30 seconds.

**Inspiration**:
- [C4 Model](https://c4model.com/) (layered architecture views)
- [Simon Brown's Software Architecture for Developers](https://softwarearchitecturefordevelopers.com/)
- Code Climate / CodeScene heat-maps

**Generated**: 2025-11-11 (auto-updated on each regeneration)

**Maintainers**: Auto-maintained by codebase scanning. No manual updates required.
