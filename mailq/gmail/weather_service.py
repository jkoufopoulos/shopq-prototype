"""

from __future__ import annotations

Weather Service - OpenWeatherMap integration

Fetches weather for destination cities (flights, events).
Caches results to minimize API calls (1-hour TTL).

Magic moment: "Your flight 345 is tomorrow at 5 PM — it'll be 95° in Houston."

Free tier: 1,000 calls/day, 60 calls/minute
Latency: ~200ms per call
"""

import os
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote_plus

import requests

from mailq.observability.logging import get_logger

logger = get_logger(__name__)

# Airport code to city mapping (top 50 US airports)
AIRPORT_TO_CITY = {
    "ATL": "Atlanta",
    "LAX": "Los Angeles",
    "ORD": "Chicago",
    "DFW": "Dallas",
    "DEN": "Denver",
    "JFK": "New York",
    "SFO": "San Francisco",
    "SEA": "Seattle",
    "LAS": "Las Vegas",
    "MCO": "Orlando",
    "EWR": "Newark",
    "CLT": "Charlotte",
    "PHX": "Phoenix",
    "IAH": "Houston",
    "MIA": "Miami",
    "BOS": "Boston",
    "MSP": "Minneapolis",
    "FLL": "Fort Lauderdale",
    "DTW": "Detroit",
    "PHL": "Philadelphia",
    "LGA": "New York",
    "BWI": "Baltimore",
    "SLC": "Salt Lake City",
    "SAN": "San Diego",
    "IAD": "Washington DC",
    "DCA": "Washington DC",
    "TPA": "Tampa",
    "PDX": "Portland",
    "STL": "St. Louis",
    "HNL": "Honolulu",
    "AUS": "Austin",
    "MDW": "Chicago",
    "BNA": "Nashville",
    "OAK": "Oakland",
    "MSY": "New Orleans",
    "RDU": "Raleigh",
    "SJC": "San Jose",
    "SAT": "San Antonio",
    "RSW": "Fort Myers",
    "SMF": "Sacramento",
    "SNA": "Santa Ana",
    "IND": "Indianapolis",
    "CLE": "Cleveland",
    "PIT": "Pittsburgh",
    "CVG": "Cincinnati",
    "CMH": "Columbus",
    "ABQ": "Albuquerque",
    "MCI": "Kansas City",
    "OMA": "Omaha",
}


class WeatherService:
    """OpenWeatherMap integration with caching"""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("OPENWEATHER_API_KEY")
        self.base_url = "http://api.openweathermap.org/data/2.5/weather"
        self._cache: dict[str, tuple] = {}  # {city_lower: (timestamp, weather_data)}

    def get_weather(
        self,
        city: str,
        airport_code: str | None = None,
        region: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Get current weather for a city.

        Args:
            city: City name (e.g., "Houston" or "Brooklyn")
            airport_code: Optional airport code for disambiguation (e.g., "IAH")
            region: Optional region/state for disambiguation (e.g., "New York")

        Returns:
            {'temp': 95, 'feels_like': 98, 'condition': 'Clear', 'description': 'clear sky'}
            or None if API fails

        Side Effects:
            - Calls external weather API (OpenWeatherMap or wttr.in)
            - Writes to in-memory cache `self._cache`
            - Logs warnings via logger.warning() on API failures
        """
        # Resolve airport code to city if provided
        if airport_code and airport_code in AIRPORT_TO_CITY:
            city = AIRPORT_TO_CITY[airport_code]

        if not city:
            return None

        # Cache key must include region to avoid ambiguity
        # e.g., "brooklyn:new york" vs "brooklyn:connecticut"
        cache_key = f"{city.lower()}:{region.lower()}" if region else city.lower()

        if cache_key in self._cache:
            cached_time, cached_data = self._cache[cache_key]
            # Cache weather for 30 minutes (weather doesn't change that fast)
            # This reduces API calls and avoids timeouts from slow fallback
            if datetime.now() - cached_time < timedelta(minutes=30):
                return cached_data

        # If no API key, use fallback provider (wttr.in)
        if not self.api_key:
            weather = self._get_weather_fallback(city, region)
            if weather:
                self._cache[cache_key] = (datetime.now(), weather)
            return weather

        try:
            # For OpenWeatherMap, include region/country for disambiguation
            # Format: "Brooklyn,NY,US" or "Brooklyn,US" for best results
            if region:
                # Try to map region to state abbreviation
                state_abbrev = {
                    "New York": "NY",
                    "California": "CA",
                    "Texas": "TX",
                    "Florida": "FL",
                    "Illinois": "IL",
                    "Pennsylvania": "PA",
                    "Ohio": "OH",
                    "Georgia": "GA",
                    "North Carolina": "NC",
                    "Michigan": "MI",
                }.get(region, region)
                query = f"{city},{state_abbrev},US"
            else:
                query = city

            response = requests.get(
                self.base_url,
                params={
                    "q": query,
                    "appid": self.api_key,
                    "units": "imperial",  # Fahrenheit
                },
                timeout=5,
            )
            response.raise_for_status()
            data = response.json()

            weather = {
                "temp": int(data["main"]["temp"]),
                "feels_like": int(data["main"]["feels_like"]),
                "condition": data["weather"][0]["main"],
                "description": data["weather"][0]["description"],
            }

            self._cache[cache_key] = (datetime.now(), weather)
            return weather

        except requests.exceptions.RequestException as e:
            logger.warning("Weather API failed for %s: %s", city, e)
            return None
        except (KeyError, ValueError) as e:
            logger.warning("Weather API response parsing failed: %s", e)
            return None

    def _get_weather_fallback(self, city: str, region: str | None = None) -> dict[str, Any] | None:
        """
        Fetch weather data from wttr.in as a fallback.

        Args:
            city: City name (e.g., "Brooklyn")
            region: Optional region/state (e.g., "New York") for disambiguation

        Side Effects:
            - Calls external weather API (wttr.in)
            - Logs warnings via logger.warning() on API failures
        """
        try:
            # For US cities, use "City,State" format for disambiguation
            # wttr.in recognizes abbreviated states (NY, CA, etc.)
            if region:
                # Convert full state names to abbreviations for common cases
                state_abbrev = {
                    "New York": "NY",
                    "California": "CA",
                    "Texas": "TX",
                    "Florida": "FL",
                    "Illinois": "IL",
                    "Pennsylvania": "PA",
                    "Ohio": "OH",
                    "Georgia": "GA",
                    "North Carolina": "NC",
                    "Michigan": "MI",
                }.get(region, region)  # Use full name if not in map

                location = f"{city},{state_abbrev}"
            else:
                location = city

            url = f"https://wttr.in/{quote_plus(location)}?format=j1"
            # wttr.in can be slow - use 10s timeout (was 5s which frequently timed out)
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            current = data["current_condition"][0]
            desc = current["weatherDesc"][0]["value"]

            return {
                "temp": int(float(current["temp_F"])),
                "feels_like": int(float(current.get("FeelsLikeF", current["temp_F"]))),
                "condition": desc,
                "description": desc,
            }
        except (requests.exceptions.RequestException, KeyError, ValueError) as exc:
            target = location if region else city
            logger.warning("Fallback weather fetch failed for %s: %s", target, exc)
            return None

    def format_weather_context(self, city: str, weather: dict[str, Any]) -> str:
        """
        Format weather into conversational text.

        Examples:
        - "it'll be 95° in Houston"
        - "it'll be a rainy 62° in Seattle"
        - "it'll be sunny and 75° in San Diego"
        - "it'll be a hot 95° in Phoenix"
        - "it'll be a chilly 42° in Boston"

        Args:
            city: City name
            weather: Weather dict from get_weather()

        Returns:
            Formatted weather context string
        """
        temp = weather["temp"]
        condition = weather["condition"].lower()

        # Add condition adjective if notable
        if condition in ["rain", "thunderstorm", "drizzle"]:
            return f"it'll be a rainy {temp}° in {city}"
        if condition == "snow":
            return f"it'll be snowing and {temp}° in {city}"
        if condition == "clear" and temp > 85:
            return f"it'll be a hot {temp}° in {city}"
        if condition == "clear" and temp < 50:
            return f"it'll be a chilly {temp}° in {city}"
        if condition == "clouds" and temp > 75:
            return f"it'll be {temp}° and cloudy in {city}"
        # Default format
        return f"it'll be {temp}° in {city}"

    def get_formatted_weather(
        self,
        city: str,
        airport_code: str | None = None,
        region: str | None = None,
    ) -> str | None:
        """
        Get weather and format in one call.

        Args:
            city: City name
            airport_code: Optional airport code
            region: Optional region for disambiguation

        Returns:
            Formatted weather string or None
        """
        weather = self.get_weather(city, airport_code, region=region)
        if not weather:
            return None

        return self.format_weather_context(city, weather)

    def clear_cache(self) -> None:
        """Clear weather cache (useful for debugging stale weather)

        Side Effects:
            - Clears in-memory cache `self._cache`
        """
        self._cache.clear()

    def get_cache_info(self) -> dict[str, Any]:
        """Get information about cached weather data"""
        return {
            "cached_locations": len(self._cache),
            "cache": {
                key: {
                    "age_minutes": int((datetime.now() - cached_time).total_seconds() / 60),
                    "temp": data["temp"],
                    "condition": data["condition"],
                }
                for key, (cached_time, data) in self._cache.items()
            },
        }


# Global singleton instance
_weather_service_instance = None


def get_weather_service() -> WeatherService:
    """Get or create weather service singleton

    Side Effects:
        - Modifies global variable `_weather_service_instance` on first call
    """
    global _weather_service_instance
    if _weather_service_instance is None:
        _weather_service_instance = WeatherService()
    return _weather_service_instance
