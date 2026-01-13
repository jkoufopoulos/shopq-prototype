#!/usr/bin/env python3
"""
SessionStart hook - appends session header to daily activity log.

Uses date-based logging (one file per day) to:
- Avoid losing data when multiple concurrent sessions run
- Group all work for a day in one file
- Archive old days automatically
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Read JSON from stdin
try:
    input_data = json.load(sys.stdin)
except json.JSONDecodeError:
    input_data = {}

session_id = input_data.get("session_id", "unknown")[:8]
now = datetime.now()
timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
today_str = now.strftime("%Y-%m-%d")

project_dir = os.environ.get("CLAUDE_PROJECT_DIR", str(Path.cwd()))
claude_dir = Path(project_dir) / ".claude"
log_file = claude_dir / f"activity_{today_str}.log"
archive_dir = claude_dir / "activity_archive"

try:
    # Archive logs older than 7 days
    archive_dir.mkdir(exist_ok=True)
    cutoff = now - timedelta(days=7)
    for old_log in claude_dir.glob("activity_*.log"):
        # Extract date from filename (activity_YYYY-MM-DD.log)
        try:
            date_str = old_log.stem.replace("activity_", "")
            log_date = datetime.strptime(date_str, "%Y-%m-%d")
            if log_date < cutoff:
                old_log.rename(archive_dir / old_log.name)
        except ValueError:
            pass  # Skip files that don't match the date pattern

    # Append session header to today's log
    with open(log_file, "a") as f:
        f.write(f"\n=== Session started: {timestamp} (ID: {session_id}) ===\n")

except Exception:
    pass

print(json.dumps({"decision": None}))
sys.exit(0)
