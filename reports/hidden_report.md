# Day 08 Lab Report

## 1. Team / student

- Name: Phạm Thanh Tùng
- Student ID: 2A202600268
- Repo/Commit: https://github.com/self-creation98/phase2-track3-day8-langgraph-agent.git
- Date: 2026-05-11


## 2. Architecture

The graph implements a support-ticket agent with the following node pipeline:

```
START → intake → classify → [conditional routing]
  simple       → answer → finalize → END
  tool         → tool → evaluate → answer → finalize → END
  missing_info → clarify → finalize → END
  risky        → risky_action → approval → tool → evaluate → answer → finalize → END
  error        → retry → tool → evaluate → [retry loop or answer → finalize → END]
  max retry    → dead_letter → finalize → END
```

**Key design decisions:**
- `classify_node` uses priority-ordered keyword matching (risky > tool > missing > error > simple)
- `evaluate_node` acts as the "done?" gate enabling bounded retry loops
- `approval_node` supports both mock and real HITL via `LANGGRAPH_INTERRUPT` env var
- All paths terminate at `finalize → END` to prevent infinite loops

## 3. State schema

| Field | Reducer | Why |
|---|---|---|
| `messages` | append (`add`) | Audit full conversation history |
| `tool_results` | append (`add`) | Track all tool calls across retries |
| `errors` | append (`add`) | Accumulate error log for debugging |
| `events` | append (`add`) | Full node-level audit trail |
| `route` | overwrite | Current routing decision only |
| `risk_level` | overwrite | Current risk assessment |
| `attempt` | overwrite | Current retry counter |
| `final_answer` | overwrite | Latest answer replaces previous |
| `evaluation_result` | overwrite | Latest evaluation gate result |
| `approval` | overwrite | Latest approval decision |

## 4. Scenario results

| Scenario | Expected route | Actual route | Success | Retries | Interrupts |
|---|---|---|---:|---:|---:|
| G01_simple | simple | simple | ✅ | 0 | 0 |
| G02_simple2 | simple | simple | ✅ | 0 | 0 |
| G03_tool | tool | tool | ✅ | 0 | 0 |
| G04_tool2 | tool | tool | ✅ | 0 | 0 |
| G05_tool3 | tool | tool | ✅ | 0 | 0 |
| G06_missing | missing_info | missing_info | ✅ | 0 | 0 |
| G07_missing2 | missing_info | missing_info | ✅ | 0 | 0 |
| G08_risky | risky | risky | ✅ | 0 | 1 |
| G09_risky2 | risky | risky | ✅ | 0 | 1 |
| G10_risky3 | risky | risky | ✅ | 0 | 1 |
| G11_risky4 | risky | risky | ✅ | 0 | 1 |
| G12_error | error | error | ✅ | 2 | 0 |
| G13_error2 | error | error | ✅ | 2 | 0 |
| G14_dead | error | error | ✅ | 1 | 0 |
| G15_mixed | risky | risky | ✅ | 0 | 1 |

**Summary:**
- Total scenarios: 15
- Success rate: 100.00%
- Average nodes visited: 6.60
- Total retries: 5
- Total interrupts: 5

## 5. Failure analysis

### Failure mode 1: Retry exhaustion → Dead letter
When a tool call fails repeatedly (e.g., S07_dead_letter with max_attempts=1), the retry loop
is bounded by `attempt >= max_attempts`. Once exceeded, `route_after_retry` sends the request
to `dead_letter_node`, which logs the failure with full context for manual review.

### Failure mode 2: Risky action without approval
If `LANGGRAPH_INTERRUPT=true` and a reviewer rejects the proposed action, `route_after_approval`
routes to `clarify` instead of `tool`, preventing unauthorized destructive operations.

### Failure mode 3: Vague/missing information
Short queries with pronouns (e.g., "Can you fix it?") are detected by word count + pronoun
heuristics and routed to `clarify` instead of hallucinating an answer.

## 6. Persistence / recovery evidence

- **MemorySaver**: Used by default for development and CI. Each scenario run uses a unique
  `thread_id` (format: `thread-{scenario_id}`), enabling state isolation between runs.
- **SqliteSaver**: Configured with `SqliteSaver(conn=sqlite3.connect(...))` and WAL mode for
  concurrent read access. State can survive process restarts.
- **Thread ID per run**: `cli.py` passes `thread_id` via `run_config["configurable"]` to enable
  per-scenario state tracking and potential crash-resume.

## 7. Extension work

### Graph Mermaid Diagram
Exported via `graph.get_graph().draw_mermaid()` — see `outputs/graph.md`.
This provides a visual architecture overview of all nodes and conditional edges.

## 8. Improvement plan

If given one more day, I would prioritize:

1. **LLM-based classification**: Replace keyword heuristics with a lightweight LLM classifier
   for more robust routing that handles paraphrased queries.
2. **Real tool integration**: Replace mock tools with actual API calls (order lookup, refund
   processing) with proper error handling and circuit breakers.
3. **Observability**: Add LangSmith tracing for production monitoring and debugging.
4. **Parallel fan-out**: Use `Send()` to run multiple tools concurrently for complex queries.
