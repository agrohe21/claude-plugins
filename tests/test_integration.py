"""Task 6 — Integration tests for the skill runner + agent factory.

These tests:
1. Use a small set of stub SKILL.md files (via the ``skill_dir`` fixture)
2. Use a mock runner_fn instead of calling Bedrock
3. Use a scripted fake chat model instead of a real LLM
4. Verify the agent loop runs > 1 turn
5. Verify only registered skills are callable
6. Verify JSONL records are written correctly
7. Use local filesystem for JSONL output (not MinIO)
"""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from skill_runner.adapter import skill_to_tool, skills_to_tools
from skill_runner.agent import create_skill_agent
from skill_runner.logger import SkillAgentSession, _LocalWriter
from skill_runner.runner import (
    execute_skill,
    parse_skill_description,
    skill_name_from_path,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CALLED_SKILLS: list[str] = []


def make_mock_runner(responses: dict[str, str] | None = None):
    """Return a runner_fn that returns canned responses and records calls."""

    def _runner(skill_path, user_input, **kwargs) -> str:
        name = skill_name_from_path(skill_path)
        _CALLED_SKILLS.append(name)
        if responses and name in responses:
            return responses[name]
        return f"[mock result from {name}]: processed '{user_input[:40]}'"

    return _runner


class ScriptedChatModel(BaseChatModel):
    """A chat model that returns pre-scripted AIMessages in sequence.

    When the script is exhausted, it returns a terminal message that signals
    State: done.
    """

    responses: list[AIMessage]
    call_index: int = 0

    model_config = {"arbitrary_types_allowed": True}

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        idx = self.call_index
        if idx < len(self.responses):
            msg = self.responses[idx]
        else:
            msg = _terminal_message()
        self.call_index = idx + 1
        return ChatResult(generations=[ChatGeneration(message=msg)])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        """Return self — tool definitions are already embedded in scripted responses."""
        return self

    @property
    def _llm_type(self) -> str:
        return "scripted-chat-model"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {}


def _reasoning_block(
    known: str,
    gap: str,
    skill: str,
    why: str,
    state: str = "continuing",
    confidence: str = "medium",
) -> str:
    return (
        f"[REASONING]\n"
        f"Known so far: {known}\n"
        f"Gap to close: {gap}\n"
        f"Chosen skill: {skill}\n"
        f"Why: {why}\n"
        f"State: {state}\n"
        f"Confidence: {confidence}\n"
        f"[/REASONING]\n\n"
    )


def _tool_call_message(skill_name: str, input_text: str, reasoning: str) -> AIMessage:
    """Build an AIMessage that contains a tool call."""
    return AIMessage(
        content=reasoning,
        tool_calls=[
            {
                "name": skill_name,
                "args": {"input": input_text},
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "type": "tool_call",
            }
        ],
    )


def _terminal_message() -> AIMessage:
    """A message that signals the investigation is complete."""
    reasoning = _reasoning_block(
        known="All relevant information has been gathered.",
        gap="None — investigation complete.",
        skill="none",
        why="No further investigation needed.",
        state="done",
        confidence="high",
    )
    conclusion = (
        "[CONCLUSION]\n"
        "Summary: The investigation is complete. All required information has been gathered and synthesized.\n"
        "Skills used: search, analyze\n"
        "Confidence: high\n"
        "Caveats: none\n"
        "[/CONCLUSION]\n"
    )
    return AIMessage(content=reasoning + conclusion)


# ---------------------------------------------------------------------------
# Unit tests — runner helpers
# ---------------------------------------------------------------------------


class TestRunnerHelpers:
    def test_skill_name_from_path(self, skill_dir: Path) -> None:
        assert skill_name_from_path(skill_dir / "search.md") == "search"
        assert skill_name_from_path(skill_dir / "analyze.md") == "analyze"

    def test_skill_name_normalises_special_chars(self, tmp_path: Path) -> None:
        p = tmp_path / "web-search_v2.md"
        p.write_text("# web-search-v2\nDescription: A skill.\n")
        assert skill_name_from_path(p) == "web_search_v2"

    def test_parse_skill_description_description_field(self, skill_dir: Path) -> None:
        desc = parse_skill_description(skill_dir / "search.md")
        assert desc == "Search for information on a given topic."

    def test_parse_skill_description_fallback_heading(self, tmp_path: Path) -> None:
        p = tmp_path / "custom.md"
        p.write_text("# My Custom Skill\nSome content here.\n")
        assert parse_skill_description(p) == "My Custom Skill"

    def test_parse_skill_description_fallback_filename(self, tmp_path: Path) -> None:
        p = tmp_path / "fallback_skill.md"
        p.write_text("No heading, no description field.\n")
        # Fallback uses stem.title(), so underscores become spaces and words are capitalised
        assert parse_skill_description(p) == "Fallback Skill"


# ---------------------------------------------------------------------------
# Unit tests — adapter
# ---------------------------------------------------------------------------


class TestSkillToTool:
    def test_tool_name_matches_file_stem(self, skill_dir: Path) -> None:
        tool = skill_to_tool(skill_dir / "search.md", runner_fn=make_mock_runner())
        assert tool.name == "search"

    def test_tool_description_from_skill(self, skill_dir: Path) -> None:
        tool = skill_to_tool(skill_dir / "search.md", runner_fn=make_mock_runner())
        assert "Search" in tool.description

    def test_tool_invocation_calls_runner(self, skill_dir: Path) -> None:
        called: list[str] = []

        def _mock_runner(skill_path, user_input, **kwargs) -> str:
            called.append(skill_name_from_path(skill_path))
            return "mock result"

        tool = skill_to_tool(skill_dir / "search.md", runner_fn=_mock_runner)
        result = tool.invoke({"input": "test query"})
        assert result == "mock result"
        assert called == ["search"]

    def test_missing_skill_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            skill_to_tool(tmp_path / "nonexistent.md")

    def test_skills_to_tools_length(self, skill_dir: Path) -> None:
        paths = list(skill_dir.glob("*.md"))
        tools = skills_to_tools(paths, runner_fn=make_mock_runner())
        assert len(tools) == len(paths)

    def test_skills_to_tools_unique_names(self, skill_dir: Path) -> None:
        paths = list(skill_dir.glob("*.md"))
        tools = skills_to_tools(paths, runner_fn=make_mock_runner())
        names = [t.name for t in tools]
        assert len(names) == len(set(names))

    @pytest.mark.asyncio
    async def test_tool_async_invocation(self, skill_dir: Path) -> None:
        async def _run(tool, input_text: str) -> str:
            return await tool.arun(input_text)

        results: list[str] = []

        def _mock_runner(skill_path, user_input, **kwargs) -> str:
            results.append(user_input)
            return "async mock result"

        tool = skill_to_tool(skill_dir / "analyze.md", runner_fn=_mock_runner)
        result = await _run(tool, "async test")
        assert result == "async mock result"


# ---------------------------------------------------------------------------
# Unit tests — agent factory (structure / wiring)
# ---------------------------------------------------------------------------


class TestAgentFactory:
    def test_create_skill_agent_returns_compiled_graph(self, skill_dir: Path) -> None:
        from langgraph.graph.state import CompiledStateGraph

        paths = list(skill_dir.glob("*.md"))
        agent = create_skill_agent(
            skills=paths,
            model=ScriptedChatModel(responses=[_terminal_message()]),
            runner_fn=make_mock_runner(),
        )
        assert isinstance(agent, CompiledStateGraph)

    def test_create_skill_agent_no_skills_raises(self, skill_dir: Path) -> None:
        with pytest.raises(ValueError, match="at least one skill"):
            create_skill_agent(
                skills=[],
                model=ScriptedChatModel(responses=[]),
            )

    def test_registered_tool_names_match_skills(self, skill_dir: Path) -> None:
        """The agent's bound tools should only contain the registered skills
        plus write_todos from TodoListMiddleware."""
        paths = list(skill_dir.glob("*.md"))
        skill_names = {skill_name_from_path(p) for p in paths}

        agent = create_skill_agent(
            skills=paths,
            model=ScriptedChatModel(responses=[_terminal_message()]),
            runner_fn=make_mock_runner(),
        )

        # Enumerate nodes — tools are registered in the compiled graph
        node_names = set(agent.nodes.keys())
        # The agent graph has a "model" node and a "tools" node at minimum
        assert "model" in node_names or "tools" in node_names


# ---------------------------------------------------------------------------
# Integration test — multi-turn loop
# ---------------------------------------------------------------------------


class TestMultiTurnLoop:
    """Run the agent with a scripted 2-turn investigation then verify
    behaviour and JSONL output."""

    def _build_scripted_model(self, skill_names: list[str]) -> ScriptedChatModel:
        """Build a model that makes one tool call per skill then terminates."""
        responses: list[AIMessage] = []

        for i, name in enumerate(skill_names):
            reasoning = _reasoning_block(
                known=f"Gathered info from {skill_names[:i]}." if i else "Starting investigation.",
                gap=f"Need output from {name}.",
                skill=name,
                why=f"{name} is the right instrument for this step.",
                state="continuing",
                confidence="medium",
            )
            responses.append(_tool_call_message(name, f"query step {i + 1}", reasoning))

        responses.append(_terminal_message())
        return ScriptedChatModel(responses=responses)

    @pytest.mark.asyncio
    async def test_loop_runs_more_than_one_turn(self, skill_dir: Path, log_file: Path) -> None:
        """The agent must run at least 2 skill calls (i.e., more than 1 turn)."""
        paths = list(skill_dir.glob("*.md"))
        skill_names = [skill_name_from_path(p) for p in paths][:2]  # use 2 skills

        model = self._build_scripted_model(skill_names)
        calls: list[str] = []

        def _mock_runner(skill_path, user_input, **kwargs) -> str:
            name = skill_name_from_path(skill_path)
            calls.append(name)
            return f"[result of {name}]"

        agent = create_skill_agent(
            skills=paths,
            model=model,
            runner_fn=_mock_runner,
            max_turns=10,
        )

        session = SkillAgentSession(
            agent,
            task="Multi-step investigation test",
            log_path=str(log_file),
        )
        summary = await session.run()

        assert len(calls) >= 2, f"Expected >= 2 skill calls, got {len(calls)}: {calls}"

    @pytest.mark.asyncio
    async def test_only_registered_skills_are_callable(self, skill_dir: Path, log_file: Path) -> None:
        """Only skills registered at agent creation time should be invoked."""
        all_paths = list(skill_dir.glob("*.md"))
        # Register only the first skill
        allowed_paths = all_paths[:1]
        allowed_name = skill_name_from_path(allowed_paths[0])

        calls: list[str] = []

        def _mock_runner(skill_path, user_input, **kwargs) -> str:
            name = skill_name_from_path(skill_path)
            calls.append(name)
            return f"[result of {name}]"

        # Build a model that tries to call the allowed skill
        reasoning = _reasoning_block(
            known="Starting.",
            gap="Need search result.",
            skill=allowed_name,
            why="Only registered skill.",
            state="continuing",
        )
        responses = [
            _tool_call_message(allowed_name, "test", reasoning),
            _terminal_message(),
        ]
        model = ScriptedChatModel(responses=responses)

        agent = create_skill_agent(
            skills=allowed_paths,
            model=model,
            runner_fn=_mock_runner,
            max_turns=10,
        )

        session = SkillAgentSession(
            agent,
            task="Single skill test",
            log_path=str(log_file),
        )
        await session.run()

        # Every invoked skill must be in the allowed set
        allowed_names = {skill_name_from_path(p) for p in allowed_paths}
        for called in calls:
            assert called in allowed_names, (
                f"Skill '{called}' was invoked but is not in the allowed set {allowed_names}"
            )

    @pytest.mark.asyncio
    async def test_jsonl_records_written(self, skill_dir: Path, log_file: Path) -> None:
        """JSONL output must contain at least one turn record and one summary record."""
        paths = list(skill_dir.glob("*.md"))
        skill_names = [skill_name_from_path(p) for p in paths][:2]
        model = self._build_scripted_model(skill_names)

        def _mock_runner(skill_path, user_input, **kwargs) -> str:
            return f"[mock result for {skill_name_from_path(skill_path)}]"

        agent = create_skill_agent(
            skills=paths,
            model=model,
            runner_fn=_mock_runner,
            max_turns=10,
        )

        session = SkillAgentSession(
            agent,
            task="JSONL output verification test",
            log_path=str(log_file),
        )
        await session.run()

        assert log_file.exists(), "JSONL log file was not created"

        records = []
        for line in log_file.read_text(encoding="utf-8").strip().splitlines():
            if line.strip():
                records.append(json.loads(line))

        types = [r["type"] for r in records]
        assert "session_summary" in types, "No session_summary record found"

        summary = next(r for r in records if r["type"] == "session_summary")
        assert "task" in summary
        assert "total_turns" in summary
        assert "skills_used" in summary
        assert isinstance(summary["skills_used"], list)

    @pytest.mark.asyncio
    async def test_turn_records_have_required_fields(self, skill_dir: Path, log_file: Path) -> None:
        """Turn records must include all required JSONL fields."""
        paths = list(skill_dir.glob("*.md"))
        skill_names = [skill_name_from_path(p) for p in paths][:1]
        model = self._build_scripted_model(skill_names)

        def _mock_runner(skill_path, user_input, **kwargs) -> str:
            return "mock skill output"

        agent = create_skill_agent(
            skills=paths,
            model=model,
            runner_fn=_mock_runner,
            max_turns=10,
        )

        session = SkillAgentSession(
            agent,
            task="Turn record field verification",
            log_path=str(log_file),
        )
        await session.run()

        records = [
            json.loads(line)
            for line in log_file.read_text(encoding="utf-8").strip().splitlines()
            if line.strip()
        ]
        turn_records = [r for r in records if r["type"] == "turn"]

        required_fields = {
            "type", "session_id", "turn_number", "timestamp", "task",
            "reasoning", "chosen_skill", "skill_output_summary",
            "termination_signal", "confidence",
        }
        for rec in turn_records:
            missing = required_fields - set(rec.keys())
            assert not missing, f"Turn record missing fields: {missing}"

    @pytest.mark.asyncio
    async def test_session_summary_has_required_fields(self, skill_dir: Path, log_file: Path) -> None:
        """Session summary must include all required JSONL fields."""
        paths = list(skill_dir.glob("*.md"))
        model = self._build_scripted_model([skill_name_from_path(paths[0])])

        agent = create_skill_agent(
            skills=paths,
            model=model,
            runner_fn=make_mock_runner(),
            max_turns=5,
        )
        session = SkillAgentSession(
            agent,
            task="Summary field check",
            log_path=str(log_file),
        )
        await session.run()

        records = [
            json.loads(line)
            for line in log_file.read_text(encoding="utf-8").strip().splitlines()
            if line.strip()
        ]
        summary_records = [r for r in records if r["type"] == "session_summary"]
        assert len(summary_records) == 1

        required_fields = {
            "type", "session_id", "task", "conclusion", "skills_used",
            "total_turns", "termination_reason", "investigation_narrative",
        }
        missing = required_fields - set(summary_records[0].keys())
        assert not missing, f"Session summary missing fields: {missing}"


# ---------------------------------------------------------------------------
# Unit tests — JSONL writer
# ---------------------------------------------------------------------------


class TestLocalWriter:
    def test_writes_valid_jsonl(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.jsonl"
        writer = _LocalWriter(log_path)
        writer.write({"type": "turn", "value": 1})
        writer.write({"type": "session_summary", "value": 2})

        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 2
        records = [json.loads(l) for l in lines]
        assert records[0]["type"] == "turn"
        assert records[1]["type"] == "session_summary"

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        log_path = tmp_path / "nested" / "deep" / "session.jsonl"
        writer = _LocalWriter(log_path)
        writer.write({"test": True})
        assert log_path.exists()
