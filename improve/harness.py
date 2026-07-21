"""
Coding harness abstraction — invokes external coding tools to apply improvements.

Supports Claude Code (via CLI subprocess) initially. Designed to be extended
with additional harnesses (Cursor, Codex, etc.) by adding implementations.

The harness creates a branch, runs the coding tool, commits, and creates a PR.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class HarnessEvent:
    """A progress event from the coding harness."""
    type: str  # "progress", "error", "done"
    content: str
    metadata: dict = field(default_factory=dict)


def validate_repo(path_or_url: str) -> str:
    """Validate and resolve a repo path.

    For local paths: verifies the directory exists and contains code files.
    For URLs: returns the URL for the harness to clone (future enhancement).

    Returns:
        Resolved absolute path or URL string.

    Raises:
        ValueError: If the path doesn't exist or isn't a valid repo.
    """
    path = os.path.expanduser(path_or_url.strip())

    if path.startswith(("http://", "https://", "git@")):
        return path

    path = os.path.abspath(path)
    if not os.path.isdir(path):
        raise ValueError(f"Directory not found: {path}")

    has_code = any(
        f.endswith((".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java", ".rb"))
        for f in os.listdir(path)
        if os.path.isfile(os.path.join(path, f))
    )
    has_subdir_code = any(
        os.path.isdir(os.path.join(path, d)) for d in os.listdir(path)
        if not d.startswith(".")
    )

    if not has_code and not has_subdir_code:
        raise ValueError(f"No code files found in: {path}")

    return path


def create_branch(repo_path: str, mode: str = "improve") -> str | None:
    """Create a new git branch for the fix.

    Returns the branch name, or None if git operations fail.
    """
    ts = str(int(time.time()))
    prefix = "improve/self-heal" if mode == "heal" else "improve/optimize"
    branch_name = f"{prefix}-{ts}"

    try:
        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=repo_path, capture_output=True, text=True, check=True,
        )
        return branch_name
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def commit_and_pr(repo_path: str, branch_name: str, title: str, body: str) -> dict:
    """Stage all changes, commit, push, and create a PR.

    Returns a dict with keys: committed, pushed, pr_url (each may be None on failure).
    """
    result = {"committed": False, "pushed": False, "pr_url": None}

    try:
        diff = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=repo_path, capture_output=True, text=True,
        )
        if not diff.stdout.strip():
            return result

        subprocess.run(
            ["git", "add", "-A"],
            cwd=repo_path, capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", title],
            cwd=repo_path, capture_output=True, text=True, check=True,
        )
        result["committed"] = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return result

    try:
        subprocess.run(
            ["git", "push", "-u", "origin", branch_name],
            cwd=repo_path, capture_output=True, text=True, check=True,
        )
        result["pushed"] = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return result

    gh = shutil.which("gh")
    if not gh:
        return result

    try:
        pr = subprocess.run(
            [gh, "pr", "create", "--title", title, "--body", body, "--head", branch_name],
            cwd=repo_path, capture_output=True, text=True, check=True,
        )
        url = pr.stdout.strip()
        if url:
            result["pr_url"] = url
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    return result


def restore_branch(repo_path: str, original_branch: str) -> None:
    """Switch back to the original branch after harness work."""
    try:
        subprocess.run(
            ["git", "checkout", original_branch],
            cwd=repo_path, capture_output=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass


def get_current_branch(repo_path: str) -> str:
    """Get the current git branch name."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path, capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "main"


async def run_harness(
    repo_path: str,
    prompt: str,
    harness_type: str = "claude_code",
) -> AsyncIterator[HarnessEvent]:
    """Run a coding harness against a repo with the given prompt.

    Yields HarnessEvent objects as the harness produces output.
    """
    if harness_type == "claude_code":
        async for event in _run_claude_code(repo_path, prompt):
            yield event
    else:
        yield HarnessEvent(
            type="error",
            content=f"Unknown harness type: {harness_type}. Supported: claude_code",
        )


async def run_followup(
    repo_path: str,
    branch_name: str,
    feedback: str,
    harness_type: str = "claude_code",
) -> AsyncIterator[HarnessEvent]:
    """Run a follow-up prompt on an existing branch for iterative feedback."""
    try:
        subprocess.run(
            ["git", "checkout", branch_name],
            cwd=repo_path, capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        yield HarnessEvent(
            type="error",
            content=f"Could not checkout branch: {branch_name}",
        )
        return

    prompt = (
        f"You are continuing to improve code on branch '{branch_name}'. "
        f"The user reviewed the previous changes and has feedback:\n\n"
        f"{feedback}\n\n"
        f"Make the requested changes. Keep changes minimal and focused."
    )

    async for event in run_harness(repo_path, prompt, harness_type):
        yield event

    try:
        diff = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=repo_path, capture_output=True, text=True,
        )
        if diff.stdout.strip():
            subprocess.run(
                ["git", "add", "-A"],
                cwd=repo_path, capture_output=True, check=True,
            )
            subprocess.run(
                ["git", "commit", "-m", f"improve: address feedback"],
                cwd=repo_path, capture_output=True, text=True, check=True,
            )
            subprocess.run(
                ["git", "push"],
                cwd=repo_path, capture_output=True, text=True, check=True,
            )
            yield HarnessEvent(
                type="progress",
                content="Follow-up changes committed and pushed.",
            )
    except (subprocess.CalledProcessError, FileNotFoundError):
        yield HarnessEvent(
            type="progress",
            content="Changes made but could not commit/push automatically.",
        )


async def _run_claude_code(repo_path: str, prompt: str) -> AsyncIterator[HarnessEvent]:
    """Invoke Claude Code CLI as a subprocess."""
    claude_path = shutil.which("claude")
    if not claude_path:
        yield HarnessEvent(
            type="error",
            content="Claude Code CLI not found. Install it with: npm install -g @anthropic-ai/claude-code",
        )
        return

    yield HarnessEvent(
        type="progress",
        content=f"Starting Claude Code in {repo_path}...",
    )

    cmd = [
        claude_path,
        "-p", prompt,
        "--allowedTools", "Edit,Read,Glob,Grep,Write,Bash",
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=repo_path,
        )

        async def read_stream(stream, is_stderr=False):
            events = []
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    events.append(HarnessEvent(
                        type="progress" if not is_stderr else "error",
                        content=text,
                    ))
            return events

        stdout_task = asyncio.create_task(read_stream(process.stdout))
        stderr_task = asyncio.create_task(read_stream(process.stderr))

        stdout_events = await stdout_task
        stderr_events = await stderr_task

        for event in stdout_events:
            yield event
        for event in stderr_events:
            yield event

        await process.wait()

        if process.returncode == 0:
            yield HarnessEvent(
                type="done",
                content="Claude Code completed successfully.",
                metadata={"exit_code": 0},
            )
        else:
            yield HarnessEvent(
                type="done",
                content=f"Claude Code exited with code {process.returncode}.",
                metadata={"exit_code": process.returncode},
            )

    except Exception as e:
        yield HarnessEvent(
            type="error",
            content=f"Failed to run Claude Code: {e}",
        )
