from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    messages: list[dict[str, Any]]
    trace: list[dict[str, Any]]
    plan: dict[str, Any] | None
    error: str | None
    iterations: int

    # Pré-audit déterministe (scan de toutes les colonnes).
    findings: dict[str, Any]

    # Anomalies que le plan final doit obligatoirement couvrir.
    requirements: list[dict[str, Any]]

    # Nombre de plans refusés (conservé pour compatibilité).
    rejections: int

    # --- nouveaux champs : LangGraph supprime toute clé non déclarée ici ---
    baseline_actions: list[dict[str, Any]]   # plan de base déterministe
    open_decisions: dict[str, Any]           # formes catégorielles soumises au LLM
    llm_error: str | None                    # échec du LLM (quota...) -> plan de base conservé
    force_submission: bool                  # reprise / dernier tour : exiger une soumission
