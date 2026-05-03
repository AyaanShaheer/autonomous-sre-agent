import subprocess
from agents.monitor.prometheus_client import query

def get_pod_logs(namespace: str, pod: str, lines: int = 50) -> str:
    """Fetch recent pod logs via kubectl."""
    try:
        result = subprocess.run(
            ["kubectl", "logs", pod, "-n", namespace,
             f"--tail={lines}", "--previous"],
            capture_output=True, text=True, timeout=10
        )
        logs = result.stdout.strip()
        if not logs:
            # Try without --previous if no previous container
            result = subprocess.run(
                ["kubectl", "logs", pod, "-n", namespace, f"--tail={lines}"],
                capture_output=True, text=True, timeout=10
            )
            logs = result.stdout.strip()
        return logs or "No logs available"
    except Exception as e:
        return f"Could not fetch logs: {e}"

def get_pod_events(namespace: str, pod: str) -> str:
    """Fetch Kubernetes events for a specific pod."""
    try:
        result = subprocess.run(
            ["kubectl", "get", "events", "-n", namespace,
             "--field-selector", f"involvedObject.name={pod}",
             "--sort-by=.lastTimestamp"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip() or "No events found"
    except Exception as e:
        return f"Could not fetch events: {e}"

def get_pod_description(namespace: str, pod: str) -> str:
    """Fetch kubectl describe output for a pod."""
    try:
        result = subprocess.run(
            ["kubectl", "describe", "pod", pod, "-n", namespace],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip() or "No description available"
    except Exception as e:
        return f"Could not describe pod: {e}"

def get_recent_cpu_memory(namespace: str, pod: str) -> dict:
    """Fetch last known CPU and memory metrics for the pod."""
    cpu_results = query(
        f'sum(rate(container_cpu_usage_seconds_total{{pod="{pod}",namespace="{namespace}",container!=""}}[5m])) * 100'
    )
    mem_results = query(
        f'sum(container_memory_working_set_bytes{{pod="{pod}",namespace="{namespace}",container!=""}}) / 1024 / 1024'
    )
    return {
        "cpu_percent": round(float(cpu_results[0]["value"][1]), 2) if cpu_results else "N/A",
        "memory_mb": round(float(mem_results[0]["value"][1]), 2) if mem_results else "N/A",
    }

def build_context(namespace: str, pod: str) -> dict:
    """Aggregate all context for a given pod."""
    return {
        "logs": get_pod_logs(namespace, pod),
        "events": get_pod_events(namespace, pod),
        "description": get_pod_description(namespace, pod),
        "metrics": get_recent_cpu_memory(namespace, pod),
    }
