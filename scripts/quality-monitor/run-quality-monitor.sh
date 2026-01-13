#!/bin/bash
#
# Run the Quality Monitor daemon
#
# Usage:
#   ./run-quality-monitor.sh                 # Run as daemon
#   ./run-quality-monitor.sh --analyze-now   # One-time analysis
#

set -e

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Install required package if not present
pip install anthropic -q 2>/dev/null || true

# Run monitor
python quality_monitor.py "$@"
