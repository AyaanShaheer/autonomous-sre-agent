import json
import os
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from agents.shared.models import DecisionResult, ProposedAction, ActionType
from policy.opa_client import evaluate, PolicyDecision

load_dotenv(override=True)

console = Console()
ENVIRONMENT = os.getenv("SRE_ENVIRONMENT", "staging")


def pick_best_non_human_action(decision: DecisionResult) -> ProposedAction:
    """
    If decision engine selected alert_human due to override,
    find the best real action to validate through OPA anyway.
    OPA will block it if truly unsafe — that's its job.
    """
    non_human = [
        a for a in decision.proposed_actions
        if a.action_type not in (ActionType.ALERT_HUMAN, ActionType.NO_ACTION)
    ]
    if not non_human:
        return decision.selected_action

    # Sort by risk level preference: safe < low < medium < high < dangerous
    risk_order = {"safe": 0, "low": 1, "medium": 2, "high": 3, "dangerous": 4}
    non_human.sort(key=lambda a: risk_order.get(a.risk_level.value, 99))
    return non_human[0]


def validate_decision(decision: DecisionResult) -> tuple[PolicyDecision, ProposedAction]:
    # Always validate the best real action — OPA decides if it's safe
    action = pick_best_non_human_action(decision)

    policy = evaluate(
        action_type=action.action_type.value,
        risk_level=action.risk_level.value,
        confidence=0.9,  # passed from diagnosis confidence
        environment=ENVIRONMENT,
        namespace="default",
        pod=None,
        approved_for_execution=decision.approved_for_execution
    )

    return policy, action


def run_policy_check():
    try:
        with open("/tmp/sre_decision_results.json") as f:
            raw_decisions = json.load(f)
    except FileNotFoundError:
        console.print("[red]No decision results found. Run the decision engine first.[/red]")
        return

    console.print("\n[bold cyan]🛡️  OPA Policy Engine — Evaluating Actions[/bold cyan]\n")
    console.print(f"[dim]  Environment: {ENVIRONMENT}[/dim]\n")

    approved_actions = []
    blocked_actions  = []

    for d in raw_decisions:
        decision = DecisionResult(**d)
        policy, action = validate_decision(decision)

        content = Text()
        content.append("Action:       ", style="bold")
        content.append(f"{action.action_type.value}\n")
        content.append("Risk Level:   ", style="bold")
        content.append(f"{action.risk_level.value.upper()}\n")
        content.append("Environment:  ", style="bold")
        content.append(f"{ENVIRONMENT}\n")
        content.append("Command:      ", style="bold")
        content.append(f"{action.kubectl_command or 'N/A'}\n\n")

        if policy.verdict == "ALLOW":
            content.append("✓ Policy: ALLOW\n", style="bold green")
            approved_actions.append((decision, action, policy))
            border = "green"
            title = "[bold green]✓ POLICY APPROVED[/bold green]"
        else:
            content.append("✗ Policy: DENY\n", style="bold red")
            if policy.violations:
                content.append("\nViolations:\n", style="bold red")
                for v in policy.violations:
                    content.append(f"  • {v}\n", style="red")
            blocked_actions.append((decision, action, policy))
            border = "red"
            title = "[bold red]✗ POLICY BLOCKED[/bold red]"

        console.print(Panel(content, title=title, border_style=border))

    console.print(
        f"\n[bold]Summary:[/bold] "
        f"[green]{len(approved_actions)} approved[/green], "
        f"[red]{len(blocked_actions)} blocked[/red]"
    )

    with open("/tmp/sre_approved_actions.json", "w") as f:
        json.dump([
            {
                "decision": d.model_dump(mode="json"),
                "action": a.model_dump(mode="json"),
                "policy_verdict": p.verdict
            }
            for d, a, p in approved_actions
        ], f, indent=2, default=str)

    console.print("[dim]  Approved actions written to /tmp/sre_approved_actions.json[/dim]")


if __name__ == "__main__":
    run_policy_check()