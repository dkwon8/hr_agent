"""
Scoring Phase Agent — scores candidates against department requirements.

Connects to the Scoring MCP server to evaluate candidates using
LLM-as-a-Judge against all 12 Red Hat Global Engineering departments.
Uses 3-pass median scoring for reliable results.

Run standalone:
    python -m phase_agents.scoring "Score these candidates"

How it works:
    1. Spawns the Scoring MCP server as a stdio subprocess
    2. Receives candidate data and a prompt
    3. GPT-5.4 calls score_candidate or score_all_candidates
    4. Each candidate is scored 3 times, median is used
    5. Returns ranked candidates with department fits and confidence ranges
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


def create_scoring_agent() -> tuple[Agent, MCPServerStdio]:
    """Create the scoring agent and its MCP server connection."""

    scoring_mcp = MCPServerStdio(
        name="Scoring MCP",
        params={
            "command": PYTHON_PATH,
            "args": ["-m", "mcp_servers.scoring.server"],
            "cwd": os.path.join(os.path.dirname(__file__), ".."),
        },
    )

    agent = Agent(
        name="Scoring Agent",
        instructions=(
            "You are a candidate scoring assistant for Red Hat's Global Engineering "
            "internship hiring pipeline. Your job is to evaluate candidates against "
            "department requirements using LLM-as-a-Judge.\n\n"
            "You can:\n"
            "- Score a single candidate against all 12 GE departments\n"
            "- Score all candidates and rank them, selecting the top K\n"
            "- View the department requirements and their required skills\n\n"
            "Scoring dimensions (per department):\n"
            "- Skills match (0-40): evidence of required skills\n"
            "- Experience relevance (0-35): relevant work/project experience\n"
            "- Potential (0-25): growth trajectory and learning signals\n\n"
            "Each candidate is scored 3 times and the median is used for stability. "
            "Report the confidence range (±X points) for each candidate.\n\n"
            "When presenting results, always include:\n"
            "- Ranked list with scores and best-fit departments\n"
            "- Top 3 department fits per candidate\n"
            "- Key reasoning for the best-fit department"
        ),
        mcp_servers=[scoring_mcp],
        model="gpt-5.4",
    )

    return agent, scoring_mcp


async def run_scoring(prompt: str) -> str:
    """Run the scoring agent with a prompt and return the response."""
    agent, scoring_mcp = create_scoring_agent()

    async with scoring_mcp:
        result = await Runner.run(agent, prompt)
        return result.final_output


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m phase_agents.scoring \"<prompt>\"")
        sys.exit(1)

    prompt = " ".join(sys.argv[1:])
    print(f"Prompt: {prompt}\n")
    response = asyncio.run(run_scoring(prompt))
    print(f"Agent: {response}")
