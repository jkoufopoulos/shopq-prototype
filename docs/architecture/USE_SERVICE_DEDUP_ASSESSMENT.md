# USE_SERVICE_DEDUP Flag Assessment

## Status: Dead Code — Recommend Removal

### What it is

`USE_SERVICE_DEDUP` is a boolean feature flag defined in `shopq/config.py:65`:

```python
USE_SERVICE_DEDUP: bool = os.getenv("SHOPQ_USE_SERVICE_DEDUP", "true").lower() == "true"
```

### Finding

The flag is **never checked anywhere in the codebase**. It was added in commit `68bf886` as a rollback lever before implementing dedup in ReturnsService. However, when the old inline dedup code was removed in commit `433976e`, no conditional branch was preserved — the service dedup path became the only path.

**Evidence:**
- `grep -r "USE_SERVICE_DEDUP" --include="*.py"` returns only the definition in `config.py`
- `shopq/api/routes/returns.py` unconditionally calls `ReturnsService.dedup_and_persist()`
- There is no fallback to inline dedup logic (it was deleted)

### Why it's safe to remove

1. **No runtime effect:** Setting the env var to `false` changes nothing — no code reads it
2. **Old code is gone:** The inline dedup that this flag was meant to toggle back to was removed in the same Phase 1 commit series
3. **Tests pass without it:** All regression tests use the service dedup path exclusively
4. **Config clutter:** It occupies a line in config.py and could mislead someone into thinking there's a toggle

### Recommendation

**Remove in the first Phase 2 commit** (or as a standalone housekeeping commit before Phase 2 starts).

Change required:
- Delete the `USE_SERVICE_DEDUP` line from `shopq/config.py`
- Delete the re-export reference if any (there isn't one currently)

This is a 1-line deletion with zero behavioral impact.

### Exit Criteria (if keeping through Phase 2)

If there were a reason to keep the flag (there isn't), the exit criteria would be:
1. Service dedup has been live for 2+ weeks with no merge bugs reported
2. Batch endpoint stats show `cards_merged > 0` in production logs (proving merge path works)
3. No rollback to inline dedup has been needed

All three conditions are already met (Phase 1 has been stable since completion), so the flag should simply be removed.
