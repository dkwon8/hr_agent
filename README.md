# HR Recruitment Agent + MLflow Improve

Two projects in one repo:

1. **HR Agent** — AI-powered recruitment assistant for Red Hat's engineering internship program. Processes resumes from Google Drive, filters by rules, validates GitHub profiles, scores with LLM-as-a-judge, and generates ranked reports.

2. **MLflow Improve** — A universal self-optimization and self-healing system built as a feature in a [forked MLflow](https://github.com/dkwon8/mlflow). Any agent logging traces to MLflow gets automatic anomaly detection, fix suggestions, and GitHub PR generation. The HR agent serves as the demo and test case.

## Architecture

```
                          ┌─────────────────────────────┐
                          │      MLflow (forked)         │
                          │                              │
  HR Agent runs    ──►    │  Traces ──► Improve feature  │
  (or any agent)          │              │               │
                          │    ┌─────────┘               │
                          │    ▼                          │
                          │  Detect anomalies (cron)     │
                          │  Generate suggestions        │
                          │  Create fix PRs (auto)       │
                          └─────────────────────────────┘
```

## HR Agent

The agent uses 5 MCP (Model Context Protocol) tool servers, each handling a different part of the pipeline:

| Server | What it does |
|--------|-------------|
| **Resume** | Lists and parses resumes from Google Drive into structured candidate data (with persistent JSON cache) |
| **Filter** | Applies location and graduation date rules (no LLM cost) |
| **GitHub** | Checks GitHub profiles — email search then name+university discovery |
| **Scoring** | 3-pass median LLM-as-a-judge scoring with score clamping (experience/40, projects/35, learning_potential/25) |
| **Output** | Generates reports, sorts resumes into per-run Drive folders, appends PDF decision pages |

The agent is **dynamic** — it adapts to any role, not just GE internships. Provide a Workday job posting URL and it fetches requirements, adjusts filtering/scoring criteria, and evaluates candidates against that specific role.

### Features

- **16 MCP tools** across 5 servers, orchestrated by OpenAI Agents SDK
- **Dynamic role adaptation** — provide a Workday URL or describe the role in natural language
- **3-pass median scoring** for reliability (±1-3 point variance)
- **Per-run Google Drive folders** — Run_TIMESTAMP/Accepted/Rejected
- **PDF decision documents** appended to each resume
- **Persistent resume cache** — skips LLM calls for previously parsed resumes
- **React dashboard** with pipeline summary, candidate scorecards, trace history, and integrated chat

## MLflow Improve

Built in a [forked MLflow](https://github.com/dkwon8/mlflow) at `mlflow/genai/improve/`. Works with any MLflow-traced agent — the HR agent is just one example.

### How it works

1. **Auto-detection** — When an agent logs traces, the system auto-detects the GitHub repo from git metadata and tags the experiment (no manual setup)
2. **Cron monitoring** — A scheduler runs every 5 minutes, analyzing traces for anomalies using z-score statistical baselines
3. **6 detectors** — Context bloat, context growth, tool redundancy, score degradation, slow execution, execution slowdown
4. **LLM code analysis** — On-demand: clones the repo, reads source files, uses GPT to find code-level issues
5. **Fix agent** — Claude Code clones the repo, analyzes the issue, and creates a GitHub PR with the fix
6. **Self-healing loop** — Detect → suggest → fix → verify, fully automatic when auto-fix is enabled

### Improve tab in MLflow UI

The forked MLflow adds an **Improve** tab to each experiment with three views:
- **Self-Optimization** — Actionable suggestions with severity, confidence, and "Fix it" buttons
- **Self-Healing** — Error alerts from traces with root cause analysis
- **Code Analysis** — Static code issues found by LLM analysis

## Quick Start

### 1. Clone and set up

```bash
git clone https://github.com/dkwon8/hr_agent.git
cd hr_agent               # repo root
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment variables

```bash
cp .env.example .env
# Edit .env with your API keys
```

Required: [OpenAI API key](https://platform.openai.com/api-keys). Optional: Google Drive service account for resume storage.

### 3. Run

```bash
# All services (MLflow + API + Dashboard)
./start.sh

# Agent only (terminal chat)
cd hr_agent
python agent.py

# Single prompt
python agent.py "Run the full pipeline"
```

### 4. Access

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:3000 |
| Dashboard API | http://localhost:8001 |
| MLflow + Improve | http://localhost:5001 |

## Project Structure

```
summer_proj/
├── hr_agent/                     # HR recruitment agent
│   ├── agent.py                  #   Main orchestrator (dynamic, role-adaptive)
│   ├── config/settings.py        #   Environment config
│   ├── mcp_servers/
│   │   ├── resume/               #   Resume parsing (Drive + PyMuPDF + LLM + cache)
│   │   ├── filter/               #   Location and graduation rules
│   │   ├── github/               #   GitHub profile lookup and validation
│   │   ├── scoring/              #   LLM-as-a-judge with score clamping
│   │   └── output/               #   Reports, Drive folders, PDF summaries
│   ├── phase_agents/             #   Sub-agents per pipeline phase
│   ├── data/job_requirements/    #   Department requirements JSON
│   └── credentials/              #   Google service account (gitignored)
├── dashboard/                    # React + Next.js web UI
│   ├── api.py                    #   FastAPI backend
│   ├── app/                      #   Next.js pages
│   └── components/               #   React components
├── improve/                      # Proxy to MLflow fork's improve API
├── docs/                         # Original design documents
├── mlflow.db                     # MLflow trace database
└── start.sh                      # Launch all services

~/mlflow/mlflow/genai/improve/    # MLflow fork — the improve feature
├── __init__.py                   #   Entry point (analyze, compare, snapshot)
├── trace_analyzer.py             #   6 statistical baseline detectors
├── code_analyzer.py              #   LLM-powered code analysis
├── suggestions.py                #   Finding → actionable suggestion mapping
├── fix_agent_registry.py         #   Fix agent interface and registry
├── fix_agents/claude_code_agent.py  # Claude Code PR creation
├── background_jobs.py            #   Huey one-shot jobs (analysis, fix)
├── scheduler.py                  #   Cron periodic monitoring
└── utils.py                      #   URL normalization
```

## Tech Stack

- **Agent:** [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) with GPT-5.4
- **Tools:** [FastMCP](https://github.com/jlowin/fastmcp) (Model Context Protocol)
- **Dashboard:** React + Next.js + TypeScript + Tailwind, FastAPI backend
- **Observability:** MLflow 3.x (forked) with traces, evaluations, and self-improvement
- **Improve:** Statistical baselines (z-score), LLM code analysis (GPT-5.4-mini), Claude Code Agent SDK
- **Resume parsing:** PyMuPDF
- **Storage:** Google Drive API
