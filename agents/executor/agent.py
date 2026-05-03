import os
import json
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel
from kubernetes import client, config
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
console = Console()


class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    FAILED  = "failed"
    SKIPPED = "skipped"
    DRY_RUN = "dry_run"


class ExecutionResult(BaseModel):
    event_id: str
    action_type: str
    kubectl_command: Optional[str]
    status: ExecutionStatus
    message: str
    timestamp: datetime
    duration_seconds: float
    dry_run: bool


def _load_k8s():
    try:
        config.load_kube_config()
    except Exception:
        config.load_incluster_config()


def delete_pod(namespace: str, pod_name: str, dry_run: bool = False) -> ExecutionResult:
    start = time.time()
    _load_k8s()
    v1 = client.CoreV1Api()

    try:
        if not dry_run:
            v1.delete_namespaced_pod(
                name=pod_name,
                namespace=namespace,
                body=client.V1DeleteOptions(grace_period_seconds=0)
            )
            status  = ExecutionStatus.SUCCESS
            message = f"Pod '{pod_name}' deleted from namespace '{namespace}'"
        else:
            status  = ExecutionStatus.DRY_RUN
            message = f"[DRY RUN] Would delete pod '{pod_name}' in namespace '{namespace}'"

    except client.exceptions.ApiException as e:
        status  = ExecutionStatus.FAILED
        message = f"API error deleting pod: {e.reason} (status {e.status})"

    return ExecutionResult(
        event_id="",
        action_type="delete_pod",
        kubectl_command=f"kubectl delete pod {pod_name} -n {namespace}",
        status=status,
        message=message,
        timestamp=datetime.now(timezone.utc),
        duration_seconds=round(time.time() - start, 3),
        dry_run=dry_run
    )


def restart_deployment(namespace: str, deployment_name: str, dry_run: bool = False) -> ExecutionResult:
    start = time.time()
    _load_k8s()
    apps_v1 = client.AppsV1Api()

    try:
        if not dry_run:
            # Patch annotation to trigger rolling restart
            patch = {
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {
                                "kubectl.kubernetes.io/restartedAt": datetime.now(timezone.utc).isoformat()
                            }
                        }
                    }
                }
            }
            apps_v1.patch_namespaced_deployment(
                name=deployment_name,
                namespace=namespace,
                body=patch
            )
            status  = ExecutionStatus.SUCCESS
            message = f"Deployment '{deployment_name}' rolling restart triggered"
        else:
            status  = ExecutionStatus.DRY_RUN
            message = f"[DRY RUN] Would restart deployment '{deployment_name}' in namespace '{namespace}'"

    except client.exceptions.ApiException as e:
        status  = ExecutionStatus.FAILED
        message = f"API error restarting deployment: {e.reason} (status {e.status})"

    return ExecutionResult(
        event_id="",
        action_type="restart_deployment",
        kubectl_command=f"kubectl rollout restart deployment/{deployment_name} -n {namespace}",
        status=status,
        message=message,
        timestamp=datetime.now(timezone.utc),
        duration_seconds=round(time.time() - start, 3),
        dry_run=dry_run
    )


def scale_deployment(namespace: str, deployment_name: str, replicas: int, dry_run: bool = False) -> ExecutionResult:
    start = time.time()
    _load_k8s()
    apps_v1 = client.AppsV1Api()

    try:
        if not dry_run:
            apps_v1.patch_namespaced_deployment_scale(
                name=deployment_name,
                namespace=namespace,
                body={"spec": {"replicas": replicas}}
            )
            status  = ExecutionStatus.SUCCESS
            message = f"Deployment '{deployment_name}' scaled to {replicas} replicas"
        else:
            status  = ExecutionStatus.DRY_RUN
            message = f"[DRY RUN] Would scale deployment '{deployment_name}' to {replicas} replicas"

    except client.exceptions.ApiException as e:
        status  = ExecutionStatus.FAILED
        message = f"API error scaling deployment: {e.reason} (status {e.status})"

    return ExecutionResult(
        event_id="",
        action_type="scale_deployment",
        kubectl_command=f"kubectl scale deployment/{deployment_name} --replicas={replicas} -n {namespace}",
        status=status,
        message=message,
        timestamp=datetime.now(timezone.utc),
        duration_seconds=round(time.time() - start, 3),
        dry_run=dry_run
    )


def resolve_deployment_name(namespace: str, pod_name: str) -> str:
    """Resolve the owning deployment name from a pod name using k8s API.
    Falls back to stripping the ReplicaSet and pod hash suffixes."""
    try:
        _load_k8s()
        v1 = client.CoreV1Api()
        pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)
        # Walk ownerReferences: Pod -> ReplicaSet -> Deployment
        for owner in (pod.metadata.owner_references or []):
            if owner.kind == "ReplicaSet":
                apps_v1 = client.AppsV1Api()
                rs = apps_v1.read_namespaced_replica_set(
                    name=owner.name, namespace=namespace
                )
                for rs_owner in (rs.metadata.owner_references or []):
                    if rs_owner.kind == "Deployment":
                        return rs_owner.name
                # ReplicaSet without Deployment owner — strip hash from RS name
                parts = owner.name.rsplit("-", 1)
                return parts[0] if len(parts) > 1 else owner.name
    except Exception:
        pass
    # Fallback: strip last two hyphen-separated segments (replicaset-hash, pod-hash)
    parts = pod_name.rsplit("-", 2)
    if len(parts) >= 3:
        return "-".join(parts[:-2])
    return pod_name


def update_resources(
    namespace: str, deployment_name: str, dry_run: bool = False,
    cpu_limit: str = "500m", memory_limit: str = "512Mi"
) -> ExecutionResult:
    """Patch resource limits on a deployment's containers."""
    start = time.time()
    _load_k8s()
    apps_v1 = client.AppsV1Api()

    try:
        if not dry_run:
            patch = {
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [{
                                "name": deployment_name,
                                "resources": {
                                    "limits": {"cpu": cpu_limit, "memory": memory_limit},
                                    "requests": {"cpu": "100m", "memory": "128Mi"}
                                }
                            }]
                        }
                    }
                }
            }
            apps_v1.patch_namespaced_deployment(
                name=deployment_name,
                namespace=namespace,
                body=patch
            )
            status  = ExecutionStatus.SUCCESS
            message = f"Deployment '{deployment_name}' resources updated (cpu={cpu_limit}, mem={memory_limit})"
        else:
            status  = ExecutionStatus.DRY_RUN
            message = f"[DRY RUN] Would update resources on deployment '{deployment_name}' (cpu={cpu_limit}, mem={memory_limit})"

    except client.exceptions.ApiException as e:
        status  = ExecutionStatus.FAILED
        message = f"API error updating resources: {e.reason} (status {e.status})"

    return ExecutionResult(
        event_id="",
        action_type="update_resources",
        kubectl_command=f"kubectl set resources deployment/{deployment_name} -n {namespace} --limits=cpu={cpu_limit},memory={memory_limit}",
        status=status,
        message=message,
        timestamp=datetime.now(timezone.utc),
        duration_seconds=round(time.time() - start, 3),
        dry_run=dry_run
    )


ACTION_HANDLERS = {
    "delete_pod":          lambda ns, pod, dep, dry: delete_pod(ns, pod, dry),
    "restart_deployment":  lambda ns, pod, dep, dry: restart_deployment(ns, dep or pod, dry),
    "scale_deployment":    lambda ns, pod, dep, dry: scale_deployment(ns, dep or pod, 0, dry),
    "update_resources":    lambda ns, pod, dep, dry: update_resources(ns, dep or pod, dry),
}


def execute_approved_actions(dry_run: bool = False) -> list[ExecutionResult]:
    try:
        with open("/tmp/sre_approved_actions.json") as f:
            approved = json.load(f)
    except FileNotFoundError:
        console.print("[red]No approved actions found. Run the policy engine first.[/red]")
        return []

    if not approved:
        console.print("[yellow]No actions were approved by policy engine.[/yellow]")
        return []

    results = []

    for entry in approved:
        action   = entry["action"]
        decision = entry["decision"]

        action_type = action["action_type"]
        namespace   = decision.get("namespace", "default")
        pod         = None
        deployment  = None

        # Extract pod/deployment from kubectl command
        cmd = action.get("kubectl_command", "") or ""
        parts = cmd.split()
        if "pod" in parts:
            idx = parts.index("pod")
            if idx + 1 < len(parts):
                pod = parts[idx + 1]
        if "deployment" in cmd or "deployment/" in cmd:
            for part in parts:
                if part.startswith("deployment/"):
                    deployment = part.split("/")[1]
                elif "deployment" in parts and parts.index("deployment") + 1 < len(parts):
                    deployment = parts[parts.index("deployment") + 1]
                    break

        # Fallback: extract from event data
        if not pod:
            for evt in decision.get("proposed_actions", []):
                c = evt.get("kubectl_command") or ""
                p = [t for t in c.split() if t not in
                     ("kubectl","delete","pod","restart","rollout","scale",
                      "deployment","-n","default","--replicas=0")]
                if p:
                    pod = p[0]
                    break

        handler = ACTION_HANDLERS.get(action_type)

        if not handler:
            result = ExecutionResult(
                event_id=decision.get("event_id", ""),
                action_type=action_type,
                kubectl_command=cmd,
                status=ExecutionStatus.SKIPPED,
                message=f"No handler implemented for action type '{action_type}'",
                timestamp=datetime.now(timezone.utc),
                duration_seconds=0,
                dry_run=dry_run
            )
        else:
            console.print(f"\n[bold cyan]⚙️  Executing:[/bold cyan] {action_type}")
            console.print(f"[dim]  Command: {cmd}[/dim]")
            if dry_run:
                console.print("[yellow]  [DRY RUN MODE — no real changes][/yellow]")

            result = handler(namespace, pod, deployment, dry_run)
            result.event_id = decision.get("event_id", "")

        results.append(result)

        # Print result
        color = {
            ExecutionStatus.SUCCESS: "green",
            ExecutionStatus.FAILED:  "red",
            ExecutionStatus.SKIPPED: "yellow",
            ExecutionStatus.DRY_RUN: "cyan",
        }.get(result.status, "white")

        console.print(f"  [{color}]{result.status.upper()}[/{color}] — {result.message}")
        console.print(f"  [dim]Duration: {result.duration_seconds}s[/dim]")

    # Write execution log
    with open("/tmp/sre_execution_log.json", "w") as f:
        json.dump(
            [r.model_dump(mode="json") for r in results],
            f, indent=2, default=str
        )

    console.print("\n[dim]  Execution log written to /tmp/sre_execution_log.json[/dim]")
    return results