import json
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from agents.shared.models import AnomalyEvent, DiagnosisResult, DecisionResult
from agents.executor.agent import ExecutionResult, ExecutionStatus
from memory.coordinator import record_full_incident, get_rag_context
from memory.vector_store import get_collection_size

console = Console()


def run_memory_pipeline():
    console.print("\n[bold cyan]🧠 Memory & Learning Loop — Running[/bold cyan]\n")

    # Load all pipeline outputs
    try:
        with open("/tmp/sre_anomaly_events.json") as f:
            raw_events = json.load(f)
        with open("/tmp/sre_diagnosis_results.json") as f:
            raw_diagnoses = json.load(f)
        with open("/tmp/sre_decision_results.json") as f:
            raw_decisions = json.load(f)
        with open("/tmp/sre_execution_log.json") as f:
            raw_executions = json.load(f)
    except FileNotFoundError as e:
        console.print(f"[red]Missing file: {e}[/red]")
        return

    # Use first available of each (for this demo)
    event     = AnomalyEvent(**raw_events[0])
    diagnosis = DiagnosisResult(**raw_diagnoses[0])
    decision  = DecisionResult(**raw_decisions[0])
    execution = ExecutionResult(**raw_executions[0])

    # Store the full incident
    console.print("📥 Storing incident to Redis + ChromaDB...")
    incident_id = record_full_incident(event, diagnosis, decision, execution)
    console.print(f"  [green]✓ Incident stored:[/green] {incident_id[:8]}...")
    console.print(f"  [dim]Vector DB now has {get_collection_size()} incident(s)[/dim]\n")

    # Query similar incidents (RAG demo)
    console.print("🔍 Querying similar past incidents...")
    rag_context = get_rag_context(event, diagnosis)

    content = Text()
    content.append(rag_context)

    console.print(Panel(
        content,
        title="[bold cyan]RAG Context (injected into future LLM prompts)[/bold cyan]",
        border_style="cyan"
    ))


if __name__ == "__main__":
    run_memory_pipeline()