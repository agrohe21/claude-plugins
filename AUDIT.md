# Task 1 — Deep Agents SDK Constraint Audit

Findings before integration code is written. Each constraint from the spec is
addressed below.

---

## 1. Bedrock Endpoint Configuration

**Can Deep Agents be configured to use an Anthropic Bedrock endpoint?**

Yes. `create_deep_agent` (and the underlying `langchain.agents.create_agent`)
accept any `BaseChatModel` instance as their `model` parameter. Passing a
`langchain_aws.ChatBedrockConverse` instance routes all agent-loop model calls
through Bedrock instead of the direct Anthropic API.

```python
from langchain_aws import ChatBedrockConverse

model = ChatBedrockConverse(
    model_id="us.anthropic.claude-sonnet-4-6-20251101-v1:0",
    region_name="us-east-1",
)
agent = create_skill_agent(skills=[...], model=model)
```

For the runner's direct API calls (Pass 1, Pass 2), the `anthropic` package
ships `AnthropicBedrock` which accepts `aws_region`, `aws_access_key`,
`aws_secret_key`, and `aws_session_token`. A shared `get_bedrock_client()`
factory centralises credentials for both surfaces.

**Conclusion: No constraint violation. Bedrock routing is fully supported.**

---

## 2. Disabling Default Built-in Tools

**Can `ls`, `read_file`, `write_file`, `edit_file`, `write_todos` be disabled?**

`create_deep_agent` hardcodes `FilesystemMiddleware` and `TodoListMiddleware`
into its middleware stack. There is no `include_filesystem=False` parameter.
The built-in tools cannot be removed by calling `create_deep_agent`.

**Workaround (chosen approach):** Use `langchain.agents.create_agent` directly
(the same function that `create_deep_agent` calls internally) and build a
minimal middleware stack that omits `FilesystemMiddleware`. This:

- Uses the exact LangGraph runtime from the Deep Agents SDK package
- Preserves loop semantics, HITL, checkpointing, and streaming
- Excludes all filesystem tools (`ls`, `read_file`, `write_file`, `edit_file`,
  `glob`, `grep`)
- Excludes `execute` (shell) by never providing a `SandboxBackendProtocol`
- Optionally keeps `TodoListMiddleware` (`write_todos`) for internal planning.
  The spec says "skills are the permission boundary" and lists filesystem ops
  as forbidden; `write_todos` is a planning aid, not a data-access tool.

**Conclusion: Cannot use `create_deep_agent` while fully enforcing the
constraint. Use `create_agent` directly. The Deep Agents SDK loop layer
(LangGraph runtime, streaming, checkpointing) is still the mechanism.**

---

## 3. Node.js / Non-Python Runtime Dependencies

**Does deepagents pull in any non-Python runtime?**

Inspected `deepagents` 0.4.10 and its full dependency closure:

```
deepagents==0.4.10
  langchain>=0.x
  langchain-core>=0.x
  langchain-anthropic>=0.x
  langchain-google-genai>=0.x
  langgraph>=0.x
  langgraph-prebuilt>=0.x
  langgraph-checkpoint>=0.x
  langgraph-sdk>=0.x
  langsmith>=0.x
  pydantic>=2
  httpx / httpcore / anyio / sniffio   (pure Python async HTTP)
  google-auth / google-genai            (pure Python)
  wcmatch / bracex / filetype           (pure Python)
```

No Node.js, no npm packages, no compiled native binaries beyond numpy (optional
transitive). The `deepagents-cli` companion package would pull in Node.js if
installed, but we do **not** install `deepagents-cli`.

**Conclusion: No constraint violation.**

---

## 4. LangGraph Version

**What LangGraph version does deepagents bundle?**

`langgraph==1.1.1` is installed as part of the deepagents dependency closure.
The agent factory imports `langchain.agents.create_agent`, `TodoListMiddleware`,
and `AnthropicPromptCachingMiddleware` — all from `langchain` 1.2.x and
`langgraph` 1.1.x.

**Conclusion: No pre-existing LangGraph usage to conflict with. Fresh repo.
LangGraph 1.1.1 is authoritative for this project.**

---

## 5. Custom System Prompt

**Does `create_deep_agent` / `create_agent` support a custom system prompt?**

Yes. `create_agent` accepts a `system_prompt` parameter (string or
`SystemMessage`). `create_deep_agent` prepends the custom prompt before its own
`BASE_AGENT_PROMPT`. When using `create_agent` directly we pass only our own
prompt, giving full control over agent behaviour with no bleed from the default
Deep Agents persona.

**Conclusion: Full control over system prompt. No constraint violation.**

---

## Summary Table

| Constraint | Status | Approach |
|---|---|---|
| Bedrock endpoint | ✅ Compatible | Pass `ChatBedrockConverse` as model; use `AnthropicBedrock` for runner |
| Disable filesystem tools | ⚠️ `create_deep_agent` hardcodes them | Use `create_agent` directly, omit `FilesystemMiddleware` |
| No Node.js | ✅ Pure Python | `deepagents` + full closure is Python-only |
| LangGraph version | ✅ 1.1.1 | No existing usage; 1.1.1 is the version |
| Custom system prompt | ✅ Supported | Pass directly to `create_agent` |
