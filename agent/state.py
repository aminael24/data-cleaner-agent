from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    messages: list[dict[str, Any]]
    trace: list[dict[str, Any]]
    plan: dict[str, Any] | None
    error: str | None
    iterations: int
