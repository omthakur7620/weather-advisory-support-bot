from __future__ import annotations

from typing import Any, TypedDict


class AdvisoryState(TypedDict, total=False):
    """
    State passed between LangGraph nodes.

    The state contains:
    - user/session context
    - extracted intent
    - location/weather data
    - deterministic SOP result
    - final response
    - clarification information
    """

    # ---------------------------------------------------------
    # Session / conversation
    # ---------------------------------------------------------

    session_id: str
    user_message: str
    conversation_history: list[dict[str, str]]

    # ---------------------------------------------------------
    # Extracted user intent
    # ---------------------------------------------------------

    activity: str | None
    location: str | None
    time_context: str | None
    target_hour: str | None
    group: str | None
    outdoor_activity: bool | None

    # ---------------------------------------------------------
    # Clarification
    # ---------------------------------------------------------

    clarification_needed: bool
    clarification_question: str | None

    # ---------------------------------------------------------
    # Intent/context metadata
    # ---------------------------------------------------------

    context_source: str | None

    # ---------------------------------------------------------
    # Location
    # ---------------------------------------------------------

    resolved_location: dict[str, Any] | None

    # ---------------------------------------------------------
    # Weather
    # ---------------------------------------------------------

    weather: dict[str, Any] | None
    weather_error: str | None

    # ---------------------------------------------------------
    # SOP evaluation
    # ---------------------------------------------------------

    sop_result: dict[str, Any] | None

    # ---------------------------------------------------------
    # Final response
    # ---------------------------------------------------------

    response: str | None

    # ---------------------------------------------------------
    # Graph status
    # ---------------------------------------------------------

    status: str | None