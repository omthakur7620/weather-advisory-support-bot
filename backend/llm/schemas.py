from typing import Literal

from pydantic import BaseModel, Field


TimeContext = Literal[
    "now",
    "today",
    "this_afternoon",
    "this_evening",
    "tonight",
    "tomorrow",
    "future",
    "unspecified",
]


class UserIntent(BaseModel):
    """
    Structured representation of the user's request.

    The LLM is responsible for understanding language and
    identifying ambiguity. It does not make weather or safety
    decisions.
    """

    activity: str | None = Field(
        default=None,
        description=(
            "Canonical outdoor activity if clearly identified. "
            "Examples: cycling, hiking, two-wheeler travel, "
            "outdoor exercise, picnic. "
            "Use null when the activity is missing or ambiguous."
        ),
    )

    location: str | None = Field(
        default=None,
        description=(
            "City, destination, or location relevant to the "
            "weather request. Use null if unavailable."
        ),
    )

    time_context: TimeContext = Field(
        default="unspecified",
        description=(
            "The time period requested by the user."
        ),
    )

    target_hour: str | None = Field(
        default=None,
        description=(
            "Exact ISO-like local forecast hour only when the "
            "user explicitly provides enough information to "
            "identify one. Otherwise null."
        ),
    )

    group: str | None = Field(
        default=None,
        description=(
            "Relevant group context such as child, elderly, "
            "pet, or general. Use null when not specified."
        ),
    )

    outdoor_activity: bool = Field(
        default=True,
        description=(
            "Whether the request concerns an outdoor activity."
        ),
    )

    clarification_needed: bool = Field(
        default=False,
        description=(
            "True when the request lacks information or contains "
            "an ambiguity that must be clarified before checking "
            "weather or applying an SOP."
        ),
    )

    clarification_question: str | None = Field(
        default=None,
        description=(
            "A concise, natural question asking only for the "
            "missing or ambiguous information required to proceed."
        ),
    )