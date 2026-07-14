"""
Output Phase Agent — generates reports and sorts resumes.

Connects to the Output MCP server to produce pipeline reports and
sort resumes into accepted/rejected folders (local or Google Drive)
with appended summary pages.

Run standalone:
    python -m phase_agents.output "Generate the report for these candidates"

How it works:
    1. Spawns the Output MCP server as a stdio subprocess
    2. Receives scored candidate data and a prompt
    3. GPT-5.4 calls generate_report and/or sort_resumes
    4. Report saved as JSON with a readable text summary
    5. Resumes sorted into accepted/rejected with PDF pages appended
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


def create_output_agent() -> tuple[Agent, MCPServerStdio]:
    """Create the output agent and its MCP server connection."""

    output_mcp = MCPServerStdio(
        name="Output MCP",
        params={
            "command": PYTHON_PATH,
            "args": ["-m", "mcp_servers.output.server"],
            "cwd": os.path.join(os.path.dirname(__file__), ".."),
        },
    )

    agent = Agent(
        name="Output Agent",
        instructions=(
            "You are a report generation assistant for Red Hat's Global Engineering "
            "internship hiring pipeline. Your job is to produce final outputs.\n\n"
            "You can:\n"
            "- Generate a pipeline report (JSON + readable text summary)\n"
            "- Sort resumes into accepted/rejected folders with summary pages\n\n"
            "When generating reports, always show the text summary to the user. "
            "The JSON file is saved for other tools to reference.\n\n"
            "When sorting resumes:\n"
            "- Accepted resumes get a page with scoring summary appended\n"
            "- Rejected resumes get a page with the rejection reason appended\n"
            "- Files go to Google Drive if configured, otherwise local folders"
        ),
        mcp_servers=[output_mcp],
        model="gpt-5.4",
    )

    return agent, output_mcp


async def run_output(prompt: str) -> str:
    """Run the output agent with a prompt and return the response."""
    agent, output_mcp = create_output_agent()

    async with output_mcp:
        result = await Runner.run(agent, prompt)
        return result.final_output


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m phase_agents.output \"<prompt>\"")
        sys.exit(1)

    prompt = " ".join(sys.argv[1:])
    print(f"Prompt: {prompt}\n")
    response = asyncio.run(run_output(prompt))
    print(f"Agent: {response}")
