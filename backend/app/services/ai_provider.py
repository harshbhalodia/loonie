"""AI provider abstraction. Entirely optional — every core LifeOS feature works without it.

Supports two request "styles" so both a plain local endpoint and a standard
OpenAI-compatible one (Ollama, LM Studio, OpenAI itself) can be configured
through config/config.yaml without code changes.
"""
from __future__ import annotations

import httpx

from app.config import get_ai_config


class AIProviderError(RuntimeError):
    pass


def is_ai_enabled() -> bool:
    return bool(get_ai_config().get("enabled", False))


def _extract_text(payload: dict, response_field: str) -> str | None:
    # 1. try the configured dot-path first (e.g. "output" or "choices.0.message.content")
    node: object = payload
    for part in response_field.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            node = None
            break
    if isinstance(node, str):
        return node

    # 2. "responses"-style shape: output is a list of {type, content} segments
    # (e.g. LM Studio/OpenAI responses API) — only the final "message" segment is the real
    # answer. If generation was cut off mid-thought, only "reasoning" segments exist — never
    # treat those as the answer, or callers will try to parse chain-of-thought as data.
    output = payload.get("output")
    if isinstance(output, list):
        for item in reversed(output):
            if isinstance(item, dict) and item.get("type") == "message" and isinstance(item.get("content"), str):
                return item["content"]
        for item in reversed(output):
            if isinstance(item, dict) and item.get("type") not in ("reasoning", None) and isinstance(item.get("content"), str):
                return item["content"]
        if any(isinstance(item, dict) and item.get("type") == "reasoning" for item in output):
            raise AIProviderError(
                "The AI model was still reasoning when generation stopped and never produced an "
                "answer. It may need more time (increase the timeout) or a smaller input."
            )

    # 3. fall back to common shapes
    for key in ("output", "response", "content", "text"):
        value = payload.get(key)
        if isinstance(value, str):
            return value

    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"]
        text = choices[0].get("text") if isinstance(choices[0], dict) else None
        if isinstance(text, str):
            return text

    return None


def generate(system_prompt: str, user_input: str, timeout: float | None = 60) -> str:
    """Calls the configured local AI endpoint and returns generated text.

    `timeout` in seconds, or None to wait indefinitely (useful for large-context reasoning models
    where there's no reasonable upper bound and the caller is fine waiting).

    Raises AIProviderError if AI is disabled, unreachable, or returns an
    unrecognized shape — callers must handle this and degrade gracefully.
    """
    cfg = get_ai_config()
    if not cfg.get("enabled", False):
        raise AIProviderError("AI is not enabled. Configure it under Settings > AI.")

    endpoint = cfg.get("endpoint")
    model = cfg.get("model")
    style = cfg.get("style", "simple")
    temperature = cfg.get("temperature", 0.2)
    response_field = cfg.get("response_field", "output")
    # Hard cap so a confused/looping reasoning model can't generate forever — without this, a bad
    # response makes the model server itself keep emitting tokens with nothing to stop it,
    # regardless of any timeout set on this side.
    max_tokens = cfg.get("max_tokens", 65536)

    if not endpoint or not model:
        raise AIProviderError("AI endpoint/model are not configured.")

    if style == "openai":
        body = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
        }
    else:
        # This "simple" style targets LM Studio's Responses-API-shaped endpoint, which uses
        # "max_output_tokens" (not "max_tokens") and rejects unrecognized keys outright.
        body = {
            "model": model,
            "system_prompt": system_prompt,
            "input": user_input,
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }

    try:
        response = httpx.post(endpoint, json=body, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except httpx.TimeoutException as exc:
        waited = f"{timeout:.0f}s" if timeout is not None else "the configured timeout"
        raise AIProviderError(
            f"AI model did not respond within {waited}. Reasoning models can be slow on "
            "large inputs — try again, use a smaller input, or increase the timeout."
        ) from exc
    except httpx.HTTPError as exc:
        raise AIProviderError(f"Could not reach AI endpoint: {exc}") from exc
    except ValueError as exc:
        raise AIProviderError(f"AI endpoint returned invalid JSON: {exc}") from exc

    text = _extract_text(payload, response_field)
    if text is None:
        raise AIProviderError(f"Could not find generated text in AI response: {payload!r}")
    return text.strip()
