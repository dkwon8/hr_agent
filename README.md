# HR Recruitment Agent

An AI-powered recruitment assistant built for Red Hat's Global Engineering internship program. It processes resumes from Google Drive, filters candidates by location and graduation date, validates GitHub profiles, scores applicants against department requirements and custom job descriptions, and generates ranked reports.

Part of a larger project that includes a forked MLflow with a universal **self-optimization and self-healing** system — see [MLflow Improve](https://github.com/dkwon8/mlflow).

## How It Works

The agent uses 5 MCP (Model Context Protocol) tool servers, each handling a different part of the pipeline:

| Server | What it does |
|--------|-------------|
| **Resume** | Lists and parses resumes from Google Drive into structured candidate data (with persistent JSON cache) |
| **Filter** | Applies location and graduation date rules (no LLM cost) |
| **GitHub** | Checks GitHub profiles — email search then name+university discovery |
| **Scoring** | 3-pass median LLM-as-a-judge scoring with score clamping (experience/40, projects/35, learning_potential/25) |
| **Output** | Generates reports, sorts resumes into per-run Drive folders, appends PDF decision pages |

The agent is **dynamic** — it adapts to any role, not just GE internships. Provide a Workday job posting URL and it fetches requirements, adjusts filtering/scoring criteria, and evaluates candidates against that specific role.

## Features

- **16 MCP tools** across 5 servers, orchestrated by OpenAI Agents SDK
- **Dynamic role adaptation** — provide a Workday URL or describe the role in natural language
- **3-pass median scoring** for reliability (±1-3 point variance)
- **Per-run Google Drive folders** — Run_TIMESTAMP/Accepted/Rejected
- **PDF decision documents** appended to each resume
- **Persistent resume cache** — skips LLM calls for previously parsed resumes
- **React dashboard** with pipeline summary, candidate scorecards, trace history, and integrated chat
- **MLflow observability** — traces, built-in evaluation scores (ToolCallCorrectness, Completeness, Efficiency, Relevance)
- **MLflow Improve integration** — self-optimization and self-healing via the forked MLflow

## Quick Start

### 1. Clone and set up

```bash
git clone https://github.com/dkwon8/hr_agent.git
cd hr_agent
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

# Terminal chat only
python agent.py

# Single prompt
python agent.py "Run the full pipeline"
```

### 4. Access

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:3000 |
| Dashboard API | http://localhost:8001 |
| MLflow | http://localhost:5001 |

## Project Structure

```
hr_agent/
├── agent.py                  # Main orchestrator agent (dynamic, role-adaptive)
├── start.sh                  # Launch all services
├── config/settings.py        # Environment config
├── mcp_servers/
│   ├── resume/               # Resume parsing (Drive + PyMuPDF + LLM + cache)
│   ├── filter/               # Location and graduation rules
│   ├── github/               # GitHub profile lookup and validation
│   ├── scoring/              # LLM-as-a-judge with score clamping
│   └── output/               # Reports, Drive folders, PDF summaries
├── dashboard/
│   ├── api.py                # FastAPI backend
│   ├── app/                  # Next.js pages
│   └── components/           # React components
├── data/
│   ├── job_requirements/     # Department requirements JSON
│   └── parsed_candidates.json # Resume cache (gitignored)
└── credentials/              # Google service account (gitignored)
```

## MLflow Improve — Self-Optimization & Self-Healing

This agent integrates with a [forked MLflow](https://github.com/dkwon8/mlflow) that adds universal self-improvement capabilities:

```python
import mlflow.genai.improve

# One line — automatic detection, manual fix via UI
mlflow.genai.improve.enable_auto_improve(
    experiment_name="recruitment-filtration-agent",
    check_every_n_traces=10,
)
```

The system:
1. **Monitors** traces automatically after every N runs
2. **Detects** performance issues (context bloat, tool redundancy, score degradation, slowdowns)
3. **Suggests** fixes with confidence scores
4. **Creates PRs** on GitHub when the user clicks "Fix it" in MLflow's Improve tab
5. **Verifies** fixes worked via before/after comparison

See the [MLflow fork](https://github.com/dkwon8/mlflow) for the full improve feature.

## Tech Stack

- **Agent:** [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) with GPT-5.4
- **Tools:** [FastMCP](https://github.com/jlowin/fastmcp) (Model Context Protocol)
- **Dashboard:** React + Next.js + TypeScript + Tailwind, FastAPI backend
- **Observability:** MLflow 3.x (forked) with traces, evaluations, and self-improvement
- **Resume parsing:** PyMuPDF
- **Storage:** Google Drive API
