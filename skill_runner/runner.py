"""Pass 1 and Pass 2 runner logic.

Pass 1 — Direct execution
    Given a skill path and a user prompt, load the SKILL.md, inject it as
    context, call Claude, return the text result.

Pass 2 — Skill selection
    Given a user prompt and a list of available skill paths, ask Claude to
    choose the most appropriate skill, then delegate to Pass 1.

Both passes use the runner client from ``bedrock.py`` (Bedrock or direct
Anthropic).  The agent loop in ``agent.py`` calls these functions through the
tool adapter in ``adapter.py``; they can also be invoked standalone.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# SKILL.md parsing helpers
# ---------------------------------------------------------------------------

_DESCRIPTION_RE = re.compile(r"(?m)^Description:\s*(.+)$")
_TITLE_RE = re.compile(r"(?m)^#\s+(.+)$")


def parse_skill_description(skill_path: str | Path) -> str:
    """Extract a short description from a SKILL.md file.

    Looks for a ``Description:`` line first; falls back to the first ``#``
    heading; falls back to the filename stem.

    Args:
        skill_path: Path to the SKILL.md file.

    Returns:
        A one-line description string.
    """
    content = Path(skill_path).read_text(encoding="utf-8")
    m = _DESCRIPTION_RE.search(content)
    if m:
        return m.group(1).strip()
    m = _TITLE_RE.search(content)
    if m:
        return m.group(1).strip()
    return Path(skill_path).stem.replace("-", " ").replace("_", " ").title()


def skill_name_from_path(skill_path: str | Path) -> str:
    """Derive a clean tool name from a SKILL.md file path.

    Strips the ``.md`` extension and replaces non-alphanumeric characters
    with underscores so the name is safe to use as an identifier / tool name.

    Args:
        skill_path: Path to the SKILL.md file.

    Returns:
        A snake_case tool name string.
    """
    stem = Path(skill_path).stem
    return re.sub(r"[^a-zA-Z0-9]+", "_", stem).strip("_").lower()


# ---------------------------------------------------------------------------
# Pass 1 — Direct skill execution
# ---------------------------------------------------------------------------

PASS1_SYSTEM_TEMPLATE = """\
You are a focused skill executor. The SKILL.md below defines the exact task you
must perform. Follow its instructions precisely and return only the result.

--- SKILL.md ---
{skill_content}
--- END SKILL.md ---
"""


def execute_skill(
    skill_path: str | Path,
    user_input: str,
    *,
    client=None,
    model_id: Optional[str] = None,
    max_tokens: int = 4096,
) -> str:
    """Pass 1: load a SKILL.md and run it against ``user_input``.

    Args:
        skill_path: Path to the SKILL.md file.
        user_input: The user's request / query to pass to the skill.
        client: Pre-built Anthropic client.  Created via ``create_runner_client``
                when ``None``.
        model_id: Override the model ID.  Defaults to environment / Bedrock default.
        max_tokens: Maximum tokens in the response.

    Returns:
        The text content of the model's first response message.

    Raises:
        FileNotFoundError: If ``skill_path`` does not exist.
        RuntimeError: If the API call fails after retries.
    """
    skill_path = Path(skill_path)
    if not skill_path.exists():
        raise FileNotFoundError(f"SKILL.md not found: {skill_path}")

    skill_content = skill_path.read_text(encoding="utf-8")
    system_prompt = PASS1_SYSTEM_TEMPLATE.format(skill_content=skill_content)

    if client is None:
        from skill_runner.bedrock import create_runner_client  # noqa: PLC0415

        client = create_runner_client()

    from skill_runner.bedrock import get_bedrock_model_id  # noqa: PLC0415

    resolved_model = model_id or get_bedrock_model_id()

    response = client.messages.create(
        model=resolved_model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_input}],
    )
    # Extract text content from the first content block
    for block in response.content:
        if hasattr(block, "text"):
            return block.text
    return ""


# ---------------------------------------------------------------------------
# Pass 2 — Skill selection then execution
# ---------------------------------------------------------------------------

PASS2_SYSTEM = """\
You are a skill selector. Given a list of available skills and a user request,
choose the single most appropriate skill and respond with ONLY the skill name —
nothing else.  Do not explain your choice.  If no skill is relevant, respond
with the word NONE.
"""

PASS2_USER_TEMPLATE = """\
Available skills:
{skill_list}

User request:
{user_input}

Respond with the skill name only.
"""


def select_and_execute_skill(
    user_input: str,
    skill_paths: list[str | Path],
    *,
    client=None,
    model_id: Optional[str] = None,
    max_tokens: int = 256,
) -> str:
    """Pass 2: select the best skill from a list, then execute it (Pass 1).

    Args:
        user_input: The user's request.
        skill_paths: List of SKILL.md paths to choose from.
        client: Pre-built Anthropic client.  Shared across selection + execution.
        model_id: Override the model ID.
        max_tokens: Max tokens for the selection step (kept short intentionally).

    Returns:
        The Pass 1 execution result of the chosen skill.

    Raises:
        ValueError: If no skill could be selected (model returned NONE).
        FileNotFoundError: If a referenced skill file does not exist.
    """
    if client is None:
        from skill_runner.bedrock import create_runner_client  # noqa: PLC0415

        client = create_runner_client()

    from skill_runner.bedrock import get_bedrock_model_id  # noqa: PLC0415

    resolved_model = model_id or get_bedrock_model_id()

    # Build skill name → path map
    skill_map: dict[str, Path] = {}
    skill_entries: list[str] = []
    for sp in skill_paths:
        name = skill_name_from_path(sp)
        desc = parse_skill_description(sp)
        skill_map[name] = Path(sp)
        skill_entries.append(f"- {name}: {desc}")

    skill_list_text = "\n".join(skill_entries)
    user_message = PASS2_USER_TEMPLATE.format(
        skill_list=skill_list_text,
        user_input=user_input,
    )

    response = client.messages.create(
        model=resolved_model,
        max_tokens=max_tokens,
        system=PASS2_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
    )

    chosen_raw = ""
    for block in response.content:
        if hasattr(block, "text"):
            chosen_raw = block.text.strip().lower()
            break

    if chosen_raw == "none" or not chosen_raw:
        raise ValueError(
            f"No appropriate skill found for request: {user_input!r}"
        )

    # Normalise the chosen name to match our key format
    chosen_name = re.sub(r"[^a-zA-Z0-9]+", "_", chosen_raw).strip("_")

    if chosen_name not in skill_map:
        # Fuzzy fallback: first partial match
        for name in skill_map:
            if chosen_name in name or name in chosen_name:
                chosen_name = name
                break
        else:
            raise ValueError(
                f"Model selected unknown skill {chosen_raw!r}. "
                f"Available: {list(skill_map)}"
            )

    return execute_skill(
        skill_map[chosen_name],
        user_input,
        client=client,
        model_id=resolved_model,
    )
