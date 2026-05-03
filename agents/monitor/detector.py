import uuid
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from agents.monitor.prometheus_client import query
from agents.shared.models import AnomalyEvent, AnomalyType, Severity

load_dotenv()

CPU_THRESHOLD    = float(os.getenv("CPU_THRESHOLD_PERCENT", 80))
MEMORY_THRESHOLD = float(os.getenv("MEMORY_THRESHOLD_PERCENT", 85))
RESTART_THRESHOLD = int(os.getenv("RESTART_THRESHOLD", 3))

def _make_event(anomaly_type, severity, namespace, metric_value, threshold, message,
                pod=None, deployment=None, node=None, raw_labels=None):
    return AnomalyEvent(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        anomaly_type=anomaly_type,
        severity=severity,
        namespace=namespace,
        pod=pod,
        deployment=deployment,
        node=node,
        metric_value=metric_value,
        threshold=threshold,
        message=message,
        raw_labels=raw_labels or {}
    )

def detect_high_cpu() -> list[AnomalyEvent]:
    events = []
    results = query(
        'sum by (namespace, pod) ('
        '  rate(container_cpu_usage_seconds_total{container!=""}[2m])'
        ') * 100'
    )
    for r in results:
        val = float(r["value"][1])
        if val > CPU_THRESHOLD:
            labels = r["metric"]
            severity = Severity.CRITICAL if val > 95 else Severity.HIGH
            events.append(_make_event(
                AnomalyType.HIGH_CPU, severity,
                namespace=labels.get("namespace", "unknown"),
                metric_value=round(val, 2),
                threshold=CPU_THRESHOLD,
                message=f"Pod {labels.get('pod')} CPU at {val:.1f}% (threshold: {CPU_THRESHOLD}%)",
                pod=labels.get("pod"),
                raw_labels=labels
            ))
    return events

def detect_high_memory() -> list[AnomalyEvent]:
    events = []
    results = query(
        'sum by (namespace, pod) (container_memory_working_set_bytes{container!=""}) '
        '/ sum by (namespace, pod) (kube_pod_container_resource_limits{resource="memory"}) * 100'
    )
    for r in results:
        try:
            val = float(r["value"][1])
        except (ValueError, ZeroDivisionError):
            continue
        if val > MEMORY_THRESHOLD:
            labels = r["metric"]
            severity = Severity.CRITICAL if val > 95 else Severity.HIGH
            events.append(_make_event(
                AnomalyType.HIGH_MEMORY, severity,
                namespace=labels.get("namespace", "unknown"),
                metric_value=round(val, 2),
                threshold=MEMORY_THRESHOLD,
                message=f"Pod {labels.get('pod')} memory at {val:.1f}% of limit (threshold: {MEMORY_THRESHOLD}%)",
                pod=labels.get("pod"),
                raw_labels=labels
            ))
    return events

def detect_crash_loops() -> list[AnomalyEvent]:
    events = []
    results = query(
        'kube_pod_container_status_waiting_reason{reason="CrashLoopBackOff"} == 1'
    )
    for r in results:
        labels = r["metric"]
        events.append(_make_event(
            AnomalyType.POD_CRASH_LOOP, Severity.CRITICAL,
            namespace=labels.get("namespace", "unknown"),
            metric_value=1.0,
            threshold=0.0,
            message=f"Pod {labels.get('pod')} is in CrashLoopBackOff",
            pod=labels.get("pod"),
            raw_labels=labels
        ))
    return events

def detect_high_restarts() -> list[AnomalyEvent]:
    events = []
    results = query(
        f'kube_pod_container_status_restarts_total > {RESTART_THRESHOLD}'
    )
    for r in results:
        val = float(r["value"][1])
        labels = r["metric"]
        events.append(_make_event(
            AnomalyType.HIGH_RESTART_COUNT, Severity.HIGH,
            namespace=labels.get("namespace", "unknown"),
            metric_value=val,
            threshold=RESTART_THRESHOLD,
            message=f"Pod {labels.get('pod')} has restarted {int(val)} times",
            pod=labels.get("pod"),
            raw_labels=labels
        ))
    return events

def run_all_detectors() -> list[AnomalyEvent]:
    events = []
    events.extend(detect_high_cpu())
    events.extend(detect_high_memory())
    events.extend(detect_crash_loops())
    events.extend(detect_high_restarts())
    return events
