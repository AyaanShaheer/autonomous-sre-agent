import os
from dotenv import load_dotenv
from rich.console import Console
from agents.shared.models import AnomalyEvent, ActionType
from agents.diagnose.agent import diagnose_event
from agents.decision.agent import decide
from agents.executor.agent import execute_approved_actions, ExecutionStatus, ExecutionResult
from policy.opa_client import evaluate
from memory.coordinator import (
    should_skip_alert, mark_alert_active,
    record_full_incident, get_rag_context
)
from orchestrator.state import SREState
from datetime import datetime, timezone

load_dotenv()
console = Console()
ENVIRONMENT = os.getenv("SRE_ENVIRONMENT", "staging")


def node_triage(state: SREState) -> SREState:
    """Pick the highest severity event to process, skip if already active."""
    if not state.events:
        state.skip_reason = "No anomaly events detected"
        return state

    # Sort by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_events = sorted(
        state.events,
        key=lambda e: severity_order.get(e.severity.value, 99)
    )

    for event in sorted_events:
        if not should_skip_alert(event):
            state.current_event = event
            mark_alert_active(event)
            console.print(
                f"\n[bold cyan]🔀 Triage:[/bold cyan] Processing "
                f"[red]{event.severity.value.upper()}[/red] — "
                f"{event.anomaly_type.value} on pod [yellow]{event.pod}[/yellow]"
            )
            return state

    state.skip_reason = "All active alerts already processed (dedup)"
    return state


def node_diagnose(state: SREState) -> SREState:
    """Run LLM diagnosis on the current event."""
    event = state.current_event
    console.print(f"[bold cyan]🧠 Diagnosing:[/bold cyan] {event.pod}")

    try:
        diagnosis = diagnose_event(event)
        state.diagnosis = diagnosis

        # Inject RAG context from memory
        state.rag_context = get_rag_context(event, diagnosis)
        if "Similar Past Incidents" in state.rag_context:
            console.print(f"  [dim]RAG: Found similar past incidents[/dim]")

        console.print(
            f"  Issue: {diagnosis.issue} "
            f"[dim](confidence: {diagnosis.confidence:.0%})[/dim]"
        )
    except Exception as e:
        state.error = f"Diagnosis failed: {e}"
        console.print(f"  [red]✗ {state.error}[/red]")

    return state


def node_decide(state: SREState) -> SREState:
    """Generate ranked action list and select the best one."""
    console.print(f"[bold cyan]⚖️  Deciding:[/bold cyan] generating action plan")

    try:
        decision = decide(state.current_event, state.diagnosis)
        state.decision = decision
        console.print(
            f"  Selected: [yellow]{decision.selected_action.action_type.value}[/yellow] "
            f"(risk: {decision.selected_action.risk_level.value})"
        )
    except Exception as e:
        state.error = f"Decision failed: {e}"
        console.print(f"  [red]✗ {state.error}[/red]")

    return state


def node_policy(state: SREState) -> SREState:
    """Validate selected action through OPA."""
    console.print(f"[bold cyan]🛡️  Policy check:[/bold cyan] OPA evaluating action")

    action = state.decision.selected_action

    # Find best real action to validate (skip alert_human)
    real_action = action
    if action.action_type == ActionType.ALERT_HUMAN:
        candidates = [
            a for a in state.decision.proposed_actions
            if a.action_type not in (ActionType.ALERT_HUMAN, ActionType.NO_ACTION)
        ]
        if candidates:
            risk_order = {"safe": 0, "low": 1, "medium": 2, "high": 3, "dangerous": 4}
            candidates.sort(key=lambda a: risk_order.get(a.risk_level.value, 99))
            real_action = candidates[0]

    console.print(
        f"  [dim]Evaluating: {real_action.action_type.value} "
        f"(risk={real_action.risk_level.value}, confidence={state.diagnosis.confidence:.0%}, "
        f"env={ENVIRONMENT})[/dim]"
    )

    policy = evaluate(
        action_type=real_action.action_type.value,
        risk_level=real_action.risk_level.value,
        confidence=state.diagnosis.confidence,
        environment=ENVIRONMENT,
        namespace=state.current_event.namespace,
        pod=state.current_event.pod,
        approved_for_execution=True  # Let OPA decide based on risk/env/confidence alone
    )

    state.policy = policy
    state.decision.selected_action = real_action

    verdict_color = "green" if policy.verdict == "ALLOW" else "red"
    console.print(f"  [{verdict_color}]{policy.verdict}[/{verdict_color}]", end="")
    if policy.violations:
        console.print(f" — {policy.violations[0]}")
    else:
        console.print()

    return state


def node_execute(state: SREState) -> SREState:
    """Execute the approved action against the cluster."""
    action = state.decision.selected_action

    console.print(
        f"[bold cyan]⚙️  Executing:[/bold cyan] "
        f"{action.action_type.value} "
        f"[dim]({action.kubectl_command})[/dim]"
    )

    pod  = state.current_event.pod
    ns   = state.current_event.namespace
    cmd  = action.kubectl_command or ""

    from agents.executor.agent import (
        delete_pod, restart_deployment, scale_deployment,
        update_resources, resolve_deployment_name,
        ExecutionResult, ExecutionStatus
    )

    dry = state.dry_run

    try:
        if action.action_type.value == "delete_pod":
            result = delete_pod(ns, pod, dry_run=dry)
        elif action.action_type.value == "restart_deployment":
            dep = resolve_deployment_name(ns, pod)
            console.print(f"  [dim]Resolved deployment: {dep}[/dim]")
            result = restart_deployment(ns, dep, dry_run=dry)
        elif action.action_type.value == "scale_deployment":
            dep = resolve_deployment_name(ns, pod)
            console.print(f"  [dim]Resolved deployment: {dep}[/dim]")
            result = scale_deployment(ns, dep, 0, dry_run=dry)
        elif action.action_type.value == "update_resources":
            dep = resolve_deployment_name(ns, pod)
            console.print(f"  [dim]Resolved deployment: {dep}[/dim]")
            result = update_resources(ns, dep, dry_run=dry)
        else:
            result = ExecutionResult(
                event_id=state.current_event.id,
                action_type=action.action_type.value,
                kubectl_command=cmd,
                status=ExecutionStatus.SKIPPED,
                message=f"No handler for {action.action_type.value}",
                timestamp=datetime.now(timezone.utc),
                duration_seconds=0,
                dry_run=dry
            )

        result.event_id = state.current_event.id
        state.execution = result

        color = "green" if result.status.value in ("success", "dry_run") else "red"
        console.print(f"  [{color}]{result.status.value.upper()}[/{color}] — {result.message}")

    except Exception as e:
        state.error = f"Execution failed: {e}"
        console.print(f"  [red]✗ {state.error}[/red]")

    return state


def node_store(state: SREState) -> SREState:
    """Persist the full incident to memory (Redis + ChromaDB)."""
    console.print("[bold cyan]💾 Storing:[/bold cyan] saving incident to memory")

    try:
        incident_id = record_full_incident(
            state.current_event,
            state.diagnosis,
            state.decision,
            state.execution
        )
        state.incident_id = incident_id
        state.completed = True
        console.print(f"  [green]✓ Incident {incident_id[:8]} stored[/green]")
    except Exception as e:
        state.error = f"Memory store failed: {e}"
        console.print(f"  [red]✗ {state.error}[/red]")

    return state


def node_skip(state: SREState) -> SREState:
    """No-op terminal node for skipped/blocked paths."""
    if state.skip_reason:
        console.print(f"[dim]⏭  Skipped: {state.skip_reason}[/dim]")
    return state


def node_alert_human(state: SREState) -> SREState:
    """Policy blocked — escalate to human."""
    console.print("[bold red]🚨 ESCALATING TO HUMAN[/bold red]")
    if state.policy and state.policy.violations:
        for v in state.policy.violations:
            console.print(f"  [red]• {v}[/red]")
    console.print(
        f"  [yellow]Manual action required for: "
        f"{state.current_event.pod} in {state.current_event.namespace}[/yellow]"
    )
    state.completed = True
    return state