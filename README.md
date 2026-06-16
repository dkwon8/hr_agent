# HR Recruitment Agent

An AI-powered recruitment assistant built for Red Hat's Global Engineering internship program. It processes resumes from Google Drive, filters candidates by location and graduation date, validates GitHub profiles, scores applicants against 12 department requirements, and generates ranked reports — all through a conversational interface.

## How It Works

The agent uses 5 MCP (Model Context Protocol) tool servers, each handling a different part of the pipeline:

| Server | What it does |
|--------|-------------|
| **Resume** | Lists and parses resumes from Google Drive into structured candidate data |
| **Filter** | Applies location and graduation date rules (no LLM cost) |
| **GitHub** | Looks up and validates candidate GitHub profiles |
| **Scoring** | Scores candidates against 12 departments using LLM-as-a-judge |
| **Output** | Generates reports and sorts resumes into accepted/rejected folders |

You can ask the agent to run the full pipeline, or use individual tools through natural language — for example, "parse the first resume" or "show me the top candidates for AI."

## Quick Start

### 1. Clone and set up the environment

```bash
git clone https://github.com/dkwon8/hr_agent.git
cd hr_agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> **Note:** Python 3.13 is recommended. Python 3.14 has compatibility issues with Chainlit.

### 2. Set up environment variables

```bash
cp .env.example .env
# Edit .env with your API keys
```

You'll need at minimum an [OpenAI API key](https://platform.openai.com/api-keys).

### 3. Set up Google Drive (for resume storage)

1. Create a [Google Cloud project](https://console.cloud.google.com) and enable the **Google Drive API**
2. Create a **service account** and download the JSON key
3. Save the key to `credentials/service_account.json`
4. Create a Google Drive folder for resumes, and share it with the service account email (found in the JSON key file under `client_email`)
5. Add the folder IDs to your `.env` file — see `.env.example` for the variable names

### 4. Run the agent

```bash
# Web UI (opens in browser at http://localhost:8000)
chainlit run app.py

# Terminal chat
python agent.py

# Single prompt
python agent.py "List the resumes"
```

## Project Structure

```
hr_agent/
├── agent.py                  # Main agent — connects to all 5 MCP servers
├── app.py                    # Chainlit web UI wrapper
├── config/
│   └── settings.py           # Environment config
├── mcp_servers/
│   ├── resume/               # Resume parsing (Google Drive + PyMuPDF + LLM)
│   ├── filter/               # Location and graduation date rules
│   ├── github/               # GitHub profile lookup and validation
│   ├── scoring/              # LLM-as-a-judge scoring against departments
│   └── output/               # Report generation and resume sorting
├── phase_agents/             # Individual phase agents (for standalone testing)
├── data/
│   └── job_requirements/     # Department requirements JSON
├── credentials/              # Google service account key (gitignored)
├── .env.example              # Template for environment variables
└── requirements.txt
```

## Tech Stack

- **Agent framework:** [OpenAI Agents SDK](https://github.com/openai/openai-agents-python)
- **Tool servers:** [FastMCP](https://github.com/jlowin/fastmcp) (Model Context Protocol)
- **LLM:** GPT-5.4 (via OpenAI API)
- **Web UI:** [Chainlit](https://github.com/Chainlit/chainlit)
- **Resume parsing:** PyMuPDF
- **Resume storage:** Google Drive API
