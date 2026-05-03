from typing import Optional, Annotated
from pydantic import BaseModel
from agents.shared.models import (
    AnomalyEvent, DiagnosisResult,
    DecisionResult
)
from agents.executor.agent import ExecutionResult
from policy.opa_client import PolicyDecision


class SREState(BaseModel):
    # Input
    events: list[AnomalyEvent] = []

    # Pipeline outputs — populated as graph progresses
    diagnosis: Optional[DiagnosisResult] = None
    rag_context: str = ""
    decision: Optional[DecisionResult] = None
    policy: Optional[PolicyDecision] = None
    execution: Optional[ExecutionResult] = None

    # Control flow
    current_event: Optional[AnomalyEvent] = None
    skip_reason: str = ""
    dry_run: bool = False
    error: str = ""

    # Final outcome
    incident_id: str = ""
    completed: bool = False

    class Config:
        arbitrary_types_allowed = True