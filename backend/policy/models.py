from typing import Any, Literal

from pydantic import BaseModel, Field


Severity = Literal["critical", "high", "moderate", "low"]


class Condition(BaseModel):
    field: str
    operator: str
    value: Any


class Decision(BaseModel):
    action: str
    message: str


class SOP(BaseModel):
    id: str
    name: str
    category: str
    severity: Severity
    priority: int = Field(ge=0)

    applies_when: dict[str, Any]

    decision: Decision
    explanation: str


class SOPConfig(BaseModel):
    version: str
    metadata: dict[str, Any]
    severity_priority: list[Severity]
    sops: list[SOP]