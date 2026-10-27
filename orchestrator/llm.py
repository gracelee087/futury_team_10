"""One model call = one Langfuse generation. Agents answer in JSON only; anything else raises AgentError,
and the caller marks the step BLOCKED (never PASS).

TEAM10_MOCK=1      canned answers from the agent's mock function (no API call, no cost)
TEAM10_MOCK=broken every agent answers garbage (tests the fail-closed path)

TEAM10_LLM_PROVIDER (T10-008)
  anthropic (default, unchanged)  Claude via the Anthropic API. Processing is NOT guaranteed to stay in Germany.
  hessian                         OpenAI-compatible endpoint https://hip-gw.hessian.ai/v1 (self-hosted open-weight
                                  models, processing stays in Germany). Key: HESSIAN_API_KEY.
                                  Models: TEAM10_HESSIAN_MODEL (author) and TEAM10_HESSIAN_MODEL_LIGHT (default = author).

Privacy (T10-008, privacy/schleuse.py): before every model call the user payload is pseudonymized and re-checked;
if anything personal is left, call() raises PrivacyBlockedError (an AgentError, so the step is BLOCKED and nothing is
sent). The static system prompt is only checked (allow_specimen: public rulebook examples). Langfuse generations
get a pseudonymized, minimized copy through privacy/langfuse_guard.py (policy "langfuse": 200 characters per string).
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from privacy import schleuse  # noqa: E402
from privacy.langfuse_guard import LangfuseGuard  # noqa: E402

PROVIDER = os.environ.get("TEAM10_LLM_PROVIDER", "anthropic").strip().lower()
HESSIAN_URL = "https://hip-gw.hessian.ai/v1"
MODELS = {"author": "claude-sonnet-5-5", "light": "claude-haiku-5-5"}
PROMPT = os.environ.get("TEAM10_PROMPT", "v2")   # v1 = experiment 1, v2 = experiment 2
PROMPT_VERSION = f"agents-{PROMPT}"
_client = None          # anthropic client (lazy); tests may inject a fake
_hessian_client = None  # OpenAI-shaped client for hessian.AI (lazy); tests may inject a fake
_guard = None


class AgentError(Exception):
    pass


class PrivacyBlockedError(AgentError):
    """Personal data was still present after pseudonymization: nothing was sent to any model."""


def lf_client():
    """Langfuse client if keys are set, else None (agents still run, nothing is recorded)."""
    if not os.environ.get("LANGFUSE_PUBLIC_KEY") or os.environ.get("TEAM10_MOCK"):   # mock runs are not recorded
        return None
    from langfuse import get_client
    return get_client()


def langfuse_guard():
    """One shared guard per process; .summary() says how many payloads were checked / withheld."""
    global _guard
    if _guard is None:
        _guard = LangfuseGuard()
    return _guard


def _claude():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()
    return _client


def _hessian():
    global _hessian_client
    if _hessian_client is None:
        key = os.environ.get("HESSIAN_API_KEY", "").strip()
        if not key:
            raise AgentError("HESSIAN_API_KEY is not set")
        from openai import OpenAI
        _hessian_client = OpenAI(base_url=HESSIAN_URL, api_key=key, timeout=120.0)
    return _hessian_client


def _model(role):
    if PROVIDER == "anthropic":
        return MODELS[role]
    if PROVIDER == "hessian":
        name = (os.environ.get("TEAM10_HESSIAN_MODEL_LIGHT") if role == "light" else None) \
            or os.environ.get("TEAM10_HESSIAN_MODEL")
        if not name:
            raise AgentError("TEAM10_HESSIAN_MODEL is not set")
        return name
    raise AgentError(f"unknown TEAM10_LLM_PROVIDER {PROVIDER!r} (anthropic | hessian)")


def _privacy_gate(agent, system, user):
    """Pseudonymize the user payload, then check it strictly. Any leftover or any error = blocked."""
    try:
        gate = schleuse.Schleuse()
        left_system = schleuse.check_clean(system, allow_specimen=True)   # static prompt, public examples allowed
        clean, summary = gate.pseudonymize(user)
        left = gate.check_clean(clean)
    except Exception as exc:   # bad PRIVACY_KEY, detector crash ...: never send what could not be checked
        raise PrivacyBlockedError(f"{agent}: privacy gate failed ({type(exc).__name__}); nothing was sent") from None
    if left_system or left:
        cats = sorted({h.category for h in left_system + left})   # categories only, never values
        raise PrivacyBlockedError(f"{agent}: personal data left after pseudonymization ({', '.join(cats)}); "
                                  "nothing was sent")
    return clean, summary["categories"]


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
    lf = lf_client()
    gen = ctx = None
    try:
        model = "mock" if mode else _model(role)
        if lf:   # input is added only after the privacy gate: the raw payload never goes to Langfuse
            gen = lf.start_as_current_generation(name=agent, model=model,
                                                 metadata={"prompt_version": PROMPT_VERSION, "role": role,
                                                           "provider": "mock" if mode else PROVIDER})
            ctx = gen.__enter__()
        user, removed = _privacy_gate(agent, system, user)   # T10-008: blocked here = no model call at all
        if ctx:
            ctx.update(input=langfuse_guard().safe(user), metadata={"privacy_categories_removed": removed})
        usage = {"input": 0, "output": 0}
        if mode == "broken":
            text, stop = "sorry, no JSON here", "end_turn"
        elif mode:
            text, stop = json.dumps(mock(user)), "end_turn"
        elif PROVIDER == "hessian":
            r = _hessian().chat.completions.create(model=model, max_tokens=max_tokens, messages=[
                {"role": "system", "content": system}, {"role": "user", "content": user}])
            text = r.choices[0].message.content or ""
            stop = {"length": "max_tokens", "content_filter": "refusal"}.get(r.choices[0].finish_reason, "end_turn")
            if r.usage:
                usage = {"input": r.usage.prompt_tokens, "output": r.usage.completion_tokens}
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
            ctx.update(output=langfuse_guard().safe(json.dumps(out, ensure_ascii=False)), usage_details=usage)
        return out
    except Exception as exc:
        reason = schleuse.scrub_for_log(f"{type(exc).__name__}: {exc}")[:300]   # error texts hold no personal data
        if ctx:
            ctx.update(level="ERROR", status_message=reason)
        if isinstance(exc, PrivacyBlockedError):
            raise
        raise AgentError(f"{agent}: {schleuse.scrub_for_log(str(exc))}") from None
    finally:
        if gen:
            gen.__exit__(None, None, None)
