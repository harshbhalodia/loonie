"""Keyword auto-learning review workflow.

wealth_keyword_candidates are auto-flagged (see services/statement_apply.py) whenever an applied
statement transaction lands with no category. This router lets the user review them, optionally
ask the AI for a best-guess category per keyword, and approve/reject each one. Approving creates
a real `WealthCategoryRule` so future statements auto-categorize that keyword deterministically.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, WealthKeywordCandidate
from app.schemas import KeywordCandidateDecisionIn, KeywordCandidateOut
from app.services import ai_provider, keyword_learning

router = APIRouter(prefix="/wealth/keyword-candidates", tags=["wealth:keyword-candidates"])


@router.get("", response_model=list[KeywordCandidateOut])
def list_candidates(
    status: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(WealthKeywordCandidate).filter(WealthKeywordCandidate.user_id == user.id)
    if status:
        query = query.filter(WealthKeywordCandidate.status == status)
    return query.order_by(WealthKeywordCandidate.occurrence_count.desc()).all()


@router.post("/learn", response_model=list[KeywordCandidateOut])
def learn_candidates(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Asks the AI to propose a category for every pending candidate with no suggestion yet.
    This is a one-off direct call to the AI provider (bypasses the generic agent framework since
    the output here is structured per-keyword data, not a free-text insight)."""
    try:
        return keyword_learning.suggest_categories(db, user)
    except ai_provider.AIProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _get_owned_candidate(db: Session, user: User, candidate_id: str) -> WealthKeywordCandidate:
    candidate = db.get(WealthKeywordCandidate, candidate_id)
    if not candidate or candidate.user_id != user.id:
        raise HTTPException(status_code=404, detail="Keyword candidate not found")
    return candidate


@router.post("/{candidate_id}/approve")
def approve_candidate(
    candidate_id: str,
    payload: KeywordCandidateDecisionIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    candidate = _get_owned_candidate(db, user, candidate_id)
    category_id = payload.category_id or candidate.suggested_category_id
    if not category_id:
        raise HTTPException(status_code=422, detail="A category_id is required (no suggestion was ever made)")
    rule = keyword_learning.approve_candidate(db, candidate, category_id)
    return {"rule_id": rule.id, "candidate_id": candidate.id}


@router.post("/{candidate_id}/reject", status_code=204)
def reject_candidate(candidate_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    candidate = _get_owned_candidate(db, user, candidate_id)
    keyword_learning.reject_candidate(db, candidate)
