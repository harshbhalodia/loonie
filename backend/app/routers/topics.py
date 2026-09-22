from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, WealthTopic
from app.schemas import TopicIn, TopicOut

router = APIRouter(prefix="/wealth/topics", tags=["wealth:topics"])

TOPIC_FIELDS = ("title", "description", "category", "status", "related_goal_id", "priority")


@router.get("", response_model=list[TopicOut])
def list_topics(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(WealthTopic)
        .filter(WealthTopic.user_id == user.id)
        .order_by(WealthTopic.priority.desc(), WealthTopic.created_at.desc())
        .all()
    )


@router.put("", response_model=TopicOut)
def upsert_topic(payload: TopicIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    topic = db.get(WealthTopic, payload.id) if payload.id else None
    if topic and topic.user_id != user.id:
        raise HTTPException(status_code=404, detail="Topic not found")

    if not topic:
        topic = WealthTopic(user_id=user.id)
        db.add(topic)

    for field in TOPIC_FIELDS:
        setattr(topic, field, getattr(payload, field))

    db.commit()
    db.refresh(topic)
    return topic


@router.delete("/{topic_id}", status_code=204)
def delete_topic(topic_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    topic = db.get(WealthTopic, topic_id)
    if not topic or topic.user_id != user.id:
        raise HTTPException(status_code=404, detail="Topic not found")
    db.delete(topic)
    db.commit()
