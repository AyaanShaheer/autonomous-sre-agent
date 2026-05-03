import os
import json
from datetime import datetime, timezone
from dotenv import load_dotenv
from groq import Groq
from agents.shared.models import AnomalyEvent, DiagnosisResult
from agents.diagnose.context_fetcher import build_context

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
CONFIDENCE_THRESHOLD = float(os.getenv("DIAGNOSIS_CONFIDENCE_THRESHOLD", 0.6))

SYSTEM_PROMPT = """You are an expert Site Reliability Engineer (SRE) with deep knowledge of Kubernetes,
container orchestration, and production incident management.

Your job is to analyze Kubernetes anomaly events combined with pod logs, metrics, and events,
then provide a structured root cause analysis.

You MUST respond with ONLY valid JSON matching this exact schema:
{
  "issue": "short title of the issue (max 10 words)",
  "root_cause": "detailed explanation of what caused this (2-4 sentences)",
  "confidence": 0.0 to 1.0,
  "severity_assessment": "one of: low, medium, high, critical",
  "immediate_actions": ["action1", "action2", "action3"],
  "long_term_recommendations": ["rec1", "rec2"],
  "requires_human_review": true or false,
  "reasoning": "your step-by-step reasoning process (3-5 sentences)"
}

Rules:
- confidence reflects how certain you are given the evidence
- requires_human_review = true if confidence < 0.7 or action is destructive
- immediate_actions should be specific kubectl commands or steps
- Be concise but precise"""


def diagnose_event(event: AnomalyEvent) -> DiagnosisResult:
    context = {}
    if event.pod and event.namespace:
        context = build_context(event.namespace, event.pod)

    user_prompt = f"""
## Anomaly Event
- Type: {event.anomaly_type.value}
- Severity: {event.severity.value}
- Namespace: {event.namespace}
- Pod: {event.pod or 'N/A'}
- Metric Value: {event.metric_value} (threshold: {event.threshold})
- Message: {event.message}
- Detected at: {event.timestamp}

## Pod Logs (last 50 lines)
{context.get('logs', 'N/A')}

## Kubernetes Events
{context.get('events', 'N/A')}

## Current Metrics
- CPU Usage: {context.get('metrics', {}).get('cpu_percent', 'N/A')}%
- Memory Usage: {context.get('metrics', {}).get('memory_mb', 'N/A')} MB

## Pod Description (condensed)
{context.get('description', 'N/A')[:2000]}

Analyze this incident and provide your structured diagnosis as JSON.
"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.1,
        max_tokens=1024,
    )

    raw = response.choices[0].message.content.strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    parsed = json.loads(raw)

    return DiagnosisResult(
        event_id=event.id,
        timestamp=datetime.now(timezone.utc),
        issue=parsed["issue"],
        root_cause=parsed["root_cause"],
        confidence=parsed["confidence"],
        severity_assessment=parsed["severity_assessment"],
        immediate_actions=parsed["immediate_actions"],
        long_term_recommendations=parsed["long_term_recommendations"],
        requires_human_review=parsed["requires_human_review"],
        reasoning=parsed["reasoning"]
    )


def run_diagnosis_on_latest_events() -> list[DiagnosisResult]:
    try:
        with open("/tmp/sre_anomaly_events.json") as f:
            raw_events = json.load(f)
    except FileNotFoundError:
        print("No events file found. Is the monitoring agent running?")
        return []

    events = [AnomalyEvent(**e) for e in raw_events]

    if not events:
        print("No active anomalies to diagnose.")
        return []

    results = []
    for event in events:
        print(f"\n🔍 Diagnosing: {event.anomaly_type.value} — {event.pod}")
        try:
            result = diagnose_event(event)
            results.append(result)

            with open("/tmp/sre_diagnosis_results.json", "w") as f:
                json.dump(
                    [r.model_dump(mode="json") for r in results],
                    f, indent=2, default=str
                )

        except Exception as e:
            print(f"  ✗ Diagnosis failed: {e}")

    return results