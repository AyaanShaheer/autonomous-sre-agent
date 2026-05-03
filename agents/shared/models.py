from pydantic import BaseModel
from datetime import datetime
from enum import Enum
from typing import Optional


class AnomalyType(str, Enum):
    HIGH_CPU = "high_cpu"
    HIGH_MEMORY = "high_memory"
    POD_CRASH_LOOP = "pod_crash_loop"
    POD_NOT_READY = "pod_not_ready"
    HIGH_RESTART_COUNT = "high_restart_count"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AnomalyEvent(BaseModel):
    id: str
    timestamp: datetime
    anomaly_type: AnomalyType
    severity: Severity
    namespace: str
    pod: Optional[str] = None
    deployment: Optional[str] = None
    node: Optional[str] = None
    metric_value: float
    threshold: float
    message: str
    raw_labels: dict = {}


class DiagnosisResult(BaseModel):
    event_id: str
    timestamp: datetime
    issue: str
    root_cause: str
    confidence: float
    severity_assessment: str
    immediate_actions: list[str]
    long_term_recommendations: list[str]
    requires_human_review: bool
    reasoning: str


class RiskLevel(str, Enum):
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    DANGEROUS = "dangerous"


class ActionType(str, Enum):
    DELETE_POD = "delete_pod"
    RESTART_DEPLOYMENT = "restart_deployment"
    SCALE_DEPLOYMENT = "scale_deployment"
    UPDATE_RESOURCES = "update_resources"
    CORDON_NODE = "cordon_node"
    NO_ACTION = "no_action"
    ALERT_HUMAN = "alert_human"


class ProposedAction(BaseModel):
    action_type: ActionType
    description: str
    kubectl_command: Optional[str] = None
    risk_level: RiskLevel
    estimated_downtime_seconds: int
    reversible: bool
    confidence_required: float        # minimum diagnosis confidence needed
    rationale: str


class DecisionResult(BaseModel):
    event_id: str
    diagnosis_id: str
    timestamp: datetime
    proposed_actions: list[ProposedAction]
    selected_action: ProposedAction
    selection_reasoning: str
    approved_for_execution: bool      # False if requires human review
    override_reason: Optional[str] = None