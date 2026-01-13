# MailQ Code-Graph

**Visual documentation that stays in sync with your code.**

100% auto-generated diagrams using the **3-Lens Approach**: pick the lens you need in the moment.

## 🔍 Pick Your Lens

Traditional architecture docs either get stale or turn into TV static. This system gives you **3 complementary lenses**:

| I want to... | Use This Lens | Quick Link |
|--------------|---------------|------------|
| 🎯 **Understand how X works** | **Task-Flow** (≤8 steps) | [/api/organize](visuals/TASK_FLOW_ORGANIZE.md) • [Digest](visuals/TASK_FLOW_DIGEST.md) • [Learning](visuals/TASK_FLOW_FEEDBACK.md) |
| 🗺️ **Know where Y belongs** | **Layer Map** (categories) | [Layer topology](visuals/LAYER_MAP.md) |
| 🔥 **See what needs attention** | **Evidence** (top 12) | [Heat-map](visuals/EVIDENCE_HEATMAP.md) |
| 📚 **See everything** | **Comprehensive** (all files) | [System](visuals/SYSTEM_DIAGRAM.md) • [Layers](visuals/CORE_LAYERS.md) • [Flow](visuals/CLASSIFICATION_FLOW.md) |

👉 **Read**: [QUICKSTART.md](QUICKSTART.md) for full 3-Lens guide

## 🚀 Quick Start

**View all diagrams** (best experience):
```bash
open code-graph/visuals/html/index.html
```

**Regenerate** after code changes:
```bash
./code-graph/scripts/quick_regen.sh
```

That's it! Everything auto-generates from your code in <1 second.

## 📊 Example: Evidence Heat-Map

```
🔥 api.py                - Score: 90  (45 commits, 0 TODOs)
🔥 background.js         - Score: 64  (32 commits, 0 TODOs)
🔥 summary-email.js      - Score: 54  (27 commits, 0 TODOs)
🔥 context_digest.py     - Score: 47  (23 commits, 1 TODO)
```

**Use this to prioritize**: refactoring, code review, roadmap planning

---

## 🛠️ How It Works

1. **Scan codebase** - Analyzes `mailq/*.py` and `extension/*.js` files
2. **Detect signals** - Git churn (30d), TODOs, imports, external services
3. **Generate markdown** - Creates Mermaid diagrams in `visuals/*.md`
4. **Convert to HTML** - Interactive versions with zoom/export in `visuals/html/`

**All automatic.** Add/remove files → regenerate → diagrams update.

---

## 📁 File Structure

```
code-graph/
├── README.md                  ← You are here
├── QUICKSTART.md              ← Full 3-Lens guide
├── scripts/
│   ├── generate_diagrams.py   ← Main generator
│   ├── generate_diagram_html.py
│   └── quick_regen.sh
└── visuals/
    ├── *.md                   ← Markdown diagrams
    └── html/
        ├── index.html         ← Interactive entry point
        └── *.html             ← Individual diagrams
```

---

## 🎯 Design Philosophy

**Problem**: Architecture docs get stale or become TV static.

**Solution**:
1. **Auto-generate** (stays in sync)
2. **3 lenses** (pick what you need)
3. **Small diagrams** (≤8 steps, <30s to understand)

**Credits**: C4 Model, CodeScene heat-maps, cognitive load research

---

## 📞 Questions?

See **[QUICKSTART.md](QUICKSTART.md)** for:
- When to use each lens
- How to add new diagrams
- How to customize evidence scoring
- FAQ

**Maintainer**: Auto-maintained by codebase scanning

**Last Updated**: Auto-updated on each regeneration
