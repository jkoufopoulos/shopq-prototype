"""

from __future__ import annotations

Feature Gates API - View and toggle feature flags

Endpoints:
- GET /api/features - List all features and their states
- GET /api/features/{feature_name} - Get specific feature state
- POST /api/features/{feature_name}/enable - Enable a feature
- POST /api/features/{feature_name}/disable - Disable a feature
- POST /api/features/{feature_name}/reset - Reset to default
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from mailq.runtime.gates import feature_gates

router = APIRouter(prefix="/api/features", tags=["Feature Gates"])


class FeatureStateResponse(BaseModel):
    """Response model for feature state"""

    name: str
    enabled: bool
    default: bool
    has_override: bool
    env_var: str


class FeatureToggleResponse(BaseModel):
    """Response model for feature toggle operations"""

    success: bool
    feature: str
    enabled: bool
    message: str


@router.get("", response_model=dict[str, FeatureStateResponse])
async def list_features() -> dict[str, FeatureStateResponse]:
    """
    List all feature gates and their current states.

    Returns:
        Dict mapping feature names to their states
    """
    config = feature_gates.get_config()

    return {
        name: FeatureStateResponse(
            name=name,
            enabled=state["enabled"],
            default=state["default"],
            has_override=state["has_override"],
            env_var=state["env_var"],
        )
        for name, state in config.items()
    }


@router.get("/{feature_name}", response_model=FeatureStateResponse)
async def get_feature(feature_name: str) -> FeatureStateResponse:
    """
    Get state of a specific feature.

    Args:
        feature_name: Feature gate name (e.g., 'digest_urgency_grouping')

    Returns:
        Feature state details
    """
    config = feature_gates.get_config()

    if feature_name not in config:
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{feature_name}' not found. Available features: {list(config.keys())}",
        )

    state = config[feature_name]
    return FeatureStateResponse(
        name=feature_name,
        enabled=state["enabled"],
        default=state["default"],
        has_override=state["has_override"],
        env_var=state["env_var"],
    )


@router.post("/{feature_name}/enable", response_model=FeatureToggleResponse)
async def enable_feature(feature_name: str) -> FeatureToggleResponse:
    """
    Enable a feature at runtime (session-only, not persisted).

    Args:
        feature_name: Feature gate name

    Returns:
        Success response
    """
    config = feature_gates.get_config()

    if feature_name not in config:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_name}' not found")

    feature_gates.enable(feature_name)

    return FeatureToggleResponse(
        success=True,
        feature=feature_name,
        enabled=True,
        message=f"Feature '{feature_name}' enabled (session-only)",
    )


@router.post("/{feature_name}/disable", response_model=FeatureToggleResponse)
async def disable_feature(feature_name: str) -> FeatureToggleResponse:
    """
    Disable a feature at runtime (session-only, not persisted).

    Args:
        feature_name: Feature gate name

    Returns:
        Success response
    """
    config = feature_gates.get_config()

    if feature_name not in config:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_name}' not found")

    feature_gates.disable(feature_name)

    return FeatureToggleResponse(
        success=True,
        feature=feature_name,
        enabled=False,
        message=f"Feature '{feature_name}' disabled (session-only)",
    )


@router.post("/{feature_name}/reset", response_model=FeatureToggleResponse)
async def reset_feature(feature_name: str) -> FeatureToggleResponse:
    """
    Reset feature to default state (remove runtime override).

    Args:
        feature_name: Feature gate name

    Returns:
        Success response
        Side Effects:
            None (pure function)
    """
    config = feature_gates.get_config()

    if feature_name not in config:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_name}' not found")

    feature_gates.reset(feature_name)

    # Get new state after reset
    new_state = feature_gates.is_enabled(feature_name)

    return FeatureToggleResponse(
        success=True,
        feature=feature_name,
        enabled=new_state,
        message=f"Feature '{feature_name}' reset to default ({new_state})",
    )
