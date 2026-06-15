"""
Ingestion Phase Agent — reads and parses resumes.

Connects to the Resume MCP server to access resumes from Google Drive
(or local folder), extract text, and parse into structured candidate data.

Run standalone:
    python -m phase_agents.ingestion "Parse all resumes from the shared folder"
    python -m phase_agents.ingestion "How many resumes are available?"

How it works:
    1. Spawns the Resume MCP server as a stdio subprocess
    2. The agent receives a user prompt
    3. GPT-5.4 decides which Resume MCP tools to call
    4. Tools execute (list files, extract PDF text, parse with LLM)
    5. Agent returns structured candidate data or answers the question
"""

from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv

# Load env before importing agents SDK (needs OPENAI_API_KEY)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from agents import Agent, Runner
from agents.mcp import MCPServerStdio


# Path to the Resume MCP server script
RESUME_MCP_PATH = os.path.join(os.path.dirname(__file__), "..", "mcp_servers", "resume", "server.py")

# Python executable from the venv
PYTHON_PATH = sys.executable


def create_ingestion_agent() -> tuple[Agent, MCPServerStdio]:
    """Create the ingestion agent and its MCP server connection.

    Returns the agent and the MCP server (which must be used as an
    async context manager to start/stop the subprocess).
    """

    # This tells the SDK to spawn our Resume MCP server as a subprocess.
    # The agent communicates with it via stdin/stdout (stdio protocol).
    resume_mcp = MCPServerStdio(
        name="Resume MCP",
        params={
            "command": PYTHON_PATH,
            "args": ["-m", "mcp_servers.resume.server"],
            "cwd": os.path.join(os.path.dirname(__file__), ".."),
        },
    )

    # The agent itself — GPT-5.4 with access to the Resume MCP tools.
    # The instructions tell the LLM what it can do and how to behave.
    agent = Agent(
        name="Ingestion Agent",
        instructions=(
            "You are a resume ingestion assistant for Red Hat's Global Engineering "
            "internship hiring pipeline. Your job is to read and parse resumes.\n\n"
            "You can:\n"
            "- List available resumes (from Google Drive or local folder)\n"
            "- Read raw text from a specific resume PDF\n"
            "- Parse a resume into structured candidate data (name, skills, graduation, etc.)\n"
            "- Parse all resumes in a folder at once\n"
            "- Search through previously parsed candidates\n\n"
            "When asked to process resumes, use parse_all_resumes to batch process them. "
            "Always report how many resumes were found, how many parsed successfully, "
            "and any errors encountered."
        ),
        mcp_servers=[resume_mcp],
        model="gpt-5.4",
    )

    return agent, resume_mcp


async def run_ingestion(prompt: str) -> str:
    """Run the ingestion agent with a prompt and return the response."""
    agent, resume_mcp = create_ingestion_agent()

    # The MCP server runs as a subprocess — we need to start it,
    # run the agent, then shut it down.
    async with resume_mcp:
        result = await Runner.run(agent, prompt)
        return result.final_output


# ── Entry Point ───────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m phase_agents.ingestion \"<prompt>\"")
        print("Example: python -m phase_agents.ingestion \"Parse all resumes\"")
        sys.exit(1)

    prompt = " ".join(sys.argv[1:])
    print(f"Prompt: {prompt}\n")

    response = asyncio.run(run_ingestion(prompt))
    print(f"Agent: {response}")
