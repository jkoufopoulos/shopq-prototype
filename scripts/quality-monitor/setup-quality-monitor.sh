#!/bin/bash
#
# Interactive setup for Quality Monitor
#

set -e

echo "🔧 Quality Monitor Setup"
echo "========================================"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found"
    exit 1
fi

# Check for API keys
ANTHROPIC_KEY=$(grep "^ANTHROPIC_API_KEY=" .env | cut -d= -f2)
GITHUB_TOKEN=$(grep "^GITHUB_TOKEN=" .env | cut -d= -f2)

NEEDS_SETUP=false

if [ "$ANTHROPIC_KEY" = "PLACEHOLDER_NEED_TO_ADD" ] || [ -z "$ANTHROPIC_KEY" ]; then
    echo "⚠️  ANTHROPIC_API_KEY not configured"
    echo "   Get your API key from: https://console.anthropic.com/settings/keys"
    echo ""
    read -p "Enter your Anthropic API key (or press Enter to skip): " INPUT_ANTHROPIC_KEY

    if [ -n "$INPUT_ANTHROPIC_KEY" ]; then
        # Update .env file
        if grep -q "^ANTHROPIC_API_KEY=" .env; then
            sed -i.bak "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$INPUT_ANTHROPIC_KEY|" .env
        else
            echo "ANTHROPIC_API_KEY=$INPUT_ANTHROPIC_KEY" >> .env
        fi
        echo "✅ Anthropic API key saved"
    else
        NEEDS_SETUP=true
    fi
    echo ""
fi

if [ "$GITHUB_TOKEN" = "PLACEHOLDER_NEED_TO_ADD" ] || [ -z "$GITHUB_TOKEN" ]; then
    echo "⚠️  GITHUB_TOKEN not configured (optional but recommended)"
    echo "   Get a token from: https://github.com/settings/tokens"
    echo "   Required scope: 'repo'"
    echo ""
    read -p "Enter your GitHub token (or press Enter to skip): " INPUT_GITHUB_TOKEN

    if [ -n "$INPUT_GITHUB_TOKEN" ]; then
        # Update .env file
        if grep -q "^GITHUB_TOKEN=" .env; then
            sed -i.bak "s|^GITHUB_TOKEN=.*|GITHUB_TOKEN=$INPUT_GITHUB_TOKEN|" .env
        else
            echo "GITHUB_TOKEN=$INPUT_GITHUB_TOKEN" >> .env
        fi
        echo "✅ GitHub token saved"
    else
        echo "⚠️  Skipping GitHub integration - issues won't be auto-created"
    fi
    echo ""
fi

# Load the updated .env
export $(cat .env | grep -v '^#' | xargs)

# Test Anthropic API if key is set
if [ "$ANTHROPIC_API_KEY" != "PLACEHOLDER_NEED_TO_ADD" ] && [ -n "$ANTHROPIC_API_KEY" ]; then
    echo "🧪 Testing Anthropic API connection..."

    python3 <<PYTHON_TEST
import os
try:
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=10,
        messages=[{"role": "user", "content": "test"}]
    )
    print("✅ Anthropic API connection successful")
except Exception as e:
    print(f"❌ Anthropic API test failed: {e}")
    exit(1)
PYTHON_TEST

    if [ $? -eq 0 ]; then
        echo ""
    else
        echo ""
        echo "⚠️  API test failed. Check your API key."
        exit 1
    fi
fi

if [ "$NEEDS_SETUP" = true ]; then
    echo "========================================"
    echo "⚠️  Setup incomplete"
    echo ""
    echo "To complete setup, edit .env and add:"
    echo "  - ANTHROPIC_API_KEY"
    echo "  - GITHUB_TOKEN (optional)"
    echo ""
    echo "Then run this script again."
    exit 1
fi

echo "========================================"
echo "✅ Quality Monitor is configured!"
echo ""
echo "Next steps:"
echo "  1. Test: ./run-quality-monitor.sh --analyze-now"
echo "  2. Start daemon: ./run-quality-monitor.sh &"
echo "  3. View logs: tail -f quality_monitor.log"
echo "  4. View issues: ./view-quality-issues.sh"
echo ""
echo "The monitor will run every 30 minutes and analyze"
echo "when it has accumulated 5+ digest sessions."
echo ""
