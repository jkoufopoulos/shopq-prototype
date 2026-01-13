"""FastAPI server for ShopQ email classification"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shopq.api.middleware.rate_limit import RateLimitMiddleware  # noqa: E402
from shopq.api.middleware.security_headers import SecurityHeadersMiddleware  # noqa: E402
from shopq.api.models import (
    EmailBatch,
    OrganizeResponse,
    SummaryRequest,
    VerifyRequest,
    VerifyResponse,
)
from shopq.api.routes.categories import router as categories_router
from shopq.api.routes.categories import set_category_manager, set_classifier
from shopq.api.routes.confidence import router as confidence_router
from shopq.api.routes.debug import router as debug_router
from shopq.api.routes.debug import set_last_batch
from shopq.api.routes.debug_ab_testing import router as debug_ab_testing_router
from shopq.api.routes.feature_gates import router as feature_gates_router  # noqa: E402
from shopq.api.routes.feedback import router as feedback_router  # noqa: E402
from shopq.api.routes.feedback import set_feedback_manager  # noqa: E402
from shopq.api.routes.health import router as health_router
from shopq.api.routes.linker import router as linker_router  # noqa: E402
from shopq.api.routes.returns import router as returns_router  # noqa: E402
from shopq.api.routes.rules import router as rules_router
from shopq.api.routes.test import router as test_router  # noqa: E402
from shopq.api.routes.tracking import router as tracking_router  # noqa: E402
from shopq.classification.memory_classifier import MemoryClassifier  # noqa: E402
from shopq.concepts.feedback import FeedbackManager  # noqa: E402
from shopq.digest.category_manager import CategoryManager  # noqa: E402
from shopq.digest.context_digest import ContextDigest  # noqa: E402
from shopq.digest.support import normalize_email_payload  # noqa: E402
from shopq.infrastructure.database import init_database  # noqa: E402
from shopq.observability.logging import get_logger  # noqa: E402
from shopq.observability.telemetry import log_event
from shopq.observability.tracking import EmailThreadTracker  # noqa: E402
from shopq.runtime.flags import is_enabled
from shopq.utils.redaction import redact  # noqa: E402

# Load environment variables from .env file
load_dotenv()

app = FastAPI(title="ShopQ API", version="2.0.0-mvp")


# Custom validation error handler to prevent information leakage
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Custom validation error handler that prevents leaking internal validation logic.

    Side Effects:
        - Logs detailed validation errors for debugging (with PII redaction)
        - Returns sanitized error messages to clients
        - Increments validation error counter for monitoring
    """
    from shopq.observability.telemetry import counter
    from shopq.utils.redaction import redact

    # Log full error for debugging (with PII redaction)
    logger.warning("Validation error on %s: %s", redact(str(request.url)), exc.errors())

    # Count validation errors for monitoring
    counter("api.validation_errors")

    # Return sanitized error to client (don't leak validation rules)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Invalid request format. Please check your request and try again.",
            "error_count": len(exc.errors()),
            # Only expose field names, not validation logic
            "invalid_fields": [str(err["loc"][-1]) for err in exc.errors()],
        },
    )


# CORS - Restrict to specific origins for security
# Only allow requests from Gmail and our Cloud Run deployment
# Set extension ID in production after Chrome Web Store publish
SHOPQ_EXTENSION_ID = os.getenv("SHOPQ_EXTENSION_ID", "")

ALLOWED_ORIGINS = [
    "https://mail.google.com",
    "https://shopq-api-488078904670.us-central1.run.app",
]

# Add Chrome extension origin if ID is configured
if SHOPQ_EXTENSION_ID:
    ALLOWED_ORIGINS.append(f"chrome-extension://{SHOPQ_EXTENSION_ID}")

# Allow localhost and unpacked extensions in development only
if os.getenv("SHOPQ_ENV", "development") == "development":
    ALLOWED_ORIGINS.extend(
        [
            "http://localhost:3000",
            "http://localhost:8000",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8000",
            "chrome-extension://lklcpjlgobojoakdnnjkcjgkfjehioip",  # Local dev extension
        ]
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)

# Rate limiting - prevent abuse and cost overruns
# Request limits: 60/minute, 1000/hour per IP
# Email limits: 100/minute, 500/hour per IP (prevents cost DoS via large batches)
app.add_middleware(
    RateLimitMiddleware,
    requests_per_minute=60,
    requests_per_hour=1000,
    emails_per_minute=100,
    emails_per_hour=500,
)

# Security headers - defense in depth
# Adds CSP, X-Frame-Options, HSTS, etc.
app.add_middleware(SecurityHeadersMiddleware)

# Initialize database schema (idempotent - safe to run on every startup)
logger = get_logger(__name__)

try:
    logger.info("Initializing database schema...")
    init_database()  # Initialize core tables
    logger.info("Core tables initialized successfully")

    EmailThreadTracker()  # Initialize tracking tables
    logger.info("Tracking tables initialized successfully")

    logger.info("Database initialization complete")

except FileNotFoundError as e:
    logger.critical("Database file not found: %s", e)
    logger.critical("This should not happen in production. Check Docker build.")
    raise RuntimeError(f"Database initialization failed: {e}") from e
except sqlite3.OperationalError as e:
    logger.critical("Database schema error: %s", e)
    logger.critical("Database may be corrupted or locked by another process")
    raise RuntimeError(f"Database initialization failed: {e}") from e
except Exception as e:
    logger.critical("Unexpected database initialization error: %s", e)
    raise RuntimeError(f"Database initialization failed: {e}") from e

# Validate security configuration on startup
env = os.getenv("SHOPQ_ENV", "development")
if env == "production":
    if not os.getenv("SHOPQ_ADMIN_API_KEY"):
        logger.critical(
            "=" * 70 + "\n"
            "🔴 CRITICAL SECURITY MISCONFIGURATION\n"
            "🔴 SHOPQ_ADMIN_API_KEY is not set in production!\n"
            "🔴 All admin endpoints would be UNPROTECTED\n"
            "🔴 Generate with: python -c 'import secrets; "
            "print(secrets.token_urlsafe(32))'\n" + "=" * 70
        )
        raise RuntimeError(
            "Security misconfiguration: SHOPQ_ADMIN_API_KEY not set in "
            "production. Refusing to start with unprotected admin endpoints."
        )
    logger.info("✓ Admin API authentication enabled (production mode)")
else:
    if not os.getenv("SHOPQ_ADMIN_API_KEY"):
        logger.warning(
            "=" * 70 + "\n"
            "⚠️  SECURITY: SHOPQ_ADMIN_API_KEY not set\n"
            "⚠️  All admin endpoints are UNPROTECTED\n"
            "⚠️  This is only acceptable in development\n"
            "⚠️  Generate with: python -c 'import secrets; "
            "print(secrets.token_urlsafe(32))'\n" + "=" * 70
        )
    else:
        logger.info("✓ Admin API authentication enabled (development mode)")

# Initialize services
category_manager = CategoryManager()
classifier = MemoryClassifier(category_manager)
feedback_manager = FeedbackManager()

# Initialize Context Digest (gracefully handle missing GOOGLE_API_KEY)
context_digest: ContextDigest | None
try:
    context_digest = ContextDigest(verbose=True)  # Context Digest (timeline-centric)
except ValueError as e:
    logger.warning("Context digest disabled: %s", e)
    context_digest = None

# Inject dependencies into routers
set_feedback_manager(feedback_manager)
set_category_manager(category_manager)
set_classifier(classifier)

# Include routers
app.include_router(debug_router)
app.include_router(debug_ab_testing_router)
app.include_router(linker_router)
app.include_router(feedback_router)
app.include_router(tracking_router)
app.include_router(test_router)
app.include_router(feature_gates_router)
app.include_router(health_router)
app.include_router(confidence_router)
app.include_router(rules_router)
app.include_router(categories_router)
app.include_router(returns_router)
# OLD digest_router removed - using SimpleDigest via /api/summary endpoint


log_event("api.startup", service="mailq", version="2.0.0-mvp")


# ============================================================================
# WAL CHECKPOINT BACKGROUND TASK
# ============================================================================
def _wal_checkpoint_loop():
    """Background thread that periodically checkpoints the WAL file

    Side Effects:
        - Calls checkpoint_wal() which writes to shopq.db (WAL checkpoint operation)
        - Logs checkpoint statistics via logger.info() and logger.error()
        - Runs indefinitely until process termination
    """
    from shopq.infrastructure.database import checkpoint_wal

    # Wait 5 minutes before first checkpoint (let app warm up)
    time.sleep(300)

    while True:
        try:
            stats = checkpoint_wal()
            if stats["bytes_freed"] > 1024 * 1024:  # Log if freed > 1MB
                logger.info("WAL checkpoint freed %d MB", stats["bytes_freed"] // (1024 * 1024))
        except Exception as e:
            logger.error("WAL checkpoint failed: %s", e)

        # Checkpoint every 5 minutes
        time.sleep(300)


# Start WAL checkpoint thread
_checkpoint_thread = threading.Thread(target=_wal_checkpoint_loop, daemon=True)
_checkpoint_thread.start()
logger.info("WAL checkpoint background task started (5-minute interval)")


# ============================================================================
# STARTUP VALIDATION
# ============================================================================
@app.on_event("startup")
async def validate_database_schema() -> None:
    """Validate database schema on startup (fail fast if database is broken)

    Side Effects:
        - Calls validate_schema() which reads from shopq.db
        - Logs validation results via logger.info() and logger.critical()
        - May raise RuntimeError on validation failure (crashes the app)
    """
    from shopq.infrastructure.database import validate_schema

    try:
        validate_schema()
        logger.info("Database schema validation passed")
    except ValueError as e:
        logger.critical("Database schema invalid: %s", e)
        raise RuntimeError(f"Database schema validation failed: {e}") from e
    except Exception as e:
        logger.critical("Startup validation error: %s", e)
        raise


# ============================================================================
# CORE ENDPOINTS
# ============================================================================


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "ShopQ API",
        "version": "2.0.0-mvp",
        "status": "running",
        "schema_version": "mvp.v1",
        "endpoints": {
            "classify": "/api/organize",
            "feedback": "/api/feedback",
            "dashboard": "/api/feedback/dashboard",
            "debug": "/api/debug/last-batch",
            "digest": "/api/digest/generate",
            "digest_preview": "/api/digest/preview/{period}",
        },
    }


@app.post("/api/organize", response_model=OrganizeResponse)
async def organize_emails(batch: EmailBatch) -> dict[str, Any]:
    """Classify emails using multi-dimensional schema

    Side Effects:
        - Calls classify_batch() which may write to confidence_logs table in shopq.db
        - Calls set_last_batch() which stores batch data in memory for debug endpoint
        - Logs telemetry events via log_event()
        - May call LLM APIs (Gemini) for classification
    """
    from shopq.api.routes.organize import (
        classify_batch,
    )  # Lazy import to avoid circular dependency

    # Pass Pydantic models directly - classify_batch handles both dicts and objects
    results, stats = classify_batch(
        classifier=classifier,
        emails=batch.emails,  # type: ignore[arg-type]
        user_prefs=batch.user_prefs or {},
    )

    # Store for debug endpoint
    set_last_batch(
        {
            "timestamp": datetime.now().isoformat(),
            "results": [
                {
                    "from": r["from"],
                    "labels": r.get("gmail_labels", r.get("labels", [])),
                    "confidence": r["type_conf"],
                    "decider": r["decider"],
                }
                for r in results
            ],
            "stats": stats,
            "elapsed_ms": stats.get("elapsed_ms", 0),
        }
    )

    return {"results": results, "model_version": "mvp-v1-multidim"}


@app.post("/api/verify", response_model=VerifyResponse)
async def verify_classification(request: VerifyRequest) -> dict[str, Any]:
    """
    Phase 6: Selective verifier - challenges first classification

    Uses disagreeable rubric prompt to catch obvious errors like:
    - Review requests marked as action_required
    - Promotional emails with action language
    - Survey/feedback marked as urgent

    Side Effects:
        - Calls run_verify() which may call LLM APIs (Gemini) for verification
        - Logs telemetry events via log_event()
    """
    from shopq.api.routes.verify import verify_classification as run_verify

    try:
        return run_verify(
            classifier=classifier,
            email=request.email,
            first_result=request.first_result,
            features=request.features,
            contradictions=request.contradictions,
        )

    except Exception as e:
        log_event("api.verify.error", error=str(e))
        # On error, confirm first classification (fail-safe)
        return {
            "verdict": "confirm",
            "correction": None,
            "rubric_violations": [],
            "confidence_delta": 0.0,
            "why_bad": f"Verifier error: {str(e)[:100]}",
        }


async def generate_context_digest_v1(request: SummaryRequest) -> dict[str, Any]:
    """
    Generate context digest using V1 pipeline (old context_digest.py).

    Side Effects:
        - Calls shopq.context_digest.generate() which may call LLM APIs
        - Calls external weather API via WeatherService
        - Logs telemetry events via log_event()
        - May write HTML/JSON to quality_logs/ directory (in caller)

    Returns:
        Dict with digest HTML and metadata
    """
    # Telemetry: Track items with missing classification fields (helps detect upstream issues)
    items_missing_classification = 0
    items_missing_type = 0

    for item in request.current_data:
        classification = item.get("classification", {})
        if not classification:
            items_missing_classification += 1
        elif not classification.get("type"):
            items_missing_type += 1

    if items_missing_classification > 0 or items_missing_type > 0:
        total = len(request.current_data)
        logger.warning(
            f"[TELEMETRY] Classification data quality issue: "
            f"{items_missing_classification}/{total} missing classification, "
            f"{items_missing_type}/{total} missing type. Defaults applied."
        )
        log_event(
            "api.context_digest.incomplete_classification",
            total_items=len(request.current_data),
            missing_classification=items_missing_classification,
            missing_type=items_missing_type,
        )

    emails = []
    for item in request.current_data:
        # Support both nested classification object AND top-level fields (sidebar path)
        # Sidebar sends: { type: 'newsletter', importance: 'routine', ... }
        # Logger sends: { classification: { type: 'newsletter', ... } }
        normalized_email = normalize_email_payload(
            {
                "messageId": item.get("messageId"),
                "threadId": item.get("threadId"),
                "subject": item.get("subject"),
                "snippet": item.get("snippet"),
                "body": item.get("body", ""),
                "from": item.get("from"),
                "from_name": item.get("from_name"),
                "classification": item.get("classification", {}),
                "emailTimestamp": item.get("emailTimestamp", item.get("timestamp")),
                # Forward top-level fields for sidebar path (fallback in normalize_email_payload)
                "type": item.get("type"),
                "importance": item.get("importance"),
                "client_label": item.get("client_label"),
                "attention": item.get("attention"),
            }
        )
        emails.append(normalized_email.to_dict())

    # Debug logging (gated behind environment variable)
    if os.getenv("SHOPQ_DEBUG_CLASSIFICATION", "").lower() in ("true", "1", "yes") and emails:
        sample_types = [(e.get("subject", "")[:20], e.get("type")) for e in emails[:5]]
        logger.debug(f"[DEBUG] First 5 normalized emails (subject, type): {sample_types}")

    log_event(
        "api.context_digest.v1.converted",
        email_count=len(emails),
        sample_subject=redact(emails[0].get("subject", "")) if emails else None,
    )

    # Generate context digest using old pipeline
    result = context_digest.generate(
        emails,
        timezone=request.timezone,
        client_now=request.client_now,
        timezone_offset=request.timezone_offset_minutes,
        city_hint=request.city,
        region_hint=request.region,
        user_name=request.user_name,
        raw_digest=request.raw_digest,
    )

    log_event(
        "api.context_digest.v1.success",
        word_count=result.get("word_count"),
        entities=result.get("entities_count"),
        featured=result.get("featured_count"),
        critical=result.get("critical_count"),
        verified=result.get("verified"),
    )

    # Return simplified result for A/B testing
    return result


async def generate_context_digest_v2(request: SummaryRequest) -> dict[str, Any]:
    """
    Generate context digest using V2 pipeline.

    DEPRECATED: This function now delegates to generate_context_digest_v1,
    which internally uses the 'digest_pipeline_v2' feature flag to switch
    to the 7-stage V2 pipeline in context_digest.py:generate_v2().

    The old standalone V2 implementation was removed because it imported
    non-existent stage classes (CriticalEmailDetectionStage, etc.).

    Side Effects:
        - Same as generate_context_digest_v1

    Returns:
        Dict with same structure as V1 for backward compatibility
    """
    log_event("api.context_digest.v2.delegating_to_v1", email_count=len(request.current_data))

    # Delegate to V1 which uses digest_pipeline_v2 feature flag internally
    # See context_digest.py:generate() -> generate_v2() for the actual V2 pipeline
    return await generate_context_digest_v1(request)


@app.post("/api/context-digest")
async def generate_context_digest(request: SummaryRequest) -> dict[str, Any]:
    """
    Generate context digest - timeline-centric narrative (<90 words)

    NEW: Uses entity extraction + LLM narrative generation
    Features:
    - Entity extraction (flights, events, deadlines)
    - Importance classification (critical/time-sensitive/routine)
    - Weather enrichment ("it'll be 95° in Houston")
    - Transparent noise summary
    - Adaptive word count based on volume
    - HTML card output

    Side Effects:
        - Calls LLM APIs (Gemini) for digest generation
        - Calls external weather API via WeatherService
        - Writes HTML and JSON files to quality_logs/ directory
        - Logs telemetry events via log_event()
        - May write to A/B testing database if enabled
    """
    try:
        log_event(
            "api.context_digest.request",
            email_count=len(request.current_data),
            session_hint=redact(datetime.now().isoformat()),
            timezone=request.timezone,
            timezone_offset=request.timezone_offset_minutes,
        )

        # Check if A/B testing is enabled
        ab_test_enabled = os.getenv("AB_TEST_ENABLED", "false").lower() in ("true", "1", "yes")

        if ab_test_enabled:
            # A/B Testing Mode: Run both pipelines and compare
            from shopq.concepts.ab_testing import get_ab_test_runner

            runner = get_ab_test_runner()

            # Define wrapper functions that match the request format
            async def run_v1(req_data: dict[str, Any]) -> dict[str, Any]:
                # Temporarily store original request
                temp_request = SummaryRequest(**req_data)
                return await generate_context_digest_v1(temp_request)

            async def run_v2(req_data: dict[str, Any]) -> dict[str, Any]:
                temp_request = SummaryRequest(**req_data)
                return await generate_context_digest_v2(temp_request)

            # Run A/B test
            ab_result = await runner.run_test(
                request_data=request.model_dump(),
                run_v1_func=run_v1,
                run_v2_func=run_v2,
            )

            log_event(
                "api.context_digest.ab_test",
                test_id=ab_result.test_id,
                winner=ab_result.winner,
                latency_delta_ms=ab_result.latency_delta_ms,
            )

            # Both pipelines have already been run and results stored
            # Return the winner's result (fallback to V1 if tie)
            if ab_result.winner == "v2" and ab_result.v2_result:
                return ab_result.v2_result
            if ab_result.v1_result:
                return ab_result.v1_result
            # Fallback - shouldn't happen but handle gracefully
            return await generate_context_digest_v1(request)

        # Check feature flag for V2 digest pipeline
        # Use first email's threadId as stable user_id for consistent rollout
        user_id = None
        if request.current_data:
            user_id = request.current_data[0].get("threadId") or request.current_data[0].get("id")

        use_v2_pipeline = is_enabled("DIGEST_V2", user_id=user_id, default=False)

        log_event(
            "api.context_digest.pipeline_selection",
            pipeline="v2" if use_v2_pipeline else "v1",
            user_id=redact(user_id) if user_id else None,
        )

        if use_v2_pipeline:
            # V2 Pipeline: New concepts/ digest pipeline
            return await generate_context_digest_v2(request)

        # V1 Pipeline: Old context_digest.py (default)
        result = await generate_context_digest_v1(request)

        # Log actual digest output for quality comparison
        try:
            # Create quality_logs directory if it doesn't exist
            log_dir = "quality_logs"
            os.makedirs(log_dir, exist_ok=True)

            # Use session_id from digest result to ensure filename matches tracking database
            session_id = result.get("session_id", datetime.now().strftime("%Y%m%d_%H%M%S"))

            # Save HTML digest output
            html_log_file = os.path.join(log_dir, f"actual_digest_{session_id}.html")
            with open(html_log_file, "w", encoding="utf-8") as f:
                f.write(f"<!-- Generated: {datetime.now().isoformat()} -->\n")
                f.write(f"<!-- Emails: {len(request.current_data)} -->\n")
                f.write(f"<!-- Featured: {result.get('featured_count', 0)} -->\n")
                f.write(f"<!-- Critical: {result.get('critical_count', 0)} -->\n")
                f.write(result["html"])

            # Save input emails for manual review and ideal determination
            emails_log_file = os.path.join(log_dir, f"input_emails_{session_id}.json")
            with open(emails_log_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "email_count": len(request.current_data),
                        "emails": [
                            {
                                "id": e.get("id", ""),
                                "subject": e.get("subject", ""),
                                "snippet": e.get("snippet", "")[:200],  # First 200 chars
                                "from": e.get("from_email", ""),
                                "type": e.get("type", ""),
                                "attention": e.get("attention", ""),
                                "domains": e.get("domains", []),
                                "timestamp": e.get("timestamp", ""),
                            }
                            for e in request.current_data
                        ],
                    },
                    f,
                    indent=2,
                )

            log_event(
                "api.context_digest.logged",
                html_file=html_log_file,
                emails_file=emails_log_file,
            )
        except Exception as e:
            log_event("api.context_digest.log_failed", error=str(e))

        generated_at_local = result.get("generated_at_local")
        subject_time = None
        if generated_at_local:
            try:
                subject_time = datetime.fromisoformat(generated_at_local.replace("Z", "+00:00"))
                log_event(
                    "api.context_digest.subject_time_parsed",
                    generated_at_local=generated_at_local,
                    subject_time=str(subject_time),
                    timezone=str(subject_time.tzinfo),
                )
            except ValueError as e:
                log_event("api.context_digest.subject_time_parse_error", error=str(e))
                subject_time = None

        if subject_time is None:
            subject_time = datetime.now()
            log_event(
                "api.context_digest.subject_time_fallback",
                subject_time=str(subject_time),
            )

        day_part = subject_time.strftime("%A, %B %d")
        time_part = subject_time.strftime("%I:%M %p")
        subject = f"Your Inbox — {day_part} at {time_part}"
        log_event("api.context_digest.subject_created", subject=subject)
        return {
            "html": result["html"],
            "subject": subject,
            "metadata": {
                "session_id": result.get("session_id"),
                "word_count": result["word_count"],
                "entities_count": result["entities_count"],
                "featured_count": result["featured_count"],
                "critical_count": result.get("critical_count", 0),
                "time_sensitive_count": result.get("time_sensitive_count", 0),
                "routine_count": result.get("routine_count", 0),
                "verified": result["verified"],
                "fallback": result.get("fallback", False),
                "timezone": result.get("timezone"),
                "generated_at_local": result.get("generated_at_local"),
                "sections": result.get("sections", {}),
                "city": result.get("city"),
            },
        }

    except Exception as e:
        log_event("api.context_digest.failure", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to generate context digest: {e!s}"
        ) from e
