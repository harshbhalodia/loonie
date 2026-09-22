"""Read-only view of queued/processing background jobs (statement parsing), for frontend
progress polling — see services/job_queue.py for the actual single-worker processing."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, WealthJob
from app.schemas import JobOut

router = APIRouter(prefix="/wealth/jobs", tags=["wealth:jobs"])


@router.get("", response_model=list[JobOut])
def list_jobs(status: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(WealthJob).filter(WealthJob.user_id == user.id)
    if status:
        query = query.filter(WealthJob.status == status)
    return query.order_by(WealthJob.created_at.desc()).limit(100).all()
