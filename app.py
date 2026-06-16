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

from agent import create_agent

from agents import Runner


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

    result = await Runner.run(agent, messages)
    response = result.final_output

    messages.append({"role": "assistant", "content": response})
    cl.user_session.set("messages", messages)

    msg.content = response
    await msg.update()


@cl.on_chat_end
async def on_chat_end():
    stack = cl.user_session.get("stack")
    if stack:
        await stack.aclose()
