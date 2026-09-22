from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, WealthCategory
from app.schemas import CategoryIn, CategoryOut

router = APIRouter(prefix="/wealth/categories", tags=["wealth:categories"])


@router.get("", response_model=list[CategoryOut])
def list_categories(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(WealthCategory)
        .filter(WealthCategory.user_id == user.id)
        .order_by(WealthCategory.group_id, WealthCategory.name)
        .all()
    )


@router.put("", response_model=CategoryOut)
def upsert_category(payload: CategoryIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    category = db.get(WealthCategory, payload.id) if payload.id else None
    if category and category.user_id != user.id:
        raise HTTPException(status_code=404, detail="Category not found")

    if not category:
        category = WealthCategory(user_id=user.id)
        db.add(category)

    for field in ("name", "group_id", "kind", "color", "is_archived"):
        setattr(category, field, getattr(payload, field))

    db.commit()
    db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=204)
def delete_category(category_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    category = db.get(WealthCategory, category_id)
    if not category or category.user_id != user.id:
        raise HTTPException(status_code=404, detail="Category not found")
    db.delete(category)
    db.commit()
