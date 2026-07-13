"""
HR Recruitment Agent as a master orchestrator.

The main agent that users interact with. Connects to all 5 MCP servers
and decides which tools to call based on the user's prompt.

Run:
    python agent.py                              # interactive chat mode
    python agent.py "Process the resumes"        # single prompt mode

How it works:
    1. Spawns all 5 MCP servers as stdio subprocesses
    2. User sends a prompt in natural language
    3. GPT-5.4 decides which tools to call and in what order
    4. Tools execute across MCP servers (resume, filter, github, scoring, output)
    5. Agent responds with results and can handle follow-up questions

The agent maintains conversation state — after processing resumes,
you can ask follow-up questions like "Why was William rejected?" or
"Show me the top candidates for AI" without re-processing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys

_CITE_PATTERN = re.compile(r"\s*(?:citeturn|turn)\d+\S*", re.IGNORECASE)


def _clean_citations(text: str) -> str:
    """Strip web search citation markers from agent output."""
    return _CITE_PATTERN.sub("", text).rstrip()


# -- Conversation history management ------------------------------------------
# Large pipeline responses (candidate reports, scoring results) can reach
# tens of KB each.  Without trimming, the full history is re-sent every turn,
# causing trace sizes to grow past 2 MB and pressuring the context window.

MAX_HISTORY_MESSAGES = 20       # keep at most 20 messages (10 user/assistant turns)
RECENT_MESSAGES_VERBATIM = 6    # most-recent 3 turns are kept verbatim
TRUNCATE_THRESHOLD = 500        # older assistant messages are truncated beyond this length


def trim_conversation_history(messages: list[dict]) -> list[dict]:
    """Return a trimmed copy of *messages* to bound context-window size.

    - Drops the oldest messages beyond MAX_HISTORY_MESSAGES.
    - Keeps the most recent RECENT_MESSAGES_VERBATIM messages verbatim.
    - Truncates older assistant messages to TRUNCATE_THRESHOLD chars.
    """
    if len(messages) <= RECENT_MESSAGES_VERBATIM:
        return list(messages)

    recent = messages[-RECENT_MESSAGES_VERBATIM:]
    older = messages[:-RECENT_MESSAGES_VERBATIM]

    budget = MAX_HISTORY_MESSAGES - RECENT_MESSAGES_VERBATIM
    if len(older) > budget:
        older = older[-budget:]

    trimmed: list[dict] = []
    for msg in older:
        content = msg.get("content", "")
        if msg["role"] == "assistant" and len(content) > TRUNCATE_THRESHOLD:
            trimmed.append({
                "role": "assistant",
                "content": content[:TRUNCATE_THRESHOLD] + "\n\n[Earlier response truncated for brevity]",
            })
        else:
            trimmed.append(msg)

    return trimmed + recent

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Suppress noisy debug logs from MCP servers and HTTP requests
logging.getLogger("mcp").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# MLflow tracing — only enable if the tracking server is reachable.
# MLflow's OpenAI autolog doesn't map all OpenAI Agents SDK span types,
# so "task", "turn", and "mcp_tools" spans show up as "Unknown". We patch
# the span type map and name function to fix this.
try:
    import urllib.request
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001")
    urllib.request.urlopen(tracking_uri, timeout=2)
    os.environ.setdefault("MLFLOW_TRACKING_URI", tracking_uri)
    os.environ.setdefault("MLFLOW_EXPERIMENT_NAME", "recruitment-filtration-agent")
    import mlflow
    from mlflow.entities import SpanType
    from mlflow.openai import _agent_tracer

    _agent_tracer._SPAN_TYPE_MAP.update({
        "task": SpanType.TASK,
        "turn": SpanType.CHAIN,
        "custom": SpanType.CHAIN,
        "mcp_tools": SpanType.TOOL,
        "transcription": SpanType.CHAIN,
        "speech": SpanType.CHAIN,
        "speech_group": SpanType.CHAIN,
    })

    _original_get_span_name = _agent_tracer._get_span_name

    def _patched_get_span_name(span_data):
        name_map = {
            "task": "Agent Task",
            "turn": "Agent Turn",
            "mcp_tools": "MCP Tool Discovery",
            "custom": "Custom",
            "transcription": "Transcription",
            "speech": "Speech",
            "speech_group": "Speech Group",
        }
        span_type = getattr(span_data, "type", None)
        if span_type in name_map:
            return name_map[span_type]
        return _original_get_span_name(span_data)

    _agent_tracer._get_span_name = _patched_get_span_name

    mlflow.openai.autolog()
except Exception:
    pass

from agents import Agent, Runner, WebSearchTool, function_tool
from agents.mcp import MCPServerStdio


PYTHON_PATH = sys.executable
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

AGENT_INSTRUCTIONS = """You are a dynamic AI recruitment assistant that adapts to any role and department.

You help recruiters process resumes, filter candidates, validate their profiles, score them against job requirements, and generate reports with reasoning.

## How You Think About Requirements

Before running the pipeline, always reason about what the job actually needs. You figure this out from context:

- If the user gives you a URL, use fetch_job_posting (for Workday links) or web search (for other sites) to retrieve the job description. Read it carefully and extract: role title, required skills, location requirements, experience level, education requirements, and any other qualifications.
- If the user describes requirements in conversation (e.g., "looking for Python developers in NYC"), use those directly.
- If no specific requirements are given and no URL is provided, use the default Red Hat Global Engineering internship configuration (get_department_requirements to see the 12 departments). Do not explain to the user that you are using the default — just use it naturally. If the resumes show students with graduation dates and university info, treat it as an internship pipeline without stating so explicitly.

## How You Think About Filtering

Decide which filters make sense based on the role:
- **Location filtering:** Apply when the job description specifies a location or the user mentions one. Pass the extracted locations to filter_candidates via target_locations. If the role is fully remote or the job description doesn't mention location, consider skipping location filtering or filtering for "Remote".
- **Graduation date filtering:** Apply when the role targets students or recent graduates (internships, entry-level). If the job is for experienced professionals (Senior Engineer, Principal, etc.), skip graduation filtering entirely — pass a wide window or omit it.
- **GitHub validation:** Use for technical roles where code contributions are relevant (engineering, data science, DevOps). Skip for non-technical roles (marketing, HR, finance, design research) — the agent should decide based on the role's nature.

Think about what makes sense. A Principal Software Engineer posting shouldn't reject candidates for graduation dates. A marketing intern doesn't need GitHub validation. Reason about it.

## Available Tools

**fetch_job_posting** — Fetches structured job data from Workday URLs directly via their API. Use this for any myworkdayjobs.com link.
**Web Search** — Built-in web search for non-Workday job sites and general lookups.

**MCP Tool Servers:**
1. Resume Tools - Read and parse resumes from Google Drive or local folder
   - list_resumes: see what resumes are available in the main resumes folder
   - list_sorted_resumes: list resumes in the accepted or rejected folder (pass folder_id from list_run_folders)
   - list_run_folders: browse timestamped pipeline run folders and their accepted/rejected subfolders on Google Drive
   - parse_resume: parse one resume into structured data
   - parse_all_resumes: batch parse all resumes
   - search_candidates: search previously parsed candidates

2. Filter Tools — Apply deterministic rules
   - check_candidate_location: verify location matches target areas
   - check_candidate_graduation: verify graduation is within window
   - filter_candidates: batch filter all candidates. Accepts optional custom parameters: target_locations (comma-separated), graduation_earliest (YYYY-MM), graduation_latest (YYYY-MM). Omit parameters to use defaults.

3. GitHub Tools — Cross-validate technical candidate profiles (use only when relevant to the role)
   - lookup_profile: get full GitHub profile with authenticity signals
   - discover_profile: find GitHub when not listed on resume
   - check_authenticity: detailed commit quality analysis

4. Scoring Tools — Advisory LLM-as-a-Judge evaluation (for recruiter reference, not pass/fail)
   - score_candidate: score one candidate against the default 12 GE departments
   - score_all_candidates: batch score and rank against default departments
   - score_candidate_for_role: score one candidate against custom role requirements you extracted
   - score_all_for_role: batch score and rank against custom role requirements you extracted
   - get_department_requirements: view default department skills requirements

5. Output Tools — Generate reports and sort resumes
   - generate_report: create JSON report + readable text summary
   - sort_resumes: sort into accepted/rejected folders with PDF pages

## Workflow

When asked to evaluate or run the pipeline:
1. **Understand the role** — Fetch job requirements if a URL is provided, or identify what the user is looking for from conversation. Reason about what kind of role this is (intern vs senior, technical vs non-technical).
2. **Parse resumes** — Call parse_all_resumes (one call handles listing, reading, and parsing). If it returns 0 resumes, use list_run_folders to find resumes from previous pipeline runs, then call parse_all_resumes with the appropriate folder_id.
3. **Filter candidates** — Call filter_candidates once with all parsed candidates. Pass custom criteria as needed based on the role.
4. **GitHub validation** — Only for technical roles where code contributions matter. Use lookup_profile for candidates with a GitHub URL, or discover_profile to find one. Skip for non-technical roles.
5. **Score candidates** — Call score_all_for_role once (for custom roles) or score_all_candidates once (for default GE departments). Do not use both.
6. **Generate report** — Call generate_report once with all candidates.
7. **Sort resumes** — Call sort_resumes once to sort into accepted/rejected folders.

## Tool Efficiency Rules — Avoid Unnecessary Calls

Do not call MCP Tool Discovery more than once per pipeline run unless processing different candidates.

Always prefer batch tools over calling individual tools in a loop:
- Use **parse_all_resumes** instead of calling parse_resume on each resume individually.
- Use **filter_candidates** instead of calling check_candidate_location or check_candidate_graduation on each candidate individually. filter_candidates applies both checks in a single call.
- Use **score_all_candidates** (or **score_all_for_role**) instead of calling score_candidate (or score_candidate_for_role) on each candidate individually.

Do not call tools whose work is already done internally by another tool you are about to call:
- **Do not call list_resumes before parse_all_resumes.** parse_all_resumes already lists and reads all resumes internally.
- **Do not call read_resume before parse_resume.** parse_resume already reads the resume internally.
- **Do not call get_department_requirements before score_all_candidates or score_candidate.** The scoring tools load department requirements internally.

Avoid redundant overlapping calls:
- **Do not call both lookup_profile and check_authenticity on the same candidate.** lookup_profile already returns authenticity signals (commit quality ratio, activity, flags). Only use check_authenticity if you need extra per-repo commit detail beyond what lookup_profile provides — this is rarely needed.
- **Choose one scoring mode per pipeline run.** Use score_all_candidates for default GE departments OR score_all_for_role for custom role requirements. Never call both.

For the standard pipeline, the minimal efficient tool sequence is:
1. parse_all_resumes (one call — lists, reads, and parses all resumes)
2. filter_candidates (one call — applies all deterministic filters)
3. GitHub validation if needed (lookup_profile or discover_profile per candidate — these are inherently per-candidate)
4. score_all_candidates or score_all_for_role (one call — scores all candidates)
5. generate_report (one call)
6. sort_resumes (one call)

## Guidelines
- Report results directly — do not narrate your internal decision-making about which mode or configuration you chose. The user does not need to know why you picked certain filters; just present the results.
- Report numbers clearly (how many parsed, passed filter, rejected, scored)
- When presenting scored candidates, show their rank, score, best-fit department/role, and note GitHub findings if available
- For rejected candidates, always explain the specific filter rule they failed
- Be concise but thorough
- Ask for clarification when the request is ambiguous
- Stay on topic. You exist solely for recruitment and candidate evaluation. You may answer technical or engineering questions when they relate to evaluating a candidate's fit. But if the question has nothing to do with hiring, candidates, or the skills being evaluated, politely decline.
"""


@function_tool
async def fetch_job_posting(url: str) -> str:
    """Fetch job requirements from a Workday job posting URL.

    Extracts the role title, location, job description, and qualifications
    directly from Workday's API. Use this tool when the user provides a
    Workday URL (e.g., redhat.wd5.myworkdayjobs.com/...).

    Returns structured JSON with the role requirements that can be passed
    to score_candidate_for_role or score_all_for_role.

    Args:
        url: A Workday job posting URL
    """
    m = re.match(
        r"https?://([^.]+)\.wd(\d+)\.myworkdayjobs\.com/(?:[^/]+/)?([^/]+)/job/(.+?)(?:\?.*)?$",
        url.strip(),
    )
    if not m:
        return json.dumps({"error": "Not a recognized Workday URL. Use web_search to find requirements from other job sites."})

    company, wd_num, site, slug = m.groups()
    api_url = f"https://{company}.wd{wd_num}.myworkdayjobs.com/wday/cxs/{company}/{site}/job/{slug}"

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(api_url, headers={"Accept": "application/json"})

    if resp.status_code != 200:
        return json.dumps({"error": f"Workday API returned status {resp.status_code}"})

    data = resp.json()
    posting = data.get("jobPostingInfo", {})

    title = posting.get("title", "")
    location = posting.get("location", "")
    job_id = posting.get("jobReqId", "")
    description_html = posting.get("jobDescription", "")

    description = re.sub(r"<[^>]+>", " ", description_html)
    description = re.sub(r"\s+", " ", description).strip()

    return json.dumps({
        "role_title": title,
        "location": location,
        "job_id": job_id,
        "organization": data.get("hiringOrganization", {}).get("name", company),
        "description": description,
        "source_url": url,
    })


def create_agent() -> tuple[Agent, list[MCPServerStdio]]:
    """Create the orchestrator agent with all 5 MCP server connections."""

    mcp_servers = [
        MCPServerStdio(
            name="Resume MCP",
            params={
                "command": PYTHON_PATH,
                "args": ["-m", "mcp_servers.resume.server"],
                "cwd": PROJECT_ROOT,
            },
            client_session_timeout_seconds=300,
        ),
        MCPServerStdio(
            name="Filter MCP",
            params={
                "command": PYTHON_PATH,
                "args": ["-m", "mcp_servers.filter.server"],
                "cwd": PROJECT_ROOT,
            },
            client_session_timeout_seconds=300,
        ),
        MCPServerStdio(
            name="GitHub MCP",
            params={
                "command": PYTHON_PATH,
                "args": ["-m", "mcp_servers.github.server"],
                "cwd": PROJECT_ROOT,
            },
            client_session_timeout_seconds=300,
        ),
        MCPServerStdio(
            name="Scoring MCP",
            params={
                "command": PYTHON_PATH,
                "args": ["-m", "mcp_servers.scoring.server"],
                "cwd": PROJECT_ROOT,
            },
            client_session_timeout_seconds=300,
        ),
        MCPServerStdio(
            name="Output MCP",
            params={
                "command": PYTHON_PATH,
                "args": ["-m", "mcp_servers.output.server"],
                "cwd": PROJECT_ROOT,
            },
            client_session_timeout_seconds=300,
        ),
    ]

    agent = Agent(
        name="HR Recruitment Agent",
        instructions=AGENT_INSTRUCTIONS,
        mcp_servers=mcp_servers,
        model="gpt-5.4-mni",
        tools=[WebSearchTool(), fetch_job_posting],
    )

    return agent, mcp_servers


async def run_single(prompt: str) -> str:
    """Run the agent with a single prompt and return the response."""
    agent, mcp_servers = create_agent()

    # Start all MCP servers, run the agent, then shut them down
    async with contextlib.AsyncExitStack() as stack:
        for server in mcp_servers:
            await stack.enter_async_context(server)

        result = await Runner.run(agent, prompt)
        try:
            mlflow.flush_trace_async_logging()
        except Exception:
            pass
        return _clean_citations(result.final_output)


async def run_interactive():
    """Run the agent in interactive chat mode."""
    agent, mcp_servers = create_agent()

    async with contextlib.AsyncExitStack() as stack:
        for server in mcp_servers:
            await stack.enter_async_context(server)

        print("=" * 60)
        print("  Red Hat — HR Recruitment Agent")
        print("=" * 60)
        print("  Type your request. Type 'quit' to exit.")
        print("=" * 60)
        print()

        # Conversation history for multi-turn
        messages = []

        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            if user_input.lower() in ("quit", "exit", "q"):
                print("Goodbye!")
                break

            if not user_input:
                continue

            # Add user message to history
            messages.append({"role": "user", "content": user_input})

            result = await Runner.run(agent, trim_conversation_history(messages))
            try:
                mlflow.flush_trace_async_logging()
            except Exception:
                pass

            response = _clean_citations(result.final_output)
            messages.append({"role": "assistant", "content": response})

            print(f"\nAgent: {response}\n")


import contextlib


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Single prompt mode
        prompt = " ".join(sys.argv[1:])
        print(f"Prompt: {prompt}\n")
        response = asyncio.run(run_single(prompt))
        print(f"Agent: {response}")
    else:
        # Interactive chat mode
        asyncio.run(run_interactive())
