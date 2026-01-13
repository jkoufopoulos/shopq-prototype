#!/bin/bash
#
# Fetch and analyze Cloud Run logs for ShopQ debugging
#
# Usage:
#   ./fetch-logs.sh          # Last 2 hours
#   ./fetch-logs.sh 6        # Last 6 hours
#   ./fetch-logs.sh 24       # Last 24 hours
#

set -e

PROJECT_ID="mailq-467118"
HOURS_AGO="${1:-2}"  # Default to 2 hours
API_URL="https://shopq-api-488078904670.us-central1.run.app"

# Calculate timestamp for N hours ago
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    START_TIME=$(date -u -v-${HOURS_AGO}H +"%Y-%m-%dT%H:%M:%SZ")
else
    # Linux
    START_TIME=$(date -u -d "${HOURS_AGO} hours ago" +"%Y-%m-%dT%H:%M:%SZ")
fi

echo "🔍 Fetching ShopQ production logs since $START_TIME (last ${HOURS_AGO} hours)..."
echo ""

# Create temp file for logs
TEMP_LOGS=$(mktemp)
trap "rm -f $TEMP_LOGS" EXIT

# Fetch logs (production only)
gcloud logging read \
"resource.type=\"cloud_run_revision\"
AND resource.labels.service_name=\"shopq-api\"
AND timestamp>=\"$START_TIME\"" \
--limit 500 \
--format json \
--project "$PROJECT_ID" > "$TEMP_LOGS" 2>/dev/null

# Check if we got any logs
if [ ! -s "$TEMP_LOGS" ]; then
    echo "❌ No logs found for the specified time range"
    echo "   Start time: $START_TIME"
    echo "   Try: gcloud auth login"
    exit 1
fi

# Parse with Python
python3 <<PYTHON_SCRIPT
import json
import sys
from collections import defaultdict
import urllib.request
import urllib.error

API_URL = "$API_URL"

try:
    with open('$TEMP_LOGS', 'r') as f:
        logs = json.load(f)
except json.JSONDecodeError as e:
    print(f"❌ Failed to parse logs: {e}")
    sys.exit(1)
except FileNotFoundError:
    print("❌ Log file not found")
    sys.exit(1)

if not logs:
    print("⚠️  No logs found in time range")
    sys.exit(0)

# Extract session IDs and API calls
session_ids = set()
api_calls = []
digest_sessions = {}

for log in logs:
    text = log.get('textPayload', '')
    timestamp = log.get('timestamp', '')
    service = log.get('resource', {}).get('labels', {}).get('service_name', 'unknown')
    http_req = log.get('httpRequest', {})

    # Track API calls
    if http_req and 'requestUrl' in http_req:
        url = http_req['requestUrl']
        method = http_req.get('requestMethod', 'GET')
        status = http_req.get('status', 0)

        if '/api/organize' in url or '/api/context-digest' in url:
            api_calls.append({
                'timestamp': timestamp,
                'service': service,
                'method': method,
                'url': url,
                'status': status
            })

    # Extract session IDs from digest logs
    if 'Session ID:' in text:
        session_id = text.split('Session ID:')[1].strip()
        session_ids.add(session_id)
        digest_sessions[session_id] = {
            'timestamp': timestamp,
            'service': service
        }

print('=' * 80)
print('🔍 API CALLS BREAKDOWN')
print('=' * 80)
print(f"Found {len(api_calls)} API calls in the last {int('$HOURS_AGO')} hours\n")

# Group by endpoint
organize_calls = [c for c in api_calls if '/api/organize' in c['url']]
digest_calls = [c for c in api_calls if '/api/context-digest' in c['url']]

if organize_calls:
    print(f"📧 /api/organize calls: {len(organize_calls)}")
    for call in organize_calls[-10:]:  # Last 10
        ts = call['timestamp'][:19].replace('T', ' ')
        status_emoji = '✅' if call['status'] == 200 else '❌'
        print(f"  {ts} [PROD] {status_emoji} {call['method']} - Status: {call['status']}")
    print()

if digest_calls:
    print(f"📋 /api/context-digest calls: {len(digest_calls)}")
    for call in digest_calls[-10:]:  # Last 10
        ts = call['timestamp'][:19].replace('T', ' ')
        status_emoji = '✅' if call['status'] == 200 else '❌'
        print(f"  {ts} [PROD] {status_emoji} {call['method']} - Status: {call['status']}")
    print()

# Fetch detailed session reports
print('=' * 80)
print('📊 DIGEST SESSION DETAILS')
print('=' * 80)
print(f"Found {len(session_ids)} digest sessions\n")

for session_id in sorted(session_ids, reverse=True)[:5]:  # Last 5 sessions
    session_info = digest_sessions.get(session_id, {})
    ts = session_info.get('timestamp', '')[:19].replace('T', ' ')
    svc_name = 'PROD' if 'shopq-api' == session_info.get('service') else 'STAGING'

    print('─' * 80)
    print(f"📅 Session: {session_id} ({ts}) [{svc_name}]")
    print('─' * 80)

    # Fetch session report from API
    try:
        url = f"{API_URL}/api/tracking/session/{session_id}"
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode())

            summary = data.get('summary', {})
            threads = data.get('threads', [])

            # Summary stats
            print(f"  Total threads: {summary.get('total_threads', 0)}")
            print(f"  Critical: {summary.get('critical', 0)}")
            print(f"  Time-sensitive: {summary.get('time_sensitive', 0)}")
            print(f"  Routine: {summary.get('routine', 0)}")
            print(f"  Entities extracted: {summary.get('entities_extracted', 0)}/{summary.get('total_threads', 0)}")
            print(f"  Verifier used: {summary.get('verifier_used', 0)}/{summary.get('total_threads', 0)}")
            print()

            # Show a few examples from each category
            critical_threads = [t for t in threads if t.get('importance') == 'critical']
            time_sensitive = [t for t in threads if t.get('importance') == 'time_sensitive']
            routine_threads = [t for t in threads if t.get('importance') == 'routine']

            if critical_threads:
                print(f"  🔴 Critical emails ({len(critical_threads)}):")
                for thread in critical_threads[:3]:
                    subject = thread.get('subject', 'No subject')[:60]
                    reason = thread.get('importance_reason', 'N/A')[:80]
                    entity = thread.get('entity_type', 'none')
                    print(f"    • {subject}")
                    print(f"      Reason: {reason}")
                    if entity and entity != 'none':
                        print(f"      Entity: {entity}")
                print()

            if time_sensitive:
                print(f"  🟡 Time-sensitive emails ({len(time_sensitive)}):")
                for thread in time_sensitive[:3]:
                    subject = thread.get('subject', 'No subject')[:60]
                    reason = thread.get('importance_reason', 'N/A')[:80]
                    print(f"    • {subject}")
                    print(f"      Reason: {reason}")
                print()

            # Show entities that were extracted
            entities = [t for t in threads if t.get('entity_extracted')]
            if entities:
                print(f"  🏷️  Entities extracted ({len(entities)}):")
                entity_types = defaultdict(int)
                for t in entities:
                    entity_types[t.get('entity_type', 'unknown')] += 1
                for etype, count in entity_types.items():
                    print(f"    • {etype}: {count}")
                print()

    except urllib.error.HTTPError as e:
        print(f"  ⚠️  Failed to fetch session report: HTTP {e.code}")
        print()
    except urllib.error.URLError as e:
        print(f"  ⚠️  Failed to fetch session report: {e.reason}")
        print()
    except Exception as e:
        print(f"  ⚠️  Failed to fetch session report: {e}")
        print()

# Overall insights
print('=' * 80)
print('💡 INSIGHTS')
print('=' * 80)

# Count errors
errors = [log for log in logs if log.get('severity') == 'ERROR']
warnings = [log for log in logs if log.get('severity') == 'WARNING']

if errors:
    print(f"⚠️  Found {len(errors)} errors - investigate these first!")
else:
    print("✅ No errors in this time range")

if warnings:
    print(f"⚠️  Found {len(warnings)} warnings")

if organize_calls:
    success_rate = len([c for c in organize_calls if c['status'] == 200]) / len(organize_calls) * 100
    print(f"📊 /api/organize success rate: {success_rate:.0f}%")

if digest_calls:
    success_rate = len([c for c in digest_calls if c['status'] == 200]) / len(digest_calls) * 100
    print(f"📊 /api/context-digest success rate: {success_rate:.0f}%")

print()
print("💡 To see more logs, run: ./fetch-logs.sh 6  (for 6 hours)")
print("💡 To view a specific session: curl $API_URL/api/tracking/session/<session_id> | jq")

PYTHON_SCRIPT
