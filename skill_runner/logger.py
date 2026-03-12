"""Task 5 — JSONL session logger.

Writes structured JSONL records after each agent turn and a session summary on
exit.  Works by processing the LangGraph event stream produced by
``agent.astream_events``.

Two record types are emitted:

Turn record (written after each tool call completes)::

    {
      "type": "turn",
      "session_id": "...",
      "turn_number": 0,
      "timestamp": "...",
      "task": "original user intent",
      "reasoning": "Claude's reasoning this turn",
      "chosen_skill": "skill-name",
      "skill_output_summary": "compressed finding",
      "termination_signal": "continuing",
      "confidence": "medium"
    }

Session summary record (written when the agent loop exits)::

    {
      "type": "session_summary",
      "session_id": "...",
      "task": "...",
      "conclusion": "...",
      "skills_used": [],
      "total_turns": 0,
      "termination_reason": "...",
      "investigation_narrative": "..."
    }

Output path configuration
--------------------------
``SKILL_RUNNER_LOG_PATH`` environment variable controls where records are
written:

- Unset or ``"minio://<bucket>/<prefix>"`` → MinIO (requires ``minio`` SDK)
- Any other value → treated as a local filesystem path

When ``log_path`` is passed directly to ``SkillAgentSession`` it overrides the
env var.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from langchain_core.messages import AIMessage, ToolMessage


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_REASONING_RE = re.compile(
    r"\[REASONING\](.*?)\[/REASONING\]", re.DOTALL | re.IGNORECASE
)
_CONCLUSION_RE = re.compile(
    r"\[CONCLUSION\](.*?)\[/CONCLUSION\]", re.DOTALL | re.IGNORECASE
)
_FIELD_RE = re.compile(r"^\s*([A-Za-z ]+):\s*(.+)$", re.MULTILINE)


def _extract_reasoning_block(text: str) -> dict[str, str]:
    """Parse the [REASONING]...[/REASONING] block from an AI message."""
    m = _REASONING_RE.search(text)
    if not m:
        return {}
    fields: dict[str, str] = {}
    for fm in _FIELD_RE.finditer(m.group(1)):
        key = fm.group(1).strip().lower().replace(" ", "_")
        fields[key] = fm.group(2).strip()
    return fields


def _extract_conclusion_block(text: str) -> dict[str, str]:
    """Parse the [CONCLUSION]...[/CONCLUSION] block from an AI message."""
    m = _CONCLUSION_RE.search(text)
    if not m:
        return {}
    fields: dict[str, str] = {}
    for fm in _FIELD_RE.finditer(m.group(1)):
        key = fm.group(1).strip().lower().replace(" ", "_")
        fields[key] = fm.group(2).strip()
    return fields


def _summarise(text: str, max_chars: int = 300) -> str:
    """Compress a long string to at most ``max_chars`` characters."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Writer abstraction
# ---------------------------------------------------------------------------


class _LocalWriter:
    """Append-only JSONL writer to the local filesystem."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, record: dict) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


class _MinIOWriter:
    """Buffered JSONL writer that flushes to MinIO on session end."""

    def __init__(self, bucket: str, object_prefix: str, session_id: str) -> None:
        from minio import Minio  # noqa: PLC0415 — optional dependency

        endpoint = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
        access_key = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
        secret_key = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
        secure = os.environ.get("MINIO_SECURE", "false").lower() == "true"

        self._client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        self._bucket = bucket
        self._object_key = f"{object_prefix.rstrip('/')}/{session_id}.jsonl"
        self._buffer: list[str] = []

        if not self._client.bucket_exists(bucket):
            self._client.make_bucket(bucket)

    def write(self, record: dict) -> None:
        self._buffer.append(json.dumps(record, ensure_ascii=False))

    def flush(self) -> None:
        if not self._buffer:
            return
        import io  # noqa: PLC0415

        data = ("\n".join(self._buffer) + "\n").encode("utf-8")
        self._client.put_object(
            self._bucket,
            self._object_key,
            io.BytesIO(data),
            length=len(data),
            content_type="application/x-ndjson",
        )
        self._buffer.clear()


def _make_writer(log_path: str | Path) -> _LocalWriter | _MinIOWriter:
    """Resolve a log path string to the appropriate writer."""
    log_path = str(log_path)
    if log_path.startswith("minio://"):
        # minio://bucket/prefix
        rest = log_path[len("minio://"):]
        parts = rest.split("/", 1)
        bucket = parts[0]
        prefix = parts[1] if len(parts) > 1 else "skill-runner-logs"
        session_id = str(uuid.uuid4())
        return _MinIOWriter(bucket, prefix, session_id)
    return _LocalWriter(log_path)


def _default_log_path() -> str:
    return os.environ.get(
        "SKILL_RUNNER_LOG_PATH",
        "minio://skill-runner/logs",
    )


# ---------------------------------------------------------------------------
# Session runner
# ---------------------------------------------------------------------------


class SkillAgentSession:
    """Runs an agent with JSONL logging.

    Usage::

        session = SkillAgentSession(
            agent=create_skill_agent(skills=[...]),
            task="Research X",
            log_path="/tmp/session.jsonl",  # local path for dev
        )
        summary = await session.run()
    """

    def __init__(
        self,
        agent,
        task: str,
        *,
        session_id: Optional[str] = None,
        log_path: Optional[str | Path] = None,
        thread_id: Optional[str] = None,
    ) -> None:
        self._agent = agent
        self._task = task
        self._session_id = session_id or str(uuid.uuid4())
        self._thread_id = thread_id or self._session_id
        _path = log_path or _default_log_path()
        self._writer = _make_writer(_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> dict[str, Any]:
        """Stream agent events, write JSONL records, return session summary dict."""
        config = {"configurable": {"thread_id": self._thread_id}}

        turn_number = 0
        skills_used: list[str] = []
        narrative_parts: list[str] = []
        termination_reason = "max_turns"
        conclusion_text = ""

        # Accumulate per-turn state between on_chat_model_end and on_tool_end
        pending_reasoning: dict[str, str] = {}
        pending_ai_text = ""
        pending_skill_name = ""

        async for event in self._agent.astream_events(
            {"messages": [{"role": "user", "content": self._task}]},
            config=config,
            version="v2",
        ):
            kind = event.get("event")

            if kind == "on_chat_model_end":
                # Extract reasoning + termination signal from the model output
                output = event.get("data", {}).get("output", {})
                ai_content = ""
                if hasattr(output, "content"):
                    for block in output.content:
                        if hasattr(block, "text"):
                            ai_content += block.text
                        elif isinstance(block, dict) and block.get("type") == "text":
                            ai_content += block.get("text", "")
                elif isinstance(output, str):
                    ai_content = output

                pending_ai_text = ai_content
                pending_reasoning = _extract_reasoning_block(ai_content)

                # Check for conclusion
                conclusion_fields = _extract_conclusion_block(ai_content)
                if conclusion_fields.get("summary"):
                    conclusion_text = conclusion_fields["summary"]

                signal = pending_reasoning.get("state", "continuing").lower()
                if signal in ("done", "propose_done"):
                    termination_reason = signal

            elif kind == "on_tool_start":
                tool_name = event.get("name", "")
                pending_skill_name = tool_name

            elif kind == "on_tool_end":
                tool_name = event.get("name", pending_skill_name)
                tool_output = ""
                output = event.get("data", {}).get("output")
                if isinstance(output, str):
                    tool_output = output
                elif hasattr(output, "content"):
                    tool_output = str(output.content)
                elif output is not None:
                    tool_output = str(output)

                if tool_name and not tool_name.startswith("write_todos"):
                    if tool_name not in skills_used:
                        skills_used.append(tool_name)

                signal = pending_reasoning.get("state", "continuing").lower()
                confidence = pending_reasoning.get("confidence", "medium")
                reasoning_text = (
                    f"Known: {pending_reasoning.get('known_so_far', '')} | "
                    f"Gap: {pending_reasoning.get('gap_to_close', '')} | "
                    f"Why: {pending_reasoning.get('why', '')}"
                ).strip(" |")

                narrative_parts.append(
                    f"Turn {turn_number}: [{tool_name}] {_summarise(tool_output, 120)}"
                )

                turn_record: dict[str, Any] = {
                    "type": "turn",
                    "session_id": self._session_id,
                    "turn_number": turn_number,
                    "timestamp": _now(),
                    "task": self._task,
                    "reasoning": reasoning_text or pending_ai_text[:200],
                    "chosen_skill": tool_name,
                    "skill_output_summary": _summarise(tool_output),
                    "termination_signal": signal,
                    "confidence": confidence,
                }
                self._writer.write(turn_record)

                turn_number += 1
                pending_reasoning = {}
                pending_ai_text = ""
                pending_skill_name = ""

            elif kind == "on_chain_end":
                # Agent loop finished
                pass

        # Write session summary
        summary: dict[str, Any] = {
            "type": "session_summary",
            "session_id": self._session_id,
            "task": self._task,
            "conclusion": conclusion_text or f"Investigation completed in {turn_number} turn(s).",
            "skills_used": skills_used,
            "total_turns": turn_number,
            "termination_reason": termination_reason,
            "investigation_narrative": " → ".join(narrative_parts) or "No tool invocations recorded.",
        }
        self._writer.write(summary)

        # Flush MinIO writer if applicable
        if hasattr(self._writer, "flush"):
            self._writer.flush()

        return summary


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------


async def run_skill_agent(
    agent,
    task: str,
    *,
    session_id: Optional[str] = None,
    log_path: Optional[str | Path] = None,
    thread_id: Optional[str] = None,
) -> dict[str, Any]:
    """Run a skill agent with full JSONL logging, returning the session summary.

    Args:
        agent: A compiled agent returned by ``create_skill_agent``.
        task: The user's investigation task / question.
        session_id: Optional session identifier (auto-generated if omitted).
        log_path: Where to write JSONL records.  See module docstring for
                  supported formats.
        thread_id: LangGraph thread identifier for checkpointing.

    Returns:
        The session summary dict.
    """
    session = SkillAgentSession(
        agent,
        task,
        session_id=session_id,
        log_path=log_path,
        thread_id=thread_id,
    )
    return await session.run()
