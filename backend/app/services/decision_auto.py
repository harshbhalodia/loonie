"""Decision Maker auto mode: an autonomous loop that proposes decision questions/options via the
local AI model and evaluates each one through Jev, one round at a time.

There is deliberately no server-side background loop — each round is driven by an explicit
`run_step` call from the frontend, so a run can never keep going unattended once the browser stops
calling it. The user reviews/edits the drafted context+plan documents before the first Jev call,
and can stop a run at any time.
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models import DecisionAutoSession, DecisionContext, DecisionPlan, DecisionRecord, User
from app.services import decision_agent, jev_client

# Every character here gets resent to the local model on every single round, and a run can go for
# 50+ rounds unattended overnight — keep the prompt bounded so generation doesn't slow to a crawl
# (or blow past the model's context window) as the run goes on. The DB row always keeps the full
# text; only the tail is fed back into the prompt.
MAX_CONTEXT_CHARS_FOR_PROMPT = 4000
MAX_PLAN_CHARS_FOR_PROMPT = 3000
MAX_ASKED_QUESTIONS_FOR_PROMPT = 20


def _tail(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return "...(earlier history omitted)...\n" + text[-max_chars:]


def get_context(db: Session, user: User) -> DecisionContext:
    row = db.query(DecisionContext).filter(DecisionContext.user_id == user.id).first()
    if not row:
        row = DecisionContext(user_id=user.id, content="")
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def get_plan(db: Session, user: User) -> DecisionPlan:
    row = db.query(DecisionPlan).filter(DecisionPlan.user_id == user.id).first()
    if not row:
        row = DecisionPlan(user_id=user.id, content="")
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def update_context(db: Session, user: User, content: str) -> DecisionContext:
    row = get_context(db, user)
    row.content = content
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_plan(db: Session, user: User, content: str) -> DecisionPlan:
    row = get_plan(db, user)
    row.content = content
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def start_session(db: Session, user: User, plan_brief: str) -> tuple[DecisionAutoSession, str, str]:
    """Drafts updated context/plan documents for this run via the local AI model, saves them, and
    creates the session. The caller (router) surfaces the draft for the user to review/edit before
    the first `run_step` call actually talks to Jev."""
    context_row = get_context(db, user)
    plan_row = get_plan(db, user)
    profile = decision_agent.build_profile_snapshot(db, user)

    drafted = decision_agent.prepare_auto_run(
        _tail(context_row.content, MAX_CONTEXT_CHARS_FOR_PROMPT),
        _tail(plan_row.content, MAX_PLAN_CHARS_FOR_PROMPT),
        plan_brief,
        profile,
    )

    context_row.content = drafted["context"]
    plan_row.content = drafted["plan"]

    session = DecisionAutoSession(user_id=user.id, plan_brief=plan_brief, status="running")

    db.add(context_row)
    db.add(plan_row)
    db.add(session)
    db.commit()
    db.refresh(context_row)
    db.refresh(plan_row)
    db.refresh(session)
    return session, context_row.content, plan_row.content


def run_step(db: Session, user: User, session: DecisionAutoSession) -> dict:
    """Runs exactly one round: propose a question via the local AI model, evaluate it via Jev,
    record it, and append a short summary line to the running context document."""
    context_row = get_context(db, user)
    plan_row = get_plan(db, user)
    profile = decision_agent.build_profile_snapshot(db, user)

    asked_questions = [
        r.question
        for r in db.query(DecisionRecord)
        .filter(DecisionRecord.session_id == session.id)
        .order_by(DecisionRecord.created_at.asc())
        .all()
    ]

    proposal = decision_agent.propose_next_step(
        session.plan_brief,
        _tail(context_row.content, MAX_CONTEXT_CHARS_FOR_PROMPT),
        _tail(plan_row.content, MAX_PLAN_CHARS_FOR_PROMPT),
        profile,
        asked_questions[-MAX_ASKED_QUESTIONS_FOR_PROMPT:],
    )

    if proposal.get("done"):
        session.status = "done"
        db.add(session)
        db.commit()
        db.refresh(session)
        return {
            "session": session,
            "decision": None,
            "done": True,
            "message": "The model found nothing further to decide for this plan.",
        }

    question = str(proposal.get("question") or "").strip()
    raw_options = proposal.get("options") or []
    options = [
        {"name": str(o.get("name") or "").strip(), "description": (o.get("description") or None)}
        for o in raw_options
        if isinstance(o, dict) and str(o.get("name") or "").strip()
    ]
    if not question or len(options) < 2:
        raise jev_client.JevError(f"Auto-mode proposal was incomplete: {proposal!r}")

    notes = proposal.get("notes") or None
    round_number = session.rounds_completed + 1

    record = DecisionRecord(
        user_id=user.id,
        session_id=session.id,
        round_number=round_number,
        question=question,
        notes=notes,
        options_json=json.dumps(options),
    )

    try:
        result = decision_agent.decide(db, user, question, options, notes)
        record.chosen_option = result["choice"]
        record.confidence = result["confidence"]
        record.probabilities_json = json.dumps(result["probabilities"])
        record.profile_snapshot_json = json.dumps(result["profile_snapshot"], default=str)
        record.status = "ok"
        confidence_pct = round((record.confidence or 0) * 100)
        summary_line = f'Round {round_number}: {question} -> chose "{record.chosen_option}" ({confidence_pct}% confidence).'
    except jev_client.JevError as exc:
        record.status = "error"
        record.error = str(exc)
        summary_line = f"Round {round_number}: {question} -> Jev error: {exc}"

    session.rounds_completed = round_number
    context_row.content = (context_row.content + "\n" + summary_line).strip()

    db.add(record)
    db.add(session)
    db.add(context_row)
    db.commit()
    db.refresh(record)
    db.refresh(session)

    return {"session": session, "decision": record, "done": False, "message": None}


def stop_session(db: Session, user: User, session: DecisionAutoSession) -> DecisionAutoSession:
    session.status = "stopped"
    db.add(session)
    db.commit()
    db.refresh(session)
    return session
