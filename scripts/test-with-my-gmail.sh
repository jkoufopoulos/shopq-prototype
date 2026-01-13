#!/bin/bash
# Run Playwright tests using your personal Chrome profile with real Gmail

# Make sure Chrome is closed first
if pgrep -x "Google Chrome" > /dev/null; then
    echo "⚠️  Chrome is running. Please close Chrome first to avoid profile lock issues."
    echo "Press Enter after closing Chrome, or Ctrl+C to cancel..."
    read
fi

# Set Chrome user data directory
export CHROME_USER_DATA="$HOME/Library/Application Support/Google/Chrome"

echo "🔧 Using Chrome profile: $CHROME_USER_DATA"
echo "📧 Tests will run against your real Gmail account"
echo ""

# Run Playwright tests
npx playwright test "$@"
