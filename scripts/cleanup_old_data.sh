#!/bin/bash
#
# Scheduled Data Cleanup Script
#
# Implements 14-day retention policy by deleting old email threads,
# digest sessions, and GCS artifacts.
#
# Usage:
#   ./scripts/cleanup_old_data.sh [--dry-run] [--days N]
#
# Options:
#   --dry-run    Show what would be deleted without deleting
#   --days N     Retention period in days (default: 14)
#
# Schedule:
#   Run daily via Cloud Scheduler:
#   gcloud scheduler jobs create http mailq-cleanup \
#     --schedule="0 2 * * *" \
#     --uri="https://shopq-api.run.app/admin/cleanup" \
#     --http-method=POST \
#     --time-zone="America/New_York"

set -euo pipefail

# Configuration
RETENTION_DAYS=${RETENTION_DAYS:-14}
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --days)
      RETENTION_DAYS="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: $0 [--dry-run] [--days N]"
      echo ""
      echo "Options:"
      echo "  --dry-run    Show what would be deleted without deleting"
      echo "  --days N     Retention period in days (default: 14)"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

# Banner
echo "================================================="
echo "ShopQ Data Cleanup - $RETENTION_DAYS Day Retention"
if [[ "$DRY_RUN" == "true" ]]; then
  echo "MODE: DRY RUN (no data will be deleted)"
else
  echo "MODE: PRODUCTION (data will be deleted)"
fi
echo "================================================="
echo ""

# Run Python cleanup script
if [[ "$DRY_RUN" == "true" ]]; then
  PYTHONPATH=. python3 -c "
import sys
sys.path.insert(0, '.')
from shopq.infrastructure.retention import cleanup_old_artifacts, get_retention_stats
import json

print('📊 Current retention stats:')
stats = get_retention_stats()
print(json.dumps(stats, indent=2))
print('')

print('🔍 Running cleanup (DRY RUN)...')
result = cleanup_old_artifacts(days=$RETENTION_DAYS, dry_run=True)
print('')
print('📈 Cleanup results (DRY RUN):')
print(json.dumps(result, indent=2))
print('')
print('✅ DRY RUN complete - no data was deleted')
"
else
  PYTHONPATH=. python3 -c "
import sys
sys.path.insert(0, '.')
from shopq.infrastructure.retention import cleanup_old_artifacts, get_retention_stats
import json

print('📊 Current retention stats BEFORE cleanup:')
stats_before = get_retention_stats()
print(json.dumps(stats_before, indent=2))
print('')

print('🗑️  Running cleanup...')
result = cleanup_old_artifacts(days=$RETENTION_DAYS, dry_run=False)
print('')
print('📈 Cleanup results:')
print(json.dumps(result, indent=2))
print('')

print('📊 Retention stats AFTER cleanup:')
stats_after = get_retention_stats()
print(json.dumps(stats_after, indent=2))
print('')

# Summary
deleted_total = result['email_threads_deleted'] + result['digest_sessions_deleted']
if deleted_total > 0:
    print(f'✅ Cleanup complete - deleted {deleted_total} total items')
else:
    print('✅ Cleanup complete - no old data found')
"
fi

echo ""
echo "================================================="
echo "Cleanup finished at $(date)"
echo "================================================="
