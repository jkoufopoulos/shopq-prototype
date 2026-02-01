# Code Review

Launch the code-reviewer agent to review code for security vulnerabilities, error handling gaps, race conditions, and architectural risks.

## Instructions

Use the Task tool to launch the code-reviewer agent with subagent_type="code-reviewer".

Provide context about:
- What code was recently changed or added
- Which files/modules were modified
- Any specific concerns to focus on

The agent will analyze the code and provide a detailed review with severity-categorized issues and specific fixes.
