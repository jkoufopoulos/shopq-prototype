#!/bin/bash
# Load environment variables from .env file
# Source this file in other scripts: source scripts/load-env.sh

# Find project root (where .env is located)
if [ -n "${BASH_SOURCE[0]}" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else
  SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
fi
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "⚠️  .env file not found at: $ENV_FILE"
  echo "   Using environment variables if already set"
  return 1 2>/dev/null || exit 1
fi

# Load .env file, ignoring comments and empty lines
# Export each variable
set -a
while IFS='=' read -r key value; do
  # Skip comments and empty lines
  if [[ ! "$key" =~ ^# && -n "$key" ]]; then
    # Remove leading/trailing whitespace and quotes
    key=$(echo "$key" | xargs)
    value=$(echo "$value" | xargs)
    # Remove quotes if present
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    # Export the variable
    export "$key=$value"
  fi
done < <(grep -v '^#' "$ENV_FILE" | grep -v '^$')
set +a

# Verify critical variables are set
if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "⚠️  ANTHROPIC_API_KEY not found in .env"
fi

if [ -z "$GITHUB_TOKEN" ]; then
  echo "⚠️  GITHUB_TOKEN not found in .env"
fi
