import os
import json
import redis
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

_client = None

def get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379"),
            decode_responses=True
        )
    return _client


def store_incident(incident_id: str, data: dict, ttl_seconds: int = 86400):
    """Store a full incident record with 24h TTL."""
    r = get_client()
    key = f"incident:{incident_id}"
    r.setex(key, ttl_seconds, json.dumps(data, default=str))


def get_incident(incident_id: str) -> dict | None:
    r = get_client()
    raw = r.get(f"incident:{incident_id}")
    return json.loads(raw) if raw else None


def store_active_alert(pod: str, namespace: str, anomaly_type: str, ttl_seconds: int = 300):
    """Track active alerts to prevent duplicate processing within 5 min."""
    r = get_client()
    key = f"active_alert:{namespace}:{pod}:{anomaly_type}"
    r.setex(key, ttl_seconds, "1")


def is_alert_active(pod: str, namespace: str, anomaly_type: str) -> bool:
    r = get_client()
    key = f"active_alert:{namespace}:{pod}:{anomaly_type}"
    return r.exists(key) == 1


def record_execution(pod: str, namespace: str, action: str, status: str):
    """Push execution outcome to a capped list for recent history."""
    r = get_client()
    key = f"executions:{namespace}:{pod}"
    entry = json.dumps({
        "action": action,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    r.lpush(key, entry)
    r.ltrim(key, 0, 49)       # keep last 50 executions
    r.expire(key, 604800)     # 7 day TTL


def get_recent_executions(pod: str, namespace: str, limit: int = 10) -> list[dict]:
    r = get_client()
    key = f"executions:{namespace}:{pod}"
    raw_list = r.lrange(key, 0, limit - 1)
    return [json.loads(x) for x in raw_list]


def get_execution_stats(pod: str, namespace: str) -> dict:
    executions = get_recent_executions(pod, namespace, limit=50)
    if not executions:
        return {"total": 0, "success_rate": 0.0, "recurrence_count": 0}
    success = sum(1 for e in executions if e["status"] == "success")
    return {
        "total": len(executions),
        "success_rate": round(success / len(executions), 2),
        "recurrence_count": len(executions)
    }


# ── Pipeline Run Persistence ──────────────────────────────────────────────────

PIPELINE_RUNS_KEY = "pipeline:runs"     # sorted set for ordering
PIPELINE_TTL = 604800                   # 7 day TTL per run


def store_pipeline_run(run_id: str, data: dict):
    """Store a pipeline run record in Redis."""
    r = get_client()
    key = f"pipeline:run:{run_id}"
    r.setex(key, PIPELINE_TTL, json.dumps(data, default=str))
    # Add to sorted set with timestamp score for ordering
    score = datetime.now(timezone.utc).timestamp()
    r.zadd(PIPELINE_RUNS_KEY, {run_id: score})
    r.expire(PIPELINE_RUNS_KEY, PIPELINE_TTL)


def get_pipeline_run(run_id: str) -> dict | None:
    """Retrieve a single pipeline run."""
    r = get_client()
    raw = r.get(f"pipeline:run:{run_id}")
    return json.loads(raw) if raw else None


def list_pipeline_runs(limit: int = 50) -> list[dict]:
    """List recent pipeline runs, newest first."""
    r = get_client()
    run_ids = r.zrevrange(PIPELINE_RUNS_KEY, 0, limit - 1)
    runs = []
    for rid in run_ids:
        raw = r.get(f"pipeline:run:{rid}")
        if raw:
            runs.append(json.loads(raw))
    return runs