#!/usr/bin/env python3
"""
Fix email_tracker.py to use central database.

Replaces all sqlite3.connect(self.db_path) with get_db_connection() context manager.
"""

import re

# Read the file
with open("mailq/email_tracker.py") as f:
    content = f.read()

# Step 1: Replace imports
content = content.replace(
    "import sqlite3\nfrom datetime import datetime", "from datetime import datetime"
)

# Step 2: Fix _init_db method - already has db_transaction
# Just need to indent the cursor.execute block

# Step 3: Replace all method-level sqlite3.connect patterns
# Pattern: conn = sqlite3.connect(self.db_path)\n        cursor = conn.cursor()
# Replace with: with get_db_connection() as conn:\n            cursor = conn.cursor()

pattern = r"(\s+)conn = sqlite3\.connect\(self\.db_path\)\n\1cursor = conn\.cursor\(\)"
replacement = r"\1with get_db_connection() as conn:\n\1    cursor = conn.cursor()"
content = re.sub(pattern, replacement, content)

# Step 4: Remove conn.commit() and conn.close() calls at method ends
content = re.sub(r"\n\s+conn\.commit\(\)", "", content)
content = re.sub(r"\n\s+conn\.close\(\)", "", content)

# Step 5: Fix the _init_db conn.commit/close (already in db_transaction, so remove)
# The _init_db uses db_transaction() which auto-commits

# Write the fixed file
with open("mailq/email_tracker.py", "w") as f:
    f.write(content)

print("✅ Fixed email_tracker.py to use central database")
