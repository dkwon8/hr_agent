"""
Chainlit UI for the HR Recruitment Agent.

Run:
    chainlit run app.py
"""

from __future__ import annotations

import contextlib
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logging.getLogger("mcp").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

import chainlit as cl
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent

from agent import create_agent

import mlflow
from agents import Runner
from agents.stream_events import RawResponsesStreamEvent, RunItemStreamEvent


TOOL_LABELS = {
    "list_resumes": "Listing resumes from Google Drive",
    "list_sorted_resumes": "Listing sorted resumes",
    "read_resume": "Reading resume PDF",
    "parse_resume": "Parsing resume with LLM",
    "parse_all_resumes": "Parsing all resumes",
    "search_candidates": "Searching candidates",
    "check_candidate_location": "Checking candidate location",
    "check_candidate_graduation": "Checking graduation date",
    "filter_candidates": "Filtering candidates",
    "lookup_profile": "Looking up GitHub profile",
    "discover_profile": "Searching for GitHub profile",
    "check_authenticity": "Checking GitHub authenticity",
    "score_candidate": "Scoring candidate against departments",
    "score_all_candidates": "Scoring all candidates",
    "get_department_requirements": "Loading department requirements",
    "generate_report": "Generating pipeline report",
    "sort_resumes": "Sorting resumes into folders",
}


@cl.on_chat_start
async def on_chat_start():
    agent, mcp_servers = create_agent()

    stack = contextlib.AsyncExitStack()
    for server in mcp_servers:
        await stack.enter_async_context(server)

    cl.user_session.set("agent", agent)
    cl.user_session.set("stack", stack)
    cl.user_session.set("messages", [])

    await cl.Message(
        content=(
            "**Red Hat — HR Recruitment Agent**\n\n"
            "I can help you process resumes, filter candidates, "
            "validate GitHub profiles, score applicants, and generate reports.\n\n"
            "Try: *\"List the resumes\"* or *\"Run the full pipeline\"*"
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    agent = cl.user_session.get("agent")
    messages = cl.user_session.get("messages")

    messages.append({"role": "user", "content": message.content})

    msg = cl.Message(content="")
    await msg.send()

    result = Runner.run_streamed(agent, messages)
    active_steps = {}

    async for event in result.stream_events():
        if isinstance(event, RawResponsesStreamEvent):
            if isinstance(event.data, ResponseTextDeltaEvent):
                await msg.stream_token(event.data.delta)

        elif isinstance(event, RunItemStreamEvent):
            if event.name == "tool_called":
                raw = event.item.raw_item
                tool_name = getattr(raw, "name", "") or ""
                call_id = getattr(raw, "call_id", "") or tool_name
                label = TOOL_LABELS.get(tool_name, f"Running {tool_name}")

                step = cl.Step(name=label, type="tool")
                step.input = tool_name
                await step.send()
                active_steps[call_id] = step

            elif event.name == "tool_output":
                raw = event.item.raw_item
                call_id = getattr(raw, "call_id", "")
                step = active_steps.pop(call_id, None)
                if step:
                    output = getattr(raw, "output", "")
                    if len(output) > 500:
                        step.output = output[:500] + "..."
                    else:
                        step.output = output
                    await step.update()

    for step in active_steps.values():
        await step.update()

    response = result.final_output
    messages.append({"role": "assistant", "content": response})
    cl.user_session.set("messages", messages)

    msg.content = response
    await msg.update()

    mlflow.flush_trace_async_logging()


@cl.on_chat_end
async def on_chat_end():
    stack = cl.user_session.get("stack")
    if stack:
        await stack.aclose()
