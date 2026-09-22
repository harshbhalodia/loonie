from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, WealthGoal
from app.schemas import GoalIn, GoalOut

router = APIRouter(prefix="/wealth/goals", tags=["wealth:goals"])


@router.get("", response_model=list[GoalOut])
def list_goals(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(WealthGoal).filter(WealthGoal.user_id == user.id).order_by(WealthGoal.created_at).all()


@router.put("", response_model=GoalOut)
def upsert_goal(payload: GoalIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    goal = db.get(WealthGoal, payload.id) if payload.id else None
    if goal and goal.user_id != user.id:
        raise HTTPException(status_code=404, detail="Goal not found")

    if not goal:
        goal = WealthGoal(user_id=user.id)
        db.add(goal)

    for field in ("name", "goal_type", "target_amount", "current_amount", "target_date"):
        setattr(goal, field, getattr(payload, field))

    db.commit()
    db.refresh(goal)
    return goal


@router.post("/{goal_id}/achieve", response_model=GoalOut)
def achieve_goal(goal_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    goal = db.get(WealthGoal, goal_id)
    if not goal or goal.user_id != user.id:
        raise HTTPException(status_code=404, detail="Goal not found")
    goal.achieved_at = date.today()
    db.commit()
    db.refresh(goal)
    return goal


@router.post("/{goal_id}/reopen", response_model=GoalOut)
def reopen_goal(goal_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    goal = db.get(WealthGoal, goal_id)
    if not goal or goal.user_id != user.id:
        raise HTTPException(status_code=404, detail="Goal not found")
    goal.achieved_at = None
    db.commit()
    db.refresh(goal)
    return goal


@router.delete("/{goal_id}", status_code=204)
def delete_goal(goal_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    goal = db.get(WealthGoal, goal_id)
    if not goal or goal.user_id != user.id:
        raise HTTPException(status_code=404, detail="Goal not found")
    db.delete(goal)
    db.commit()
