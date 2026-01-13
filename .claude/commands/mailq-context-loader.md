# MailQ Context Loader

Launch the mailq-context-loader agent to initialize the MailQ development environment and load project guardrails.

## Instructions

Use the Task tool to launch the mailq-context-loader agent with subagent_type="mailq-context-loader".

This agent should be used:
- When starting a new MailQ development session
- Before beginning substantial MailQ development work
- After conversation has drifted from established patterns
- When you need to refresh understanding of MailQ's development constraints

The agent will read CLAUDE.md, restate the North Star, and confirm all development guardrails are loaded.
