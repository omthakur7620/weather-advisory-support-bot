"""LangGraph nodes for the weather-advisory support bot."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.core.config import get_groq_api_key, get_groq_model
from backend.graph.state import AdvisoryState
from backend.llm.intent import IntentExtractor
from backend.llm.response import ResponseComposer
from backend.policy.loader import load_sop_config
from backend.policy.matcher import SOPMatcher
from backend.services.weather import (
    Location,
    OpenMeteoWeatherService,
    WeatherServiceError,
)


# ============================================================
# REQUEST UNDERSTANDING
# ============================================================


def understand_request(state: AdvisoryState) -> dict:
    """
    Understand the user's request using the LLM.

    The LLM is responsible only for extracting language-level intent.

    It does not:
    - make safety decisions
    - evaluate SOPs
    - invent weather
    - choose a policy
    """

    previous_context = {
        "activity": state.get("activity"),
        "location": state.get("location"),
        "time_context": state.get("time_context"),
        "target_hour": state.get("target_hour"),
        "group": state.get("group"),
        "outdoor_activity": state.get("outdoor_activity"),
    }

    extractor = IntentExtractor(
        api_key=get_groq_api_key(),
        model=get_groq_model(),
    )

    intent = extractor.extract(
        state["user_message"],
        previous_context=previous_context,
    )

    return {
        "activity": intent.activity,
        "location": intent.location,
        "time_context": intent.time_context,
        "target_hour": intent.target_hour,
        "group": intent.group,
        "outdoor_activity": intent.outdoor_activity,
        "clarification_needed": intent.clarification_needed,
        "clarification_question": intent.clarification_question,
        "context_source": "llm_with_session_context",
        "status": "request_understood",
    }


# ============================================================
# CLARIFICATION
# ============================================================


def ask_clarification(state: AdvisoryState) -> dict:
    """
    Return a clarification question when the user's intent is
    genuinely ambiguous.

    This node does not attempt to guess the user's activity,
    location, or safety intent.
    """

    question = state.get("clarification_question")

    if not question:
        question = (
            "Could you clarify what activity you mean and, if relevant, "
            "the location or time?"
        )

    return {
        "response": question,
        "status": "clarification_required",
    }


# ============================================================
# LOCATION
# ============================================================


def resolve_location(state: AdvisoryState) -> dict:
    """
    Resolve the user's city using Open-Meteo's geocoding API.

    No location is invented.

    If the location cannot be resolved, the graph receives an
    explicit failure status.
    """

    city = state.get("location")

    if not city:
        return {
            "resolved_location": None,
            "weather_error": None,
            "status": "location_missing",
        }

    service = OpenMeteoWeatherService()

    try:
        location = service.resolve_location(city)

    except WeatherServiceError as exc:
        return {
            "resolved_location": None,
            "weather_error": str(exc),
            "status": "location_error",
        }

    return {
        "resolved_location": {
            "name": location.name,
            "latitude": location.latitude,
            "longitude": location.longitude,
            "timezone": location.timezone,
        },
        "weather_error": None,
        "status": "location_resolved",
    }


# ============================================================
# TIME RESOLUTION
# ============================================================


def resolve_time(state: AdvisoryState) -> dict:
    """
    Convert semantic time context into a deterministic hourly
    timestamp.

    The LLM identifies the intended time period.

    This node determines the actual forecast hour using the
    resolved location's timezone.

    This node does not retrieve weather or make safety decisions.
    """

    resolved = state.get("resolved_location")

    if not resolved:
        return {
            "target_hour": None,
            "status": "time_error",
        }

    time_context = state.get("time_context")

    # ---------------------------------------------------------
    # Current weather
    # ---------------------------------------------------------

    if time_context in (None, "unspecified", "now"):
        return {
            "target_hour": None,
            "status": "time_resolved",
        }

    timezone_name = resolved.get("timezone")

    if not timezone_name:
        return {
            "target_hour": None,
            "status": "time_error",
        }

    try:
        timezone = ZoneInfo(timezone_name)

    except ZoneInfoNotFoundError:
        return {
            "target_hour": None,
            "status": "time_error",
        }

    now = datetime.now(timezone)

    # ---------------------------------------------------------
    # Explicit target hour from the intent extractor
    # ---------------------------------------------------------

    if state.get("target_hour"):
        return {
            "target_hour": state["target_hour"],
            "status": "time_resolved",
        }

    # ---------------------------------------------------------
    # Deterministic daypart hours
    # ---------------------------------------------------------

    daypart_hours = {
        "this_afternoon": 15,
        "this_evening": 18,
        "tonight": 21,
    }

    if time_context in daypart_hours:
        target_hour_value = daypart_hours[time_context]

        target = now.replace(
            hour=target_hour_value,
            minute=0,
            second=0,
            microsecond=0,
        )

        # If today's representative hour has already passed,
        # use the next day's occurrence.
        if target <= now:
            target += timedelta(days=1)

    # ---------------------------------------------------------
    # Tomorrow
    # ---------------------------------------------------------

    elif time_context == "tomorrow":
        target = (
            now + timedelta(days=1)
        ).replace(
            hour=12,
            minute=0,
            second=0,
            microsecond=0,
        )

    # ---------------------------------------------------------
    # Today
    # ---------------------------------------------------------

    elif time_context == "today":
        target = (
            now.replace(
                minute=0,
                second=0,
                microsecond=0,
            )
            + timedelta(hours=1)
        )

    # ---------------------------------------------------------
    # Generic future request
    # ---------------------------------------------------------

    elif time_context == "future":
        return {
            "target_hour": None,
            "status": "time_error",
        }

    # ---------------------------------------------------------
    # Unknown time context
    # ---------------------------------------------------------

    else:
        return {
            "target_hour": None,
            "status": "time_error",
        }

    target_hour = target.strftime("%Y-%m-%dT%H:%M")

    return {
        "target_hour": target_hour,
        "status": "time_resolved",
    }


# ============================================================
# WEATHER
# ============================================================


def get_weather(state: AdvisoryState) -> dict:
    """
    Retrieve live weather from Open-Meteo.

    Current/now requests use current weather.

    Future/daypart requests use the deterministic target_hour
    produced by resolve_time().

    This node never creates fallback weather values.
    """

    resolved = state.get("resolved_location")

    if not resolved:
        return {
            "weather": None,
            "weather_error": (
                "Weather lookup skipped because the location "
                "was not resolved."
            ),
            "status": "weather_error",
        }

    service = OpenMeteoWeatherService()

    location = Location(
        name=resolved["name"],
        latitude=resolved["latitude"],
        longitude=resolved["longitude"],
        timezone=resolved["timezone"],
    )

    time_context = state.get("time_context")

    # ---------------------------------------------------------
    # Current weather
    # ---------------------------------------------------------

    if time_context in (None, "unspecified", "now"):
        try:
            weather = service.get_weather(location)

        except WeatherServiceError as exc:
            return {
                "weather": None,
                "weather_error": str(exc),
                "status": "weather_error",
            }

        return {
            "weather": weather,
            "weather_error": None,
            "status": "weather_resolved",
        }

    # ---------------------------------------------------------
    # Hourly forecast
    # ---------------------------------------------------------

    target_hour = state.get("target_hour")

    # Never guess a forecast timestamp.
    if not target_hour:
        return {
            "weather": None,
            "weather_error": (
                f"Hourly weather was requested for "
                f"'{time_context}', but no exact target hour "
                "has been resolved."
            ),
            "status": "weather_error",
        }

    try:
        weather = service.get_weather(
            location,
            target_hour=target_hour,
        )

    except WeatherServiceError as exc:
        return {
            "weather": None,
            "weather_error": str(exc),
            "status": "weather_error",
        }

    return {
        "weather": weather,
        "weather_error": None,
        "status": "weather_resolved",
    }


# ============================================================
# SOP EVALUATION
# ============================================================


def evaluate_sop(state: AdvisoryState) -> dict:
    """
    Evaluate live weather against the external SOP configuration.

    This is a deterministic policy decision.

    The LLM does not decide whether an SOP applies.

    Weather values come from Open-Meteo.

    Policy rules come from sops/sops.yaml.
    """

    weather = state.get("weather")

    if not weather:
        return {
            "sop_result": {
                "matched": False,
                "sop_id": None,
                "sop_name": None,
                "severity": None,
                "action": None,
                "message": None,
                "explanation": None,
            },
            "status": "no_weather_for_sop",
        }

    sop_path = (
        Path(__file__).resolve().parents[2]
        / "sops"
        / "sops.yaml"
    )

    config = load_sop_config(sop_path)

    matcher = SOPMatcher(config)

    user_context = {
        "activity": state.get("activity"),
        "location": state.get("location"),
        "group": state.get("group"),
        "outdoor_activity": state.get("outdoor_activity"),
        "time_context": state.get("time_context"),
        "target_hour": state.get("target_hour"),
    }

    result = matcher.match(
        user_context=user_context,
        weather=weather,
    )

    return {
        "sop_result": result,
        "status": (
            "sop_matched"
            if result.get("matched")
            else "no_sop"
        ),
    }


# ============================================================
# RESPONSE COMPOSITION
# ============================================================


def compose_response(state: AdvisoryState) -> dict:
    """
    Compose the final user-facing response.

    The response composer receives:

    - the user's current message
    - recent conversation history
    - structured intent
    - trusted weather data
    - deterministic SOP result

    The response composer does not make policy decisions.
    """

    sop_result = state.get("sop_result")

    # ---------------------------------------------------------
    # No SOP result available
    # ---------------------------------------------------------

    if not sop_result:
        return {
            "response": (
                "I couldn't determine an applicable weather "
                "policy for this request."
            ),
            "status": "response_error",
        }

    weather = state.get("weather")

    # ---------------------------------------------------------
    # Weather unavailable
    # ---------------------------------------------------------

    if not weather:
        return {
            "response": (
                "I don't have reliable weather data for this "
                "request, so I can't provide weather-based guidance."
            ),
            "status": "response_error",
        }

    composer = ResponseComposer(
        api_key=get_groq_api_key(),
        model=get_groq_model(),
    )

    response = composer.compose(
        user_message=state["user_message"],
        activity=state.get("activity"),
        location=state.get("location"),
        time_context=state.get("time_context"),
        weather=weather,
        sop_result=sop_result,
        conversation_history=state.get(
            "conversation_history",
            [],
        ),
    )

    return {
        "response": response,
        "status": "response_composed",
    }


# ============================================================
# NO-SOP RESPONSE
# ============================================================


def no_sop_node(state: AdvisoryState) -> dict:
    """
    Handle the case where no configured SOP applies.

    The user should still receive useful factual weather
    information when weather was successfully retrieved.

    Important:
    - Do not claim the activity is safe.
    - Do not invent safety advice.
    - Do not fabricate a policy.
    """

    weather = state.get("weather")

    if not weather:
        return {
            "response": (
                "No applicable SOP was found, and I don't have "
                "reliable weather data to provide additional "
                "weather information."
            ),
            "status": "no_sop_response",
        }

    composer = ResponseComposer(
        api_key=get_groq_api_key(),
        model=get_groq_model(),
    )

    no_sop_result = {
        "matched": False,
        "sop_id": None,
        "sop_name": None,
        "severity": None,
        "action": None,
        "message": None,
        "explanation": (
            "No configured SOP matched the user's activity "
            "and the retrieved weather conditions."
        ),
    }

    response = composer.compose(
        user_message=state["user_message"],
        activity=state.get("activity"),
        location=state.get("location"),
        time_context=state.get("time_context"),
        weather=weather,
        sop_result=no_sop_result,
        conversation_history=state.get(
            "conversation_history",
            [],
        ),
    )

    return {
        "response": response,
        "status": "no_sop_response",
    }


# ============================================================
# LOCATION ERROR
# ============================================================


def location_error_node(state: AdvisoryState) -> dict:
    """
    Honest fallback when location resolution fails.

    No weather values are invented.
    """

    error = state.get("weather_error")

    if error:
        response = (
            "I couldn't resolve that location, so I couldn't "
            "retrieve reliable weather data for it."
        )
    else:
        response = (
            "I couldn't resolve the requested location, so I "
            "couldn't retrieve reliable weather data."
        )

    return {
        "response": response,
        "status": "location_error_response",
    }


# ============================================================
# LOCATION MISSING
# ============================================================


def location_missing_node(state: AdvisoryState) -> dict:
    """
    Handle a request where no location is available.

    The assistant does not invent a location.
    """

    return {
        "response": (
            "Which city or location should I check the weather for?"
        ),
        "status": "location_missing_response",
    }


# ============================================================
# TIME ERROR
# ============================================================


def time_error_node(state: AdvisoryState) -> dict:
    """
    Honest fallback when the requested time period cannot be
    deterministically resolved.
    """

    return {
        "response": (
            "I couldn't determine the exact forecast time for "
            "that request. Please specify a clearer time such as "
            "today, tomorrow, this evening, or tonight."
        ),
        "status": "time_error_response",
    }


# ============================================================
# WEATHER ERROR
# ============================================================


def weather_error_node(state: AdvisoryState) -> dict:
    """
    Honest fallback when live weather retrieval fails.

    No forecast values are invented.
    """

    return {
        "response": (
            "I couldn't retrieve reliable live weather data for "
            "that request, so I won't guess the forecast or give "
            "weather-based guidance."
        ),
        "status": "weather_error_response",
    }