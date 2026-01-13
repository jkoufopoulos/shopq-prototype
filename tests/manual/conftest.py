"""Exclude manual tests from pytest collection.

Manual tests require specific fixtures and environments.
Run them individually when needed with proper setup.
"""

# Prevent pytest from collecting tests in this directory
collect_ignore_glob = ["*.py"]
