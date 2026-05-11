"""Node functions for the LangGraph workflow.

Each function should be small, testable, and return a partial state update. Avoid mutating the
input state in place.
"""

from __future__ import annotations

import re
from typing import Any

from .state import AgentState, ApprovalDecision, Route, make_event

# ---------------------------------------------------------------------------
# Keyword sets for routing — ordered by priority (risky first)
# ---------------------------------------------------------------------------
RISKY_KEYWORDS: set[str] = {
    "refund", "delete", "send", "cancel", "remove", "revoke", "terminate", "destroy",
}
TOOL_KEYWORDS: set[str] = {
    "status", "order", "lookup", "check", "track", "find", "search", "query",
}
ERROR_KEYWORDS: set[str] = {
    "timeout", "fail", "failure", "error", "crash", "unavailable", "exception",
}

# PII patterns for basic masking
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_RE = re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b")


def _clean_words(text: str) -> list[str]:
    """Split text into lowercase words with punctuation stripped."""
    return [w.strip("?!.,;:\"'()[]{}") for w in text.lower().split()]


def _mask_pii(text: str) -> str:
    """Replace obvious PII patterns with [REDACTED]."""
    text = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = _PHONE_RE.sub("[REDACTED_PHONE]", text)
    return text


def intake_node(state: AgentState) -> dict[str, Any]:
    """Normalize raw query into state fields.

    Performs whitespace normalization, PII masking, and metadata extraction.
    """
    raw_query = state.get("query", "").strip()
    sanitized = _mask_pii(raw_query)
    return {
        "query": sanitized,
        "messages": [f"intake:{sanitized[:80]}"],
        "events": [make_event("intake", "completed", "query normalized and PII masked")],
    }


def classify_node(state: AgentState) -> dict[str, Any]:
    """Classify the query into a route using keyword-based heuristics.

    Priority order: risky > tool > missing_info > error > simple.
    Uses word-boundary matching to avoid substring false positives.
    """
    query = state.get("query", "").lower()
    clean = _clean_words(query)
    route = Route.SIMPLE
    risk_level = "low"

    # Priority 1: Risky — destructive or external-effect actions
    if RISKY_KEYWORDS & set(clean):
        route = Route.RISKY
        risk_level = "high"
    # Priority 2: Tool — lookup / search operations
    elif TOOL_KEYWORDS & set(clean):
        route = Route.TOOL
        risk_level = "low"
    # Priority 3: Missing info — very short / vague queries
    elif len(clean) < 5 and any(w in clean for w in ("it", "that", "this", "them")):
        route = Route.MISSING_INFO
        risk_level = "low"
    # Priority 4: Error — transient or system failures
    elif ERROR_KEYWORDS & set(clean):
        route = Route.ERROR
        risk_level = "medium"
    # Default: Simple
    # (route already set to SIMPLE)

    return {
        "route": route.value,
        "risk_level": risk_level,
        "events": [make_event("classify", "completed", f"route={route.value}, risk={risk_level}")],
    }


def ask_clarification_node(state: AgentState) -> dict[str, Any]:
    """Ask for missing information instead of hallucinating.

    Generates a context-aware clarification question based on the original query.
    """
    query = state.get("query", "")
    question = (
        f"Your request \"{query}\" is too vague. "
        "Could you provide more details such as an order ID, account number, "
        "or a clearer description of what you need help with?"
    )
    return {
        "pending_question": question,
        "final_answer": question,
        "events": [make_event("clarify", "completed", "context-aware clarification requested")],
    }


def tool_node(state: AgentState) -> dict[str, Any]:
    """Call a mock tool with idempotent execution.

    Simulates transient failures for error-route scenarios to demonstrate retry loops.
    Returns structured tool results.
    """
    attempt = int(state.get("attempt", 0))
    scenario_id = state.get("scenario_id", "unknown")

    # Simulate transient failure for error-route scenarios on early attempts
    if state.get("route") == Route.ERROR.value and attempt < 2:
        result = (
            f"ERROR: transient failure | "
            f"attempt={attempt} | scenario={scenario_id} | "
            f"reason=service_unavailable"
        )
    else:
        result = (
            f"SUCCESS: tool_result | "
            f"scenario={scenario_id} | "
            f"data={{\"status\": \"resolved\", \"attempt\": {attempt}}}"
        )
    return {
        "tool_results": [result],
        "events": [
            make_event("tool", "completed", f"tool executed attempt={attempt}", idempotent=True),
        ],
    }


def risky_action_node(state: AgentState) -> dict[str, Any]:
    """Prepare a risky action for approval with evidence and risk justification.

    Documents the proposed action, risk level, and original query for the reviewer.
    """
    query = state.get("query", "")
    risk_level = state.get("risk_level", "high")
    proposed = (
        f"PROPOSED ACTION: Execute risky operation.\n"
        f"  Original query: \"{query}\"\n"
        f"  Risk level: {risk_level}\n"
        f"  Justification: Query contains destructive/external-effect keywords.\n"
        f"  Requires human approval before proceeding."
    )
    return {
        "proposed_action": proposed,
        "events": [make_event(
            "risky_action", "pending_approval",
            f"risky action prepared, risk_level={risk_level}",
        )],
    }


def approval_node(state: AgentState) -> dict[str, Any]:
    """Human approval step with optional LangGraph interrupt().

    Set LANGGRAPH_INTERRUPT=true to use real interrupt() for HITL demos.
    Default uses mock decision so tests and CI run offline.
    Supports approve / reject decisions.
    """
    import os

    if os.getenv("LANGGRAPH_INTERRUPT", "").lower() == "true":
        from langgraph.types import interrupt

        value = interrupt({
            "proposed_action": state.get("proposed_action"),
            "risk_level": state.get("risk_level"),
        })
        if isinstance(value, dict):
            decision = ApprovalDecision(**value)
        else:
            decision = ApprovalDecision(approved=bool(value))
    else:
        # Mock approval for lab — always approve
        decision = ApprovalDecision(
            approved=True,
            reviewer="mock-reviewer",
            comment="Auto-approved in mock mode for lab execution",
        )
    return {
        "approval": decision.model_dump(),
        "events": [make_event(
            "approval", "completed",
            f"approved={decision.approved}, reviewer={decision.reviewer}",
        )],
    }


def retry_or_fallback_node(state: AgentState) -> dict[str, Any]:
    """Record a retry attempt with exponential backoff metadata.

    Implements bounded retry: increments attempt counter and logs backoff delay.
    """
    attempt = int(state.get("attempt", 0)) + 1
    max_attempts = int(state.get("max_attempts", 3))
    backoff_ms = min(1000 * (2 ** (attempt - 1)), 30000)  # exponential backoff, max 30s

    errors = [f"transient failure attempt={attempt}"]
    return {
        "attempt": attempt,
        "errors": errors,
        "events": [make_event(
            "retry", "completed",
            f"retry attempt={attempt}/{max_attempts}, backoff={backoff_ms}ms",
            attempt=attempt,
            max_attempts=max_attempts,
            backoff_ms=backoff_ms,
        )],
    }


def answer_node(state: AgentState) -> dict[str, Any]:
    """Produce a final response grounded in tool results and approval context."""
    tool_results = state.get("tool_results", [])
    approval = state.get("approval")

    if tool_results:
        latest = tool_results[-1]
        answer = f"Based on tool results: {latest}"
    elif approval:
        answer = (
            f"Action approved by {approval.get('reviewer', 'unknown')}. "
            f"Proceeding with execution."
        )
    else:
        answer = (
            f"Regarding your query: \"{state.get('query', '')}\"\n"
            f"Here is your answer: The request has been processed successfully."
        )
    return {
        "final_answer": answer,
        "events": [make_event("answer", "completed", "answer generated from available context")],
    }


def evaluate_node(state: AgentState) -> dict[str, Any]:
    """Evaluate tool results — the 'done?' check that enables retry loops.

    Checks for ERROR markers in tool output. Structured validation:
    - If latest result contains 'ERROR' → needs_retry
    - Otherwise → success
    """
    tool_results = state.get("tool_results", [])
    latest = tool_results[-1] if tool_results else ""

    if "ERROR" in latest:
        return {
            "evaluation_result": "needs_retry",
            "events": [make_event(
                "evaluate", "completed",
                f"tool result indicates failure, retry needed. Result: {latest[:60]}",
            )],
        }
    return {
        "evaluation_result": "success",
        "events": [make_event("evaluate", "completed", "tool result validated successfully")],
    }


def dead_letter_node(state: AgentState) -> dict[str, Any]:
    """Log unresolvable failures for manual review.

    Third layer of error strategy: retry → fallback → dead letter.
    Creates a structured dead-letter entry with full context.
    """
    attempt = state.get("attempt", 0)
    max_attempts = state.get("max_attempts", 3)
    errors = state.get("errors", [])

    dead_letter_entry = {
        "scenario_id": state.get("scenario_id", "unknown"),
        "query": state.get("query", ""),
        "attempts_made": attempt,
        "max_attempts": max_attempts,
        "error_log": list(errors),
        "resolution": "manual_review_required",
    }

    return {
        "final_answer": (
            f"Request could not be completed after {attempt}/{max_attempts} retry attempts. "
            f"Logged for manual review. Dead-letter ID: DL-{state.get('scenario_id', 'unknown')}"
        ),
        "events": [make_event(
            "dead_letter", "completed",
            f"max retries exceeded, attempt={attempt}/{max_attempts}",
            dead_letter=dead_letter_entry,
        )],
    }


def finalize_node(state: AgentState) -> dict[str, Any]:
    """Finalize the run and emit a final audit event."""
    return {"events": [make_event("finalize", "completed", "workflow finished")]}
