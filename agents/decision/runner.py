from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from agents.decision.agent import run_decision_on_latest

console = Console()

RISK_COLORS = {
    "safe":      "green",
    "low":       "cyan",
    "medium":    "yellow",
    "high":      "orange1",
    "dangerous": "red",
}


def main():
    console.print("\n[bold cyan]⚖️  SRE Decision Engine — Running[/bold cyan]\n")
    results = run_decision_on_latest()

    for r in results:
        # Actions table
        table = Table(box=box.SIMPLE_HEAVY, header_style="bold cyan", show_header=True)
        table.add_column("#", width=3)
        table.add_column("Action", width=22)
        table.add_column("Risk", width=10)
        table.add_column("Downtime", width=10)
        table.add_column("Reversible", width=10)
        table.add_column("Command", width=55)

        for i, action in enumerate(r.proposed_actions):
            color = RISK_COLORS.get(action.risk_level.value, "white")
            is_selected = action == r.selected_action
            prefix = "→ " if is_selected else "  "
            style = "bold" if is_selected else ""
            table.add_row(
                f"{prefix}{i}",
                f"[{style}]{action.action_type.value}[/{style}]" if style else action.action_type.value,
                f"[{color}]{action.risk_level.value.upper()}[/{color}]",
                f"{action.estimated_downtime_seconds}s",
                "✓" if action.reversible else "✗",
                action.kubectl_command or "—"
            )

        # Decision summary
        approved_str = (
            "[bold green]✓ APPROVED FOR EXECUTION[/bold green]"
            if r.approved_for_execution
            else "[bold red]✗ REQUIRES HUMAN APPROVAL[/bold red]"
        )

        content = Text()
        content.append("Selected Action:   ", style="bold")
        content.append(f"{r.selected_action.action_type.value}\n")
        content.append("Command:           ", style="bold")
        content.append(f"{r.selected_action.kubectl_command or 'N/A'}\n")
        content.append("Risk Level:        ", style="bold")
        rc = RISK_COLORS.get(r.selected_action.risk_level.value, "white")
        content.append(f"{r.selected_action.risk_level.value.upper()}\n", style=rc)
        content.append("Rationale:         ", style="bold")
        content.append(f"{r.selected_action.rationale}\n\n")
        content.append("Selection Reason:  ", style="bold dim")
        content.append(f"{r.selection_reasoning}\n\n", style="dim")
        if r.override_reason:
            content.append("⚠️  Override:        ", style="bold yellow")
            content.append(f"{r.override_reason}\n\n", style="yellow")

        console.print(table)
        console.print(Panel(
            content,
            title=approved_str,
            border_style="green" if r.approved_for_execution else "red"
        ))


if __name__ == "__main__":
    main()