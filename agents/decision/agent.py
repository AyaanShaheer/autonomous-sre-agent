import os
import json
from datetime import datetime, timezone
from dotenv import load_dotenv
from groq import Groq
from agents.shared.models import (
    AnomalyEvent, DiagnosisResult, DecisionResult,
    ProposedAction, ActionType, RiskLevel
)

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

SYSTEM_PROMPT = """You are an expert Kubernetes SRE Decision Engine.

Given an anomaly event and its diagnosis, you must generate a ranked list of possible
remediation actions and select the best one based on safety, effectiveness, and risk.

You MUST respond with ONLY valid JSON matching this exact schema:
{
  "proposed_actions": [
    {
      "action_type": "one of: delete_pod, restart_deployment, scale_deployment, update_resources, cordon_node, no_action, alert_human",
      "description": "human readable description of the action",
      "kubectl_command": "exact kubectl command to run, or null",
      "risk_level": "one of: safe, low, medium, high, dangerous",
      "estimated_downtime_seconds": 0,
      "reversible": true or false,
      "confidence_required": 0.0 to 1.0,
      "rationale": "why this action addresses the root cause"
    }
  ],
  "selected_action_index": 0,
  "selection_reasoning": "why you chose this action over the others",
  "approved_for_execution": true or false
}

Ranking rules:
- Always generate at least 3 candidate actions
- Prefer safe, reversible actions over destructive ones
- approved_for_execution = false if: diagnosis confidence < 0.7, risk_level is high/dangerous,
  or the environment is production
- The selected action must be the best balance of effectiveness and safety
- Include alert_human as a fallback action always
- kubectl_command must be a real, executable command"""


def decide(event: AnomalyEvent, diagnosis: DiagnosisResult) -> DecisionResult:
    user_prompt = f"""
## Anomaly Event
- ID: {event.id}
- Type: {event.anomaly_type.value}
- Severity: {event.severity.value}
- Namespace: {event.namespace}
- Pod: {event.pod or 'N/A'}
- Message: {event.message}

## Diagnosis
- Issue: {diagnosis.issue}
- Root Cause: {diagnosis.root_cause}
- Confidence: {diagnosis.confidence:.0%}
- Severity Assessment: {diagnosis.severity_assessment}
- Requires Human Review: {diagnosis.requires_human_review}

## Suggested Immediate Actions (from diagnosis)
{chr(10).join(f"- {a}" for a in diagnosis.immediate_actions)}

Generate a ranked list of remediation actions and select the best one.
Remember: namespace is '{event.namespace}', pod is '{event.pod}'.
"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.1,
        max_tokens=2048,
    )

    raw = response.choices[0].message.content.strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    parsed = json.loads(raw)

    proposed_actions = [
        ProposedAction(
            action_type=ActionType(a["action_type"]),
            description=a["description"],
            kubectl_command=a.get("kubectl_command"),
            risk_level=RiskLevel(a["risk_level"]),
            estimated_downtime_seconds=a["estimated_downtime_seconds"],
            reversible=a["reversible"],
            confidence_required=a["confidence_required"],
            rationale=a["rationale"]
        )
        for a in parsed["proposed_actions"]
    ]

    selected = proposed_actions[parsed["selected_action_index"]]

    # Safety override: force human review if high risk or low confidence
    approved = parsed["approved_for_execution"]
    override_reason = None
    if selected.risk_level in (RiskLevel.HIGH, RiskLevel.DANGEROUS):
        approved = False
        override_reason = f"Risk level '{selected.risk_level.value}' requires human approval"
    elif diagnosis.confidence < 0.7:
        approved = False
        override_reason = f"Diagnosis confidence {diagnosis.confidence:.0%} below 70% threshold"
    elif diagnosis.requires_human_review:
        approved = False
        override_reason = "Diagnosis flagged for human review"

    return DecisionResult(
        event_id=event.id,
        diagnosis_id=diagnosis.event_id,
        timestamp=datetime.now(timezone.utc),
        proposed_actions=proposed_actions,
        selected_action=selected,
        selection_reasoning=parsed["selection_reasoning"],
        approved_for_execution=approved,
        override_reason=override_reason
    )


def run_decision_on_latest() -> list[DecisionResult]:
    try:
        with open("/tmp/sre_anomaly_events.json") as f:
            raw_events = json.load(f)
        with open("/tmp/sre_diagnosis_results.json") as f:
            raw_diagnoses = json.load(f)
    except FileNotFoundError as e:
        print(f"Missing file: {e}. Run monitoring + diagnosis agents first.")
        return []

    if not raw_events or not raw_diagnoses:
        print("No events or diagnoses found.")
        return []

    # Match by pod name since event IDs regenerate every poll cycle
    # Build a map: pod -> latest anomaly event
    events_by_pod: dict[str, AnomalyEvent] = {}
    for e in raw_events:
        event = AnomalyEvent(**e)
        pod_key = f"{event.namespace}/{event.pod}"
        events_by_pod[pod_key] = event  # last one wins

    # Deduplicate diagnoses by pod — keep highest confidence per pod
    best_diagnosis_by_pod: dict[str, DiagnosisResult] = {}
    for d in raw_diagnoses:
        diagnosis = DiagnosisResult(**d)
        # Find which pod this diagnosis is about by scanning events
        # Use the issue text to match — or just pick best confidence per pod
        matched_pod = None
        for pod_key, event in events_by_pod.items():
            if event.pod and event.pod in diagnosis.issue.lower():
                matched_pod = pod_key
                break
        if not matched_pod:
            # Fallback: assign to first available pod
            matched_pod = list(events_by_pod.keys())[0] if events_by_pod else None

        if matched_pod:
            existing = best_diagnosis_by_pod.get(matched_pod)
            if not existing or diagnosis.confidence > existing.confidence:
                best_diagnosis_by_pod[matched_pod] = diagnosis

    if not best_diagnosis_by_pod:
        print("Could not match any diagnoses to events.")
        return []

    results = []
    for pod_key, diagnosis in best_diagnosis_by_pod.items():
        event = events_by_pod.get(pod_key)
        if not event:
            continue

        print(f"\n⚖️  Deciding action for: {diagnosis.issue} — {event.pod}")
        try:
            result = decide(event, diagnosis)
            results.append(result)
        except Exception as e:
            print(f"  ✗ Decision failed: {e}")

    with open("/tmp/sre_decision_results.json", "w") as f:
        json.dump(
            [r.model_dump(mode="json") for r in results],
            f, indent=2, default=str
        )

    return results