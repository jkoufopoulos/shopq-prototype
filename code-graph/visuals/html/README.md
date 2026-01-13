# Interactive HTML Diagram Viewer

Beautiful, interactive HTML versions of MailQ's architecture diagrams.

## Features

✨ **Interactive**
- Zoom in/out with mouse or keyboard (+/-/0 keys)
- Pan around large diagrams
- Smooth animations

📥 **Export**
- Export as SVG (vector, infinite scaling)
- Export as PNG (high-resolution bitmap)
- Print-friendly mode

🎨 **Beautiful**
- Modern, gradient design
- Color-coded components
- Professional typography
- Mobile-responsive

## How to Use

### Open in Browser

**Option 1: Double-click**
```
Double-click: index.html
```

**Option 2: Command line**
```bash
open code-graph/visuals/html/index.html
```

**Option 3: From project root**
```bash
open code-graph/visuals/html/index.html
```

### Keyboard Shortcuts

- `+` or `=` - Zoom in
- `-` - Zoom out
- `0` - Reset zoom
- `Ctrl+P` - Print

### Available Diagrams

1. **System Architecture** (`system_architecture.html`)
   - High-level component overview
   - Shows Extension ↔ Backend ↔ External Services
   - Perfect for onboarding

2. **Classification Flow** (`classification_flow.html`)
   - Detailed step-by-step flow
   - Shows Email → Label with decision points
   - Perfect for debugging

## Auto-Generation

These HTML files are automatically generated from the Mermaid diagrams in the parent directory.

**Regenerate:**
```bash
./code-graph/scripts/quick_regen.sh
```

This will:
1. Scan the codebase
2. Generate Mermaid diagrams (`.md` files)
3. Convert to interactive HTML (`.html` files)

**Auto-regeneration:**
The git post-commit hook automatically regenerates diagrams when you commit changes to `.py` or `.js` files.

## Technical Details

**Stack:**
- Mermaid.js v10 (diagram rendering)
- Vanilla JavaScript (zoom, pan, export)
- CSS Grid & Flexbox (responsive layout)

**Browser Compatibility:**
- Chrome/Edge ✅
- Firefox ✅
- Safari ✅
- Mobile browsers ✅

**No Dependencies:**
All assets loaded from CDN. No local dependencies or build step required.

## Troubleshooting

**Diagrams not loading?**
- Check browser console for errors
- Ensure internet connection (Mermaid.js loads from CDN)
- Try force-refresh (Cmd+Shift+R)

**Export not working?**
- Ensure browser allows file downloads
- Check that diagram has fully rendered before exporting

**Zoom not working?**
- Wait for diagram to fully load (loading spinner should disappear)
- Try keyboard shortcuts instead of buttons

## Links

- [Markdown version: SYSTEM_DIAGRAM.md](../SYSTEM_DIAGRAM.md)
- [Markdown version: CLASSIFICATION_FLOW.md](../CLASSIFICATION_FLOW.md)
- [Documentation Index](../../../INDEX.md)
- [Architecture Docs](../../../docs/ARCHITECTURE.md)

---

**Auto-generated:** Run `./code-graph/scripts/quick_regen.sh` to update
