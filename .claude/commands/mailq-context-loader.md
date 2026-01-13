# ShopQ Context Loader

Launch the mailq-context-loader agent to initialize the ShopQ development environment and load project guardrails.

## Instructions

Use the Task tool to launch the mailq-context-loader agent with subagent_type="mailq-context-loader".

This agent should be used:
- When starting a new ShopQ development session
- Before beginning substantial ShopQ development work
- After conversation has drifted from established patterns
- When you need to refresh understanding of ShopQ's development constraints

The agent will read CLAUDE.md, restate the North Star, and confirm all development guardrails are loaded.
