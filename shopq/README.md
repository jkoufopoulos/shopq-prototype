# shopq/ Architecture Guide

This directory contains the core ShopQ backend - a Gmail AI assistant that classifies emails and generates daily digests.

## Directory Structure (7 directories)

```
shopq/
├── api/            # HTTP endpoints, routes, middleware
├── classification/ # Email sorting (rules, patterns, LLM, filters, entities)
├── digest/         # Daily summary (pipeline, rendering, templates)
├── gmail/          # Gmail API integration
├── llm/            # AI/LLM services and prompts
├── storage/        # Database, models, caching
├── shared/         # Config, logging, utilities, features
└── data/           # SQLite database (runtime)
```

### api/
FastAPI application, route handlers, and middleware (auth, rate limiting, security headers).

### classification/
Email importance and type classification: rules engine, pattern matching, LLM classifier, filters (GitHub quality, self-emails), entity extraction, temporal enrichment.

### digest/
Daily digest generation: processing pipeline, section assignment, categorization, HTML rendering, templates.

### gmail/
Gmail API integration: OAuth, client, parser, plus related services (weather, location, link builder).

### llm/
LLM integration: client wrapper for Vertex/Gemini, prompt templates.

### storage/
Data persistence: SQLite database config, repositories, data models, cloud storage, caching, retention policies.

### shared/
Cross-cutting utilities: settings, logging, auth, feature flags, A/B testing, retry logic, telemetry.

## Key Flows

### Email Classification
```
gmail/client → classification/rules_engine → classification/importance_classifier → storage/models
```

### Digest Generation
```
digest/digest_pipeline → digest/categorizer → digest/renderer → digest/templates/
```

### API Request
```
api/routes/ → api/middleware/ → digest/ or classification/ → storage/
```

## Getting Started

1. **Add an endpoint**: `api/routes/`
2. **Add classification logic**: `classification/`
3. **Modify digest output**: `digest/` + `digest/templates/`
4. **Add Gmail integration**: `gmail/`
5. **Add LLM features**: `llm/`
6. **Add shared utility**: `shared/`
