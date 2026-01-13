#!/bin/bash
#
# View quality issues from the monitor
#
# Usage:
#   ./view-quality-issues.sh           # Show all unresolved issues
#   ./view-quality-issues.sh --all     # Show all issues
#   ./view-quality-issues.sh --stats   # Show statistics
#

set -e

DB="quality_monitor.db"

if [ ! -f "$DB" ]; then
    echo "❌ Database not found: $DB"
    echo "   Run ./run-quality-monitor.sh first"
    exit 1
fi

case "${1:-}" in
    --all)
        echo "📊 All Quality Issues"
        echo "=================================================================================="
        sqlite3 "$DB" -header -column <<EOF
SELECT
    substr(created_at, 1, 19) as timestamp,
    severity,
    pattern,
    CASE WHEN resolved THEN '✅' ELSE '⏳' END as status,
    CASE WHEN github_issue_url IS NOT NULL THEN '🔗' ELSE '' END as github
FROM quality_issues
ORDER BY created_at DESC;
EOF
        ;;

    --stats)
        echo "📈 Quality Monitor Statistics"
        echo "=================================================================================="
        echo ""
        echo "Sessions Analyzed:"
        sqlite3 "$DB" <<EOF
SELECT '  Total: ' || COUNT(*) FROM analyzed_sessions;
SELECT '  Last 7 days: ' || COUNT(*) FROM analyzed_sessions
    WHERE date(analyzed_at) >= date('now', '-7 days');
EOF
        echo ""
        echo "Issues by Severity:"
        sqlite3 "$DB" <<EOF
SELECT '  ' || UPPER(severity) || ': ' || COUNT(*)
FROM quality_issues
GROUP BY severity
ORDER BY CASE severity WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END;
EOF
        echo ""
        echo "Resolution Status:"
        sqlite3 "$DB" <<EOF
SELECT
    '  Resolved: ' || SUM(CASE WHEN resolved THEN 1 ELSE 0 END) ||
    ' / Unresolved: ' || SUM(CASE WHEN NOT resolved THEN 1 ELSE 0 END)
FROM quality_issues;
EOF
        echo ""
        echo "GitHub Issues Created:"
        sqlite3 "$DB" <<EOF
SELECT '  Total: ' || COUNT(*) FROM quality_issues WHERE github_issue_url IS NOT NULL;
EOF
        ;;

    *)
        echo "🔍 Unresolved Quality Issues"
        echo "=================================================================================="

        # Get unresolved issues with full details
        sqlite3 "$DB" <<EOF
.mode line
SELECT
    '
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 Created: ' || substr(created_at, 1, 19) || '
🎯 Severity: ' || UPPER(severity) || '
❗ Pattern: ' || pattern || '
📊 Evidence: ' || evidence || '
🔍 Root Cause: ' || root_cause || '
💡 Suggested Fix: ' || suggested_fix ||
CASE
    WHEN github_issue_url IS NOT NULL
    THEN '
🔗 GitHub Issue: ' || github_issue_url
    ELSE ''
END as details
FROM quality_issues
WHERE NOT resolved
ORDER BY
    CASE severity WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
    created_at DESC;
EOF

        echo ""
        echo "=================================================================================="
        echo ""
        echo "💡 Commands:"
        echo "  ./view-quality-issues.sh --all     # Show all issues"
        echo "  ./view-quality-issues.sh --stats   # Show statistics"
        echo ""
        echo "To mark an issue as resolved:"
        echo "  sqlite3 $DB \"UPDATE quality_issues SET resolved = 1 WHERE id = <id>\""
        ;;
esac
