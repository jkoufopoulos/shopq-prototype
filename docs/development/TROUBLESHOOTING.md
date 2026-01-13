# Quality System Troubleshooting

## Common Issues and Solutions

### Issue: "ANTHROPIC_API_KEY not set" when starting

**Cause**: The `.env` file had inline comments that Python couldn't parse.

**Solution**: Remove inline comments from `.env` file. Comments should be on their own line.

❌ **Wrong:**
```bash
CHECK_INTERVAL_MINUTES=30  # How often to check
```

✅ **Correct:**
```bash
# How often to check (minutes)
CHECK_INTERVAL_MINUTES=30
```

**Status**: ✅ FIXED in current .env file

---

### Issue: load-env.sh not working in some shells

**Cause**: Original script used `source <(...)` which doesn't work in all shells.

**Solution**: Updated to use `while read` loop for better compatibility.

**Status**: ✅ FIXED in scripts/load-env.sh

---

### Issue: ValueError when parsing environment variables

**Error:**
```
ValueError: invalid literal for int() with base 10: '30 # How often...'
```

**Cause**: Python's `int()` can't parse values with inline comments.

**Solution**:
1. Remove inline comments from `.env`
2. Put comments on separate lines above the variable

**Status**: ✅ FIXED

---

### Issue: "No new sessions" when running analysis

**Cause**: No new digest sessions have been created since last analysis.

**Solution**:
- Process emails with ShopQ to create new sessions
- Or lower `MIN_SESSIONS_FOR_ANALYSIS` in `.env` for testing

**Not an error** - system is working correctly, just waiting for new data.

---

### Issue: Quality Monitor Daemon crashes on startup

**Check logs:**
```bash
tail -50 scripts/quality-monitor/quality_monitor.log
```

**Common causes:**
1. `.env` file has syntax errors
2. Environment variables have inline comments
3. Missing dependencies (anthropic library)

**Solutions:**
1. Verify `.env` format (no inline comments)
2. Install dependencies: `pip install anthropic`
3. Check API keys are valid

---

### Issue: Webhook server not receiving notifications

**Check:**
1. Server is running:
   ```bash
   ./scripts/quality-system-status.sh
   ```

2. Port 9000 is accessible:
   ```bash
   curl http://localhost:9000/webhook/digest-generated
   ```

3. Backend is configured to send webhooks (see docs/BACKEND_WEBHOOK_INTEGRATION.md)

**Note**: Webhook is optional. System works without it via polling.

---

## Quick Fixes

### Restart the system
```bash
./scripts/stop-quality-system.sh
./scripts/start-quality-system.sh
```

### Check what's running
```bash
./scripts/quality-system-status.sh
```

### View logs
```bash
# Monitor daemon
tail -f scripts/quality-monitor/quality_monitor.log

# Webhook server
tail -f scripts/quality-monitor/webhook.log

# Both
tail -f scripts/quality-monitor/*.log
```

### Test environment loading
```bash
source scripts/load-env.sh
echo "ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:0:20}..."
echo "GITHUB_TOKEN: ${GITHUB_TOKEN:0:15}..."
```

### Force manual analysis (bypass thresholds)
```bash
# Temporarily lower thresholds in .env
MIN_EMAILS_FOR_ANALYSIS=1

# Restart and run
./scripts/stop-quality-system.sh
./scripts/run-quality-pipeline.sh
```

---

## .env File Format Rules

✅ **DO:**
- Put comments on their own lines
- Use `KEY=VALUE` format
- No spaces around `=`
- Quotes are optional for simple values

❌ **DON'T:**
- Use inline comments (`KEY=VALUE # comment`)
- Add spaces around `=` (`KEY = VALUE`)
- Use complex shell syntax

**Example:**
```bash
# API Keys (required)
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_TOKEN=ghp_...

# Thresholds
# How many emails trigger analysis
MIN_EMAILS_FOR_ANALYSIS=25

# How often to check (minutes)
CHECK_INTERVAL_MINUTES=30
```

---

## Getting Help

1. **Check status**: `./scripts/quality-system-status.sh`
2. **Check logs**: `tail -50 scripts/quality-monitor/*.log`
3. **Verify .env**: `cat .env | grep -v "^#" | grep -v "^$"`
4. **Test loading**: `source scripts/load-env.sh && env | grep ANTHROPIC`

If still stuck, check:
- `SETUP_COMPLETE.md` - Setup guide
- `docs/QUALITY_CONTROL_PIPELINE.md` - Technical docs
- GitHub issues in the quality_monitor.log
