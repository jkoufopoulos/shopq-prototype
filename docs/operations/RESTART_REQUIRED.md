# ⚠️  SERVER RESTART REQUIRED

## Current Situation

Your uvicorn server (PID 65409) has been running since **Sunday 5PM** with `--reload` enabled.

Our code fixes are in place but **NOT ACTIVE** because:
1. The server was started BEFORE we made the changes
2. File watching caused restart loops before any requests could complete
3. The [Importance] logs are still showing (old code is still running)

## Current Log Volume

```bash
$ wc -l /tmp/shopq-api.log
9685 /tmp/shopq-api.log
```

This will continue to grow until you restart the server properly.

## Fix: Restart the Server

### Step 1: Stop the current server

```bash
# Kill the running uvicorn process
kill 65409 89899

# Or kill all uvicorn processes:
pkill -f "uvicorn shopq.api"

# Verify it's stopped:
lsof -ti:8000
# (should return nothing)
```

### Step 2: Clear the log file

```bash
> /tmp/shopq-api.log
echo "Log file cleared at $(date)" > /tmp/shopq-api.log
```

### Step 3: Start the server WITHOUT --reload

```bash
# Production mode (no reload, minimal logging)
uvicorn shopq.api:app --host 127.0.0.1 --port 8000

# If you need debugging:
DEBUG=true uvicorn shopq.api:app --host 127.0.0.1 --port 8000
```

**DO NOT USE `--reload` flag** - it causes restart loops when files are written.

### Step 4: Test a manual run

1. Click "Organize" in the ShopQ extension
2. Check the log:
   ```bash
   tail -100 /tmp/shopq-api.log
   ```
3. You should see:
   - **NO `[Importance]` logs** (unless DEBUG=true)
   - **NO `[Entity]` logs** (unless DEBUG=true)
   - Only API request/response logs
   - ~2-5 lines per request

## Expected Results After Restart

### Production Mode (default)
```bash
$ tail -20 /tmp/shopq-api.log

Log file cleared at Wed Nov  6 [time]
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
✅ Confidence thresholds validated successfully
✅ Feedback manager initialized with connection pool
✅ Vertex Gemini 2.0 classifier initialized (multi-dimensional)
✅ Memory classifier initialized with Vertex AI (multi-dimensional) + connection pool
✅ Feedback manager initialized with connection pool
📊 Using v2 prompt: Urgency-grouped narrative
INFO:     Application startup complete.
INFO:     127.0.0.1:54321 - "POST /api/context-digest HTTP/1.1" 200 OK
```

That's it! **~10 lines** for startup, **1-2 lines per request**.

### Debug Mode (DEBUG=true)
```bash
$ tail -100 /tmp/shopq-api.log

[Same startup logs]
[ContextDigest] Starting context digest generation...
[Importance] CRITICAL: Security alert - ...
[Importance] ROUTINE: Test Email - ...
[Entity] ✅ FlightEntity: United Flight 789...
[ContextDigest] ✅ Context digest generation complete
INFO:     127.0.0.1:54321 - "POST /api/context-digest HTTP/1.1" 200 OK
```

**~100-150 lines per request** (detailed but manageable for debugging).

## Verification

After restarting, run one digest and check:

```bash
# Count logs from a single run
tail -200 /tmp/shopq-api.log | grep -E "\[Importance\]|\[Entity\]|\[ContextDigest\]" | wc -l
```

**Expected:**
- Production mode: `0` (no verbose logs)
- Debug mode: `~100` (per-email logs enabled)

## Why This Happened

1. **uvicorn --reload** watches ALL Python files for changes
2. Quality monitor scripts write `.py` files
3. We edited code files while server was running
4. Each change triggered a restart
5. Restart logs × 20-30 restarts = thousands of lines

## Long-term Solution

For development, use one of these approaches:

**Option A: Disable reload** (recommended)
```bash
uvicorn shopq.api:app --host 127.0.0.1 --port 8000
```

**Option B: Use reload with exclusions** (requires uvicorn config)
```python
# uvicorn_config.py
reload_dirs = ["mailq"]  # Only watch shopq/ directory
reload_excludes = ["scripts/*", "quality_logs/*", "*.db"]
```

**Option C: Separate processes**
- Terminal 1: Run backend (no reload)
- Terminal 2: Run quality monitor
- Never mix file-writing scripts with --reload

---

**TL;DR**: Kill the server (PID 65409), clear the log, restart WITHOUT `--reload`, and you'll see ~10 lines per digest instead of 10,000.
