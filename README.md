# 🤖 LangGraph Agentic Orchestration Lab

## 🌟 Overview
A production-ready LangGraph workflow for a support-ticket agent featuring state management, conditional routing, bounded retry loops, Human-in-the-Loop (HITL) approval, SQLite persistence, and an interactive Streamlit UI demo.

This project achieved a perfect **100/100** score on the hidden evaluation dataset (15/15 scenarios passed) and fully implements all advanced extensions.

## ✨ Key Features
- **Intelligent Routing**: Priority-based keyword routing for simple, tool, missing info, and risky intents.
- **Robust Error Handling**: Bounded retry loops with a dead-letter queue for exhausted tool attempts.
- **Human-In-The-Loop (HITL)**: Real interruption mechanism allowing admins to approve or reject risky actions (`LANGGRAPH_INTERRUPT=true`).
- **State Persistence**: Crash recovery and time-travel powered by LangGraph's `SqliteSaver` (WAL mode enabled).
- **Streamlit Demo UI**: An interactive web interface to run scenarios, test crash recovery, and review state history.

---

## 🚀 How to Run

### 1. Installation
Ensure you have Python 3.11+ installed.
```bash
# Clone the repository
git clone https://github.com/self-creation98/phase2-track3-day8-langgraph-agent.git
cd phase2-track3-day8-langgraph-agent

# Install the project and all dependencies (dev tools, sqlite checkpointer, and streamlit)
pip install -e ".[dev,sqlite,ui]"
```

### 2. Run the Streamlit UI Demo (Recommended!)
This is the best way to experience the HITL, Time Travel, and Crash Recovery features visually.
```bash
python -m streamlit run app.py
```
- Open `http://localhost:8501` in your browser.
- **Scenario Runner**: Select a scenario from the sidebar and click **Start Fresh Run**.
- **HITL Testing**: Run a risky scenario (e.g., `S04_risky` or `S08_cancel`). The execution will pause and wait for your manual Approval/Rejection on the UI.
- **Crash Recovery Testing**: Copy the `thread_id` at the top of the screen. Stop the server (`Ctrl+C`), restart it, and paste your ID into the **Recover Session** box.
- **Time Travel**: Expand the Time Travel section at the bottom to explore the raw state of past checkpoints.

### 3. Run Automated Tests & Scenarios (CLI)
If you prefer the command line, you can run the automated evaluation pipeline:

```bash
# 1. Run all unit tests
python -m pytest -v

# 2. Run all evaluation scenarios (generates outputs/metrics.json)
python -m langgraph_agent_lab.cli run-scenarios --config configs/lab.yaml --output outputs/metrics.json

# 3. Validate scenario results (Expected: 100% success rate)
python -m langgraph_agent_lab.cli validate-metrics --metrics outputs/metrics.json
```

### 4. Code Quality
The codebase maintains strict linting and type discipline (0 errors).
```bash
# Run the Ruff linter
python -m ruff check src tests
```

---

## 📊 Architecture Diagram
The graph routing logic has been auto-exported to **[outputs/graph.md](outputs/graph.md)**. You can preview it in VS Code or GitHub to see the full flowchart of how the agent routes requests, loops through retries, and handles dead letters.

## 📝 Lab Reports
Detailed analysis of the architecture, metrics, failure modes, and improvement plans can be found here:
- **[reports/lab_report.md](reports/lab_report.md)**: Main lab report.
- **[reports/hidden_report.md](reports/hidden_report.md)**: Result of the hidden test dataset evaluation.

---
*Developed by Phạm Thanh Tùng - Student ID: 2A202600268*
