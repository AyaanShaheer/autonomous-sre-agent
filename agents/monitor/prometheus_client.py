import requests
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")

def query(promql: str) -> list[dict]:
    """Run an instant PromQL query, return list of result items."""
    try:
        resp = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": promql},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        if data["status"] == "success":
            return data["data"]["result"]
        return []
    except Exception as e:
        print(f"[Prometheus] Query failed: {e}")
        return []

def query_value(promql: str) -> Optional[float]:
    """Return the first scalar value from a PromQL query."""
    results = query(promql)
    if results:
        return float(results[0]["value"][1])
    return None
