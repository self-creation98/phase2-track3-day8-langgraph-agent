import os
import uuid
import streamlit as st
from langgraph.types import Command

# Set environment variable to enable real interrupt for HITL
os.environ["LANGGRAPH_INTERRUPT"] = "true"

from langgraph_agent_lab.scenarios import load_scenarios
from langgraph_agent_lab.graph import build_graph
from langgraph_agent_lab.persistence import build_checkpointer
from langgraph_agent_lab.state import initial_state

st.set_page_config(page_title="LangGraph Agent Demo", layout="wide", page_icon="🤖")

st.title("🤖 LangGraph Agent: HITL & Time Travel Demo")

def get_graph():
    """Cache the graph and SQLite checkpointer connection."""
    # This enables Crash Recovery: state is saved to a local SQLite file.
    # Even if Streamlit restarts or the browser refreshes, we can recover state via thread_id.
    checkpointer = build_checkpointer("sqlite", database_url="demo_checkpoints.db")
    return build_graph(checkpointer=checkpointer)

graph = get_graph()

# --- SIDEBAR: Scenario Selection & Crash Recovery ---
st.sidebar.header("1. Scenario Runner")
scenarios = load_scenarios("data/sample/scenarios.jsonl")
scenario_dict = {s.id: s for s in scenarios}

selected_scenario_id = st.sidebar.selectbox("Choose a scenario:", list(scenario_dict.keys()))
selected_scenario = scenario_dict[selected_scenario_id]

st.sidebar.markdown(f"**Query:** `{selected_scenario.query}`")
st.sidebar.markdown(f"**Expected Route:** `{selected_scenario.expected_route.value}`")

if st.sidebar.button("🚀 Start Fresh Run", type="primary"):
    # Generate a unique thread ID for the new run
    new_thread_id = f"demo-{selected_scenario_id}-{uuid.uuid4().hex[:6]}"
    st.session_state["thread_id"] = new_thread_id
    
    # Initialize and run
    state = initial_state(selected_scenario)
    state["thread_id"] = new_thread_id
    graph.invoke(state, config={"configurable": {"thread_id": new_thread_id}})
    st.rerun()

st.sidebar.divider()
st.sidebar.header("2. Crash Recovery")
st.sidebar.markdown("Paste an existing `thread_id` below to recover an interrupted or past session.")
recover_thread_id = st.sidebar.text_input("Thread ID:")
if st.sidebar.button("🔄 Recover Session"):
    st.session_state["thread_id"] = recover_thread_id
    st.rerun()


# --- MAIN AREA ---
thread_id = st.session_state.get("thread_id")

if not thread_id:
    st.info("👈 Please click 'Start Fresh Run' in the sidebar to begin.")
    st.stop()

st.caption(f"**Current Thread ID:** `{thread_id}` (Save this to test Crash Recovery!)")

config = {"configurable": {"thread_id": thread_id}}

try:
    current_state = graph.get_state(config)
except Exception as e:
    st.error(f"Error loading state: {e}")
    st.stop()

if not current_state or not current_state.values:
    st.warning("No state found for this Thread ID. Please start a fresh run.")
    st.stop()

state_values = current_state.values

# Render Chat / Event History
st.subheader("💬 Event Flow")
events = state_values.get("events", [])
for event in events:
    # Use different avatars for system vs user
    avatar = "👤" if event["node"] == "intake" else "⚙️"
    with st.chat_message("user" if event["node"] == "intake" else "assistant", avatar=avatar):
        st.markdown(f"**Node:** `{event['node']}` | **Action:** `{event['event_type']}`")
        st.write(event["message"])

if state_values.get("final_answer"):
    st.success(f"**Final Answer:** {state_values['final_answer']}")
elif state_values.get("pending_question"):
    st.warning(f"**Clarification Required:** {state_values['pending_question']}")

# --- HITL: Approval Interface ---
# Check if execution is paused at the 'approval' node
if current_state.next and "approval" in current_state.next:
    st.divider()
    st.header("⚠️ Human-in-the-Loop (HITL) Intervention Required")
    st.warning("The agent needs human approval before executing a risky action.")
    
    st.code(state_values.get("proposed_action", "No action detailed."))
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Approve Action", type="primary", use_container_width=True):
            graph.invoke(Command(resume={"approved": True, "reviewer": "AdminUI"}), config=config)
            st.rerun()
    with col2:
        if st.button("❌ Reject Action", use_container_width=True):
            graph.invoke(Command(resume={"approved": False, "reviewer": "AdminUI"}), config=config)
            st.rerun()

# --- TIME TRAVEL & STATE HISTORY ---
st.divider()
st.header("⏪ Time Travel & State History")
st.markdown("Explore past checkpoints. Selecting a past checkpoint will show the raw state at that exact moment.")

history = list(graph.get_state_history(config))
if history:
    # Reverse the history so the most recent is at the top
    checkpoint_opts = [f"Step {len(history) - i}: {h.next[0] if h.next else 'END'}" for i, h in enumerate(history)]
    
    selected_idx = st.selectbox(
        "View past state (Checkpoints):", 
        range(len(history)), 
        format_func=lambda i: f"Checkpoint {history[i].config['configurable']['checkpoint_id']} - {checkpoint_opts[i]}"
    )
    
    selected_history = history[selected_idx]
    
    with st.expander("Show Raw State at this Checkpoint", expanded=True):
        st.json(selected_history.values)
        
    if selected_idx != 0:
        st.info("💡 **Time Travel Forking**: To time travel, you would update the state at this specific `checkpoint_id` and invoke the graph again. In this read-only demo, we just explore the history.")
