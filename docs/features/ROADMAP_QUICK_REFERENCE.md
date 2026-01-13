# Roadmap Quick Reference

**TL;DR**: How to update the roadmap when you complete work

---

## Quick Commands

### Mark Story as Complete
```bash
python3 scripts/update_roadmap.py --complete US-001
```

### Mark Story as In Progress
```bash
python3 scripts/update_roadmap.py --in-progress US-003
```

### Preview Changes (Dry Run)
```bash
python3 scripts/update_roadmap.py --complete US-001 --dry-run
```

### Complete + Commit in One Step
```bash
python3 scripts/update_roadmap.py --complete US-001 --commit
```

---

## Claude Code Slash Commands (Even Easier!)

```
/complete US-001    # Claude updates everything for you
/progress US-003    # Mark as in progress
```

Claude will:
- ✅ Verify acceptance criteria
- ✅ Update ROADMAP.md
- ✅ Update USER_STORIES.md
- ✅ Create git commit
- ✅ Show summary

---

## File Locations

- **Roadmap**: `/ROADMAP.md`
- **User Stories**: `docs/USER_STORIES.md`
- **Automation Script**: `scripts/update_roadmap.py`
- **Full Documentation**: `docs/ROADMAP_AUTOMATION.md`

---

## Workflow

1. **Complete a feature** (all tests pass, docs written)
2. **Run update script** or use `/complete US-XXX`
3. **Review changes** with `git diff ROADMAP.md`
4. **Commit** (automatically with `--commit` or manually)

---

## Status Emojis

- 🔴 **NOT STARTED** - Hasn't begun
- 🟡 **IN PROGRESS** - Currently working
- ✅ **DONE** (date) - Completed

---

## Need Help?

See full docs: `docs/ROADMAP_AUTOMATION.md`
