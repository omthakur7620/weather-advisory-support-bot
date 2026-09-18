"""Session runner for the weather-advisory support bot."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.graph.graph import build_graph


@dataclass
class Session:
    """
    In-memory conversation session.

    Session memory persists while the session is active and is
    discarded when the session is reset.
    """

    session_id: str
    conversation_history: list[dict[str, str]] = field(
        default_factory=list
    )

    # ---------------------------------------------------------
    # Intent memory
    # ---------------------------------------------------------

    activity: str | None = None
    location: str | None = None
    time_context: str | None = None
    target_hour: str | None = None
    group: str | None = None
    outdoor_activity: bool | None = None

    # ---------------------------------------------------------
    # Clarification memory
    # ---------------------------------------------------------

    clarification_needed: bool = False
    clarification_question: str | None = None


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def get_or_create(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(
                session_id=session_id
            )

        return self._sessions[session_id]

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def reset(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


class WeatherAdvisoryRunner:
    def __init__(self) -> None:
        self.session_manager = SessionManager()
        self.graph = build_graph()

    def run(
        self,
        *,
        session_id: str,
        user_message: str,
    ) -> dict[str, Any]:
        session = self.session_manager.get_or_create(session_id)

        initial_state = {
            "session_id": session.session_id,
            "user_message": user_message,
            "conversation_history": list(
                session.conversation_history
            ),

            # -------------------------------------------------
            # Existing session context
            # -------------------------------------------------

            "activity": session.activity,
            "location": session.location,
            "time_context": session.time_context,
            "target_hour": session.target_hour,
            "group": session.group,
            "outdoor_activity": session.outdoor_activity,

            # -------------------------------------------------
            # Clarification context
            # -------------------------------------------------

            "clarification_needed": session.clarification_needed,
            "clarification_question": (
                session.clarification_question
            ),
        }

        result = self.graph.invoke(initial_state)

        self._update_session(
            session=session,
            user_message=user_message,
            result=result,
        )

        return result

    def _update_session(
        self,
        *,
        session: Session,
        user_message: str,
        result: dict[str, Any],
    ) -> None:
        # -----------------------------------------------------
        # Update extracted intent
        # -----------------------------------------------------

        if result.get("activity") is not None:
            session.activity = result["activity"]

        if result.get("location") is not None:
            session.location = result["location"]

        if result.get("time_context") is not None:
            session.time_context = result["time_context"]

        if result.get("target_hour") is not None:
            session.target_hour = result["target_hour"]

        if result.get("group") is not None:
            session.group = result["group"]

        if result.get("outdoor_activity") is not None:
            session.outdoor_activity = result[
                "outdoor_activity"
            ]

        # -----------------------------------------------------
        # Update clarification state
        # -----------------------------------------------------

        if result.get("clarification_needed") is not None:
            session.clarification_needed = result[
                "clarification_needed"
            ]

        if result.get("clarification_question") is not None:
            session.clarification_question = result[
                "clarification_question"
            ]

        # Once the current request has been successfully
        # understood, the previous clarification is no longer
        # active.
        if result.get("status") != "clarification_required":
            session.clarification_needed = False
            session.clarification_question = None

        # -----------------------------------------------------
        # Conversation history
        # -----------------------------------------------------

        session.conversation_history.append(
            {
                "role": "user",
                "content": user_message,
            }
        )

        if result.get("response"):
            session.conversation_history.append(
                {
                    "role": "assistant",
                    "content": result["response"],
                }
            )

    def reset_session(self, session_id: str) -> None:
        self.session_manager.reset(session_id)