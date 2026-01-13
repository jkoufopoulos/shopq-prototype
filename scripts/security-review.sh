#!/bin/bash
# MailQ Security Review Script
# Invokes the mailq-security-reviewer agent to audit the codebase

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🔒 Starting MailQ Security Review${NC}"
echo ""
echo "This will audit:"
echo "  - Authentication & OAuth implementation"
echo "  - Gmail API integration & token handling"
echo "  - LLM classification prompts & output parsing"
echo "  - Extension permissions & content security"
echo "  - Database queries & schema"
echo "  - Logging & error handling"
echo "  - Secret management"
echo ""

# Check if specific focus area was provided
FOCUS_AREA=""
if [ -n "$1" ]; then
    FOCUS_AREA="Focus area: $1"
    echo -e "${YELLOW}Focusing on: $1${NC}"
    echo ""
fi

# Run the agent
# Note: This assumes you're using Claude Code CLI or similar
# Adjust the invocation method based on your setup

claude-code agent run mailq-security-reviewer \
    --prompt "Perform a comprehensive security audit of the MailQ codebase. ${FOCUS_AREA}

Key areas to review:
1. **Authentication Security**: OAuth token handling, refresh logic, storage
2. **Gmail API Integration**: API calls, token usage, data handling
3. **LLM Security**: Prompt injection risks, output validation
4. **Extension Security**: Manifest permissions, CSP, content scripts
5. **Data Security**: Database queries, SQL injection risks, PII handling
6. **Secrets Management**: .env files, credential storage, API keys
7. **Error Handling**: Information leakage in errors/logs

Please provide:
- Critical vulnerabilities (immediate action required)
- High-priority issues (fix before next release)
- Medium-priority improvements (address soon)
- Best practice recommendations

For each issue, include:
- Location (file:line)
- Description
- Risk level
- Remediation steps"

echo ""
echo -e "${GREEN}✅ Security review complete${NC}"
