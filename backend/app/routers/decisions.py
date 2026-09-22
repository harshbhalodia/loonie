import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_jev_config
from app.database import get_db
from app.deps import get_current_user
from app.models import DecisionAutoSession, DecisionRecord, User
from app.schemas import (
    AutoSessionOut,
    AutoSessionStartIn,
    AutoSessionStartOut,
    AutoStepOut,
    DecisionContextIn,
    DecisionContextOut,
    DecisionCreateIn,
    DecisionOut,
    DecisionPlanIn,
    DecisionPlanOut,
    JevStatus,
)
from app.services import ai_provider, decision_agent, decision_auto, jev_client

router = APIRouter(prefix="/decisions", tags=["decisions"])
jev_router = APIRouter(prefix="/jev", tags=["jev"])


def _to_out(record: DecisionRecord) -> DecisionOut:
    return DecisionOut(
        id=record.id,
        session_id=record.session_id,
        round_number=record.round_number,
        question=record.question,
        notes=record.notes,
        options=json.loads(record.options_json),
        chosen_option=record.chosen_option,
        confidence=record.confidence,
        probabilities=json.loads(record.probabilities_json) if record.probabilities_json else {},
        profile_snapshot=json.loads(record.profile_snapshot_json) if record.profile_snapshot_json else None,
        status=record.status,
        error=record.error,
        created_at=record.created_at,
    )


def _session_out(session: DecisionAutoSession) -> AutoSessionOut:
    return AutoSessionOut(
        id=session.id,
        plan_brief=session.plan_brief,
        status=session.status,
        rounds_completed=session.rounds_completed,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _load_session(db: Session, user: User, session_id: str) -> DecisionAutoSession:
    session = (
        db.query(DecisionAutoSession)
        .filter(DecisionAutoSession.id == session_id, DecisionAutoSession.user_id == user.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Auto session not found")
    return session


@jev_router.get("/status", response_model=JevStatus)
def jev_status(user: User = Depends(get_current_user)):
    cfg = get_jev_config()
    return JevStatus(
        enabled=bool(cfg.get("enabled", False) and cfg.get("api_key")),
        model=cfg.get("model"),
        base_url=cfg.get("base_url") or jev_client.DEFAULT_BASE_URL,
    )


@router.get("", response_model=list[DecisionOut])
def list_decisions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    records = (
        db.query(DecisionRecord)
        .filter(DecisionRecord.user_id == user.id)
        .order_by(DecisionRecord.created_at.desc())
        .limit(100)
        .all()
    )
    return [_to_out(r) for r in records]


@router.post("", response_model=DecisionOut)
def create_decision(payload: DecisionCreateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    options = [o.model_dump() for o in payload.options]
    record = DecisionRecord(
        user_id=user.id,
        question=payload.question,
        notes=payload.notes,
        options_json=json.dumps(options),
    )

    try:
        result = decision_agent.decide(db, user, payload.question, options, payload.notes)
        record.chosen_option = result["choice"]
        record.confidence = result["confidence"]
        record.probabilities_json = json.dumps(result["probabilities"])
        record.profile_snapshot_json = json.dumps(result["profile_snapshot"], default=str)
        record.status = "ok"
    except jev_client.JevError as exc:
        record.status = "error"
        record.error = str(exc)

    db.add(record)
    db.commit()
    db.refresh(record)
    return _to_out(record)


@router.get("/context", response_model=DecisionContextOut)
def get_context(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = decision_auto.get_context(db, user)
    return DecisionContextOut(content=row.content, updated_at=row.updated_at)


@router.put("/context", response_model=DecisionContextOut)
def put_context(payload: DecisionContextIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = decision_auto.update_context(db, user, payload.content)
    return DecisionContextOut(content=row.content, updated_at=row.updated_at)


@router.get("/plan", response_model=DecisionPlanOut)
def get_plan(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = decision_auto.get_plan(db, user)
    return DecisionPlanOut(content=row.content, updated_at=row.updated_at)


@router.put("/plan", response_model=DecisionPlanOut)
def put_plan(payload: DecisionPlanIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = decision_auto.update_plan(db, user, payload.content)
    return DecisionPlanOut(content=row.content, updated_at=row.updated_at)


@router.post("/auto/start", response_model=AutoSessionStartOut)
def start_auto_session(
    payload: AutoSessionStartIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    try:
        session, context, plan = decision_auto.start_session(db, user, payload.plan_brief)
    except ai_provider.AIProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return AutoSessionStartOut(session=_session_out(session), context=context, plan=plan)


@router.get("/auto", response_model=list[AutoSessionOut])
def list_auto_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sessions = (
        db.query(DecisionAutoSession)
        .filter(DecisionAutoSession.user_id == user.id)
        .order_by(DecisionAutoSession.created_at.desc())
        .all()
    )
    return [_session_out(s) for s in sessions]


@router.get("/auto/{session_id}", response_model=AutoSessionOut)
def get_auto_session(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _session_out(_load_session(db, user, session_id))


@router.post("/auto/{session_id}/step", response_model=AutoStepOut)
def step_auto_session(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = _load_session(db, user, session_id)
    if session.status != "running":
        raise HTTPException(status_code=400, detail=f"Session is {session.status}, not running.")
    try:
        result = decision_auto.run_step(db, user, session)
    except (ai_provider.AIProviderError, jev_client.JevError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return AutoStepOut(
        session=_session_out(result["session"]),
        decision=_to_out(result["decision"]) if result["decision"] else None,
        done=result["done"],
        message=result["message"],
    )


@router.post("/auto/{session_id}/stop", response_model=AutoSessionOut)
def stop_auto_session(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = _load_session(db, user, session_id)
    return _session_out(decision_auto.stop_session(db, user, session))


@router.get("/{decision_id}", response_model=DecisionOut)
def get_decision(decision_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    record = db.query(DecisionRecord).filter(DecisionRecord.id == decision_id, DecisionRecord.user_id == user.id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Decision not found")
    return _to_out(record)


@router.delete("/{decision_id}", status_code=204)
def delete_decision(decision_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    record = db.query(DecisionRecord).filter(DecisionRecord.id == decision_id, DecisionRecord.user_id == user.id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Decision not found")
    db.delete(record)
    db.commit()
