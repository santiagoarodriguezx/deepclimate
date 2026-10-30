"""Typed Jev policy decisions for automated source and ML operations.

The repository has no Typesafe SDK, endpoint contract, or configured provider.
Until those are supplied, Jev uses this deterministic, auditable fallback.
The API boundary is intentionally narrow: it cannot run arbitrary commands.
"""

import datetime
import json
import math
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.database.models import JevDecisionRecord


class TypesafePolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["ingest_source", "train_candidate", "promote_model"]
    subject: str = Field(min_length=1, max_length=128)
    evidence: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class TypesafePolicyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    reason: str = Field(min_length=1, max_length=500)


class TypesafeDecisionProvider(Protocol):
    """Narrow adapter contract; no guessed HTTP endpoint is called."""

    def decide(self, request: TypesafePolicyRequest) -> TypesafePolicyResponse: ...


class JevDecision(BaseModel):
    action: str
    subject: str
    allowed: bool
    reason: str
    engine: str = "jev_deterministic_v1"
    external_provider_status: str = "unavailable"
    evidence: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class JevDecisionEngine:
    """Safety rules that keep data ingestion independent and ML promotion gated."""

    @staticmethod
    def provider_status() -> dict[str, str]:
        return {
            "provider": "Typesafe",
            "status": "unavailable",
            "reason": "No Typesafe SDK, service URL, or request/response contract exists in this project copy.",
            "fallback": "jev_deterministic_v1",
        }

    def decide_ingestion(
        self,
        source_id: str,
        *,
        enabled: bool = True,
        due: bool = True,
        failure_count: int = 0,
    ) -> JevDecision:
        evidence = {
            "enabled": enabled,
            "due": due,
            "consecutive_failures": max(0, int(failure_count)),
        }
        if not enabled:
            return JevDecision(action="ingest_source", subject=source_id, allowed=False,
                               reason="La fuente está desactivada por configuración.", evidence=evidence)
        if not due:
            return JevDecision(action="ingest_source", subject=source_id, allowed=False,
                               reason="La siguiente ejecución aún no está vencida.", evidence=evidence)
        return JevDecision(action="ingest_source", subject=source_id, allowed=True,
                           reason="La fuente está habilitada y su intervalo de actualización venció.", evidence=evidence)

    def decide_model_candidate(
        self,
        subject: str,
        *,
        dataset_ready: bool,
        mae: float | None,
        baseline_mae: float | None,
        champion_mae: float | None = None,
    ) -> JevDecision:
        evidence = {
            "dataset_ready": dataset_ready,
            "mae": mae,
            "baseline_mae": baseline_mae,
            "champion_mae": champion_mae,
        }
        if not dataset_ready:
            return JevDecision(action="promote_model", subject=subject, allowed=False,
                               reason="La serie no cumple el mínimo de continuidad temporal para entrenamiento.", evidence=evidence)
        if mae is None or baseline_mae is None or not math.isfinite(mae) or not math.isfinite(baseline_mae):
            return JevDecision(action="promote_model", subject=subject, allowed=False,
                               reason="Faltan métricas temporales finitas para evaluar el candidato.", evidence=evidence)
        if mae < 0 or baseline_mae < 0:
            return JevDecision(action="promote_model", subject=subject, allowed=False,
                               reason="Las métricas de error deben ser no negativas.", evidence=evidence)
        if mae >= baseline_mae:
            return JevDecision(action="promote_model", subject=subject, allowed=False,
                               reason="El candidato no supera el baseline de persistencia en MAE.", evidence=evidence)
        if champion_mae is not None and (not math.isfinite(champion_mae) or mae >= champion_mae):
            return JevDecision(action="promote_model", subject=subject, allowed=False,
                               reason="El candidato no mejora estrictamente el MAE del modelo campeón.", evidence=evidence)
        return JevDecision(action="promote_model", subject=subject, allowed=True,
                           reason="El candidato supera el baseline y, si existe, mejora al campeón en validación temporal.", evidence=evidence)


def persist_decision(db: Session, decision: JevDecision) -> JevDecisionRecord:
    record = JevDecisionRecord(
        action=decision.action,
        subject=decision.subject,
        allowed=decision.allowed,
        reason=decision.reason,
        engine=decision.engine,
        external_provider_status=decision.external_provider_status,
        created_at=datetime.datetime.utcnow(),
        metadata_json=json.dumps(decision.evidence, ensure_ascii=False, allow_nan=False),
    )
    db.add(record)
    db.flush()
    return record
