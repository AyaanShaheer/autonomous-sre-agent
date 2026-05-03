import subprocess
import json
import os
from dataclasses import dataclass

POLICY_PATH = os.path.join(os.path.dirname(__file__), "opa", "sre_policy.rego")

@dataclass
class PolicyDecision:
    allowed: bool
    denied: bool
    violations: list[str]
    input_document: dict

    @property
    def verdict(self) -> str:
        if self.denied or not self.allowed:
            return "DENY"
        return "ALLOW"


def evaluate(
    action_type: str,
    risk_level: str,
    confidence: float,
    environment: str,
    namespace: str,
    pod: str | None = None,
    approved_for_execution: bool = True,
    extra: dict | None = None
) -> PolicyDecision:
    """
    Evaluate an action against OPA policy.
    Returns PolicyDecision with verdict, violations.
    """

    input_doc = {
        "action_type": action_type,
        "risk_level": risk_level,
        "confidence": confidence,
        "environment": environment,
        "namespace": namespace,
        "pod": pod or "",
        "approved_for_execution": approved_for_execution,
        **(extra or {})
    }

    # Run OPA eval for allow
    allow_result = _run_opa("data.sre.policy.allow", input_doc)
    deny_result  = _run_opa("data.sre.policy.deny", input_doc)
    violations   = _run_opa_set("data.sre.policy.violation", input_doc)

    return PolicyDecision(
        allowed=allow_result,
        denied=deny_result,
        violations=violations,
        input_document=input_doc
    )


def _run_opa(query: str, input_doc: dict) -> bool:
    try:
        result = subprocess.run(
            ["opa", "eval",
             "--data", POLICY_PATH,
             "--input", "/dev/stdin",
             "--format", "raw",
             query],
            input=json.dumps(input_doc),
            capture_output=True,
            text=True,
            timeout=5
        )
        output = result.stdout.strip()
        return output == "true"
    except Exception as e:
        print(f"OPA eval error: {e}")
        return False


def _run_opa_set(query: str, input_doc: dict) -> list[str]:
    try:
        result = subprocess.run(
            ["opa", "eval",
             "--data", POLICY_PATH,
             "--input", "/dev/stdin",
             "--format", "json",
             query],
            input=json.dumps(input_doc),
            capture_output=True,
            text=True,
            timeout=5
        )
        data = json.loads(result.stdout)
        values = data.get("result", [{}])[0].get("expressions", [{}])[0].get("value", [])
        if isinstance(values, list):
            return values
        if isinstance(values, set):
            return list(values)
        return []
    except Exception:
        return []