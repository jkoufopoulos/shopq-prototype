#!/usr/bin/env python3
"""
PostToolUse hook - logs all tool invocations to SESSION_LOG.md activity section.

This provides crash recovery by maintaining a real-time log of what Claude is doing,
even before commits are made.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Read JSON from stdin
try:
    input_data = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(0)  # Silently continue if invalid JSON

# Extract data
tool_name = input_data.get("tool_name", "unknown")
tool_input = input_data.get("tool_input", {})
session_id = input_data.get("session_id", "unknown")[:8]  # Short ID
timestamp = datetime.now().strftime("%H:%M:%S")

# Build human-readable summary based on tool type
if tool_name == "Edit":
    file_path = tool_input.get("file_path", "unknown")
    # Get just filename for brevity
    filename = Path(file_path).name
    summary = f"Edit: {filename}"
elif tool_name == "Write":
    file_path = tool_input.get("file_path", "unknown")
    filename = Path(file_path).name
    summary = f"Write: {filename}"
elif tool_name == "Read":
    file_path = tool_input.get("file_path", "unknown")
    filename = Path(file_path).name
    summary = f"Read: {filename}"
elif tool_name == "Bash":
    command = tool_input.get("command", "")[:60]  # Truncate long commands
    summary = f"Bash: {command}"
elif tool_name == "Glob":
    pattern = tool_input.get("pattern", "")
    summary = f"Glob: {pattern}"
elif tool_name == "Grep":
    pattern = tool_input.get("pattern", "")[:40]
    summary = f"Grep: {pattern}"
elif tool_name == "Task":
    desc = tool_input.get("description", "")[:40]
    summary = f"Task: {desc}"
elif tool_name == "TodoWrite":
    todos = tool_input.get("todos", [])
    in_progress = [t.get("content", "")[:30] for t in todos if t.get("status") == "in_progress"]
    summary = f"Todo: {in_progress[0]}" if in_progress else f"Todo: updated {len(todos)} items"
else:
    summary = f"{tool_name}"

# Log file path (date-based: activity_YYYY-MM-DD.log)
project_dir = os.environ.get("CLAUDE_PROJECT_DIR", str(Path.cwd()))
today_str = datetime.now().strftime("%Y-%m-%d")
log_file = Path(project_dir) / ".claude" / f"activity_{today_str}.log"

# Append to log
try:
    with open(log_file, "a") as f:
        f.write(f"{timestamp} | {session_id} | {summary}\n")
except Exception:
    pass  # Don't fail the hook if logging fails

# Return success (don't block anything)
print(json.dumps({"decision": None}))
sys.exit(0)
