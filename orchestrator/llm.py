"""One Claude call = one Langfuse generation. Agents answer in JSON only; anything else raises AgentError,
and the caller marks the step BLOCKED (never PASS).

TEAM10_MOCK=1      canned answers from the agent's mock function (no API call, no cost)
TEAM10_MOCK=broken every agent answers garbage (tests the fail-closed path)

T10-043 provider configuration (env, all optional):
  ANTHROPIC_API_KEY      Anthropic key for the SÜSIE orchestrator (SDK default lookup)
  ANTHROPIC_BASE_URL     override endpoint (e.g. a gateway); the SDK honors this natively
  TEAM10_MODEL_AUTHOR    model for role 'author'   (default claude-sonnet-5-5)
  TEAM10_MODEL_LIGHT     model for role 'light'    (default claude-haiku-5-5)
Langfuse payloads pass through Fares's privacy guard (privacy/langfuse_guard.py) before they leave.
"""
import json
import os
import re

MODELS = {"author": os.environ.get("TEAM10_MODEL_AUTHOR", "claude-sonnet-5-5"),
          "light": os.environ.get("TEAM10_MODEL_LIGHT", "claude-haiku-5-5")}
PROMPT = os.environ.get("TEAM10_PROMPT", "v2")   # v1 = experiment 1, v2 = experiment 2
PROMPT_VERSION = f"agents-{PROMPT}"
_client = None


class AgentError(Exception):
    pass


def lf_client():
    """Langfuse client if keys are set, else None (agents still run, nothing is recorded)."""
    if not os.environ.get("LANGFUSE_PUBLIC_KEY") or os.environ.get("TEAM10_MOCK"):   # mock runs are not recorded
        return None
    from langfuse import get_client
    return get_client()


def _claude():
    global _client
    if _client is None:
        try:
            import anthropic
        except ImportError as exc:
            raise AgentError("the anthropic package is not installed (pip install anthropic)") from exc
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            raise AgentError("no ANTHROPIC_API_KEY set — configure the orchestrator provider or use TEAM10_MOCK=1")
        _client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL itself
    return _client


def parse_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise AgentError("no JSON object in the answer")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        raise AgentError(f"invalid JSON: {exc}") from None


def call(agent, role, system, user, mock, max_tokens=32000):
    """Run one agent. role: 'author' (Sonnet) or 'light' (Haiku). mock(user) -> dict for TEAM10_MOCK=1."""
    mode = os.environ.get("TEAM10_MOCK")
    model = "mock" if mode else MODELS[role]
    lf = lf_client()
    guard = None
    gen = None
    if lf:
        try:
            from privacy.langfuse_guard import LangfuseGuard
            guard = LangfuseGuard()
        except ImportError:   # privacy/ not on the path: fail closed, send nothing to Langfuse unguarded
            lf = None
    if lf:
        gen = lf.start_as_current_generation(name=agent, model=model,
                                             input=guard.safe({"system": system, "user": user}),
                                             metadata=guard.safe({"prompt_version": PROMPT_VERSION, "role": role}))
    ctx = gen.__enter__() if gen else None
    try:
        usage = {"input": 0, "output": 0}
        if mode == "broken":
            text, stop = "sorry, no JSON here", "end_turn"
        elif mode:
            text, stop = json.dumps(mock(user)), "end_turn"
        else:
            with _claude().messages.stream(model=model, max_tokens=max_tokens, system=system,
                                           messages=[{"role": "user", "content": user}]) as stream:
                r = stream.get_final_message()
            stop = r.stop_reason
            text = "".join(b.text for b in r.content if b.type == "text")
            usage = {"input": r.usage.input_tokens, "output": r.usage.output_tokens}
        if stop in ("refusal", "max_tokens"):
            raise AgentError(f"stop_reason {stop}")
        out = parse_json(text)
        if ctx:
            ctx.update(output=guard.safe(out), usage_details=usage)
        return out
    except Exception as exc:
        if ctx:
            ctx.update(level="ERROR", status_message=f"{type(exc).__name__}: {exc}"[:300])
        raise AgentError(f"{agent}: {exc}") from None
    finally:
        if gen:
            gen.__exit__(None, None, None)
