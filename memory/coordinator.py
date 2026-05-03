import json
import uuid
from datetime import datetime, timezone
from agents.shared.models import AnomalyEvent, DiagnosisResult, DecisionResult
from agents.executor.agent import ExecutionResult
from memory.redis_client import (
    store_incident, record_execution,
    store_active_alert, is_alert_active, get_execution_stats
)
from memory.vector_store import store_incident_vector, query_similar_incidents


def should_skip_alert(event: AnomalyEvent) -> bool:
    """Returns True if this alert was already processed recently (dedup)."""
    return is_alert_active(
        pod=event.pod or "",
        namespace=event.namespace,
        anomaly_type=event.anomaly_type.value
    )


def mark_alert_active(event: AnomalyEvent):
    store_active_alert(
        pod=event.pod or "",
        namespace=event.namespace,
        anomaly_type=event.anomaly_type.value
    )


def record_full_incident(
    event: AnomalyEvent,
    diagnosis: DiagnosisResult,
    decision: DecisionResult,
    execution: ExecutionResult
):
    """Persist the complete incident lifecycle to both Redis and ChromaDB."""
    incident_id = str(uuid.uuid4())
    outcome = execution.status.value

    # Redis — full incident snapshot
    incident_data = {
        "incident_id":    incident_id,
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "event":          event.model_dump(mode="json"),
        "diagnosis":      diagnosis.model_dump(mode="json"),
        "decision":       decision.model_dump(mode="json"),
        "execution":      execution.model_dump(mode="json"),
        "outcome":        outcome,
    }
    store_incident(incident_id, incident_data)

    # Redis — execution history for this pod
    record_execution(
        pod=event.pod or "",
        namespace=event.namespace,
        action=decision.selected_action.action_type.value,
        status=outcome
    )

    # ChromaDB — vector embedding for RAG
    store_incident_vector(
        incident_id=incident_id,
        anomaly_type=event.anomaly_type.value,
        issue=diagnosis.issue,
        root_cause=diagnosis.root_cause,
        action_taken=decision.selected_action.action_type.value,
        outcome=outcome,
        namespace=event.namespace,
        pod=event.pod or ""
    )

    return incident_id


def get_rag_context(event: AnomalyEvent, diagnosis: DiagnosisResult) -> str:
    """Retrieve similar past incidents to inject as context into LLM prompts."""
    similar = query_similar_incidents(
        anomaly_type=event.anomaly_type.value,
        issue=diagnosis.issue,
        root_cause=diagnosis.root_cause,
        n_results=3
    )

    if not similar:
        return "No similar past incidents found."

    lines = ["## Similar Past Incidents (from memory):"]
    for i, s in enumerate(similar, 1):
        meta = s["metadata"]
        similarity = round((1 - s["distance"]) * 100, 1)
        lines.append(
            f"\n[{i}] Similarity: {similarity}%\n"
            f"  Issue:   {meta.get('issue', 'N/A')}\n"
            f"  Action:  {meta.get('action_taken', 'N/A')}\n"
            f"  Outcome: {meta.get('outcome', 'N/A')}"
        )

    stats = get_execution_stats(event.pod or "", event.namespace)
    if stats["total"] > 0:
        lines.append(
            f"\n## Pod History:\n"
            f"  Total past incidents: {stats['total']}\n"
            f"  Success rate:         {stats['success_rate'] * 100:.0f}%\n"
            f"  Recurrence count:     {stats['recurrence_count']}"
        )

    return "\n".join(lines)