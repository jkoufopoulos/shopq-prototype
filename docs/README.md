# MailQ Documentation

Comprehensive technical documentation for the MailQ project.

## Quick Navigation

**New to MailQ?** Start here:
1. [../README.md](../README.md) - Project overview
2. [../QUICKSTART.md](../QUICKSTART.md) - Setup and getting started
3. [architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md) - System design

**AI Assistants**: Read [../MAILQ_REFERENCE.md](../MAILQ_REFERENCE.md) first for full context.

## Documentation Structure

### `/architecture` - System Design & Structure

Core architecture, configuration, and system design documentation:

- **ARCHITECTURE.md** - Comprehensive system design and data flow
- **ARCHITECTURE_OVERVIEW.md** - High-level system overview
- **CONFIGURATION.md** - Environment and configuration setup
- **CORE_PRINCIPLES.md** - 5 architectural principles guiding development
- **DATABASE_ARCHITECTURE.md** - Database schema and design
- **DATABASE_POLICY.md** - Database usage policies
- **PROJECT_STRUCTURE.md** - Codebase organization
- **DEPENDENCY_GRAPH.md** - Component dependencies
- **SQL_GUIDE.md** - SQL operations guide
- **AGENTS.md** - Guidelines for AI assistants and contributors
- **importance_deciders.md** - Importance classification logic
- **repo_map.md** - Repository structure map

### `/development` - Developer Workflows

Testing, debugging, deployment, and quality workflows:

- **TESTING.md** - Comprehensive test procedures
- **TESTING_PLAN.md** - Test strategy and planning
- **TESTING_STATUS_REPORT.md** - Current test coverage status
- **TESTING_COMPLETE_SUMMARY.md** - Testing milestone summary
- **WORKFLOWS.md** - Development workflows
- **DEBUGGING.md** - Troubleshooting guide
- **DEPLOYMENT_PLAYBOOK.md** - Production deployment procedures
- **DIGEST_QUALITY_WORKFLOW.md** - Manual digest testing workflow
- **QC_WORKFLOW.md** - Quality control procedures
- **QUALITY_MONITOR.md** - Automated quality monitoring system
- **VERIFICATION_GUIDE.md** - Verification procedures

### `/features` - Feature Documentation

Specific feature implementations and usage:

- **LLM_SECTION_ASSIGNMENT.md** - LLM-based section assignment
- **LLM_USAGE_IN_DIGEST.md** - LLM pipeline in digest generation
- **PHASE_4_TEMPORAL_DECAY.md** - Temporal decay for events
- **GMAIL_CATEGORIES.md** - Gmail label categories
- **VERIFY_FIRST_STRATEGY.md** - Two-pass verification system
- **LABEL_CACHE.md** - In-memory caching system
- **DYNAMIC_EXAMPLES.md** - Few-shot learning system
- **EXTENSION_CHECKPOINTING.md** - Extension state management

### `/product` - Product Planning

User stories, roadmaps, and product planning:

- **USER_STORIES.md** - User stories and acceptance criteria
- **ROADMAP_AUTOMATION.md** - Roadmap automation tools
- **ROADMAP_QUICK_REFERENCE.md** - Quick roadmap reference
- **MULTI_TENANCY_PLAN.md** - Multi-user tenancy design

### `/security` - Security Documentation

Security design, threats, and mitigations:

- **EXTENSION_SECURITY.md** - Chrome extension security design
- **TRUST_THREATS_AND_MITIGATIONS.md** - Security threat analysis
- **ONBOARDING_TRUST_COPY.md** - User-facing trust messaging

### `/operations` - Operational Guides

*Existing directory* - Restart procedures and operational guides

### `/archive` - Historical Documentation

Completed implementations, deprecated plans, and historical docs:

- **implementation/** - Implementation summaries (Type Mapper, Integration, etc.)
- **logging/** - Structured logging implementation docs
- **rollback/** - Rollback procedures and conditions
- **REFACTORING_NEEDED.md** - Historical refactoring analysis

## Documentation Standards

### File Naming
- Use SCREAMING_SNAKE_CASE for general docs (ARCHITECTURE.md)
- Use descriptive names that indicate content
- Avoid version numbers in filenames (use git history)

### Structure
1. **Title and Purpose** - Clear H1 title and 1-2 sentence purpose
2. **Quick Links** - Table of contents for long docs
3. **Main Content** - Well-organized with H2/H3 headers
4. **Examples** - Code examples where applicable
5. **Related Docs** - Links to related documentation

### Maintenance
- Update docs when making related code changes
- Archive completed implementation docs to `/archive`
- Delete or consolidate redundant documentation
- Review and update quarterly

## By Topic

### Architecture & Design
- [architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md) - System design
- [architecture/CORE_PRINCIPLES.md](architecture/CORE_PRINCIPLES.md) - Design principles
- [architecture/DATABASE_ARCHITECTURE.md](architecture/DATABASE_ARCHITECTURE.md) - Database schema

### Testing & Quality
- [development/TESTING.md](development/TESTING.md) - Test procedures
- [development/QUALITY_MONITOR.md](development/QUALITY_MONITOR.md) - Quality monitoring
- [development/VERIFICATION_GUIDE.md](development/VERIFICATION_GUIDE.md) - Verification

### Deployment
- [development/DEPLOYMENT_PLAYBOOK.md](development/DEPLOYMENT_PLAYBOOK.md) - Deployment guide
- [development/WORKFLOWS.md](development/WORKFLOWS.md) - Development workflows

### Features
- [features/LLM_SECTION_ASSIGNMENT.md](features/LLM_SECTION_ASSIGNMENT.md) - LLM section assignment
- [features/PHASE_4_TEMPORAL_DECAY.md](features/PHASE_4_TEMPORAL_DECAY.md) - Temporal decay
- [features/VERIFY_FIRST_STRATEGY.md](features/VERIFY_FIRST_STRATEGY.md) - Two-pass verification

### Security
- [security/EXTENSION_SECURITY.md](security/EXTENSION_SECURITY.md) - Extension security
- [security/TRUST_THREATS_AND_MITIGATIONS.md](security/TRUST_THREATS_AND_MITIGATIONS.md) - Threat analysis

### Product
- [product/USER_STORIES.md](product/USER_STORIES.md) - User stories
- [product/MULTI_TENANCY_PLAN.md](product/MULTI_TENANCY_PLAN.md) - Multi-tenancy design

## Contributing to Documentation

When adding new documentation:
1. Choose the appropriate subdirectory based on topic
2. Follow the documentation standards above
3. Add links to related docs
4. Update this README if adding a new category
5. Archive implementation docs after feature completion

---

**Total Docs**: ~50 files (down from 60+)
**Last Major Cleanup**: 2025-01-17
