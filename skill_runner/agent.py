"""Task 3 — Agent factory.

``create_skill_agent`` assembles a LangGraph-backed agentic loop that is
constrained to a specific set of skills.  It intentionally does NOT use
``deepagents.create_deep_agent`` because that function hardcodes
``FilesystemMiddleware`` and there is no supported way to remove it
(see AUDIT.md §2).

Instead, ``langchain.agents.create_agent`` is called directly with a
hand-picked minimal middleware stack:

  TodoListMiddleware               — internal planning (write_todos only)
  AnthropicPromptCachingMiddleware — transparent performance aid; ignored on
                                     non-Anthropic models
  PatchToolCallsMiddleware         — safety: patches malformed tool calls
  ModelCallLimitMiddleware         — hard max_turns ceiling

No filesystem tools (ls, read_file, write_file, edit_file, glob, grep) are
registered.  The registered tools are ONLY the skills provided by the caller.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Sequence

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    TodoListMiddleware,
)
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware
from langchain_core.language_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph

from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware

from skill_runner.adapter import skills_to_tools
from skill_runner.prompt import INVESTIGATOR_SYSTEM_PROMPT


def create_skill_agent(
    skills: Sequence[str | Path],
    *,
    max_turns: int = 20,
    model: Optional[BaseChatModel] = None,
    runner_fn: Optional[Callable] = None,
    runner_client=None,
    runner_model_id: Optional[str] = None,
    checkpointer=None,
    name: str = "skill-agent",
) -> CompiledStateGraph:
    """Create a skill-constrained investigative agent.

    The agent loop is provided by LangGraph (the runtime that deepagents is
    built on).  Only the skills listed in ``skills`` are registered as tools.
    No filesystem tools are present.

    Args:
        skills: List of paths to SKILL.md files that define the allowed
                toolset for this agent invocation.
        max_turns: Hard ceiling on the number of model-call turns.  The agent
                   is forcibly stopped after this many iterations regardless of
                   its internal state signal.
        model: Pre-configured ``BaseChatModel``.  When ``None``, the factory
               calls ``skill_runner.bedrock.create_chat_model`` which uses
               Bedrock when AWS credentials are present and falls back to the
               direct Anthropic API for local development.
        runner_fn: Override the Pass 1 execution callable passed to each tool.
                   Useful for testing (pass a mock function).
        runner_client: Pre-built Anthropic client forwarded to the runner.
        runner_model_id: Model ID override forwarded to the runner's API calls.
        checkpointer: Optional LangGraph ``Checkpointer`` for state persistence.
        name: Graph name label (cosmetic).

    Returns:
        A compiled ``CompiledStateGraph`` ready to invoke.

    Example::

        agent = create_skill_agent(
            skills=["skills/web_search.md", "skills/summarize.md"],
            max_turns=10,
        )
        result = agent.invoke(
            {"messages": [{"role": "user", "content": "Research X and summarise"}]},
            config={"configurable": {"thread_id": "session-1"}},
        )
    """
    if model is None:
        from skill_runner.bedrock import create_chat_model  # noqa: PLC0415

        model = create_chat_model()

    # Convert skill paths to LangChain tools
    tools = skills_to_tools(
        list(skills),
        runner_fn=runner_fn,
        client=runner_client,
        model_id=runner_model_id,
    )

    if not tools:
        raise ValueError(
            "create_skill_agent requires at least one skill path in `skills`."
        )

    # Minimal middleware stack — NO FilesystemMiddleware, NO SubAgentMiddleware
    middleware = [
        TodoListMiddleware(),
        AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
        PatchToolCallsMiddleware(),
        ModelCallLimitMiddleware(run_limit=max_turns),
    ]

    return create_agent(
        model,
        tools=tools,
        system_prompt=INVESTIGATOR_SYSTEM_PROMPT,
        middleware=middleware,
        checkpointer=checkpointer,
        name=name,
    ).with_config({"recursion_limit": max(1000, max_turns * 10)})
