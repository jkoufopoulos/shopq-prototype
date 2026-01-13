# Complete User Story

Mark a user story as complete and update ROADMAP.md automatically.

## Instructions

When the user runs `/complete US-XXX`, you should:

1. **Verify the user story exists** in `docs/USER_STORIES.md` and ROADMAP.md
2. **Check acceptance criteria** - Ask user to confirm all criteria are met
3. **Run the update script**:
   ```bash
   python scripts/update_roadmap.py --complete US-XXX --date $(date +%Y-%m-%d)
   ```
4. **Update USER_STORIES.md** - Change status to ✅ DONE
5. **Show summary** of what was completed (reference docs, test results, etc.)
6. **Ask if user wants to commit** the changes

## Example Usage

```
User: /complete US-001
Claude:
📋 Marking US-001 as complete: Calendar Events Never Misclassified

Checking acceptance criteria:
✅ Google Calendar invites → type=event (≥95% accuracy)
✅ Outlook calendar invites → type=event (≥95% accuracy)
✅ Type mapper processes <1ms per email
✅ Zero additional LLM calls for calendar events
✅ Tests: 36/36 passing

All criteria met! Updating roadmap...

[Runs script and updates files]

✅ ROADMAP.md updated
✅ USER_STORIES.md updated

Summary:
- Feature: Type Mapper MVP
- Delivered: 2025-11-10
- Tests: 36/36 passing
- Reference: docs/TYPE_MAPPER_IMPLEMENTATION_SUMMARY.md

Would you like me to create a git commit for these changes?
```

## User Story Format

Always reference the user story format from `docs/USER_STORIES.md`:
- US-XXX format (e.g., US-001, US-012)
- Verify all acceptance criteria boxes are checked
- Update both ROADMAP.md and USER_STORIES.md
- Add completion date

## Related Commands

- `/complete US-XXX` - Mark as complete
- `/progress US-XXX` - Mark as in progress
- `/revert US-XXX` - Mark as not started
