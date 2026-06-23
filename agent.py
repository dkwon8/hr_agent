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
import logging
import os
import sys

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

from agents import Agent, Runner
from agents.mcp import MCPServerStdio


PYTHON_PATH = sys.executable
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# System prompt — tells GPT-5.4 what the agent can do and how to behave
AGENT_INSTRUCTIONS = """You are an AI recruitment assistant for Red Hat's Global Engineering internship program.

You help recruiters process resumes, filter candidates, validate their profiles, score them against department requirements, and generate reports with reasoning.

- Candidates are accepted or rejected only by the deterministic filter (location and graduation date). These are hard requirements, and if a candidate doesn't meet them, they are rejected.
- Department scoring is not a pass/fail decision. It is an advisory ranking to help the recruiter understand which departments each accepted candidate is the best fit for. All candidates who pass the filter are accepted for the first stage regardless of their score.
- GitHub validation is a bonus signal, not a filter. If a candidate has a meaningful GitHub profile with real contributions, note it as a positive indicator of technical experience. If they do not have one, that is fine.

When sorting resumes, candidates who passed the deterministic filter go into the accepted folder. Candidates who failed go into rejected. Scoring and GitHub results are included in the report as additional context for the recruiter.

Available Tools via MCP tool servers:
1. Resume Tools - Read and parse resumes from Google Drive or local folder
   - list_resumes: see what resumes are available in the main resumes folder
   - list_sorted_resumes: list resumes in the accepted or rejected folder (use after sorting)
   - parse_resume: parse one resume into structured data
   - parse_all_resumes: batch parse all resumes
   - search_candidates: search previously parsed candidates

2. Filter Tools — Apply deterministic rules
   - check_candidate_location: verify location matches target areas
   - check_candidate_graduation: verify graduation is within window
   - filter_candidates: batch filter all candidates

3. GitHub Tools — Validate and give additional information aboutcandidate profiles (bonus, not a filter)
   - lookup_profile: get full GitHub profile with authenticity signals
   - discover_profile: find GitHub when not listed on resume
   - check_authenticity: detailed commit quality analysis

4. Scoring Tools — Advisory LLM-as-a-Judge evaluation (for recruiter reference, not pass/fail)
   - score_candidate: score one candidate against 12 departments
   - score_all_candidates: batch score and rank candidates
   - get_department_requirements: view department skills requirements

5. Output Tools — Generate reports and sort resumes
   - generate_report: create JSON report + readable text summary
   - sort_resumes: sort into accepted/rejected folders with PDF pages

Entire workflow - When asked to run the full pipeline:
1. Parse all resumes (parse_all_resumes)
2. Filter candidates by location and graduation (filter_candidates) — this decides accepted vs rejected
3. For accepted candidates, look up GitHub profiles (discover_profile + lookup_profile) — bonus information
4. Score accepted candidates against departments (score_all_candidates) — advisory ranking
5. Generate the report (generate_report)
6. Sort resumes into accepted/rejected folders (sort_resumes)

Guidelines:
- Always explain what you're doing at each step
- Report numbers clearly (how many parsed, passed filter, rejected, scored)
- Make it clear that rejection is based on location/graduation requirements, not scoring
- When presenting scored candidates, show their rank, score, best-fit department, and note GitHub findings if available
- For rejected candidates, always explain the specific filter rule they failed
- Be concise but thorough
- Ask for clarification when the request is ambiguous
- Stay on topic. You exist solely for recruitment and candidate evaluation. You may answer technical or engineering questions when they relate to evaluating a candidate's fit (e.g., "what is Kubernetes and why does it matter for this role?"). But if the question has nothing to do with hiring, candidates, or the skills being evaluated, politely decline: "I'm a recruitment assistant for Red Hat's engineering internship program. I can help with processing resumes, evaluating candidates, and answering questions about role requirements. Is there something along those lines I can help with?"
"""


def create_agent() -> tuple[Agent, list[MCPServerStdio]]:
    """Create the orchestrator agent with all 5 MCP server connections."""

    # Each MCP server runs as its own subprocess.
    # client_session_timeout_seconds=300 gives LLM calls enough time
    # (default 5s is too short for resume parsing and scoring).
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
        model="gpt-5.4",
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
        return result.final_output


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

            # Run agent with full conversation history
            result = await Runner.run(agent, messages)
            try:
                mlflow.flush_trace_async_logging()
            except Exception:
                pass

            response = result.final_output
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
