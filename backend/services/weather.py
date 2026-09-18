"""Open-Meteo geocoding and weather service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

REQUEST_TIMEOUT_SECONDS = 10


class WeatherServiceError(Exception):
    """Raised when location or weather data cannot be retrieved."""


@dataclass
class Location:
    """Resolved geographic location."""

    name: str
    latitude: float
    longitude: float
    timezone: str


class OpenMeteoWeatherService:
    """Fetch location and weather data from Open-Meteo."""

    def resolve_location(self, city: str) -> Location:
        """
        Resolve a city name using Open-Meteo's free geocoding API.
        """

        try:
            response = requests.get(
                GEOCODING_URL,
                params={
                    "name": city,
                    "count": 1,
                    "language": "en",
                    "format": "json",
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )

            response.raise_for_status()

        except requests.RequestException as exc:
            raise WeatherServiceError(
                f"Unable to resolve location '{city}'."
            ) from exc

        data = response.json()
        results = data.get("results", [])

        if not results:
            raise WeatherServiceError(
                f"Location '{city}' could not be found."
            )

        result = results[0]

        return Location(
            name=result["name"],
            latitude=float(result["latitude"]),
            longitude=float(result["longitude"]),
            timezone=result.get("timezone", "auto"),
        )

    def get_weather(
        self,
        location: Location,
        *,
        target_hour: str | None = None,
    ) -> dict[str, Any]:
        """
        Fetch current or hourly weather from Open-Meteo.

        target_hour:
            None -> current weather
            ISO local datetime -> matching hourly forecast
        """

        params = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "current": (
                "temperature_2m,"
                "precipitation,"
                "wind_speed_10m,"
                "weather_code"
            ),
            "hourly": (
                "temperature_2m,"
                "precipitation_probability,"
                "precipitation,"
                "wind_speed_10m,"
                "uv_index,"
                "weather_code"
            ),
            "timezone": location.timezone,
            "forecast_days": 7,
        }

        try:
            response = requests.get(
                FORECAST_URL,
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )

            response.raise_for_status()

        except requests.RequestException as exc:
            raise WeatherServiceError(
                "Unable to retrieve live weather data."
            ) from exc

        data = response.json()

        if target_hour is None:
            return self._normalize_current_weather(data)

        return self._normalize_hourly_weather(
            data,
            target_hour,
        )

    @staticmethod
    def _normalize_current_weather(
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Convert Open-Meteo current data to our internal format."""

        current = data.get("current")

        if not current:
            raise WeatherServiceError(
                "Weather API returned no current weather data."
            )

        return {
            "temperature_c": current.get("temperature_2m"),
            "precipitation_mm": current.get("precipitation"),
            "wind_speed_kmh": current.get("wind_speed_10m"),
            "weather_code": current.get("weather_code"),
            "observed_at": current.get("time"),
        }

    @staticmethod
    def _normalize_hourly_weather(
        data: dict[str, Any],
        target_hour: str,
    ) -> dict[str, Any]:
        """Find and normalize a specific hourly forecast."""

        hourly = data.get("hourly")

        if not hourly:
            raise WeatherServiceError(
                "Weather API returned no hourly weather data."
            )

        times = hourly.get("time", [])

        try:
            index = times.index(target_hour)
        except ValueError as exc:
            raise WeatherServiceError(
                f"No weather forecast available for {target_hour}."
            ) from exc

        return {
            "temperature_c": hourly["temperature_2m"][index],
            "precipitation_mm": hourly["precipitation"][index],
            "precipitation_probability": hourly[
                "precipitation_probability"
            ][index],
            "wind_speed_kmh": hourly["wind_speed_10m"][index],
            "uv_index": hourly["uv_index"][index],
            "weather_code": hourly["weather_code"][index],
            "observed_at": times[index],
        }