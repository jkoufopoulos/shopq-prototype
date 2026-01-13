#!/usr/bin/env bash
# Pre-commit hook to prevent new SQLite database files
# Part of database consolidation governance (see CLAUDE.md section 8)

set -e

# Get list of staged .db files
STAGED_DBS=$(git diff --cached --name-only --diff-filter=A | grep '\.db$' || true)

if [ -z "$STAGED_DBS" ]; then
    # No new .db files, all good
    exit 0
fi

# Whitelist: Allowed database files (central database + test database)
ALLOWED_DBS=(
    "mailq/data/mailq.db"
    "mailq/data/mailq_test.db"
)

# Check if any staged .db file is NOT in whitelist
VIOLATION=0
for db_file in $STAGED_DBS; do
    ALLOWED=0
    for allowed in "${ALLOWED_DBS[@]}"; do
        if [ "$db_file" = "$allowed" ]; then
            ALLOWED=1
            break
        fi
    done

    if [ $ALLOWED -eq 0 ]; then
        echo "❌ ERROR: New SQLite database file detected: $db_file"
        VIOLATION=1
    fi
done

if [ $VIOLATION -eq 1 ]; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "DATABASE POLICY VIOLATION"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "MailQ uses ONE SQLite database: mailq/data/mailq.db"
    echo ""
    echo "Creating new .db files is FORBIDDEN without architectural review."
    echo "See CLAUDE.md section 8 (Database Policy) for details."
    echo ""
    echo "What to do instead:"
    echo "  1. Add your tables to mailq/data/mailq.db"
    echo "  2. Use mailq/config/database.py::get_db_connection()"
    echo "  3. Update mailq/config/database.py::init_database() with your schema"
    echo ""
    echo "If you believe this is a legitimate new database:"
    echo "  1. Document the architectural justification"
    echo "  2. Get approval from architecture reviewer"
    echo "  3. Add to whitelist in scripts/hooks/check-no-new-databases.sh"
    echo ""
    echo "To bypass this check (NOT RECOMMENDED):"
    echo "  git commit --no-verify"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 1
fi

exit 0
