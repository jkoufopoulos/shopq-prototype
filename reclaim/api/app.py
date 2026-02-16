"""FastAPI server for Reclaim Return Watch"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from reclaim.api.middleware.csrf import CSRFMiddleware
from reclaim.api.middleware.rate_limit import RateLimitMiddleware
from reclaim.api.middleware.security_headers import SecurityHeadersMiddleware
from reclaim.api.routes.extract import router as extract_router
from reclaim.api.routes.health import router as health_router
from reclaim.config import APP_VERSION, CHROME_EXTENSION_ORIGIN
from reclaim.observability.logging import get_logger
from reclaim.observability.telemetry import log_event

# Load environment variables from .env file
load_dotenv()

app = FastAPI(title="Reclaim Return Watch API", version=APP_VERSION)

# Initialize logger
logger = get_logger(__name__)


# Custom validation error handler to prevent information leakage
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Custom validation error handler that prevents leaking internal validation logic.
    """
    from reclaim.observability.telemetry import counter
    from reclaim.utils.redaction import redact

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
            "invalid_fields": [str(err["loc"][-1]) for err in exc.errors()],
        },
    )


# CORS - Restrict to specific origins for security
ALLOWED_ORIGINS = [
    "https://mail.google.com",
    "https://reclaim-api-488078904670.us-central1.run.app",
    CHROME_EXTENSION_ORIGIN,
]

# Allow localhost and unpacked extensions in development only
if os.getenv("RECLAIM_ENV", os.getenv("SHOPQ_ENV", "development")) == "development":
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
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)

# SEC-006: CSRF protection - validate Origin header on state-changing requests
app.add_middleware(CSRFMiddleware, allowed_origins=ALLOWED_ORIGINS)

# Rate limiting - prevent abuse
app.add_middleware(
    RateLimitMiddleware,
    requests_per_minute=60,
    requests_per_hour=1000,
)

# Security headers
app.add_middleware(SecurityHeadersMiddleware)

# Include routers (stateless — no database initialization needed)
app.include_router(health_router)
app.include_router(extract_router)

log_event("api.startup", service="reclaim-return-watch", version=APP_VERSION)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "Reclaim API",
        "status": "running",
    }
