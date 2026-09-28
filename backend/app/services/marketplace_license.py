"""Offline signed license tokens for paid marketplace blueprints — a local, DEMO stand-in for a
real payment/entitlement backend (see the `localagents` repo's
docs/architecture/blueprint-marketplace.md for the intended hosted-marketplace design).

NOT DRM: verifying a token only proves it was issued using this app's own configured
`marketplace.demo_license_secret` — it does not prevent a token being copied/shared. Replace
with a real hosted entitlement service before treating paid blueprints as production licensing.
"""
from __future__ import annotations

import hashlib
import hmac


class EntitlementError(RuntimeError):
    pass


def sign(blueprint_id: str, version: str, licensee: str, secret: str) -> str:
    payload = f"{blueprint_id}:{version}:{licensee}"
    signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def verify(token: str, secret: str) -> dict[str, str]:
    try:
        blueprint_id, version, licensee, signature = token.split(":", 3)
    except ValueError as exc:
        raise EntitlementError(f"Malformed license token: {token!r}") from exc

    payload = f"{blueprint_id}:{version}:{licensee}"
    expected = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise EntitlementError("License signature does not match — invalid or tampered token.")
    return {"blueprint_id": blueprint_id, "version": version, "licensee": licensee}
