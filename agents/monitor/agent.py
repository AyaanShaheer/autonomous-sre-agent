import time
import os
import json
from rich.console import Console
from rich.table import Table
from rich import box
from dotenv import load_dotenv
from agents.monitor.detector import run_all_detectors
from agents.shared.models import Severity

load_dotenv()
console = Console()
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", 30))

SEVERITY_COLORS = {
    Severity.LOW:      "green",
    Severity.MEDIUM:   "yellow",
    Severity.HIGH:     "orange1",
    Severity.CRITICAL: "red",
}

def print_events(events):
    if not events:
        console.print("[dim]  ✓ No anomalies detected[/dim]")
        return

    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold cyan")
    table.add_column("Severity", style="bold", width=10)
    table.add_column("Type", width=20)
    table.add_column("Namespace", width=12)
    table.add_column("Pod", width=35)
    table.add_column("Message", width=60)

    for e in events:
        color = SEVERITY_COLORS.get(e.severity, "white")
        table.add_row(
            f"[{color}]{e.severity.upper()}[/{color}]",
            e.anomaly_type.value,
            e.namespace,
            e.pod or "-",
            e.message
        )
    console.print(table)

def run():
    console.print("[bold cyan]🤖 Autonomous SRE — Monitoring Agent Started[/bold cyan]")
    console.print(f"[dim]  Prometheus: {os.getenv('PROMETHEUS_URL')}[/dim]")
    console.print(f"[dim]  Poll interval: {POLL_INTERVAL}s[/dim]\n")

    while True:
        console.rule(f"[dim]Poll @ {__import__('datetime').datetime.now().strftime('%H:%M:%S')}[/dim]")
        try:
            events = run_all_detectors()
            print_events(events)

            # Write latest events to a JSON file for other agents to consume
            with open("/tmp/sre_anomaly_events.json", "w") as f:
                json.dump([e.model_dump(mode="json") for e in events], f, indent=2, default=str)

        except Exception as ex:
            console.print(f"[red]  ✗ Detector error: {ex}[/red]")

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run()
