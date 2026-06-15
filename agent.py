"""
HR Recruitment Agent — master orchestrator.

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

from agents import Agent, Runner
from agents.mcp import MCPServerStdio


PYTHON_PATH = sys.executable
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# System prompt — tells GPT-5.4 what the agent can do and how to behave
AGENT_INSTRUCTIONS = """You are an AI recruitment assistant for Red Hat's Global Engineering internship program.

You help recruiters process resumes, filter candidates, validate their profiles, score them against department requirements, and generate reports with reasoning.

AVAILABLE CAPABILITIES (via MCP tool servers):

1. **Resume Tools** — Read and parse resumes from Google Drive or local folder
   - list_resumes: see what resumes are available
   - parse_resume: parse one resume into structured data
   - parse_all_resumes: batch parse all resumes
   - search_candidates: search previously parsed candidates

2. **Filter Tools** — Apply deterministic rules (no LLM cost)
   - check_candidate_location: verify location matches target areas
   - check_candidate_graduation: verify graduation is within window
   - filter_candidates: batch filter all candidates

3. **GitHub Tools** — Validate and enrich candidate profiles
   - lookup_profile: get full GitHub profile with authenticity signals
   - discover_profile: find GitHub when not listed on resume
   - check_authenticity: detailed commit quality analysis

4. **Scoring Tools** — LLM-as-a-Judge evaluation
   - score_candidate: score one candidate against 12 departments
   - score_all_candidates: batch score and rank, select top K
   - get_department_requirements: view department skills requirements

5. **Output Tools** — Generate reports and sort resumes
   - generate_report: create JSON report + readable text summary
   - sort_resumes: sort into accepted/rejected folders with PDF pages

WORKFLOW — When asked to run the full pipeline:
1. Parse all resumes (parse_all_resumes)
2. Filter candidates by location and graduation (filter_candidates)
3. For candidates who passed, validate via GitHub (discover_profile + lookup_profile)
4. Score remaining candidates against departments (score_all_candidates)
5. Generate the report (generate_report)
6. Sort resumes into folders (sort_resumes)

GUIDELINES:
- Always explain what you're doing at each step
- Report numbers clearly (how many parsed, passed, rejected, scored)
- When presenting scored candidates, show their rank, score, confidence range, and best-fit department
- For rejected candidates, always explain the specific reason
- Be concise but thorough
- Ask for clarification when the request is ambiguous
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

            # Add agent response to history
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
