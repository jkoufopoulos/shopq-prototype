# GitHub API Access Rule for Claude Code

## Problem
When fetching from GitHub API in bash scripts or slash commands, the `GITHUB_TOKEN` environment variable from `.env` must be properly loaded.

## Root Cause
- Direct `source .env` doesn't properly export variables in all contexts
- Python `urllib` with `os.getenv()` doesn't inherit bash environment variables correctly
- The token exists and works, but isn't accessible to subprocesses

## Solution: Always use this pattern

```bash
#!/bin/bash
set -e

# ALWAYS load environment with the project's load-env.sh script
source scripts/load-env.sh 2>/dev/null || source ./scripts/load-env.sh 2>/dev/null || true

# Then use curl (NOT Python urllib) for GitHub API calls
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/OWNER/REPO/issues?state=open"
```

## Why This Works
1. `load-env.sh` properly exports all variables from `.env`
2. `curl` inherits exported environment variables correctly
3. Python can then parse curl's output without needing to access env vars

## What NOT to Do
❌ Don't use `source .env` directly
❌ Don't use Python `urllib.request` with `os.getenv('GITHUB_TOKEN')`
❌ Don't assume the token is invalid if you get 401 errors

## Testing
```bash
# Verify token is loaded
source scripts/load-env.sh && echo "Token: ${GITHUB_TOKEN:0:10}..."

# Test GitHub API access
source scripts/load-env.sh && curl -s -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/jkoufopoulos/mailq-prototype/issues?per_page=1" | \
  python3 -c "import sys, json; d=json.load(sys.stdin); print('✅ Works') if isinstance(d, list) else print('❌ Failed:', d.get('message'))"
```

## Created
2025-11-07 - After debugging `/analyze-quality` slash command
