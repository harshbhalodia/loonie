"""Pilot: the chat that fronts the whole app. Stores the endless conversation, searches it, answers
free-form questions from the user's computed profile, and recognises uploaded statements."""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import PilotMessage, User, WealthAccount
from app.schemas import (
    PilotAskIn,
    PilotAskOut,
    PilotMessageIn,
    PilotMessageOut,
    PilotSearchHit,
    StatementIdentifyOut,
)
from app.services import ai_provider, decision_agent, fx
from app.services.statement_identify import identify_statement
from app.models import MarketplaceDataGrant, MarketplaceInstalledBlueprint
from app.routers import marketplace
from app.schemas import (
    BlueprintRunResult,
    DataScopeOut,
    GrantScopesIn,
    PilotAdvisorOut,
    PilotAdvisorRunIn,
    PilotAdvisorsOut,
)
from app.services import marketplace_catalog, wealth_scopes
from app.services.marketplace_catalog import BlueprintDefinition

router = APIRouter(prefix="/pilot", tags=["pilot"])

MAX_PAYLOAD_CHARS = 200_000

ASK_SYSTEM_PROMPT = """You are Pilot, the assistant inside Loonie, a personal finance app.
You receive the user's question plus pre-computed, trusted facts as JSON. Answer only from those
facts; never invent or recompute a figure that isn't present. If the facts don't cover the
question, say what is missing and which Loonie page or action would help. Amounts are in the
currency named by base_currency. Be warm, concrete and brief (3-6 sentences, plain text, no
markdown headers). This is decision support, not licensed financial advice."""


def _to_out(row: PilotMessage) -> PilotMessageOut:
    try:
        payload = json.loads(row.payload_json) if row.payload_json else None
    except ValueError:
        payload = None
    return PilotMessageOut(id=row.id, role=row.role, text=row.text, payload=payload, created_at=row.created_at)


@router.get("/messages", response_model=list[PilotMessageOut])
def list_messages(
    before: datetime | None = None,
    role: str | None = None,
    limit: int = Query(default=30, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Newest first. Pass the oldest loaded message's `created_at` as `before` to page backwards."""
    query = db.query(PilotMessage).filter(PilotMessage.user_id == user.id)
    if before is not None:
        query = query.filter(PilotMessage.created_at < before)
    if role in ("user", "assistant"):
        query = query.filter(PilotMessage.role == role)
    rows = query.order_by(PilotMessage.created_at.desc()).limit(limit).all()
    return [_to_out(r) for r in rows]


@router.post("/messages", response_model=PilotMessageOut)
def add_message(payload: PilotMessageIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    encoded = json.dumps(payload.payload) if payload.payload else None
    if encoded and len(encoded) > MAX_PAYLOAD_CHARS:
        raise HTTPException(status_code=413, detail="Message payload is too large")
    row = PilotMessage(user_id=user.id, role=payload.role, text=payload.text, payload_json=encoded)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.delete("/messages", status_code=204)
def clear_messages(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(PilotMessage).filter(PilotMessage.user_id == user.id).delete()
    db.commit()


@router.get("/search", response_model=list[PilotSearchHit])
def search_messages(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=30, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Finds past questions and answers containing the text; each question comes with its reply."""
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    rows = (
        db.query(PilotMessage)
        .filter(PilotMessage.user_id == user.id, PilotMessage.text.ilike(f"%{escaped}%", escape="\\"))
        .order_by(PilotMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    hits: list[PilotSearchHit] = []
    seen: set[str] = set()
    for row in rows:
        if row.role == "user":
            question, answer = row, _next_reply(db, user.id, row)
        else:
            question = _previous_question(db, user.id, row)
            answer = row if question is not None else None
            question = question or row
        if question.id in seen:
            continue
        seen.add(question.id)
        hits.append(PilotSearchHit(message=_to_out(question), reply=_to_out(answer) if answer else None))
    return hits


def _next_reply(db: Session, user_id: str, question: PilotMessage) -> PilotMessage | None:
    return (
        db.query(PilotMessage)
        .filter(PilotMessage.user_id == user_id, PilotMessage.role == "assistant", PilotMessage.created_at > question.created_at)
        .order_by(PilotMessage.created_at.asc())
        .first()
    )


def _previous_question(db: Session, user_id: str, answer: PilotMessage) -> PilotMessage | None:
    return (
        db.query(PilotMessage)
        .filter(PilotMessage.user_id == user_id, PilotMessage.role == "user", PilotMessage.created_at < answer.created_at)
        .order_by(PilotMessage.created_at.desc())
        .first()
    )


@router.post("/ask", response_model=PilotAskOut)
def ask(payload: PilotAskIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Free-form question, answered by the user's own AI model from their computed profile."""
    if not ai_provider.is_ai_enabled():
        raise HTTPException(status_code=503, detail="AI is turned off. Turn it on under Settings → AI model to ask free-form questions.")
    facts = decision_agent.build_profile_snapshot(db, user)
    facts.setdefault("base_currency", fx.get_base_currency(db, user.id))
    try:
        answer = ai_provider.generate(
            ASK_SYSTEM_PROMPT, json.dumps({"question": payload.question, "facts": facts}, default=str), timeout=600
        )
    except ai_provider.AIProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PilotAskOut(answer=answer.strip())


@router.post("/identify-statement", response_model=StatementIdentifyOut)
async def identify(file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Recognises a dropped statement (type, currency, likely account) so the user never has to pick."""
    accounts = db.query(WealthAccount).filter(WealthAccount.user_id == user.id).all()
    name = file.filename or "statement"
    guess = identify_statement(name, await file.read(), accounts)
    return StatementIdentifyOut(
        file_name=name,
        file_type=guess.file_type,
        kind=guess.kind,
        kind_label=guess.kind_label,
        currency=guess.currency,
        last4=guess.last4,
        matched_account_id=guess.matched_account_id,
        confidence=guess.confidence,
        candidates=guess.candidates,
        reasons=guess.reasons,
    )


# ---------------- advisors: packs from LocalAgents Studio, invisible to the user ----------------


def _requested_ids(definition: BlueprintDefinition) -> list[str]:
    return [s for s in definition.inputs if s in wealth_scopes.known_scope_ids()]


def _installed_ids(db: Session, user_id: str) -> set[str]:
    rows = db.query(MarketplaceInstalledBlueprint.blueprint_id).filter(MarketplaceInstalledBlueprint.user_id == user_id)
    return {blueprint_id for (blueprint_id,) in rows}


def _granted(db: Session, user_id: str, blueprint_id: str) -> list[str]:
    grant = (
        db.query(MarketplaceDataGrant)
        .filter(MarketplaceDataGrant.user_id == user_id, MarketplaceDataGrant.blueprint_id == blueprint_id)
        .first()
    )
    return json.loads(grant.granted_scopes_json) if grant else []


def _is_available(definition: BlueprintDefinition, installed: set[str]) -> bool:
    """Free packs and anything Studio delivered are simply there; other paid packs need an install."""
    return definition.source == "studio" or definition.tier == "free" or definition.id in installed


def _advisor_out(definition: BlueprintDefinition, granted: list[str]) -> PilotAdvisorOut:
    requested = wealth_scopes.describe(_requested_ids(definition))
    ids = [r.id for r in requested]
    return PilotAdvisorOut(
        id=definition.id,
        name=definition.name,
        publisher=definition.publisher,
        version=definition.version,
        kind=definition.kind,
        summary=definition.summary,
        examples=definition.examples,
        triggers=definition.triggers,
        scenario_count=len(definition.scenarios),
        requested=[DataScopeOut(**r.__dict__) for r in requested],
        granted=[g for g in granted if g in ids],
        consent_needed=any(i not in granted for i in ids),
        source=definition.source,
        tier=definition.tier,
    )


@router.get("/advisors", response_model=PilotAdvisorsOut)
def list_advisors(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Every advisor Pilot can use for this person, with what each would need to read."""
    marketplace_catalog.ADVISORS_DIR.mkdir(parents=True, exist_ok=True)
    installed = _installed_ids(db, user.id)
    return PilotAdvisorsOut(
        advisors=[
            _advisor_out(d, _granted(db, user.id, d.id))
            for d in marketplace_catalog.load_catalog()
            if _is_available(d, installed)
        ],
        folder=str(marketplace_catalog.ADVISORS_DIR),
        problems=marketplace_catalog.load_problems(),
    )


@router.post("/advisors/{advisor_id}/run", response_model=BlueprintRunResult)
def run_advisor(
    advisor_id: str,
    payload: PilotAdvisorRunIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Runs an advisor for the chat. Agreeing to share data happens in the conversation
    (`allow`), and only ever covers the categories that advisor declares."""
    try:
        definition = marketplace_catalog.get_blueprint(advisor_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown advisor") from None
    if not _is_available(definition, _installed_ids(db, user.id)):
        raise HTTPException(status_code=402, detail=f"{definition.name} isn't included with your account.")

    row = (
        db.query(MarketplaceInstalledBlueprint)
        .filter(MarketplaceInstalledBlueprint.user_id == user.id, MarketplaceInstalledBlueprint.blueprint_id == advisor_id)
        .first()
    )
    if row is None:
        row = MarketplaceInstalledBlueprint(user_id=user.id, blueprint_id=advisor_id)
        db.add(row)
    row.version = definition.version
    row.tier = definition.tier
    db.commit()

    if payload.allow:
        marketplace.grant_scopes(advisor_id, GrantScopesIn(scopes=_requested_ids(definition)), user, db)
    return marketplace.run(advisor_id, user, db)
