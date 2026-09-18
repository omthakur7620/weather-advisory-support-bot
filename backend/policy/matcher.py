"""Deterministic SOP matching engine."""

from __future__ import annotations

from typing import Any

from backend.policy.models import SOP, SOPConfig


class SOPMatcher:
    """
    Deterministic engine that evaluates weather/user context
    against business-defined SOPs.

    The matcher does not use an LLM and does not invent policy.
    """

    def __init__(self, config: SOPConfig):
        self.config = config

    def match(
        self,
        user_context: dict[str, Any],
        weather: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Evaluate all SOPs and return the highest-priority applicable SOP.

        Resolution order:
        1. Severity
        2. Specificity
        3. Explicit SOP priority
        4. SOP ID as deterministic final tie-breaker
        """

        applicable: list[dict[str, Any]] = []

        context = {
            **user_context,
            "weather": weather,
        }

        for sop in self.config.sops:
            matched_conditions = self._evaluate_rule(
                sop.applies_when,
                context,
            )

            if matched_conditions is not None:
                applicable.append(
                    {
                        "sop": sop,
                        "matched_conditions": matched_conditions,
                    }
                )

        if not applicable:
            return {
                "matched": False,
                "sop_id": None,
                "sop_name": None,
                "category": None,
                "severity": None,
                "action": None,
                "explanation": None,
                "matched_conditions": [],
            }

        selected = sorted(
            applicable,
            key=lambda item: self._sort_key(item),
        )[0]

        sop: SOP = selected["sop"]

        return {
            "matched": True,
            "sop_id": sop.id,
            "sop_name": sop.name,
            "category": sop.category,
            "severity": sop.severity,
            "action": sop.decision.action,
            "explanation": sop.explanation,
            "matched_conditions": selected["matched_conditions"],
        }

    def _sort_key(self, item: dict[str, Any]) -> tuple[int, int, int, str]:
        """
        Lower tuple values win.

        Severity is evaluated first, followed by specificity,
        explicit priority, then SOP ID.
        """

        sop: SOP = item["sop"]

        severity_rank = {
            severity: index
            for index, severity in enumerate(
                self.config.severity_priority
            )
        }

        severity_value = severity_rank[sop.severity]

        specificity = self._specificity(sop.applies_when)

        # Higher specificity and priority should win,
        # so negate them for ascending sort.
        return (
            severity_value,
            -specificity,
            -sop.priority,
            sop.id,
        )

    def _specificity(self, rule: dict[str, Any]) -> int:
        """Count explicit conditions in a rule."""

        if not rule:
            return 0

        if "all" in rule:
            return sum(
                self._specificity(condition)
                for condition in rule["all"]
            )

        if "any" in rule:
            return sum(
                self._specificity(condition)
                for condition in rule["any"]
            )

        if self._is_condition(rule):
            return 1

        return 0

    def _evaluate_rule(
        self,
        rule: dict[str, Any],
        context: dict[str, Any],
    ) -> list[dict[str, Any]] | None:
        """
        Evaluate a logical SOP rule.

        Supported structures:

        1. Single condition:
           field + operator + value

        2. all:
           Every child rule must match.

        3. any:
           At least one child rule must match.

        4. all + any:
           Both groups must match:
               all conditions AND (any condition)

        Returns matched condition details when the rule passes.
        Returns None when the rule does not pass.
        """

        if not rule:
            return []

        matched_conditions: list[dict[str, Any]] = []

        # Leaf condition
        if self._is_condition(rule):
            return self._evaluate_condition(
                rule,
                context,
            )

        # "all" means every child must match.
        if "all" in rule:
            for child_rule in rule["all"]:
                result = self._evaluate_rule(
                    child_rule,
                    context,
                )

                if result is None:
                    return None

                matched_conditions.extend(result)

        # "any" means at least one child must match.
        if "any" in rule:
            any_match = False

            for child_rule in rule["any"]:
                result = self._evaluate_rule(
                    child_rule,
                    context,
                )

                if result is not None:
                    any_match = True
                    matched_conditions.extend(result)
                    break

            if not any_match:
                return None

        # The rule is valid only if all requested logical groups passed.
        if "all" in rule or "any" in rule:
            return matched_conditions

        raise ValueError(
            f"Unsupported SOP rule structure: {rule}"
        )

    @staticmethod
    def _is_condition(rule: dict[str, Any]) -> bool:
        """Check whether a rule is a leaf condition."""

        return {
            "field",
            "operator",
            "value",
        }.issubset(rule.keys())

    def _evaluate_condition(
        self,
        condition: dict[str, Any],
        context: dict[str, Any],
    ) -> list[dict[str, Any]] | None:
        """Evaluate one deterministic condition."""

        field = condition["field"]
        operator = condition["operator"]
        expected = condition["value"]

        actual = self._get_field(context, field)

        # Missing weather/context data must never be guessed.
        if actual is None:
            return None

        matched = self._compare(
            actual=actual,
            operator=operator,
            expected=expected,
        )

        if not matched:
            return None

        return [
            {
                "field": field,
                "actual": actual,
                "operator": operator,
                "threshold": expected,
            }
        ]

    @staticmethod
    def _get_field(
        context: dict[str, Any],
        field: str,
    ) -> Any:
        """Read a dotted field such as weather.wind_speed_kmh."""

        value: Any = context

        for part in field.split("."):
            if not isinstance(value, dict):
                return None

            value = value.get(part)

            if value is None:
                return None

        return value

    @staticmethod
    def _compare(
        actual: Any,
        operator: str,
        expected: Any,
    ) -> bool:
        """Apply a supported comparison operator."""

        if operator == "equals":
            return actual == expected

        if operator == "not_equals":
            return actual != expected

        if operator == "greater_than":
            return actual > expected

        if operator == "greater_than_or_equal":
            return actual >= expected

        if operator == "less_than":
            return actual < expected

        if operator == "less_than_or_equal":
            return actual <= expected

        if operator == "between":
            if not isinstance(expected, dict):
                raise ValueError(
                    "'between' requires {'min': value, 'max': value}"
                )

            if "min" not in expected or "max" not in expected:
                raise ValueError(
                    "'between' requires both 'min' and 'max'"
                )

            lower = expected["min"]
            upper = expected["max"]

            return lower <= actual <= upper

        if operator == "in":
            if not isinstance(expected, list):
                raise ValueError(
                    "'in' requires a list of values"
                )

            return actual in expected

        raise ValueError(
            f"Unsupported SOP operator: {operator}"
        )