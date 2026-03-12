"""Bedrock client configuration for the skill runner.

Provides a shared factory for both:
- Direct API calls (Pass 1 / Pass 2): uses ``anthropic.AnthropicBedrock``
- Agent loop model calls: uses ``langchain_aws.ChatBedrockConverse``

All credentials are read from environment variables so no secrets are
embedded in source.  The same env vars that the AWS SDK uses by convention
are honoured:

  AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN,
  AWS_DEFAULT_REGION, AWS_PROFILE

Additionally, the following runner-specific vars are supported:

  BEDROCK_MODEL_ID  — Claude model ID on Bedrock (default below)
  ANTHROPIC_API_KEY — fallback when Bedrock env vars are absent
"""

from __future__ import annotations

import os
from typing import Optional

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_BEDROCK_MODEL_ID = "us.anthropic.claude-sonnet-4-6-20251101-v1:0"
DEFAULT_REGION = "us-east-1"


def get_bedrock_model_id() -> str:
    return os.environ.get("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL_ID)


def get_aws_region() -> str:
    return (
        os.environ.get("AWS_DEFAULT_REGION")
        or os.environ.get("AWS_REGION")
        or DEFAULT_REGION
    )


# ---------------------------------------------------------------------------
# Direct Anthropic / Bedrock client (for runner Pass 1 / Pass 2)
# ---------------------------------------------------------------------------


def create_runner_client():
    """Return an Anthropic client for direct API calls.

    Prefers ``AnthropicBedrock`` when AWS credentials are present; falls back
    to the standard ``Anthropic`` client (useful for local development where
    only ``ANTHROPIC_API_KEY`` is set).

    Returns:
        Either ``anthropic.AnthropicBedrock`` or ``anthropic.Anthropic``.
    """
    aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    aws_session_token = os.environ.get("AWS_SESSION_TOKEN")
    aws_profile = os.environ.get("AWS_PROFILE")
    region = get_aws_region()

    use_bedrock = bool(aws_access_key or aws_profile)

    if use_bedrock:
        from anthropic import AnthropicBedrock  # noqa: PLC0415

        kwargs: dict = {"aws_region": region}
        if aws_access_key:
            kwargs["aws_access_key"] = aws_access_key
        if aws_secret_key:
            kwargs["aws_secret_key"] = aws_secret_key
        if aws_session_token:
            kwargs["aws_session_token"] = aws_session_token
        if aws_profile:
            kwargs["aws_profile"] = aws_profile

        return AnthropicBedrock(**kwargs)

    # Fallback: direct Anthropic API (local dev / CI)
    from anthropic import Anthropic  # noqa: PLC0415

    return Anthropic()


# ---------------------------------------------------------------------------
# LangChain chat model (for the agent loop)
# ---------------------------------------------------------------------------


def create_chat_model(
    model_id: Optional[str] = None,
    temperature: float = 0.0,
):
    """Return a LangChain ``BaseChatModel`` for the agent loop.

    Prefers ``ChatBedrockConverse`` when AWS credentials are present; falls
    back to ``ChatAnthropic`` otherwise.

    Args:
        model_id: Override the Bedrock model ID / Anthropic model name.
        temperature: Sampling temperature (default 0 for determinism).

    Returns:
        A configured ``BaseChatModel`` instance.
    """
    aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_profile = os.environ.get("AWS_PROFILE")
    use_bedrock = bool(aws_access_key or aws_profile)

    if use_bedrock:
        from langchain_aws import ChatBedrockConverse  # noqa: PLC0415

        return ChatBedrockConverse(
            model_id=model_id or get_bedrock_model_id(),
            region_name=get_aws_region(),
            temperature=temperature,
        )

    # Fallback: direct Anthropic API
    from langchain_anthropic import ChatAnthropic  # noqa: PLC0415

    # ChatAnthropic uses "claude-*" style model names, not Bedrock ARNs
    anthropic_model = (
        model_id
        if model_id and not model_id.startswith("us.")
        else "claude-sonnet-4-6-20251101"
    )
    return ChatAnthropic(
        model_name=anthropic_model,
        temperature=temperature,
    )
