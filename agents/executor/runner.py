import sys
from rich.console import Console
from agents.executor.agent import execute_approved_actions

console = Console()


def main():
    dry_run = "--dry-run" in sys.argv

    console.print("\n[bold cyan]⚙️  SRE Action Executor[/bold cyan]")
    if dry_run:
        console.print("[bold yellow]  Mode: DRY RUN — no real changes will be made[/bold yellow]\n")
    else:
        console.print("[bold red]  Mode: LIVE — actions will be executed against the cluster[/bold red]\n")

    results = execute_approved_actions(dry_run=dry_run)

    success = sum(1 for r in results if r.status.value == "success")
    failed  = sum(1 for r in results if r.status.value == "failed")
    skipped = sum(1 for r in results if r.status.value in ("skipped", "dry_run"))

    console.print(
        f"\n[bold]Execution Summary:[/bold] "
        f"[green]{success} succeeded[/green]  "
        f"[red]{failed} failed[/red]  "
        f"[yellow]{skipped} skipped/dry-run[/yellow]"
    )


if __name__ == "__main__":
    main()