"""Decision agent: grounds a Jev Choice question in a snapshot of the user's own profile.

Same principle as `app.services.agents`: the LLM/model is never handed raw database access and
never invents numbers. Here, the "profile" is a JSON snapshot built entirely from existing
deterministic analytics functions and sent to Jev as the `state`; Jev only ever picks one of the
user's own options and reports its confidence — collecting context and calling the API is this
backend's job, not the frontend's.
"""
from __future__ import annotations

import json
import re

from json_repair import repair_json
from sqlalchemy.orm import Session

from app.models import User, WealthAccount, WealthAsset, WealthCategory, WealthCategoryGroup, WealthEntry, WealthGoal
from app.services import ai_provider, jev_client
from app.services.analytics import (
    compute_cashflow_series,
    compute_goal_feasibility,
    compute_liquidity,
    compute_net_worth,
)

AUTO_PREP_SYSTEM_PROMPT = """You maintain two running documents for a personal finance decision-making tool:
- "context": a short running history/summary of past decisions and their outcomes.
- "plan": a summary of the user's goals, budget, and high-level plan.
You are given the existing "context", the existing "plan", verified financial profile facts, and a
new high-level plan brief the user just typed in for a new run. Rewrite/extend both documents so
they reflect the new plan brief on top of what's already there (do not discard useful existing
history, but do fold the new brief in as the current focus). Be concrete and reference the actual
profile facts given — never invent numbers. Keep each document readable plain text, a few short
paragraphs or bullet points, not JSON. Never use a double-quote character (") inside the
context/plan text itself (use single quotes instead) since it must stay valid JSON.
Return ONLY a JSON object (no markdown fences, no commentary):
{"context": "...", "plan": "..."}"""

PROPOSE_SYSTEM_PROMPT = """You help run an autonomous decision-making loop for a personal finance app.
You are given: the user's plan brief for this run, a running "context" document (history of past
decisions), a "plan" document (goals/budget/high-level plan), verified financial profile facts, and
the list of questions already asked+decided in this run. Propose exactly ONE next concrete decision
question that would meaningfully help execute the plan, with 2 to 4 concrete, mutually exclusive
options to choose between. Never repeat a question already asked (check the list). Only reference
numbers present in the profile facts — never invent them. If there is genuinely nothing further
useful left to decide for this plan right now, say so instead. Never use a double-quote character
(") inside any text value (use single quotes instead) since it must stay valid JSON.
Return ONLY a JSON object (no markdown fences, no commentary), one of:
{"done": false, "question": "...", "options": [{"name": "...", "description": "..."}], "notes": "..."}
{"done": true}"""


def _extract_json_object(raw: str) -> dict:
    cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ai_provider.AIProviderError(f"AI response was not a JSON object: {raw[:300]!r}")
    candidate = cleaned[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except ValueError:
        # reasoning models often emit near-JSON (unescaped inner quotes, trailing commas, etc.) —
        # repair_json tolerates those before we give up.
        try:
            parsed = json.loads(repair_json(candidate))
        except ValueError as exc:
            raise ai_provider.AIProviderError(f"AI response was not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ai_provider.AIProviderError(f"AI response was not a JSON object: {raw[:300]!r}")
    return parsed


def build_profile_snapshot(db: Session, user: User) -> dict:
    """Deterministic facts about the user's financial situation, given to Jev as context."""
    accounts = db.query(WealthAccount).filter(WealthAccount.user_id == user.id).all()
    assets = db.query(WealthAsset).filter(WealthAsset.user_id == user.id).all()
    entries = db.query(WealthEntry).filter(WealthEntry.user_id == user.id).all()
    categories = db.query(WealthCategory).filter(WealthCategory.user_id == user.id).all()
    groups = db.query(WealthCategoryGroup).filter(WealthCategoryGroup.user_id == user.id).all()
    goals = db.query(WealthGoal).filter(WealthGoal.user_id == user.id).all()

    cashflow = compute_cashflow_series(entries, months_back=6)
    avg_monthly_net = round(sum(c["net"] for c in cashflow) / len(cashflow), 2) if cashflow else 0.0

    return {
        "net_worth": compute_net_worth(accounts, assets),
        "liquidity": compute_liquidity(accounts, entries, categories, groups),
        "avg_monthly_net_cashflow_last_6_months": avg_monthly_net,
        "cashflow_last_6_months": cashflow,
        "goal_feasibility": compute_goal_feasibility(goals, avg_monthly_net),
    }


def decide(db: Session, user: User, question: str, options: list[dict], notes: str | None) -> dict:
    """Runs one Choice question through Jev. `options` is [{"name": ..., "description": ...}].

    Returns {"choice", "confidence", "probabilities", "profile_snapshot"}. Raises JevError if
    Jev is disabled/unreachable — callers must handle that and still keep the decision on record.
    """
    profile = build_profile_snapshot(db, user)

    state_parts = [
        "The following are verified facts about the user's financial profile — treat them as "
        "ground truth, do not question or second-guess them:",
        json.dumps(profile, default=str),
        "",
        f"The user needs to decide: {question}",
    ]
    if notes:
        state_parts.append(f"Additional context from the user: {notes}")
    state = "\n".join(state_parts)

    criteria = {opt["name"]: (opt.get("description") or opt["name"]) for opt in options}

    answers = jev_client.ask(
        state=state,
        questions={
            "decision": {
                "type": "choice",
                "instructions": question,
                "criteria": criteria,
            }
        },
    )

    answer = answers.get("decision")
    if not isinstance(answer, dict):
        raise jev_client.JevError(f"Jev did not return a 'decision' answer: {answers!r}")

    return {
        "choice": answer.get("choice"),
        "confidence": answer.get("confidence"),
        "probabilities": answer.get("probabilities") or {},
        "profile_snapshot": profile,
    }


def prepare_auto_run(existing_context: str, existing_plan: str, plan_brief: str, profile: dict) -> dict:
    """Calls the local AI model to draft updated context/plan documents for a new auto-mode run.

    Returns {"context": str, "plan": str}. Raises ai_provider.AIProviderError if the local AI is
    disabled/unreachable/malformed — the caller reviews/edits the result before anything is sent
    to Jev, so nothing here talks to the public API.
    """
    prompt_context = {
        "existing_context": existing_context,
        "existing_plan": existing_plan,
        "new_plan_brief": plan_brief,
        "profile_snapshot": profile,
    }
    raw = ai_provider.generate(AUTO_PREP_SYSTEM_PROMPT, json.dumps(prompt_context, default=str), timeout=3600)
    data = _extract_json_object(raw)
    return {
        "context": str(data.get("context") or existing_context),
        "plan": str(data.get("plan") or existing_plan),
    }


def propose_next_step(
    plan_brief: str, context: str, plan: str, profile: dict, already_asked_questions: list[str]
) -> dict:
    """Calls the local AI model to propose the next auto-mode decision question + options.

    Returns either {"done": True} or {"done": False, "question": str, "options": [...], "notes": str
    | None}. Raises ai_provider.AIProviderError on failure/malformed output.
    """
    prompt_context = {
        "plan_brief": plan_brief,
        "context": context,
        "plan": plan,
        "profile_snapshot": profile,
        "already_asked_questions": already_asked_questions,
    }
    raw = ai_provider.generate(PROPOSE_SYSTEM_PROMPT, json.dumps(prompt_context, default=str), timeout=3600)
    return _extract_json_object(raw)
