"""
Paraphrased intent evaluation for the Weather Advisory Support Bot.

Purpose:
- Verify that the LLM understands user intent from natural/paraphrased language.
- Verify that SOP matching still happens deterministically after intent extraction.
- Verify that weather values used by the final response come from the supplied
  weather state rather than being invented by the model.

These evaluations use controlled weather data so that the evaluation is
repeatable. They do NOT modify production weather logic.
"""

from __future__ import annotations

from backend.app.runner import WeatherAdvisoryRunner


# ============================================================
# CONTROLLED WEATHER DATA
# ============================================================

CONTROLLED_WEATHER = {
    "temperature_c": 27.0,
    "precipitation_mm": 0.0,
    "precipitation_probability": 10,
    "wind_speed_kmh": 45.0,
    "uv_index": 4.0,
    "weather_code": 1,
    "observed_at": "2026-09-18T12:00",
}


# ============================================================
# TEST CASES
# ============================================================

CASES = [
    {
        "name": "Paraphrase 1 - trail activity",
        "message": (
            "I'm thinking of spending tomorrow on a hiking trail "
            "around Nashik. Can you check the conditions?"
        ),
        "expected_activity": "hiking",
        "expected_location": "Nashik",
        "expected_sop": "SOP-HIKING-RAIN-01",
        "expected_severity": "high",
        "weather": {
            **CONTROLLED_WEATHER,
            "precipitation_mm": 3.2,
            "precipitation_probability": 85,
            "wind_speed_kmh": 18.0,
        },
        "description": (
            "Checks whether natural wording such as 'spending tomorrow "
            "on a hiking trail' is interpreted as hiking."
        ),
    },
    {
        "name": "Paraphrase 2 - motorcycle travel",
        "message": (
            "Would it be sensible to head out on my motorcycle "
            "in Pune tomorrow if the wind is strong?"
        ),
        "expected_activity": "two-wheeler travel",
        "expected_location": "Pune",
        "expected_sop": "SOP-TWOWHEELER-WIND-01",
        "expected_severity": "high",
        "weather": {
            **CONTROLLED_WEATHER,
            "precipitation_mm": 0.0,
            "precipitation_probability": 10,
            "wind_speed_kmh": 45.0,
        },
        "description": (
            "Checks whether 'motorcycle' and 'head out' are interpreted "
            "as the configured two-wheeler travel intent."
        ),
    },
]


# ============================================================
# HELPERS
# ============================================================

def contains_number(text: str, value: object) -> bool:
    """
    Check whether a weather value appears in the generated response.

    Handles common formatting differences such as:
        45
        45.0
        45 km/h
    """

    if value is None:
        return False

    numeric = str(value)

    if numeric in text:
        return True

    try:
        number = float(value)

        if number.is_integer():
            return str(int(number)) in text

        return f"{number:g}" in text

    except (TypeError, ValueError):
        return False


def run_case(runner: WeatherAdvisoryRunner, case: dict) -> dict:
    """
    Run one paraphrased-intent evaluation.

    The runner is given controlled weather so this evaluation focuses on
    intent understanding + deterministic SOP matching.
    """

    original_weather_method = None

    # --------------------------------------------------------
    # Patch only this runner instance's weather service.
    #
    # Production weather code remains unchanged.
    # --------------------------------------------------------

    try:
        from backend.services.weather import OpenMeteoWeatherService

        original_weather_method = (
            OpenMeteoWeatherService.get_weather
        )

        def controlled_weather(
            self,
            location,
            *,
            target_hour=None,
        ):
            return dict(case["weather"])

        OpenMeteoWeatherService.get_weather = controlled_weather

        result = runner.run(
            session_id=f"paraphrase-{case['name']}",
            user_message=case["message"],
        )

    finally:
        if original_weather_method is not None:
            OpenMeteoWeatherService.get_weather = original_weather_method

    # --------------------------------------------------------
    # Extract state
    # --------------------------------------------------------

    sop_result = result.get("sop_result") or {}
    weather = result.get("weather") or {}

    response = result.get("response") or ""

    activity = result.get("activity")
    location = result.get("location")

    # --------------------------------------------------------
    # Checks
    # --------------------------------------------------------

    activity_pass = (
        activity == case["expected_activity"]
    )

    location_pass = (
        location is not None
        and case["expected_location"].lower()
        in str(location).lower()
    )

    sop_pass = (
        sop_result.get("matched") is True
        and sop_result.get("sop_id")
        == case["expected_sop"]
    )

    severity_pass = (
        sop_result.get("severity")
        == case["expected_severity"]
    )

    weather_state_pass = (
        weather == case["weather"]
    )

    response_sop_pass = (
        case["expected_sop"] in response
    )

    response_weather_pass = (
        contains_number(
            response,
            case["weather"]["wind_speed_kmh"],
        )
        or contains_number(
            response,
            case["weather"]["precipitation_mm"],
        )
    )

    passed = all(
        [
            activity_pass,
            location_pass,
            sop_pass,
            severity_pass,
            weather_state_pass,
            response_sop_pass,
            response_weather_pass,
        ]
    )

    notes = []

    if not activity_pass:
        notes.append(
            f"Intent mismatch: expected activity "
            f"'{case['expected_activity']}', got '{activity}'."
        )

    if not location_pass:
        notes.append(
            f"Location mismatch: expected "
            f"'{case['expected_location']}', got '{location}'."
        )

    if not sop_pass:
        notes.append(
            f"SOP mismatch: expected "
            f"'{case['expected_sop']}', got "
            f"'{sop_result.get('sop_id')}'."
        )

    if not severity_pass:
        notes.append(
            f"Severity mismatch: expected "
            f"'{case['expected_severity']}', got "
            f"'{sop_result.get('severity')}'."
        )

    if not weather_state_pass:
        notes.append(
            "The final graph state did not preserve the controlled "
            "weather values."
        )

    if not response_sop_pass:
        notes.append(
            "The response did not explicitly cite the matched SOP."
        )

    if not response_weather_pass:
        notes.append(
            "The response did not include a supplied weather value."
        )

    if not notes:
        notes.append(
            "Paraphrased intent was correctly extracted, the expected "
            "SOP was selected, and the response remained grounded in "
            "the supplied weather state."
        )

    return {
        "passed": passed,
        "activity_pass": activity_pass,
        "location_pass": location_pass,
        "sop_pass": sop_pass,
        "severity_pass": severity_pass,
        "weather_state_pass": weather_state_pass,
        "response_sop_pass": response_sop_pass,
        "response_weather_pass": response_weather_pass,
        "activity": activity,
        "location": location,
        "sop_id": sop_result.get("sop_id"),
        "severity": sop_result.get("severity"),
        "response": response,
        "notes": notes,
    }


# ============================================================
# MAIN EVALUATION
# ============================================================

def main() -> None:
    print("=" * 72)
    print("PARAPHRASED INTENT EVALUATION")
    print("=" * 72)

    print()
    print("What this checks:")
    print(
        "- Natural language intent understanding rather than keyword lookup."
    )
    print(
        "- Correct mapping from paraphrased intent to configured SOP."
    )
    print(
        "- Preservation of actual supplied weather values."
    )
    print(
        "- Explicit SOP traceability in the generated response."
    )
    print()

    runner = WeatherAdvisoryRunner()

    passed_count = 0

    for index, case in enumerate(CASES, start=1):
        print("-" * 72)
        print(f"CASE {index}: {case['name']}")
        print("-" * 72)

        print(f"Question: {case['message']}")
        print()
        print(f"What is being checked:")
        print(f"  {case['description']}")

        print()
        print("Pass looks like:")
        print(
            f"  Activity = {case['expected_activity']}"
        )
        print(
            f"  Location contains = {case['expected_location']}"
        )
        print(
            f"  SOP = {case['expected_sop']}"
        )
        print(
            f"  Severity = {case['expected_severity']}"
        )
        print(
            "  Response contains the supplied weather value"
        )
        print(
            "  Response explicitly cites the matched SOP"
        )

        result = run_case(
            runner,
            case,
        )

        if result["passed"]:
            passed_count += 1

        print()
        print(
            f"Detected activity: {result['activity']}"
        )
        print(
            f"Detected location: {result['location']}"
        )
        print(
            f"Matched SOP: {result['sop_id']}"
        )
        print(
            f"Severity: {result['severity']}"
        )

        print()
        print("Response:")
        print(result["response"])

        print()
        print(
            f"RESULT: {'PASS' if result['passed'] else 'FAIL'}"
        )

        print("Notes:")
        for note in result["notes"]:
            print(f"  - {note}")

        print()

    print("=" * 72)
    print(
        f"SUMMARY: {passed_count}/{len(CASES)} "
        "paraphrased-intent cases passed"
    )
    print("=" * 72)

    if passed_count != len(CASES):
        raise SystemExit(1)


if __name__ == "__main__":
    main()