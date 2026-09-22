"""Thin client for TypeSafe AI's public Jev "System One" inference API.

This is the only module that talks to the public https://api.typesafe.ai endpoint. Building the
request (state/context + questions) is the caller's job — this module just sends it and hands
back the typed `answers` the API returns. See https://docs.typesafe.ai for the API shape.
"""
from __future__ import annotations

import httpx

from app.config import get_jev_config

DEFAULT_BASE_URL = "https://api.typesafe.ai/v1/systemone"


class JevError(RuntimeError):
    pass


def is_jev_enabled() -> bool:
    cfg = get_jev_config()
    return bool(cfg.get("enabled", False) and cfg.get("api_key"))


def ask(state: str, questions: dict, timeout: float = 60) -> dict:
    """Sends one System One request and returns the `answers` dict, keyed by question id."""
    cfg = get_jev_config()
    api_key = cfg.get("api_key")
    if not cfg.get("enabled", False) or not api_key:
        raise JevError("Jev is not enabled. Add your API key under `jev:` in config/config.yaml.")

    base_url = cfg.get("base_url") or DEFAULT_BASE_URL
    model = cfg.get("model") or "jev-latest"

    body = {"state": state, "model": model, "questions": questions}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    print(f"[jev_client] REQUEST -> {base_url}\n{body}")

    try:
        response = httpx.post(base_url, json=body, headers=headers, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        print(f"[jev_client] RESPONSE <- {payload}")
    except httpx.TimeoutException as exc:
        raise JevError(f"Jev did not respond within {timeout:.0f}s.") from exc
    except httpx.HTTPStatusError as exc:
        raise JevError(f"Jev API returned {exc.response.status_code}: {exc.response.text[:300]}") from exc
    except httpx.HTTPError as exc:
        raise JevError(f"Could not reach the Jev API: {exc}") from exc
    except ValueError as exc:
        raise JevError(f"Jev API returned invalid JSON: {exc}") from exc

    answers = payload.get("answers")
    if not isinstance(answers, dict):
        raise JevError(f"Unexpected Jev response shape: {payload!r}")
    return answers
