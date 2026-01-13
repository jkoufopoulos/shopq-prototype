# Mark User Story In Progress

Mark a user story as in progress and update ROADMAP.md automatically.

## Instructions

When the user runs `/progress US-XXX`, you should:

1. **Verify the user story exists** in `docs/USER_STORIES.md` and ROADMAP.md
2. **Run the update script**:
   ```bash
   python scripts/update_roadmap.py --in-progress US-XXX
   ```
3. **Update USER_STORIES.md** - Change status to 🟡 IN PROGRESS
4. **Show what's being worked on** (acceptance criteria, estimated effort)
5. **Ask if user wants to commit** the changes

## Example Usage

```
User: /progress US-003
Claude:
📋 Marking US-003 as in progress: Deterministic Digest Rendering

Working on:
- Enforce Pydantic Classification contract at API boundaries (≥99.5%)
- Render digest only from versioned DTO (digest_dto_v3)
- Add snapshot tests for byte-identical HTML
- Wire centralized link builder for Gmail deep-links

Estimated effort: 2 days
Priority: P0

✅ ROADMAP.md updated
✅ USER_STORIES.md updated

Would you like me to create a git commit for these changes?
```

## Related Commands

- `/complete US-XXX` - Mark as complete
- `/progress US-XXX` - Mark as in progress
- `/revert US-XXX` - Mark as not started
