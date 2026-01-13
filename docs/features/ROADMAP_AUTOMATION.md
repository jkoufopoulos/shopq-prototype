# Roadmap Automation Guide

**Purpose**: Automatically update ROADMAP.md when completing user stories

**Last Updated**: 2025-11-10

---

## Overview

We've automated roadmap updates to:
1. ✅ Reduce manual effort maintaining ROADMAP.md
2. ✅ Ensure consistency between user stories and roadmap
3. ✅ Track progress automatically
4. ✅ Create git commits with proper context

---

## Quick Start

### Using Python Script (Direct)

```bash
# Mark a story as complete
python3 scripts/update_roadmap.py --complete US-001

# Mark as in progress
python3 scripts/update_roadmap.py --in-progress US-003

# Mark as not started (revert)
python3 scripts/update_roadmap.py --not-started US-004

# Complete with custom date
python3 scripts/update_roadmap.py --complete US-002 --date 2025-11-09

# Complete and create git commit
python3 scripts/update_roadmap.py --complete US-001 --commit

# Dry run (preview changes)
python3 scripts/update_roadmap.py --complete US-001 --dry-run
```

---

### Using Claude Code Slash Commands (Recommended)

Claude Code has built-in slash commands that make this even easier:

```
# Mark a story as complete
/complete US-001

# Mark as in progress
/progress US-003
```

**What Claude does**:
1. Verifies the user story exists
2. Checks acceptance criteria (asks you to confirm)
3. Runs the update script automatically
4. Updates both ROADMAP.md and USER_STORIES.md
5. Shows a summary of what was completed
6. Asks if you want to create a git commit

---

## How It Works

### Script Behavior

The `scripts/update_roadmap.py` script:

1. **Finds the user story** in ROADMAP.md by ID (e.g., US-001)
2. **Updates the status line**:
   - 🔴 **NOT STARTED** → status when task hasn't begun
   - 🟡 **IN PROGRESS** → status when actively working
   - ✅ **DONE** (YYYY-MM-DD) → status when complete
3. **Recalculates progress summary**:
   - Counts items per phase (NOW/NEXT/LATER)
   - Updates percentages
   - Updates total progress
4. **Optionally creates git commit** with descriptive message

---

## File Structure

### Files Updated by Automation

1. **ROADMAP.md** (automatically updated)
   - Status emoji changes
   - Progress summary table recalculated
   - Completion dates added

2. **docs/USER_STORIES.md** (manually updated via Claude)
   - Status field updated
   - Acceptance criteria checkboxes marked
   - Reference docs updated

---

## Workflow Examples

### Example 1: Completing a Feature

**Scenario**: You just finished implementing Type Mapper MVP (US-001)

**Steps**:
1. Verify all acceptance criteria are met
2. Run tests to confirm (36/36 passing)
3. Update roadmap:
   ```bash
   python3 scripts/update_roadmap.py --complete US-001 --commit
   ```
4. Or use Claude:
   ```
   /complete US-001
   ```

**Result**:
- ROADMAP.md updated: US-001 marked ✅ **DONE** (2025-11-10)
- Progress summary: NOW section shows 4/13 complete (31%)
- Git commit created: "docs: Mark US-001 as complete"

---

### Example 2: Starting a New Feature

**Scenario**: You're about to work on Centralized Guardrails (US-005)

**Steps**:
1. Update status to in progress:
   ```bash
   python3 scripts/update_roadmap.py --in-progress US-005
   ```
2. Or use Claude:
   ```
   /progress US-005
   ```

**Result**:
- ROADMAP.md updated: US-005 marked 🟡 **IN PROGRESS**
- Progress summary: NOW section shows 1 item in progress
- You can now track active work easily

---

### Example 3: Reverting a Status

**Scenario**: You marked US-004 as in progress by mistake

**Steps**:
1. Revert to not started:
   ```bash
   python3 scripts/update_roadmap.py --not-started US-004
   ```

**Result**:
- ROADMAP.md updated: US-004 marked 🔴 **NOT STARTED**
- Progress summary recalculated

---

## Advanced Usage

### Custom Completion Dates

If you completed a story on a different day:

```bash
python3 scripts/update_roadmap.py --complete US-002 --date 2025-11-09
```

### Bulk Updates

Update multiple stories in sequence:

```bash
python3 scripts/update_roadmap.py --complete US-001 --commit
python3 scripts/update_roadmap.py --complete US-002 --commit
python3 scripts/update_roadmap.py --complete US-003 --commit
```

Or create a simple shell script:

```bash
#!/bin/bash
# complete_batch.sh

for story in US-001 US-002 US-003; do
  python3 scripts/update_roadmap.py --complete $story
done

git add ROADMAP.md
git commit -m "docs: Mark US-001, US-002, US-003 as complete"
```

---

## Integration with Git

### Auto-Commit Option

Use `--commit` to automatically create a git commit:

```bash
python3 scripts/update_roadmap.py --complete US-001 --commit
```

**Commit message format**:
```
docs: Mark US-001 as done
```

### Manual Commit

If you prefer to review changes first:

```bash
# Update roadmap
python3 scripts/update_roadmap.py --complete US-001

# Review changes
git diff ROADMAP.md

# Commit manually
git add ROADMAP.md
git commit -m "docs: Complete US-001 - Type Mapper MVP"
```

---

## Troubleshooting

### Error: "User story US-XXX not found in ROADMAP.md"

**Cause**: The user story doesn't exist in ROADMAP.md

**Solution**: Check that:
1. The story ID is correct (e.g., US-001, not US-1)
2. The story exists in ROADMAP.md (search for `US-XXX`)
3. The story has a `**User Story**: [US-XXX]` line

---

### Warning: "Status line not found for US-XXX"

**Cause**: The story exists but doesn't have a `**Status**: ...` line within 5 lines above

**Solution**: Check the ROADMAP.md format. Each user story should have:

```markdown
#### 1. Feature Name
**Status**: 🔴 **NOT STARTED**
**User Story**: [US-XXX](docs/USER_STORIES.md#us-xxx)
**Priority**: P0
**Effort**: X days
```

---

### Script Not Executable

**Error**: `Permission denied: scripts/update_roadmap.py`

**Solution**: Make the script executable:
```bash
chmod +x scripts/update_roadmap.py
```

---

## Best Practices

### 1. Use Dry Run First

Always preview changes before applying:

```bash
python3 scripts/update_roadmap.py --complete US-001 --dry-run
```

### 2. Verify Acceptance Criteria

Before marking as complete:
1. Review `docs/USER_STORIES.md`
2. Check all acceptance criteria boxes
3. Verify tests pass
4. Confirm reference docs exist

### 3. Update USER_STORIES.md Too

The script updates ROADMAP.md, but you should also update USER_STORIES.md:
- Change `**Status**: 🔴 NOT STARTED` to `**Status**: ✅ DONE`
- Add completion date
- Check acceptance criteria boxes

Claude's `/complete` command does this automatically.

### 4. Commit After Each Completion

Use `--commit` to create atomic commits:

```bash
python3 scripts/update_roadmap.py --complete US-001 --commit
```

This creates a clear history of progress.

---

## Maintenance

### Updating the Script

The script is located at: `scripts/update_roadmap.py`

**If you change ROADMAP.md format**:
1. Update the regex patterns in `update_user_story_status()`
2. Update the progress summary parsing in `update_progress_summary()`
3. Test with `--dry-run` on all user stories

**If you add new status types**:
1. Update `status_emoji` dict in `update_user_story_status()`
2. Update help text and examples
3. Update slash command documentation

---

## Future Enhancements

**Possible improvements**:
- [ ] Auto-detect completion from git commits (parse commit messages)
- [ ] GitHub Action to update roadmap on PR merge
- [ ] Slack/Discord notification when stories complete
- [ ] Dashboard view of progress over time
- [ ] Auto-generate weekly progress reports

---

## Related Documentation

- `/ROADMAP.md` - Consolidated product roadmap
- `docs/USER_STORIES.md` - Formal user stories with acceptance criteria
- `.claude/commands/complete.md` - Claude slash command for completion
- `.claude/commands/progress.md` - Claude slash command for in-progress
- `scripts/update_roadmap.py` - Python automation script

---

**Last Review**: 2025-11-10
**Next Review Due**: 2025-12-10
