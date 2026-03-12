"""Task 2 — Skill-to-tool adapter.

Converts a SKILL.md file into a LangChain ``StructuredTool`` that the agent
loop can call.  The tool's callable delegates to the runner's Pass 1 execution
function (``execute_skill``), which handles all Claude API interactions.

No direct Claude API calls happen inside this module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from skill_runner.runner import (
    execute_skill,
    parse_skill_description,
    skill_name_from_path,
)


class SkillInput(BaseModel):
    """Input schema for any skill tool."""

    input: str = Field(
        description="The request or query to pass to the skill."
    )


def skill_to_tool(
    skill_path: str | Path,
    runner_fn: Optional[Callable] = None,
    client=None,
    model_id: Optional[str] = None,
) -> StructuredTool:
    """Convert a SKILL.md file into a LangChain tool.

    Args:
        skill_path: Path to the SKILL.md file.
        runner_fn: Override the execution callable.  Defaults to
                   ``execute_skill``.  Must accept ``(skill_path, user_input,
                   **kwargs)`` and return a string.
        client: Pre-built Anthropic client forwarded to the runner.
        model_id: Model ID override forwarded to the runner.

    Returns:
        A ``StructuredTool`` whose name is derived from the SKILL.md filename,
        whose description is derived from the SKILL.md content, and whose
        callable invokes the runner's Pass 1 function.

    Raises:
        FileNotFoundError: If ``skill_path`` does not exist.
    """
    skill_path = Path(skill_path)
    if not skill_path.exists():
        raise FileNotFoundError(f"SKILL.md not found: {skill_path}")

    name = skill_name_from_path(skill_path)
    description = parse_skill_description(skill_path)
    resolved_runner = runner_fn or execute_skill

    # Capture path / client / model in closure — no mutable global state
    _skill_path = skill_path
    _client = client
    _model_id = model_id

    def _run(input: str) -> str:  # noqa: A002
        return resolved_runner(
            _skill_path,
            input,
            client=_client,
            model_id=_model_id,
        )

    async def _arun(input: str) -> str:  # noqa: A002
        # Run synchronous runner in a thread to avoid blocking the event loop
        import asyncio  # noqa: PLC0415

        return await asyncio.to_thread(
            resolved_runner,
            _skill_path,
            input,
            client=_client,
            model_id=_model_id,
        )

    return StructuredTool(
        name=name,
        description=description,
        args_schema=SkillInput,
        func=_run,
        coroutine=_arun,
    )


def skills_to_tools(
    skill_paths: list[str | Path],
    runner_fn: Optional[Callable] = None,
    client=None,
    model_id: Optional[str] = None,
) -> list[StructuredTool]:
    """Convert a list of SKILL.md paths into a list of LangChain tools.

    Args:
        skill_paths: List of paths to SKILL.md files.
        runner_fn: Override the execution callable (applied to all tools).
        client: Pre-built Anthropic client forwarded to each tool.
        model_id: Model ID override forwarded to each tool.

    Returns:
        List of ``StructuredTool`` instances, one per skill.
    """
    return [
        skill_to_tool(sp, runner_fn=runner_fn, client=client, model_id=model_id)
        for sp in skill_paths
    ]
