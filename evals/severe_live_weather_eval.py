from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

import requests

from backend.graph.graph import build_graph
from backend.services import weather as weather_module


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

REQUEST_TIMEOUT_SECONDS = 15

# We use Pune for the live evaluation.
CITY = "Pune"

# The severe SOP currently means:
#
# outdoor activity AND (
#     (precipitation_probability >= 80 AND precipitation_mm > 5)
#     OR wind_speed_kmh > 50
# )
#
# These thresholds intentionally mirror the configured SOP.
PRECIP_PROBABILITY_THRESHOLD = 80.0
PRECIPITATION_THRESHOLD = 5.0
WIND_THRESHOLD = 50.0


@dataclass
class LiveWeatherCase:
    city: str
    target_hour: str
    weather: dict


def normalize_text(value: str) -> str:
    return (
        value.lower()
        .replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
        .replace("\u00a0", " ")
    )


def resolve_location(city: str) -> dict:
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

    data = response.json()
    results = data.get("results", [])

    if not results:
        raise RuntimeError(f"Could not resolve location: {city}")

    result = results[0]

    return {
        "name": result["name"],
        "latitude": float(result["latitude"]),
        "longitude": float(result["longitude"]),
        "timezone": result.get("timezone", "auto"),
    }


def fetch_live_forecast(location: dict) -> dict:
    response = requests.get(
        FORECAST_URL,
        params={
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "hourly": (
                "temperature_2m,"
                "precipitation_probability,"
                "precipitation,"
                "wind_speed_10m,"
                "uv_index,"
                "weather_code"
            ),
            "timezone": location["timezone"],
            "forecast_days": 7,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    return response.json()


def find_severe_hour(forecast: dict) -> LiveWeatherCase | None:
    hourly = forecast.get("hourly")

    if not hourly:
        raise RuntimeError("Open-Meteo returned no hourly forecast.")

    times = hourly.get("time", [])
    temperatures = hourly.get("temperature_2m", [])
    precipitation_probabilities = hourly.get(
        "precipitation_probability", []
    )
    precipitations = hourly.get("precipitation", [])
    wind_speeds = hourly.get("wind_speed_10m", [])
    uv_indices = hourly.get("uv_index", [])
    weather_codes = hourly.get("weather_code", [])

    lengths = [
        len(times),
        len(temperatures),
        len(precipitation_probabilities),
        len(precipitations),
        len(wind_speeds),
        len(uv_indices),
        len(weather_codes),
    ]

    if len(set(lengths)) != 1:
        raise RuntimeError(
            "Open-Meteo returned hourly arrays with inconsistent lengths."
        )

    candidates = []

    for index, target_hour in enumerate(times):
        temperature = temperatures[index]
        precipitation_probability = (
            precipitation_probabilities[index]
        )
        precipitation = precipitations[index]
        wind_speed = wind_speeds[index]

        severe_from_rain = (
            precipitation_probability >= PRECIP_PROBABILITY_THRESHOLD
            and precipitation > PRECIPITATION_THRESHOLD
        )

        severe_from_wind = wind_speed > WIND_THRESHOLD

        if severe_from_rain or severe_from_wind:
            candidates.append(
                (
                    index,
                    target_hour,
                    temperature,
                    precipitation_probability,
                    precipitation,
                    wind_speed,
                    uv_indices[index],
                    weather_codes[index],
                    severe_from_rain,
                    severe_from_wind,
                )
            )

    if not candidates:
        return None

    # Prefer the strongest actual condition so that the evaluation
    # is clearly grounded in a genuinely severe forecast hour.
    candidates.sort(
        key=lambda item: (
            item[5],  # wind speed
            item[4],  # precipitation
            item[3],  # precipitation probability
        ),
        reverse=True,
    )

    (
        index,
        target_hour,
        temperature,
        precipitation_probability,
        precipitation,
        wind_speed,
        uv_index,
        weather_code,
        severe_from_rain,
        severe_from_wind,
    ) = candidates[0]

    weather = {
        "temperature_c": temperature,
        "precipitation_mm": precipitation,
        "precipitation_probability": precipitation_probability,
        "wind_speed_kmh": wind_speed,
        "uv_index": uv_index,
        "weather_code": weather_code,
        "observed_at": target_hour,
    }

    return LiveWeatherCase(
        city=CITY,
        target_hour=target_hour,
        weather=weather,
    )


def install_live_weather(location: dict, weather: dict) -> None:
    """
    Keep the graph's weather interface unchanged while ensuring the
    exact live Open-Meteo values selected by this evaluation are passed
    into the graph.

    No weather values are fabricated.
    """

    def live_resolve_location(self, city: str):
        return weather_module.Location(
            name=location["name"],
            latitude=location["latitude"],
            longitude=location["longitude"],
            timezone=location["timezone"],
        )

    def live_get_weather(self, resolved_location, *, target_hour=None):
        return dict(weather)

    weather_module.OpenMeteoWeatherService.resolve_location = (
        live_resolve_location
    )

    weather_module.OpenMeteoWeatherService.get_weather = (
        live_get_weather
    )


def contains_numeric_value(text: str, expected: float) -> bool:
    numbers = re.findall(r"-?\d+(?:\.\d+)?", text)

    for number in numbers:
        try:
            if abs(float(number) - float(expected)) < 0.01:
                return True
        except ValueError:
            continue

    return False


def assert_live_case_passed(
    result: dict,
    case: LiveWeatherCase,
) -> None:
    sop_result = result.get("sop_result")

    assert sop_result, "No SOP result returned."

    assert sop_result.get("matched") is True, (
        "No SOP matched the live severe-weather conditions."
    )

    assert sop_result.get("sop_id") == "SOP-OUTDOOR-SEVERE-01", (
        "Expected the severe-weather SOP, but got "
        f"{sop_result.get('sop_id')}"
    )

    assert sop_result.get("severity") == "critical", (
        "Expected critical severity, but got "
        f"{sop_result.get('severity')}"
    )

    weather = result.get("weather")

    assert weather is not None, "Graph returned no weather data."

    for key, expected_value in case.weather.items():
        actual_value = weather.get(key)

        if isinstance(expected_value, (float, int)):
            assert actual_value is not None
            assert abs(float(actual_value) - float(expected_value)) < 0.01, (
                f"Weather mismatch for {key}: "
                f"expected {expected_value}, got {actual_value}"
            )
        else:
            assert actual_value == expected_value, (
                f"Weather mismatch for {key}: "
                f"expected {expected_value}, got {actual_value}"
            )

    response = result.get("response")

    assert response, "No response generated."

    normalized_response = normalize_text(response)

    assert "sop-outdoor-severe-01" in normalized_response, (
        "Response does not reference the severe-weather SOP."
    )

    # Verify that the response exposes the actual weather values
    # that caused the severe policy to match.
    severe_weather_value_found = False

    for value in [
        case.weather["wind_speed_kmh"],
        case.weather["precipitation_probability"],
        case.weather["precipitation_mm"],
    ]:
        if contains_numeric_value(response, value):
            severe_weather_value_found = True
            break

    assert severe_weather_value_found, (
        "Response does not contain the actual live weather value "
        "that grounded the severe-weather decision."
    )


def main() -> None:
    print()
    print("LIVE SEVERE-WEATHER EVALUATION")
    print("=" * 72)
    print("Location:", CITY)
    print("Weather source: Open-Meteo live API")
    print("No weather values are hardcoded.")
    print()

    try:
        print("1. Resolving location through Open-Meteo geocoding...")
        location = resolve_location(CITY)

        print(
            f"   Resolved: {location['name']} "
            f"({location['latitude']}, {location['longitude']})"
        )
        print(f"   Timezone: {location['timezone']}")

        print()
        print("2. Fetching live 7-day hourly forecast...")
        forecast = fetch_live_forecast(location)

        print("   Forecast retrieved successfully.")

        print()
        print("3. Searching the live forecast for a genuinely severe hour...")

        case = find_severe_hour(forecast)

        if case is None:
            print()
            print("RESULT: NOT REPRODUCIBLE")
            print()
            print(
                "No forecast hour in the current live Pune forecast "
                "satisfied the configured severe-weather thresholds:"
            )
            print(
                f"- precipitation probability >= "
                f"{PRECIP_PROBABILITY_THRESHOLD}% AND "
                f"precipitation > {PRECIPITATION_THRESHOLD} mm"
            )
            print(f"- OR wind speed > {WIND_THRESHOLD} km/h")
            print()
            print(
                "This is an honest live-evaluation result. "
                "No synthetic severe weather was introduced."
            )
            print(
                "Live conditions change, so the same evaluation can "
                "become reproducible when a qualifying forecast exists."
            )
            return

        print()
        print("   Severe forecast hour found:")
        print(f"   Time: {case.target_hour}")

        print()
        print("   Actual Open-Meteo values:")
        for key, value in case.weather.items():
            print(f"   {key}: {value}")

        print()
        print("4. Running the real LangGraph...")
        print("   User intent: outdoor activity in Pune at the selected hour.")

        install_live_weather(location, case.weather)

        graph = build_graph()

        user_message = (
            f"Can I do an outdoor activity in {CITY} at "
            f"{case.target_hour}?"
        )

        result = graph.invoke(
            {
                "session_id": "eval-live-severe-weather",
                "user_message": user_message,
                "conversation_history": [],
            }
        )

        print()
        print("Extracted activity:")
        print(result.get("activity"))

        print()
        print("Matched SOP:")
        print(result.get("sop_result"))

        print()
        print("Weather passed through graph:")
        print(result.get("weather"))

        print()
        print("Response:")
        print(result.get("response"))

        print()

        try:
            assert_live_case_passed(result, case)
        except AssertionError as exc:
            print("RESULT: FAIL")
            print(f"Reason: {exc}")
            return

        print("RESULT: PASS")
        print()
        print("Live severe-weather evaluation passed.")
        print(
            "The severe decision was grounded in actual Open-Meteo "
            "forecast values."
        )
        print(
            "Note: live weather changes, so the selected hour and "
            "weather values are expected to vary between runs."
        )

    except requests.RequestException as exc:
        print()
        print("RESULT: UNAVAILABLE")
        print(f"Open-Meteo request failed: {exc}")
        print(
            "This run could not evaluate live severe weather because "
            "the external weather service was unavailable."
        )

    except Exception as exc:
        print()
        print("RESULT: ERROR")
        print(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()