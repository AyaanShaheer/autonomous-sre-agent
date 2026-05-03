from langgraph.graph import StateGraph, END
from orchestrator.state import SREState
from orchestrator.nodes import (
    node_triage, node_diagnose, node_decide,
    node_policy, node_execute, node_store,
    node_skip, node_alert_human
)


def route_after_triage(state: SREState) -> str:
    if state.skip_reason or not state.current_event:
        return "skip"
    return "diagnose"


def route_after_diagnose(state: SREState) -> str:
    if state.error:
        return "skip"
    return "decide"


def route_after_decide(state: SREState) -> str:
    if state.error:
        return "skip"
    return "policy"


def route_after_policy(state: SREState) -> str:
    if state.policy and state.policy.verdict == "ALLOW":
        return "execute"
    return "alert_human"


def route_after_execute(state: SREState) -> str:
    if state.error:
        return "skip"
    return "store"


def build_graph() -> StateGraph:
    graph = StateGraph(SREState)

    # Register nodes
    graph.add_node("triage",       node_triage)
    graph.add_node("diagnose",     node_diagnose)
    graph.add_node("decide",       node_decide)
    graph.add_node("policy",       node_policy)
    graph.add_node("execute",      node_execute)
    graph.add_node("store",        node_store)
    graph.add_node("skip",         node_skip)
    graph.add_node("alert_human",  node_alert_human)

    # Entry point
    graph.set_entry_point("triage")

    # Conditional edges
    graph.add_conditional_edges("triage",   route_after_triage,   {"skip": "skip", "diagnose": "diagnose"})
    graph.add_conditional_edges("diagnose", route_after_diagnose,  {"skip": "skip", "decide": "decide"})
    graph.add_conditional_edges("decide",   route_after_decide,    {"skip": "skip", "policy": "policy"})
    graph.add_conditional_edges("policy",   route_after_policy,    {"execute": "execute", "alert_human": "alert_human"})
    graph.add_conditional_edges("execute",  route_after_execute,   {"skip": "skip", "store": "store"})

    # Terminal edges
    graph.add_edge("store",        END)
    graph.add_edge("skip",         END)
    graph.add_edge("alert_human",  END)

    return graph.compile()


# Singleton
sre_graph = build_graph()