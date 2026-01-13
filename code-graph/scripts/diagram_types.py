#!/usr/bin/env python3
"""
Type definitions for code-graph diagram generation system.

Provides TypedDict schemas for structured data to enable type checking
and prevent runtime errors from invalid data shapes.
"""

from typing import TypedDict


# ============================================================================
# Diagram Structure Types (for generate_diagram_html.py)
# ============================================================================


class CategoryInfo(TypedDict):
    """Information about a diagram category (subgraph)."""
    name: str
    emoji: str
    nodes: list[str]


class DiagramStructure(TypedDict):
    """Parsed structure of a Mermaid diagram."""
    categories: dict[str, CategoryInfo]  # category_id -> CategoryInfo
    nodes: dict[str, str]  # node_id -> category_id


class ExecutionStep(TypedDict):
    """A single execution step in a sequence diagram."""
    number: int
    title: str  # e.g., "Extension → Backend"
    description: str  # Plain language description


class DiagramSpec(TypedDict):
    """Specification for a single diagram to generate."""
    file: str  # HTML filename (e.g., "system_storyboard.html")
    markdown: str  # Markdown filename (e.g., "SYSTEM_STORYBOARD.md")
    title: str  # Display title
    description: str  # Short description
    category: str  # Category for grouping (e.g., "story", "task-flow")


# ============================================================================
# Git and Component Analysis Types (for generate_evidence_html.py)
# ============================================================================


class GitCommit(TypedDict):
    """A single git commit."""
    hash: str  # Short commit hash (e.g., "a1b2c3d")
    when: str  # Relative time (e.g., "2 days ago")
    message: str  # Commit message


class TodoItem(TypedDict):
    """A TODO/FIXME comment found in code."""
    line: int  # Line number
    text: str  # Full line text with TODO/FIXME


class ComponentDetails(TypedDict):
    """Detailed information about a component file."""
    path: str  # Relative path to file
    commits: list[GitCommit]  # Recent commits (last 5)
    todos: list[TodoItem]  # TODO/FIXME comments
    imports: list[str]  # External dependencies


class ActivityRow(TypedDict):
    """A row in the activity heatmap table."""
    layer: str  # Layer emoji (e.g., "🌐 API", "⚙️ Core")
    component: str  # Component name (e.g., "api.py")
    commits: str  # Commit count (string for display)
    todos: str  # TODO count (string for display)
    activity: str  # Activity indicator (fire emojis)


class QualityMetrics(TypedDict):
    """Quality metrics for the codebase."""
    test_failures: list[dict[str, str]]  # List of test failures
    recent_errors: list[dict[str, str | int]]  # Recent errors with counts
    components_with_issues: list[str]  # Component names with issues


# ============================================================================
# Configuration Types
# ============================================================================


class DatabaseConfig(TypedDict):
    """Database configuration detected from codebase."""
    path: str  # Database file path
    tables: list[str]  # Table names
    pool_size: int  # Connection pool size


class ExternalService(TypedDict):
    """External service configuration."""
    name: str  # Service name (e.g., "Vertex AI")
    description: str  # Short description
    files: list[str]  # Files using this service
    model: str  # Optional: model name for LLM services


class ExtensionConfig(TypedDict):
    """Chrome extension configuration."""
    cache_expiry_hours: int
    daily_budget_cap: float
    tier_costs: dict[str, float]
    verifier_range: tuple[float, float]


# ============================================================================
# Validation Error Types
# ============================================================================


class ValidationError(TypedDict):
    """A validation error found during processing."""
    file: str
    line: int
    message: str
    severity: str  # "error" or "warning"
