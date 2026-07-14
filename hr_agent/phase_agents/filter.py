"""
Filter Phase Agent — applies deterministic rules to filter candidates.

Connects to the Filter MCP server to check location and graduation date
against Red Hat's hiring requirements. No LLM scoring cost — pure rules.

Run standalone:
    python -m phase_agents.filter "Filter these candidates for Boston and Raleigh"

How it works:
    1. Spawns the Filter MCP server as a stdio subprocess
    2. Receives candidates (as JSON) and a prompt
    3. GPT-5.4 decides which filter tools to call
    4. Returns passed/rejected lists with reasons
"""

from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from agents import Agent, Runner
from agents.mcp import MCPServerStdio


FILTER_MCP_PATH = os.path.join(os.path.dirname(__file__), "..", "mcp_servers", "filter", "server.py")
PYTHON_PATH = sys.executable


def create_filter_agent() -> tuple[Agent, MCPServerStdio]:
    """Create the filter agent and its MCP server connection."""

    filter_mcp = MCPServerStdio(
        name="Filter MCP",
        params={
            "command": PYTHON_PATH,
            "args": ["-m", "mcp_servers.filter.server"],
            "cwd": os.path.join(os.path.dirname(__file__), ".."),
        },
    )

    agent = Agent(
        name="Filter Agent",
        instructions=(
            "You are a candidate filtering assistant for Red Hat's Global Engineering "
            "internship hiring pipeline. Your job is to apply deterministic rules.\n\n"
            "You can:\n"
            "- Check if a candidate's location matches target hiring areas "
            "(Boston, Raleigh, Remote by default)\n"
            "- Check if a candidate's graduation date falls within the hiring window\n"
            "- Filter a full list of candidates, separating passed from rejected\n\n"
            "When filtering candidates, always report:\n"
            "- How many passed and how many were rejected\n"
            "- The specific reason each rejected candidate failed\n"
            "- No LLM scoring is used — these are pure rule-based checks"
        ),
        mcp_servers=[filter_mcp],
        model="gpt-5.4",
    )

    return agent, filter_mcp


async def run_filter(prompt: str) -> str:
    """Run the filter agent with a prompt and return the response."""
    agent, filter_mcp = create_filter_agent()

    async with filter_mcp:
        result = await Runner.run(agent, prompt)
        return result.final_output


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m phase_agents.filter \"<prompt>\"")
        sys.exit(1)

    prompt = " ".join(sys.argv[1:])
    print(f"Prompt: {prompt}\n")
    response = asyncio.run(run_filter(prompt))
    print(f"Agent: {response}")
