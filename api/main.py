import os
import json
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
console = Console()

# ── Request / Response models ─────────────────────────────────────────────────

class RunPipelineRequest(BaseModel):
    dry_run: bool = True
    namespace: Optional[str] = "default"

class PipelineResponse(BaseModel):
    run_id: str
    status: str
    message: str
    timestamp: str

class IncidentSummary(BaseModel):
    incident_id: str
    timestamp: str
    issue: str
    action_taken: str
    outcome: str
    pod: str
    namespace: str

class PolicyCheckRequest(BaseModel):
    action_type: str
    risk_level: str
    confidence: float
    environment: str
    namespace: str
    pod: Optional[str] = None

class HealthResponse(BaseModel):
    status: str
    prometheus: str
    redis: str
    vector_db: str
    timestamp: str


# ── Background job store (Redis-backed for persistence across restarts) ───────

from memory.redis_client import (
    store_pipeline_run, get_pipeline_run, list_pipeline_runs
)

_jobs: dict[str, dict] = {}  # write-through cache for in-flight runs


def _save_run(run_id: str):
    """Persist current run state to Redis."""
    if run_id in _jobs:
        store_pipeline_run(run_id, _jobs[run_id])


# ── App lifecycle ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    console.print("[bold cyan]🚀 Autonomous SRE API starting...[/bold cyan]")
    yield
    console.print("[dim]API shutting down[/dim]")


app = FastAPI(
    title="Autonomous SRE API",
    description="Enterprise Autonomous SRE System — Explainable, Policy-Aware, Self-Learning AI for Kubernetes Operations",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health():
    """Check health of all system components."""
    import redis as redis_lib
    from memory.vector_store import get_collection_size

    # Prometheus
    try:
        from agents.monitor.prometheus_client import query
        r = query("up")
        prom_status = "ok" if r else "no_targets"
    except Exception:
        prom_status = "unreachable"

    # Redis
    try:
        r = redis_lib.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
        r.ping()
        redis_status = "ok"
    except Exception:
        redis_status = "unreachable"

    # ChromaDB
    try:
        count = get_collection_size()
        vdb_status = f"ok ({count} incidents)"
    except Exception:
        vdb_status = "unreachable"

    overall = "healthy" if all(
        s.startswith("ok") for s in [prom_status, redis_status, vdb_status]
    ) else "degraded"

    return HealthResponse(
        status=overall,
        prometheus=prom_status,
        redis=redis_status,
        vector_db=vdb_status,
        timestamp=datetime.now(timezone.utc).isoformat()
    )


# ── Monitoring ────────────────────────────────────────────────────────────────

@app.get("/api/v1/anomalies", tags=["Monitoring"])
async def get_anomalies():
    """Return currently detected anomalies from Prometheus."""
    from agents.monitor.detector import run_all_detectors
    events = run_all_detectors()
    return {
        "count": len(events),
        "anomalies": [e.model_dump(mode="json") for e in events],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ── Pipeline ──────────────────────────────────────────────────────────────────

def _run_pipeline_sync(run_id: str, dry_run: bool):
    """Runs in background thread."""
    try:
        _jobs[run_id]["status"] = "running"
        _save_run(run_id)

        from agents.monitor.detector import run_all_detectors
        from orchestrator.state import SREState
        from orchestrator.graph import sre_graph

        events = run_all_detectors()

        if not events:
            _jobs[run_id].update({
                "status": "completed",
                "message": "No anomalies detected",
                "events_found": 0
            })
            _save_run(run_id)
            return

        state = SREState(events=events, dry_run=dry_run)
        final = sre_graph.invoke(state)

        incident_id = final.get("incident_id", "")
        completed = final.get("completed", False)
        escalated = completed and not incident_id
        skip_reason = final.get("skip_reason", "")

        if skip_reason:
            message = f"Skipped: {skip_reason}"
        elif escalated:
            message = "Escalated to human review"
        elif incident_id:
            message = "Pipeline completed successfully"
        else:
            message = "Pipeline completed"

        _jobs[run_id].update({
            "status": "completed",
            "message": message,
            "events_found": len(events),
            "incident_id": incident_id,
            "completed": completed,
            "escalated": escalated,
            "error": final.get("error", "")
        })
        _save_run(run_id)

    except Exception as e:
        _jobs[run_id].update({
            "status": "failed",
            "message": str(e)
        })
        _save_run(run_id)


@app.post("/api/v1/pipeline/run", response_model=PipelineResponse, tags=["Pipeline"])
async def run_pipeline(req: RunPipelineRequest, background_tasks: BackgroundTasks):
    """Trigger a full SRE pipeline run asynchronously."""
    run_id = str(uuid.uuid4())[:8]
    _jobs[run_id] = {
        "run_id": run_id,
        "status": "queued",
        "message": "Pipeline queued",
        "dry_run": req.dry_run,
        "started_at": datetime.now(timezone.utc).isoformat()
    }
    _save_run(run_id)
    background_tasks.add_task(_run_pipeline_sync, run_id, req.dry_run)
    return PipelineResponse(
        run_id=run_id,
        status="queued",
        message=f"Pipeline run {run_id} queued ({'dry-run' if req.dry_run else 'live'})",
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@app.get("/api/v1/pipeline/runs/{run_id}", tags=["Pipeline"])
async def get_run_status(run_id: str):
    """Get the status of a pipeline run by ID."""
    # Check in-memory cache first (for in-flight runs), then Redis
    job = _jobs.get(run_id) or get_pipeline_run(run_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return job


@app.get("/api/v1/pipeline/runs", tags=["Pipeline"])
async def list_runs():
    """List all pipeline runs (persisted in Redis)."""
    runs = list_pipeline_runs(limit=50)
    return {
        "count": len(runs),
        "runs": runs
    }


# ── Incidents ─────────────────────────────────────────────────────────────────

@app.get("/api/v1/incidents", tags=["Incidents"])
async def list_incidents():
    """Return all stored incidents from vector DB metadata."""
    from memory.vector_store import _get_collection
    try:
        col = _get_collection()
        results = col.get(include=["metadatas"])
        incidents = []
        for i, meta in enumerate(results["metadatas"]):
            incidents.append({
                "incident_id": results["ids"][i],
                "issue":        meta.get("issue", "N/A"),
                "action_taken": meta.get("action_taken", "N/A"),
                "outcome":      meta.get("outcome", "N/A"),
                "pod":          meta.get("pod", "N/A"),
                "namespace":    meta.get("namespace", "N/A"),
            })
        return {"count": len(incidents), "incidents": incidents}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/incidents/similar", tags=["Incidents"])
async def find_similar(anomaly_type: str, issue: str, root_cause: str = ""):
    """Find past incidents similar to a given description."""
    from memory.vector_store import query_similar_incidents
    similar = query_similar_incidents(anomaly_type, issue, root_cause)
    return {"count": len(similar), "results": similar}


# ── Policy ────────────────────────────────────────────────────────────────────

@app.post("/api/v1/policy/check", tags=["Policy"])
async def check_policy(req: PolicyCheckRequest):
    """Evaluate an action against the OPA policy engine."""
    from policy.opa_client import evaluate
    result = evaluate(
        action_type=req.action_type,
        risk_level=req.risk_level,
        confidence=req.confidence,
        environment=req.environment,
        namespace=req.namespace,
        pod=req.pod
    )
    return {
        "verdict":    result.verdict,
        "allowed":    result.allowed,
        "denied":     result.denied,
        "violations": result.violations,
        "input":      result.input_document
    }


# ── Cluster ───────────────────────────────────────────────────────────────────

@app.get("/api/v1/cluster/pods", tags=["Cluster"])
async def list_pods(namespace: str = "default"):
    """List pods in a namespace with their status."""
    from kubernetes import client, config
    try:
        try:
            config.load_kube_config()
        except Exception:
            config.load_incluster_config()

        v1 = client.CoreV1Api()
        pods = v1.list_namespaced_pod(namespace)
        return {
            "namespace": namespace,
            "count": len(pods.items),
            "pods": [
                {
                    "name":     p.metadata.name,
                    "status":   p.status.phase,
                    "ready":    all(c.ready for c in (p.status.container_statuses or [])),
                    "restarts": sum(c.restart_count for c in (p.status.container_statuses or [])),
                    "node":     p.spec.node_name,
                    "age":      str(datetime.now(timezone.utc) - p.metadata.creation_timestamp.replace(tzinfo=timezone.utc))
                }
                for p in pods.items
            ]
        }
    except Exception as e:
        return {
            "namespace": namespace,
            "count": 0,
            "pods": [],
            "error": f"Could not connect to cluster: {str(e)}"
        }