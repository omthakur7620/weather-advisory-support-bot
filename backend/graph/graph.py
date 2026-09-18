"""LangGraph workflow for the weather-advisory support bot."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from backend.graph.nodes import (
    ask_clarification,
    compose_response,
    evaluate_sop,
    get_weather,
    location_error_node,
    location_missing_node,
    no_sop_node,
    resolve_location,
    resolve_time,
    time_error_node,
    understand_request,
    weather_error_node,
)
from backend.graph.state import AdvisoryState


# ============================================================
# ROUTERS
# ============================================================

def intent_router(state: AdvisoryState) -> str:
    """
    Decide whether the request needs clarification.

    This router only handles conversational completeness.
    It does not make any weather or safety decision.
    """

    if state.get("clarification_needed"):
        return "clarification"

    if not state.get("location"):
        return "location_missing"

    return "continue"


def location_result_router(state: AdvisoryState) -> str:
    """
    Route based on the result of location resolution.
    """

    if state.get("resolved_location"):
        return "continue"

    if state.get("status") == "location_missing":
        return "location_missing"

    return "error"


def time_result_router(state: AdvisoryState) -> str:
    """
    Route based on deterministic time resolution.
    """

    if state.get("status") == "time_resolved":
        return "continue"

    return "error"


def weather_result_router(state: AdvisoryState) -> str:
    """
    Route based on whether trusted weather data was retrieved.
    """

    if state.get("weather"):
        return "continue"

    return "error"


def sop_router(state: AdvisoryState) -> str:
    """
    Route based on deterministic SOP evaluation.

    The matcher is authoritative here. The LLM never chooses
    whether an SOP applies.
    """

    sop_result = state.get("sop_result") or {}

    if sop_result.get("matched") is True:
        return "matched"

    return "no_sop"


# ============================================================
# GRAPH CONSTRUCTION
# ============================================================

def build_graph():
    """
    Build and compile the weather-advisory LangGraph.

    Main flow:

        understand_request
                |
        +-------+--------+
        |                |
    clarification   location check
        |                |
       END        +------+------+
                  |             |
          location missing   resolve
                  |             |
                 END      location result
                                |
                       +--------+--------+
                       |                 |
                    error            resolve time
                       |                 |
                      END          +------+------+
                                   |             |
                                error         weather
                                   |             |
                                  END       +-----+-----+
                                            |           |
                                         error      evaluate SOP
                                            |           |
                                           END     +-----+-----+
                                                   |         |
                                                matched   no SOP
                                                   |         |
                                             compose     no_sop
                                                   |         |
                                                  END       END

    The important safety boundary is that:
    - language understanding is handled by the LLM
    - weather retrieval is handled by Open-Meteo
    - SOP matching is deterministic
    - response generation only verbalizes supplied facts
    """

    workflow = StateGraph(AdvisoryState)

    # --------------------------------------------------------
    # Nodes
    # --------------------------------------------------------

    workflow.add_node(
        "understand_request",
        understand_request,
    )

    workflow.add_node(
        "ask_clarification",
        ask_clarification,
    )

    workflow.add_node(
        "location_missing",
        location_missing_node,
    )

    workflow.add_node(
        "resolve_location",
        resolve_location,
    )

    workflow.add_node(
        "location_error",
        location_error_node,
    )

    workflow.add_node(
        "resolve_time",
        resolve_time,
    )

    workflow.add_node(
        "time_error",
        time_error_node,
    )

    workflow.add_node(
        "get_weather",
        get_weather,
    )

    workflow.add_node(
        "weather_error",
        weather_error_node,
    )

    workflow.add_node(
        "evaluate_sop",
        evaluate_sop,
    )

    workflow.add_node(
        "compose_response",
        compose_response,
    )

    workflow.add_node(
        "no_sop",
        no_sop_node,
    )

    # --------------------------------------------------------
    # Entry point
    # --------------------------------------------------------

    workflow.add_edge(
        START,
        "understand_request",
    )

    # --------------------------------------------------------
    # Intent branching
    # --------------------------------------------------------

    workflow.add_conditional_edges(
        "understand_request",
        intent_router,
        {
            "clarification": "ask_clarification",
            "location_missing": "location_missing",
            "continue": "resolve_location",
        },
    )

    workflow.add_edge(
        "ask_clarification",
        END,
    )

    workflow.add_edge(
        "location_missing",
        END,
    )

    # --------------------------------------------------------
    # Location resolution branching
    # --------------------------------------------------------

    workflow.add_conditional_edges(
        "resolve_location",
        location_result_router,
        {
            "continue": "resolve_time",
            "location_missing": "location_missing",
            "error": "location_error",
        },
    )

    workflow.add_edge(
        "location_error",
        END,
    )

    # --------------------------------------------------------
    # Time resolution branching
    # --------------------------------------------------------

    workflow.add_conditional_edges(
        "resolve_time",
        time_result_router,
        {
            "continue": "get_weather",
            "error": "time_error",
        },
    )

    workflow.add_edge(
        "time_error",
        END,
    )

    # --------------------------------------------------------
    # Weather retrieval branching
    # --------------------------------------------------------

    workflow.add_conditional_edges(
        "get_weather",
        weather_result_router,
        {
            "continue": "evaluate_sop",
            "error": "weather_error",
        },
    )

    workflow.add_edge(
        "weather_error",
        END,
    )

    # --------------------------------------------------------
    # SOP evaluation branching
    # --------------------------------------------------------

    workflow.add_conditional_edges(
        "evaluate_sop",
        sop_router,
        {
            "matched": "compose_response",
            "no_sop": "no_sop",
        },
    )

    # --------------------------------------------------------
    # Terminal response paths
    # --------------------------------------------------------

    workflow.add_edge(
        "compose_response",
        END,
    )

    workflow.add_edge(
        "no_sop",
        END,
    )

    return workflow.compile()


# ============================================================
# COMPILED GRAPH
# ============================================================

weather_advisory_graph = build_graph()