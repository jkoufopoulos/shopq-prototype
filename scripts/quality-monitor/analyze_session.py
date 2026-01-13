#!/usr/bin/env python3
"""Manually analyze a specific session"""

from __future__ import annotations

import os

# Set environment variables BEFORE importing quality_monitor
os.environ["ANTHROPIC_API_KEY"] = (
    "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"
)
os.environ["MAILQ_API_URL"] = "http://localhost:8000"

import sys

sys.path.insert(0, "/Users/justinkoufopoulos/Projects/mailq-prototype/scripts/quality-monitor")

import json
import urllib.request

from quality_monitor import QualityMonitor

# Session to analyze
SESSION_ID = "20251106_031420"
API_URL = "http://localhost:8000"

print(f"Analyzing session: {SESSION_ID}")
print("=" * 80)

# Fetch session data
url = f"{API_URL}/api/tracking/session/{SESSION_ID}"
print(f"\nFetching: {url}")

with urllib.request.urlopen(url, timeout=30) as response:
    session_data = json.loads(response.read().decode())

print(f"✅ Session loaded: {session_data['summary']['total_threads']} threads")
print(f"   Featured: {session_data['summary']['digest_breakdown']['featured']}")
print(f"   Importance: {session_data['summary']['importance']}")

# Create quality monitor
monitor = QualityMonitor()

# Analyze classification
print("\n" + "=" * 80)
print("CLASSIFICATION ANALYSIS")
print("=" * 80 + "\n")

classification_issues = monitor.analyze_with_claude([session_data])
print(f"Found {len(classification_issues)} classification issues:\n")

for i, issue in enumerate(classification_issues, 1):
    print(f"{i}. [{issue['severity'].upper()}] {issue['pattern']}")
    print(f"   Evidence: {issue['evidence'][:100]}...")
    print()

# Analyze digest format
print("\n" + "=" * 80)
print("DIGEST FORMAT ANALYSIS")
print("=" * 80 + "\n")

format_issues = monitor.analyze_digest_format([session_data])
print(f"Found {len(format_issues)} format issues:\n")

for i, issue in enumerate(format_issues, 1):
    print(f"{i}. [{issue['severity'].upper()}] {issue['pattern']}")
    print(f"   Evidence: {issue['evidence'][:100]}...")
    print()

# Summary
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"\nTotal issues found: {len(classification_issues) + len(format_issues)}")
print(f"  - Classification: {len(classification_issues)}")
print(f"  - Format: {len(format_issues)}")
print(f"\nSession: {SESSION_ID}")
print(f"Threads: {session_data['summary']['total_threads']}")
