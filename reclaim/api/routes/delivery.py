"""
Delivery API endpoints for Uber Direct return pickups.

Provides endpoints for:
- Getting delivery quotes
- Confirming and dispatching deliveries
- Checking delivery status
- Canceling deliveries
- Listing carrier locations
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from reclaim.api.middleware.user_auth import AuthenticatedUser, get_current_user
from reclaim.delivery.carrier_locations import get_all_locations, get_nearby_locations
from reclaim.delivery.models import (
    Address,
    CarrierLocation,
    ConfirmRequest,
    DeliveryResponse,
    QuoteRequest,
    QuoteResponse,
)
from reclaim.delivery.service import (
    DeliveryNotFoundError,
    DeliveryService,
    InvalidStateError,
    LocationNotFoundError,
    QuoteExpiredError,
    get_delivery_service,
)
from reclaim.observability.logging import get_logger
from reclaim.utils.error_sanitizer import sanitize_error_message

router = APIRouter(prefix="/api/delivery", tags=["delivery"])
logger = get_logger(__name__)


# ============================================================================
# Request/Response Models
# ============================================================================


class QuoteAPIRequest(BaseModel):
    """API request to get a delivery quote."""

    order_key: str
    pickup_address: Address
    dropoff_location_id: str


class ConfirmAPIRequest(BaseModel):
    """API request to confirm a delivery."""

    delivery_id: str


class CarrierLocationResponse(BaseModel):
    """API response for a carrier location."""

    id: str
    name: str
    carrier: str
    address: Address
    hours: str
    distance_miles: float | None = None


class LocationListResponse(BaseModel):
    """API response for list of carrier locations."""

    locations: list[CarrierLocationResponse]


# ============================================================================
# Carrier Location Endpoints
# ============================================================================


@router.get("/locations", response_model=LocationListResponse)
async def list_locations(
    lat: float | None = Query(None, description="User latitude for distance sorting"),
    lng: float | None = Query(None, description="User longitude for distance sorting"),
    carrier: str | None = Query(None, description="Filter by carrier (UPS, FedEx)"),
    limit: int = Query(10, ge=1, le=50, description="Maximum locations to return"),
) -> LocationListResponse:
    """
    List carrier locations (UPS/FedEx drop-off points).

    If lat/lng provided, returns locations sorted by distance.
    Otherwise returns all locations.
    """
    if lat is not None and lng is not None:
        locations = get_nearby_locations(lat, lng, limit=limit, carrier=carrier)
    else:
        locations = get_all_locations()
        if carrier:
            locations = [loc for loc in locations if loc.carrier == carrier]
        locations = locations[:limit]

    return LocationListResponse(
        locations=[
            CarrierLocationResponse(
                id=loc.id,
                name=loc.name,
                carrier=loc.carrier,
                address=loc.address,
                hours=loc.hours,
                distance_miles=loc.distance_miles,
            )
            for loc in locations
        ]
    )


# ============================================================================
# Quote Endpoints
# ============================================================================


@router.post("/quote", response_model=QuoteResponse)
async def create_quote(
    request: QuoteAPIRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> QuoteResponse:
    """
    Get a delivery quote for a return pickup.

    Creates a delivery record and requests a quote from Uber Direct.
    The quote is valid for ~5 minutes and must be confirmed to dispatch a driver.
    """
    try:
        service = get_delivery_service()
        quote_request = QuoteRequest(
            order_key=request.order_key,
            pickup_address=request.pickup_address,
            dropoff_location_id=request.dropoff_location_id,
        )

        response = await service.get_quote(user.id, quote_request)

        logger.info(
            "Created quote for user %s: delivery %s, fee %s",
            user.id,
            response.delivery_id,
            response.fee_display,
        )

        return response

    except LocationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.error("Failed to create quote: %s", e)
        raise HTTPException(
            status_code=500,
            detail=sanitize_error_message(str(e), 500),
        ) from None


# ============================================================================
# Delivery Endpoints
# ============================================================================


@router.post("/confirm", response_model=DeliveryResponse)
async def confirm_delivery(
    request: ConfirmAPIRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> DeliveryResponse:
    """
    Confirm a quote and dispatch a driver.

    The user has accepted the quote and wants to proceed with the delivery.
    This will charge the user and dispatch an Uber driver.
    """
    try:
        service = get_delivery_service()
        confirm_request = ConfirmRequest(delivery_id=request.delivery_id)

        response = await service.confirm_delivery(user.id, confirm_request)

        logger.info(
            "Confirmed delivery %s for user %s",
            request.delivery_id,
            user.id,
        )

        return response

    except DeliveryNotFoundError:
        raise HTTPException(status_code=404, detail="Delivery not found") from None
    except InvalidStateError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except QuoteExpiredError:
        raise HTTPException(
            status_code=400,
            detail="Quote has expired. Please request a new quote.",
        ) from None
    except Exception as e:
        logger.error("Failed to confirm delivery: %s", e)
        raise HTTPException(
            status_code=500,
            detail=sanitize_error_message(str(e), 500),
        ) from None


@router.get("/{delivery_id}", response_model=DeliveryResponse)
async def get_delivery(
    delivery_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> DeliveryResponse:
    """
    Get the current status of a delivery.

    Returns the latest status from Uber Direct, including driver info
    and ETAs when available.
    """
    try:
        service = get_delivery_service()
        response = await service.get_delivery(user.id, delivery_id)
        return response

    except DeliveryNotFoundError:
        raise HTTPException(status_code=404, detail="Delivery not found") from None
    except Exception as e:
        logger.error("Failed to get delivery: %s", e)
        raise HTTPException(
            status_code=500,
            detail=sanitize_error_message(str(e), 500),
        ) from None


@router.get("/order/{order_key}", response_model=DeliveryResponse | None)
async def get_delivery_for_order(
    order_key: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> DeliveryResponse | None:
    """
    Get the most recent delivery for a return card.

    Returns None if no delivery exists for this order.
    """
    try:
        service = get_delivery_service()
        return await service.get_delivery_for_order(user.id, order_key)

    except Exception as e:
        logger.error("Failed to get delivery for order: %s", e)
        raise HTTPException(
            status_code=500,
            detail=sanitize_error_message(str(e), 500),
        ) from None


@router.post("/{delivery_id}/cancel")
async def cancel_delivery(
    delivery_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    """
    Cancel a pending delivery.

    Only deliveries that haven't been picked up can be canceled.
    """
    try:
        service = get_delivery_service()
        canceled = await service.cancel_delivery(user.id, delivery_id)

        if canceled:
            logger.info("Canceled delivery %s for user %s", delivery_id, user.id)
            return {"success": True, "message": "Delivery canceled"}
        else:
            return {"success": False, "message": "Failed to cancel delivery"}

    except DeliveryNotFoundError:
        raise HTTPException(status_code=404, detail="Delivery not found") from None
    except InvalidStateError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        logger.error("Failed to cancel delivery: %s", e)
        raise HTTPException(
            status_code=500,
            detail=sanitize_error_message(str(e), 500),
        ) from None


@router.get("/active", response_model=list[DeliveryResponse])
async def list_active_deliveries(
    user: AuthenticatedUser = Depends(get_current_user),
) -> list[DeliveryResponse]:
    """
    List all active deliveries for the user.

    Active deliveries are those that are quoted, pending, in pickup, or in dropoff.
    """
    try:
        service = get_delivery_service()
        return await service.list_active_deliveries(user.id)

    except Exception as e:
        logger.error("Failed to list active deliveries: %s", e)
        raise HTTPException(
            status_code=500,
            detail=sanitize_error_message(str(e), 500),
        ) from None


# ============================================================================
# Webhook Endpoint
# ============================================================================


class UberWebhookPayload(BaseModel):
    """Payload from Uber Direct webhook."""

    event_type: str
    delivery_id: str
    status: str | None = None
    driver_name: str | None = None
    driver_phone: str | None = None
    tracking_url: str | None = None
    pickup_eta: str | None = None
    dropoff_eta: str | None = None


@router.post("/webhook/uber", status_code=202)
async def uber_webhook(request: Request) -> dict:
    """
    Receive delivery status updates from Uber Direct.

    Validates HMAC signature and updates delivery status in DB.
    This endpoint is exempt from CSRF and auth checks.
    """
    import hmac
    import os

    from reclaim.delivery.models import DeliveryStatus
    from reclaim.delivery.repository import DeliveryRepository

    body = await request.body()

    # Verify signature in production (skip in mock mode)
    if os.getenv("UBER_DIRECT_MOCK", "true").lower() != "true":
        signature = request.headers.get("X-Uber-Signature", "")
        secret = os.getenv("UBER_DIRECT_WEBHOOK_SECRET", "")

        if secret:
            expected = hmac.new(
                secret.encode(),
                body,
                "sha256",
            ).hexdigest()

            if not hmac.compare_digest(signature, expected):
                logger.warning("Invalid Uber webhook signature")
                raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        import json

        payload_dict = json.loads(body)
        payload = UberWebhookPayload(**payload_dict)

        logger.info(
            "Received Uber webhook: event=%s, delivery=%s, status=%s",
            payload.event_type,
            payload.delivery_id,
            payload.status,
        )

        # Find our delivery by Uber's ID
        delivery = DeliveryRepository.get_by_uber_id(payload.delivery_id)
        if not delivery:
            logger.warning("Webhook for unknown delivery: %s", payload.delivery_id)
            return {"status": "ignored", "reason": "unknown_delivery"}

        # Update status if provided
        if payload.status:
            try:
                new_status = DeliveryStatus(payload.status)
                DeliveryRepository.update_status(
                    delivery_id=delivery.id,
                    new_status=new_status,
                    driver_name=payload.driver_name,
                    driver_phone=payload.driver_phone,
                    tracking_url=payload.tracking_url,
                    pickup_eta=payload.pickup_eta,
                    dropoff_eta=payload.dropoff_eta,
                )
                logger.info(
                    "Updated delivery %s status to %s via webhook",
                    delivery.id,
                    new_status.value,
                )
            except ValueError:
                logger.warning("Unknown status from webhook: %s", payload.status)

        return {"status": "accepted"}

    except Exception as e:
        logger.error("Failed to process Uber webhook: %s", e)
        # Return 202 anyway to prevent retries for parsing errors
        return {"status": "error", "reason": str(e)}
