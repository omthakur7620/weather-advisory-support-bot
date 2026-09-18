"""
Clear SOP evaluation cases for the Weather Advisory Support Bot.

These evaluations exercise the real LangGraph and real LLM intent
extraction while replacing the weather service with deterministic
test weather.

Why mock weather here?
----------------------
Clear SOP evaluations should be repeatable. Live weather changes,
which could make a valid SOP test pass or fail depending on when
the evaluation is run.

The separate severe-weather evaluation will use genuinely live
Open-Meteo data as required by the assignment.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from backend.app.runner import WeatherAdvisoryRunner
from backend.services.weather import Location
from backend.services import weather as weather_module


# ============================================================
# Evaluation case definition
# ============================================================


@dataclass
class EvaluationCase:
    name: str
    user_message: str
    location: Location
    weather: dict
    expected_sop_id: str
    expected_severity: str

    # Only weather values that are materially relevant to the
    # selected SOP need to appear in the natural-language response.
    required_response_weather_values: list[float]

    pass_condition: str


# ============================================================
# Deterministic test weather
# ============================================================

HIKING_RAIN_WEATHER = {
    "temperature_c": 27.0,
    "precipitation_mm": 3.2,
    "precipitation_probability": 85,
    "wind_speed_kmh": 15.0,
    "uv_index": 5.0,
    "weather_code": 61,
    "observed_at": "2026-09-18T12:00",
}


CYCLING_WIND_WEATHER = {
    "temperature_c": 28.0,
    "precipitation_mm": 0.0,
    "precipitation_probability": 10,
    "wind_speed_kmh": 45.0,
    "uv_index": 5.0,
    "weather_code": 1,
    "observed_at": "2026-09-18T12:00",
}


# ============================================================
# Evaluation cases
# ============================================================

CASES = [
    EvaluationCase(
        name="Clear SOP — Hiking during likely rain",
        user_message=(
            "Would it be okay to go hiking in Nashik tomorrow?"
        ),
        location=Location(
            name="Nashik",
            latitude=20.0059,
            longitude=73.7797,
            timezone="Asia/Kolkata",
        ),
        weather=HIKING_RAIN_WEATHER,
        expected_sop_id="SOP-HIKING-RAIN-01",
        expected_severity="high",
        required_response_weather_values=[
            3.2,
            85.0,
        ],
        pass_condition=(
            "The graph identifies hiking in Nashik, retrieves the "
            "controlled test weather, matches SOP-HIKING-RAIN-01, "
            "and the final response reflects the SOP decision and "
            "the weather values that materially triggered the SOP."
        ),
    ),
    EvaluationCase(
        name="Clear SOP — Cycling in strong wind",
        user_message=(
            "Is it safe to cycle in Pune tomorrow?"
        ),
        location=Location(
            name="Pune",
            latitude=18.5204,
            longitude=73.8567,
            timezone="Asia/Kolkata",
        ),
        weather=CYCLING_WIND_WEATHER,
        expected_sop_id="SOP-CYCLE-WIND-01",
        expected_severity="high",
        required_response_weather_values=[
            45.0,
        ],
        pass_condition=(
            "The graph identifies cycling in Pune, retrieves the "
            "controlled test weather, matches SOP-CYCLE-WIND-01, "
            "and the final response reflects the SOP decision and "
            "the wind value that triggered the SOP."
        ),
    ),
]


# ============================================================
# Helpers
# ============================================================


def normalize_text(value: str) -> str:
    """
    Normalize punctuation differences commonly introduced by LLMs.

    For example:

        SOP-HIKING-RAIN-01
        SOP-HIKING-RAIN-01

    should be treated as the same identifier.
    """

    return (
        value
        .replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
        .lower()
    )


def contains_numeric_value(
    text: str,
    expected: float,
) -> bool:
    """
    Check whether a numeric value appears in the response while
    accepting normal formatting differences such as:

        27
        27.0
        27.00
        27 °C

    without accepting unrelated larger numbers.
    """

    matches = re.findall(
        r"(?<![\d.])\d+(?:\.\d+)?(?![\d.])",
        text,
    )

    for match in matches:
        try:
            actual = float(match)
        except ValueError:
            continue

        if abs(actual - expected) < 1e-9:
            return True

    return False


# ============================================================
# Weather-service patch
# ============================================================


def install_test_weather(case: EvaluationCase) -> None:
    """
    Replace Open-Meteo calls with deterministic weather for one
    evaluation case.

    This does not modify production weather code.
    """

    def fake_resolve_location(
        self,
        city: str,
    ) -> Location:
        return case.location

    def fake_get_weather(
        self,
        location: Location,
        *,
        target_hour: str | None = None,
    ) -> dict:
        return dict(case.weather)

    weather_module.OpenMeteoWeatherService.resolve_location = (
        fake_resolve_location
    )

    weather_module.OpenMeteoWeatherService.get_weather = (
        fake_get_weather
    )


# ============================================================
# Assertions
# ============================================================


def assert_case_passed(
    case: EvaluationCase,
    result: dict,
) -> list[str]:
    failures: list[str] = []

    sop_result = result.get("sop_result") or {}

    actual_sop_id = sop_result.get("sop_id")
    actual_severity = sop_result.get("severity")

    response = result.get("response") or ""
    weather = result.get("weather") or {}

    normalized_response = normalize_text(response)
    normalized_expected_sop = normalize_text(
        case.expected_sop_id
    )

    # --------------------------------------------------------
    # 1. SOP must match
    # --------------------------------------------------------

    if actual_sop_id != case.expected_sop_id:
        failures.append(
            f"Expected SOP {case.expected_sop_id}, "
            f"got {actual_sop_id!r}."
        )

    # --------------------------------------------------------
    # 2. Severity must match
    # --------------------------------------------------------

    if actual_severity != case.expected_severity:
        failures.append(
            f"Expected severity {case.expected_severity}, "
            f"got {actual_severity!r}."
        )

    # --------------------------------------------------------
    # 3. Weather must exist in graph state
    # --------------------------------------------------------

    if not weather:
        failures.append(
            "No weather data was present in the final graph state."
        )

    # --------------------------------------------------------
    # 4. Verify the controlled weather reached the graph
    # --------------------------------------------------------

    for key, expected_value in case.weather.items():

        if key == "observed_at":
            continue

        actual_value = weather.get(key)

        if isinstance(expected_value, (int, float)):

            if actual_value is None:
                failures.append(
                    f"Weather field {key!r} is missing from "
                    f"the graph result."
                )

            elif float(actual_value) != float(expected_value):
                failures.append(
                    f"Weather field {key!r}: expected "
                    f"{expected_value}, got {actual_value}."
                )

    # --------------------------------------------------------
    # 5. Final response must exist
    # --------------------------------------------------------

    if not response.strip():
        failures.append(
            "The graph produced no final response."
        )

    # --------------------------------------------------------
    # 6. Response must be traceable to selected SOP
    #
    # LLMs may use typographic hyphens, so compare normalized text.
    # --------------------------------------------------------

    if normalized_expected_sop not in normalized_response:
        failures.append(
            f"Final response does not reference "
            f"{case.expected_sop_id}."
        )

    # --------------------------------------------------------
    # 7. Response must reflect relevant weather facts
    #
    # We intentionally do NOT require every weather field to be
    # printed. Natural language may say "no expected precipitation"
    # rather than "0.0 mm".
    # --------------------------------------------------------

    for expected_value in (
        case.required_response_weather_values
    ):

        if not contains_numeric_value(
            response,
            expected_value,
        ):
            failures.append(
                f"Final response does not contain the relevant "
                f"weather value {expected_value}."
            )

    # --------------------------------------------------------
    # 8. The response should reflect the configured action
    # --------------------------------------------------------

    if case.expected_sop_id == "SOP-HIKING-RAIN-01":

        if (
            "advise against" not in normalized_response
            and "against hiking" not in normalized_response
        ):
            failures.append(
                "Final response does not reflect the configured "
                "hiking SOP action."
            )

    elif case.expected_sop_id == "SOP-CYCLE-WIND-01":

        if (
            "advise against" not in normalized_response
            and "against cycling" not in normalized_response
        ):
            failures.append(
                "Final response does not reflect the configured "
                "cycling SOP action."
            )

    return failures


# ============================================================
# Evaluation runner
# ============================================================


def run_case(
    case: EvaluationCase,
) -> bool:

    print()
    print("=" * 78)
    print(case.name)
    print("=" * 78)

    print()
    print("What is being checked:")
    print(case.pass_condition)

    print()
    print("User:")
    print(case.user_message)

    print()
    print("Controlled test weather:")
    print(case.weather)

    install_test_weather(case)

    runner = WeatherAdvisoryRunner()

    result = runner.run(
        session_id=f"eval-{case.expected_sop_id}",
        user_message=case.user_message,
    )

    failures = assert_case_passed(
        case,
        result,
    )

    print()
    print("Actual SOP:")
    print(
        (result.get("sop_result") or {}).get("sop_id")
    )

    print()
    print("Actual severity:")
    print(
        (result.get("sop_result") or {}).get("severity")
    )

    print()
    print("Final response:")
    print(result.get("response"))

    print()

    if failures:
        print("RESULT: FAIL")

        for failure in failures:
            print(f"  - {failure}")

        return False

    print("RESULT: PASS")
    return True


def main() -> None:

    passed = 0

    for case in CASES:

        if run_case(case):
            passed += 1

    total = len(CASES)

    print()
    print("=" * 78)
    print("CLEAR SOP EVALUATION SUMMARY")
    print("=" * 78)

    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("Overall result: PASS")
    else:
        print("Overall result: FAIL")

    print()
    print("Evaluation notes:")
    print(
        "- Weather is deterministic in these two cases so the "
        "tests are repeatable."
    )
    print(
        "- Intent extraction and response composition still use "
        "the configured application LLM."
    )
    print(
        "- Numeric assertions accept normal formatting differences "
        "such as 27 and 27.0."
    )
    print(
        "- SOP identifier checks normalize typographic hyphens."
    )
    print(
        "- The response is checked only for weather values that "
        "are materially relevant to the selected SOP."
    )
    print(
        "- The severe-weather evaluation will separately use "
        "genuinely live Open-Meteo conditions."
    )


if __name__ == "__main__":
    main()