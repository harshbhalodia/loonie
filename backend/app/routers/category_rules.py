from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, WealthCategoryRule
from app.schemas import CategoryRuleIn, CategoryRuleOut

router = APIRouter(prefix="/wealth/category-rules", tags=["wealth:category-rules"])


@router.get("", response_model=list[CategoryRuleOut])
def list_category_rules(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(WealthCategoryRule)
        .filter(WealthCategoryRule.user_id == user.id)
        .order_by(WealthCategoryRule.keyword)
        .all()
    )


@router.put("", response_model=CategoryRuleOut)
def upsert_category_rule(payload: CategoryRuleIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rule = db.get(WealthCategoryRule, payload.id) if payload.id else None
    if rule and rule.user_id != user.id:
        raise HTTPException(status_code=404, detail="Rule not found")

    if not rule:
        rule = WealthCategoryRule(user_id=user.id)
        db.add(rule)

    for field in ("keyword", "category_id"):
        setattr(rule, field, getattr(payload, field))

    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=204)
def delete_category_rule(rule_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rule = db.get(WealthCategoryRule, rule_id)
    if not rule or rule.user_id != user.id:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()
