import json
import sys
import time
from rich.console import Console
from rich.rule import Rule
from agents.shared.models import AnomalyEvent
from agents.monitor.detector import run_all_detectors
from orchestrator.state import SREState
from orchestrator.graph import sre_graph

console = Console()


def run_once(dry_run: bool = False):
    console.print(Rule("[bold cyan]🤖 Autonomous SRE — Full Pipeline Run[/bold cyan]"))

    # Step 1: detect
    console.print("\n[bold cyan]📡 Monitoring:[/bold cyan] querying Prometheus...")
    events = run_all_detectors()

    if not events:
        console.print("  [dim]✓ No anomalies detected[/dim]")
        return

    console.print(f"  Found [red]{len(events)}[/red] anomaly event(s)")

    # Step 2: run graph
    initial_state = SREState(events=events, dry_run=dry_run)
    final_state = sre_graph.invoke(initial_state)

    # Summary
    console.print()
    console.rule("[dim]Pipeline Complete[/dim]")

    if final_state.get("completed"):
        incident_id = final_state.get("incident_id", "")
        if incident_id:
            console.print(f"\n[bold green]✓ Incident resolved:[/bold green] {incident_id[:8]}")
        else:
            console.print(f"\n[bold yellow]⚠ Escalated to human review[/bold yellow]")
    elif final_state.get("skip_reason"):
        console.print(f"\n[dim]Skipped: {final_state.get('skip_reason')}[/dim]")

    if final_state.get("error"):
        console.print(f"\n[red]Error: {final_state.get('error')}[/red]")


def run_loop(interval: int = 30, dry_run: bool = False):
    console.print(f"[bold cyan]🔁 Starting continuous SRE loop (interval: {interval}s)[/bold cyan]")
    console.print(f"[dim]  Mode: {'DRY RUN' if dry_run else 'LIVE'}[/dim]\n")

    while True:
        try:
            run_once(dry_run=dry_run)
        except KeyboardInterrupt:
            console.print("\n[yellow]Stopped by user[/yellow]")
            break
        except Exception as e:
            console.print(f"[red]Loop error: {e}[/red]")

        time.sleep(interval)


if __name__ == "__main__":
    dry_run   = "--dry-run" in sys.argv
    loop_mode = "--loop" in sys.argv

    if loop_mode:
        run_loop(interval=30, dry_run=dry_run)
    else:
        run_once(dry_run=dry_run)