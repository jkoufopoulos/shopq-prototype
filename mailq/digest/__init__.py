"""
Digest generation subsystem.

This package handles all aspects of digest (daily email summary) generation:
- Pipeline: V2 pipeline with explicit stage dependencies (7 stages)
- Categorization: Sorting emails into digest sections (today, coming_up, worth_knowing, noise)
- Rendering: Converting email data to HTML (deterministic, template-based)
- Temporal: Time-based adjustments (T0 intrinsic → T1 time-adjusted)
- Delivery: Sending digest emails to users

Architecture (Nov 2025):
    V2 is now the only pipeline (V1 deleted Nov 2025).

    mailq/digest/
    ├── context_digest.py      - Main entry point (orchestrator)
    ├── digest_pipeline.py     - Pipeline contracts and orchestration
    ├── digest_stages_v2.py    - 7-stage pipeline implementation
    ├── section_assignment_t0.py - T0 intrinsic section classification
    ├── temporal.py            - Temporal decay and T1 adjustments
    ├── card_renderer.py       - HTML card generation (fallback path)
    ├── support.py             - DTOs, adapters, utilities
    ├── delivery.py            - Email delivery
    └── templates/             - HTML templates

Usage:
    from mailq.digest import DigestDTOv3
    from mailq.digest.context_digest import generate_context_digest

    # Direct pipeline access
    from mailq.digest.digest_pipeline import DigestPipeline
"""

# Public API exports (will be populated as we refactor context_digest.py)
from mailq.digest.support import DigestDTOv3  # noqa: F401

__all__ = [
    "DigestDTOv3",
    # Additional exports will be added as context_digest.py is refactored
]

# Package metadata
__version__ = "3.0.0"  # Digest v3 (context-aware, entity-grouped)
