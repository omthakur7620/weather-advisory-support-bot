from __future__ import annotations

import re
from dataclasses import dataclass

from backend.graph.graph import build_graph
from backend.services import weather as weather_module


@dataclass
class EvaluationCase:
    name: str
    user_message: str
    expected_activity: str
    expected_location: str
    controlled_weather: dict


CASES = [
    EvaluationCase(
        name="No SOP for photography",
        user_message=(
            "I'm planning to do some photography outdoors in Pune tomorrow. "
            "What does the forecast look like?"
        ),
        expected_activity="outdoor activity",
        expected_location="Pune",
        controlled_weather={
            "temperature_c": 29.0,
            "precipitation_mm": 0.2,
            "precipitation_probability": 20.0,
            "wind_speed_kmh": 18.0,
            "uv_index": 6.0,
            "weather_code": 2,
            "observed_at": "2026-09-18T12:00",
        },
    )
]


def install_test_weather(weather: dict) -> None:
    """Replace only external weather calls for repeatability."""

    def fake_resolve_location(self, city: str):
        return weather_module.Location(
            name=city,
            latitude=18.51957,
            longitude=73.85535,
            timezone="Asia/Kolkata",
        )

    def fake_get_weather(self, location, *, target_hour=None):
        return dict(weather)

    weather_module.OpenMeteoWeatherService.resolve_location = (
        fake_resolve_location
    )

    weather_module.OpenMeteoWeatherService.get_weather = (
        fake_get_weather
    )


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


def contains_numeric_value(text: str, expected: float) -> bool:
    numbers = re.findall(r"-?\d+(?:\.\d+)?", text)

    for number in numbers:
        try:
            if abs(float(number) - float(expected)) < 0.01:
                return True
        except ValueError:
            continue

    return False


def assert_case_passed(
    case: EvaluationCase,
    result: dict,
) -> None:
    # ---------------------------------------------------------
    # 1. The graph must have processed the request.
    # ---------------------------------------------------------
    assert result.get("status") != "error", (
        f"Graph returned an error: {result.get('weather_error')}"
    )

    # ---------------------------------------------------------
    # 2. Weather must exist.
    # ---------------------------------------------------------
    weather = result.get("weather")

    assert weather is not None, (
        "No weather data was returned. "
        "The no-SOP path must still expose available weather."
    )

    # ---------------------------------------------------------
    # 3. Confirm the controlled weather reached the graph.
    # ---------------------------------------------------------
    for key, expected_value in case.controlled_weather.items():
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

    # ---------------------------------------------------------
    # 4. There must be NO applicable SOP.
    # ---------------------------------------------------------
    sop_result = result.get("sop_result")

    assert sop_result is not None, "No SOP result returned."

    assert sop_result.get("matched") is False, (
        "Expected no SOP to apply, but an SOP was matched: "
        f"{sop_result}"
    )

    assert sop_result.get("sop_id") is None, (
        "No-SOP result unexpectedly contains an SOP ID."
    )

    # ---------------------------------------------------------
    # 5. Response must exist.
    # ---------------------------------------------------------
    response = result.get("response")

    assert response, "No response generated."

    normalized_response = normalize_text(response)

    # ---------------------------------------------------------
    # 6. Response must explicitly communicate no SOP.
    # ---------------------------------------------------------
    no_sop_phrases = [
        "no specific safety sop",
        "no applicable sop",
        "no sop applies",
        "no applicable safety sop",
        "does not match any",
    ]

    assert any(
        phrase in normalized_response for phrase in no_sop_phrases
    ), (
        "Response does not explicitly communicate that no applicable "
        "SOP covers the situation."
    )

    # ---------------------------------------------------------
    # 7. Response must contain actual weather information.
    # ---------------------------------------------------------
    weather_values_to_check = [
        case.controlled_weather["temperature_c"],
        case.controlled_weather["wind_speed_kmh"],
        case.controlled_weather["precipitation_mm"],
    ]

    for expected_value in weather_values_to_check:
        assert contains_numeric_value(response, expected_value), (
            f"Response does not contain weather value "
            f"{expected_value}."
        )

    # ---------------------------------------------------------
    # 8. The response must NOT fabricate an SOP recommendation.
    # ---------------------------------------------------------
    fabricated_policy_phrases = [
        "according to sop",
        "sop recommends",
        "sop advises",
        "advised to avoid",
        "advises against",
        "recommend against",
        "do not go",
        "avoid going",
    ]

    # A no-SOP response should not claim a policy-backed action.
    for phrase in fabricated_policy_phrases:
        assert phrase not in normalized_response, (
            f"No-SOP response appears to invent policy guidance "
            f"through phrase: {phrase!r}"
        )


def run_case(case: EvaluationCase) -> bool:
    print("=" * 72)
    print(case.name)
    print("=" * 72)

    print(f"\nUser message:\n{case.user_message}")

    print("\nWhat this checks:")
    print("- Weather is available")
    print("- Activity has no matching configured SOP")
    print("- Graph reaches the explicit no-SOP path")
    print("- Response communicates that no SOP applies")
    print("- Response still reports actual weather values")
    print("- Response does not invent policy-backed advice")

    print("\nControlled weather:")
    for key, value in case.controlled_weather.items():
        print(f"- {key}: {value}")

    install_test_weather(case.controlled_weather)

    graph = build_graph()

    result = graph.invoke(
        {
            "session_id": f"eval-{case.name}",
            "user_message": case.user_message,
            "conversation_history": [],
        }
    )

    print("\nExtracted activity:")
    print(result.get("activity"))

    print("\nExtracted location:")
    print(result.get("location"))

    print("\nWeather:")
    print(result.get("weather"))

    print("\nSOP result:")
    print(result.get("sop_result"))

    print("\nResponse:")
    print(result.get("response"))

    try:
        assert_case_passed(case, result)
    except AssertionError as exc:
        print("\nRESULT: FAIL")
        print(f"Reason: {exc}")
        return False

    print("\nRESULT: PASS")
    return True


def main() -> None:
    passed = 0

    print()
    print("NO-SOP EVALUATION")
    print("=" * 72)
    print(
        "Weather is controlled for repeatability; "
        "the LangGraph no-SOP path is real."
    )
    print()

    for case in CASES:
        if run_case(case):
            passed += 1

    print("\n" + "=" * 72)
    print(f"Passed: {passed}/{len(CASES)}")
    print("=" * 72)

    if passed == len(CASES):
        print("Overall result: PASS")
    else:
        print("Overall result: FAIL")

    print("\nEvaluation notes:")
    print(
        "- Photography is intentionally not represented by any configured SOP."
    )
    print(
        "- The test verifies that weather facts are still returned."
    )
    print(
        "- The test verifies that no policy recommendation is fabricated."
    )
    print(
        "- Controlled weather is used only for deterministic evaluation."
    )


if __name__ == "__main__":
    main()