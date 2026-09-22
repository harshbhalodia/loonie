import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import AgentExecutionLog, User, WealthInsight
from app.schemas import AgentExecutionOut, AgentInfo, AgentRunResult, InsightOut
from app.services import ai_provider
from app.services.agents import AGENTS, run_agent

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentInfo])
def list_agents():
    return [
        AgentInfo(id=a.id, name=a.name, version=a.version, description=a.description, reads=a.reads, writes=a.writes)
        for a in AGENTS.values()
    ]


@router.post("/{agent_id}/run", response_model=AgentRunResult)
def run(agent_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if agent_id not in AGENTS:
        raise HTTPException(status_code=404, detail="Unknown agent")

    log = AgentExecutionLog(
        user_id=user.id,
        agent_id=agent_id,
        agent_version=AGENTS[agent_id].version,
        status="ok",
        input_ref="",
    )

    try:
        summary, facts = run_agent(agent_id, db, user)
        log.input_ref = json.dumps({"reads": AGENTS[agent_id].reads})
        log.output = summary
        db.add(log)

        db.add(
            WealthInsight(
                user_id=user.id,
                agent_id=agent_id,
                severity="info",
                summary=summary,
                facts_json=json.dumps(facts, default=str),
            )
        )
        db.commit()
        return AgentRunResult(agent_id=agent_id, status="ok", summary=summary, facts=facts)

    except ai_provider.AIProviderError as exc:
        log.status = "error"
        log.error = str(exc)
        db.add(log)
        db.commit()
        return AgentRunResult(agent_id=agent_id, status="error", error=str(exc))


@router.get("/{agent_id}/history", response_model=list[AgentExecutionOut])
def history(agent_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(AgentExecutionLog)
        .filter(AgentExecutionLog.user_id == user.id, AgentExecutionLog.agent_id == agent_id)
        .order_by(AgentExecutionLog.created_at.desc())
        .limit(50)
        .all()
    )


insights_router = APIRouter(prefix="/wealth/insights", tags=["wealth:insights"])


@insights_router.get("", response_model=list[InsightOut])
def list_insights(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(WealthInsight)
        .filter(WealthInsight.user_id == user.id)
        .order_by(WealthInsight.created_at.desc())
        .limit(50)
        .all()
    )
