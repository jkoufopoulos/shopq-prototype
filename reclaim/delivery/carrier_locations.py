"""
Carrier location data for return package drop-off.

MVP: Hardcoded list of UPS/FedEx locations.
Future: Integrate with UPS/FedEx store locator APIs for dynamic lookup.
"""

from __future__ import annotations

import math

from reclaim.delivery.models import Address, CarrierLocation


# Hardcoded carrier locations for MVP
# Covers major SF Bay Area locations
CARRIER_LOCATIONS: list[dict] = [
    # San Francisco
    {
        "id": "ups_sf_market",
        "name": "The UPS Store",
        "carrier": "UPS",
        "address": {
            "street": "123 Market St",
            "city": "San Francisco",
            "state": "CA",
            "zip_code": "94102",
            "lat": 37.7879,
            "lng": -122.4074,
        },
        "hours": "Mon-Fri 8am-7pm, Sat 9am-5pm",
    },
    {
        "id": "fedex_sf_mission",
        "name": "FedEx Office",
        "carrier": "FedEx",
        "address": {
            "street": "456 Mission St",
            "city": "San Francisco",
            "state": "CA",
            "zip_code": "94105",
            "lat": 37.7897,
            "lng": -122.3942,
        },
        "hours": "Mon-Fri 7am-9pm, Sat-Sun 9am-6pm",
    },
    {
        "id": "ups_sf_castro",
        "name": "The UPS Store",
        "carrier": "UPS",
        "address": {
            "street": "2269 Market St",
            "city": "San Francisco",
            "state": "CA",
            "zip_code": "94114",
            "lat": 37.7643,
            "lng": -122.4324,
        },
        "hours": "Mon-Fri 8:30am-6:30pm, Sat 10am-4pm",
    },
    {
        "id": "fedex_sf_soma",
        "name": "FedEx Office",
        "carrier": "FedEx",
        "address": {
            "street": "303 2nd St",
            "city": "San Francisco",
            "state": "CA",
            "zip_code": "94107",
            "lat": 37.7855,
            "lng": -122.3963,
        },
        "hours": "Mon-Fri 7am-10pm, Sat-Sun 9am-6pm",
    },
    # Oakland
    {
        "id": "ups_oakland_broadway",
        "name": "The UPS Store",
        "carrier": "UPS",
        "address": {
            "street": "1960 Broadway",
            "city": "Oakland",
            "state": "CA",
            "zip_code": "94612",
            "lat": 37.8087,
            "lng": -122.2689,
        },
        "hours": "Mon-Fri 8am-7pm, Sat 9am-5pm",
    },
    {
        "id": "fedex_oakland_piedmont",
        "name": "FedEx Office",
        "carrier": "FedEx",
        "address": {
            "street": "4150 Piedmont Ave",
            "city": "Oakland",
            "state": "CA",
            "zip_code": "94611",
            "lat": 37.8257,
            "lng": -122.2523,
        },
        "hours": "Mon-Fri 8am-8pm, Sat 9am-6pm, Sun 11am-5pm",
    },
    # Palo Alto
    {
        "id": "ups_palo_alto",
        "name": "The UPS Store",
        "carrier": "UPS",
        "address": {
            "street": "2225 El Camino Real",
            "city": "Palo Alto",
            "state": "CA",
            "zip_code": "94306",
            "lat": 37.4238,
            "lng": -122.1330,
        },
        "hours": "Mon-Fri 8am-7pm, Sat 9am-5pm",
    },
    {
        "id": "fedex_palo_alto",
        "name": "FedEx Office",
        "carrier": "FedEx",
        "address": {
            "street": "340 University Ave",
            "city": "Palo Alto",
            "state": "CA",
            "zip_code": "94301",
            "lat": 37.4457,
            "lng": -122.1600,
        },
        "hours": "Mon-Fri 7am-9pm, Sat-Sun 9am-6pm",
    },
    # San Jose
    {
        "id": "ups_san_jose_santana",
        "name": "The UPS Store",
        "carrier": "UPS",
        "address": {
            "street": "3055 Olin Ave",
            "city": "San Jose",
            "state": "CA",
            "zip_code": "95128",
            "lat": 37.3201,
            "lng": -121.9470,
        },
        "hours": "Mon-Fri 8am-7pm, Sat 9am-5pm",
    },
    {
        "id": "fedex_san_jose",
        "name": "FedEx Office",
        "carrier": "FedEx",
        "address": {
            "street": "150 S 1st St",
            "city": "San Jose",
            "state": "CA",
            "zip_code": "95113",
            "lat": 37.3328,
            "lng": -121.8891,
        },
        "hours": "Mon-Fri 7am-9pm, Sat-Sun 10am-5pm",
    },
    # Berkeley
    {
        "id": "ups_berkeley",
        "name": "The UPS Store",
        "carrier": "UPS",
        "address": {
            "street": "2107 Shattuck Ave",
            "city": "Berkeley",
            "state": "CA",
            "zip_code": "94704",
            "lat": 37.8717,
            "lng": -122.2687,
        },
        "hours": "Mon-Fri 9am-7pm, Sat 10am-5pm",
    },
    {
        "id": "fedex_berkeley",
        "name": "FedEx Office",
        "carrier": "FedEx",
        "address": {
            "street": "2501 Telegraph Ave",
            "city": "Berkeley",
            "state": "CA",
            "zip_code": "94704",
            "lat": 37.8658,
            "lng": -122.2588,
        },
        "hours": "Mon-Fri 7am-10pm, Sat-Sun 9am-6pm",
    },
]


def _haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate haversine distance between two points in miles.

    Args:
        lat1, lng1: First point coordinates
        lat2, lng2: Second point coordinates

    Returns:
        Distance in miles
    """
    R = 3959  # Earth's radius in miles

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def get_all_locations() -> list[CarrierLocation]:
    """
    Get all carrier locations.

    Returns:
        List of CarrierLocation objects
    """
    return [
        CarrierLocation(
            id=loc["id"],
            name=loc["name"],
            carrier=loc["carrier"],
            address=Address(**loc["address"]),
            hours=loc["hours"],
        )
        for loc in CARRIER_LOCATIONS
    ]


def get_location_by_id(location_id: str) -> CarrierLocation | None:
    """
    Get a specific carrier location by ID.

    Args:
        location_id: Location identifier (e.g., "ups_sf_market")

    Returns:
        CarrierLocation if found, None otherwise
    """
    for loc in CARRIER_LOCATIONS:
        if loc["id"] == location_id:
            return CarrierLocation(
                id=loc["id"],
                name=loc["name"],
                carrier=loc["carrier"],
                address=Address(**loc["address"]),
                hours=loc["hours"],
            )
    return None


def get_nearby_locations(
    user_lat: float,
    user_lng: float,
    limit: int = 5,
    carrier: str | None = None,
) -> list[CarrierLocation]:
    """
    Get carrier locations sorted by distance from user.

    Args:
        user_lat: User's latitude
        user_lng: User's longitude
        limit: Maximum number of locations to return
        carrier: Optional filter by carrier ("UPS" or "FedEx")

    Returns:
        List of CarrierLocation objects with distance_miles populated,
        sorted by distance (nearest first)
    """
    locations_with_distance: list[tuple[float, dict]] = []

    for loc in CARRIER_LOCATIONS:
        # Filter by carrier if specified
        if carrier and loc["carrier"] != carrier:
            continue

        loc_lat = loc["address"]["lat"]
        loc_lng = loc["address"]["lng"]
        distance = _haversine_distance(user_lat, user_lng, loc_lat, loc_lng)
        locations_with_distance.append((distance, loc))

    # Sort by distance
    locations_with_distance.sort(key=lambda x: x[0])

    # Take top N and convert to CarrierLocation
    result = []
    for distance, loc in locations_with_distance[:limit]:
        carrier_loc = CarrierLocation(
            id=loc["id"],
            name=loc["name"],
            carrier=loc["carrier"],
            address=Address(**loc["address"]),
            hours=loc["hours"],
            distance_miles=round(distance, 1),
        )
        result.append(carrier_loc)

    return result


def get_locations_by_city(city: str) -> list[CarrierLocation]:
    """
    Get all carrier locations in a specific city.

    Args:
        city: City name (case-insensitive)

    Returns:
        List of CarrierLocation objects in that city
    """
    city_lower = city.lower()
    return [
        CarrierLocation(
            id=loc["id"],
            name=loc["name"],
            carrier=loc["carrier"],
            address=Address(**loc["address"]),
            hours=loc["hours"],
        )
        for loc in CARRIER_LOCATIONS
        if loc["address"]["city"].lower() == city_lower
    ]
