package sre.policy

import future.keywords.if
import future.keywords.in

# Default: deny everything, allow must be explicitly granted
default allow = false
default deny = false

# ──────────────────────────────────────────────
# ALLOW rules — safe actions always permitted
# ──────────────────────────────────────────────

allow if {
    input.action_type == "alert_human"
}

allow if {
    input.action_type == "no_action"
}

allow if {
    input.action_type == "delete_pod"
    input.environment != "production"
    input.risk_level in ["safe", "low", "medium"]
    input.confidence >= 0.6
}

allow if {
    input.action_type == "restart_deployment"
    input.environment != "production"
    input.risk_level in ["safe", "low", "medium"]
    input.confidence >= 0.6
}

allow if {
    input.action_type == "scale_deployment"
    input.environment != "production"
    input.risk_level in ["safe", "low", "medium"]
    input.confidence >= 0.6
}

allow if {
    input.action_type == "update_resources"
    input.environment != "production"
    input.risk_level in ["safe", "low", "medium"]
    input.confidence >= 0.6
}

# ──────────────────────────────────────────────
# DENY rules — always blocked regardless of allow
# ──────────────────────────────────────────────

deny if {
    input.environment == "production"
    input.action_type in ["delete_pod", "restart_deployment", "scale_deployment", "cordon_node"]
    msg := "Direct pod/deployment actions blocked in production — use human approval workflow"
}

deny if {
    input.risk_level == "dangerous"
    msg := "Dangerous risk level actions are never auto-approved"
}

deny if {
    input.risk_level == "high"
    input.environment == "production"
    msg := "High risk actions blocked in production environment"
}

deny if {
    input.confidence < 0.6
    msg := "Diagnosis confidence below minimum threshold of 60%"
}

deny if {
    input.action_type == "cordon_node"
    msg := "Node cordoning always requires human approval"
}

# ──────────────────────────────────────────────
# Violation messages — collected for audit log
# ──────────────────────────────────────────────

violation[msg] if {
    deny
    msg := sprintf("DENIED: action=%s env=%s risk=%s confidence=%.2f",
        [input.action_type, input.environment, input.risk_level, input.confidence])
}