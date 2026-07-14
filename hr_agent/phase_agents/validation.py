"""
Validation Phase Agent — cross-validates candidate profiles via GitHub.

Connects to the GitHub MCP server to look up profiles, discover profiles
for candidates who didn't list GitHub on their resume, and assess
the authenticity of their work.

Run standalone:
    python -m phase_agents.validation "Check GitHub for these candidates"

How it works:
    1. Spawns the GitHub MCP server as a stdio subprocess
    2. For each candidate, looks up or discovers their GitHub profile
    3. Assesses commit quality, activity, and authenticity
    4. Returns enriched candidate data with validation notes
"""

from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from agents import Agent, Runner
from agents.mcp import MCPServerStdio


PYTHON_PATH = sys.executable


def create_validation_agent() -> tuple[Agent, MCPServerStdio]:
    """Create the validation agent and its MCP server connection."""

    github_mcp = MCPServerStdio(
        name="GitHub MCP",
        params={
            "command": PYTHON_PATH,
            "args": ["-m", "mcp_servers.github.server"],
            "cwd": os.path.join(os.path.dirname(__file__), ".."),
        },
    )

    agent = Agent(
        name="Validation Agent",
        instructions=(
            "You are a profile validation assistant for Red Hat's Global Engineering "
            "internship hiring pipeline. Your job is to cross-validate candidates "
            "via their GitHub profiles.\n\n"
            "You can:\n"
            "- Look up a GitHub profile by URL (get repos, languages, activity)\n"
            "- Discover a GitHub profile by email or name when not listed on resume\n"
            "- Check the authenticity of a GitHub profile (commit quality, activity flags)\n\n"
            "For each candidate:\n"
            "1. If they have a GitHub URL, use lookup_profile\n"
            "2. If they don't, try discover_profile using their email and university\n"
            "3. Report what you found: repos, languages, activity status, commit quality\n"
            "4. Flag any concerns (all forks, no activity, low-effort commits)\n\n"
            "Always be clear about confidence levels when discovering profiles — "
            "a high-confidence email match is reliable, a name search match may be wrong."
        ),
        mcp_servers=[github_mcp],
        model="gpt-5.4",
    )

    return agent, github_mcp


async def run_validation(prompt: str) -> str:
    """Run the validation agent with a prompt and return the response."""
    agent, github_mcp = create_validation_agent()

    async with github_mcp:
        result = await Runner.run(agent, prompt)
        return result.final_output


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m phase_agents.validation \"<prompt>\"")
        sys.exit(1)

    prompt = " ".join(sys.argv[1:])
    print(f"Prompt: {prompt}\n")
    response = asyncio.run(run_validation(prompt))
    print(f"Agent: {response}")
