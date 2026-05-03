from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from agents.diagnose.agent import run_diagnosis_on_latest_events

console = Console()


def main():
    console.print("\n[bold cyan]🧠 SRE Diagnosis Agent — Running[/bold cyan]\n")
    results = run_diagnosis_on_latest_events()

    for r in results:
        confidence_color = (
            "green" if r.confidence >= 0.8
            else "yellow" if r.confidence >= 0.6
            else "red"
        )

        content = Text()
        content.append("📋 Issue:        ", style="bold")
        content.append(f"{r.issue}\n")
        content.append("🔍 Root Cause:   ", style="bold")
        content.append(f"{r.root_cause}\n\n")
        content.append("🎯 Confidence:   ", style="bold")
        content.append(f"{r.confidence:.0%}\n", style=confidence_color)
        content.append("⚠️  Severity:     ", style="bold")
        content.append(f"{r.severity_assessment.upper()}\n")
        content.append("👤 Human Review: ", style="bold")
        content.append(f"{'YES ⚠️' if r.requires_human_review else 'No'}\n\n")

        content.append("⚡ Immediate Actions:\n", style="bold yellow")
        for i, action in enumerate(r.immediate_actions, 1):
            content.append(f"  {i}. {action}\n")

        content.append("\n🔧 Long-term Recommendations:\n", style="bold blue")
        for rec in r.long_term_recommendations:
            content.append(f"  • {rec}\n")

        content.append("\n💭 Reasoning:\n", style="bold dim")
        content.append(f"{r.reasoning}\n", style="dim")

        console.print(Panel(
            content,
            title=f"[bold red]Event {r.event_id[:8]}[/bold red]",
            border_style="cyan"
        ))


if __name__ == "__main__":
    main()