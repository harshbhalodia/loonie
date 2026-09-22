from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, WealthCategory, WealthCategoryGroup
from app.schemas import CategoryGroupIn, CategoryGroupOut

router = APIRouter(prefix="/wealth/category-groups", tags=["wealth:category-groups"])


@router.get("", response_model=list[CategoryGroupOut])
def list_category_groups(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(WealthCategoryGroup)
        .filter(WealthCategoryGroup.user_id == user.id)
        .order_by(WealthCategoryGroup.sort_order, WealthCategoryGroup.name)
        .all()
    )


@router.put("", response_model=CategoryGroupOut)
def upsert_category_group(payload: CategoryGroupIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    group = db.get(WealthCategoryGroup, payload.id) if payload.id else None
    if group and group.user_id != user.id:
        raise HTTPException(status_code=404, detail="Category group not found")

    if not group:
        group = WealthCategoryGroup(user_id=user.id)
        db.add(group)

    for field in ("name", "color", "sort_order", "is_essential"):
        setattr(group, field, getattr(payload, field))

    db.commit()
    db.refresh(group)
    return group


@router.delete("/{group_id}", status_code=204)
def delete_category_group(group_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    group = db.get(WealthCategoryGroup, group_id)
    if not group or group.user_id != user.id:
        raise HTTPException(status_code=404, detail="Category group not found")

    in_use = db.query(WealthCategory).filter(WealthCategory.group_id == group_id).count()
    if in_use:
        raise HTTPException(status_code=400, detail="Reassign categories using this group before deleting it")

    db.delete(group)
    db.commit()
