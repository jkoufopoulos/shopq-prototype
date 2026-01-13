# Code-Graph Usage

## Quick Commands

```bash
# Architecture Explorer (NEW!) - Browse all components
open code-graph/visuals/html/explorer.html

# View diagrams (interactive HTML)
open code-graph/visuals/html/index.html

# Regenerate diagrams (<1 second)
./code-graph/scripts/quick_regen.sh
```

## Architecture Explorer

**NEW in Phase 4**: Interactive component browser that lets you explore the entire codebase architecture.

**Features:**
- 🔍 **Full-text search** - Search across component names and descriptions
- 📂 **Layer filtering** - Filter by extension, backend, or view all
- 🔗 **Quick navigation** - One-click jump to docs, source code, and tests
- 🎯 **Related components** - See components in the same layer or subsystem
- 📊 **Diagram integration** - Links to relevant visual diagrams for each component
- ⌨️ **Keyboard shortcuts** - Cmd/Ctrl+K to search, Esc to clear

**Perfect for:**
- Onboarding new developers (find components quickly)
- Understanding dependencies (see what connects to what)
- Finding source code and tests (no grepping needed)
- Exploring the architecture without reading through file lists

## What Gets Updated

When you run `quick_regen.sh`:
1. Scans `shopq/*.py` and `extension/*.js` files
2. Regenerates 4 Mermaid diagrams
3. Creates interactive HTML versions
4. **NEW**: Injects ShopQ-specific context from `SHOPQ_REFERENCE.md` into each diagram

## Features

### Dynamic Context Panels

Each interactive HTML diagram now includes a **context-aware info panel** with:

- **System Architecture**: Core flow, classification dimensions, key components
- **Classification Flow**: Confidence thresholds, verifier triggers, prompt files
- **Learning Loop**: How learning works, rule confidence, databases
- **Cost & Performance**: Cost breakdown, performance targets, optimization

**How to use:**
- Click the **"📚 Context"** button on any diagram page
- Info panel slides in from the right with relevant ShopQ details
- Press **ESC** or click **✕** to close
- Context automatically updates when you regenerate diagrams

### Auto-Update

Diagrams auto-regenerate on git commit via `.git/hooks/post-commit`

All context is pulled dynamically from `SHOPQ_REFERENCE.md`, so your diagrams always reflect the latest system information.

## Archive

Old codebase analysis tools moved to `code-graph/archive/` (not maintained).

See [README.md](README.md) for full documentation.
