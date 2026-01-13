"""Exclude archived tests from pytest collection.

These tests were archived as part of the Phase 0.5 cleanup because they
test deprecated or removed functionality. They are kept for reference only.
"""

# Prevent pytest from collecting tests in this directory
collect_ignore_glob = ["*.py"]
