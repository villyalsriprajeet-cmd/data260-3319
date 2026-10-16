# Part 2 endpoints: POST /api/chat, GET /api/memory/{user_id}, GET /api/aggregate/{user_id}
import uuid
from urllib.error import URLError
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from .. import memory
from ..mongo_db import get_episodes, get_messages, get_summaries
router = APIRouter(prefix="/api", tags=["Chat memory (MongoDB)"])
class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    user_id: str = Field(min_length=1, max_length=64)
    session_id: str | None = Field(default=None, min_length=1, max_length=64)  # optional, defaults to the latest session
    message: str = Field(min_length=1, max_length=2000)
def clean(doc):
    doc = {k: v for k, v in doc.items() if k not in ("_id", "embedding")}  # no ObjectId and no 384-number vectors in the JSON
    if doc.get("created_at"):
        doc["created_at"] = doc["created_at"].isoformat()
    return doc
def latest_session_id(user_id):
    doc = get_messages().find_one({"user_id": user_id}, sort=[("created_at", -1), ("_id", -1)])
    return doc["session_id"] if doc else None
@router.post("/chat")
def chat(body: ChatRequest):
    session_id = body.session_id or latest_session_id(body.user_id) or f"sess-{uuid.uuid4().hex[:8]}"  # latest session, else a new one
    try:
        out = memory.chat_turn(body.user_id, session_id, body.message)
    except (URLError, ConnectionError) as exc:
        raise HTTPException(status_code=503, detail=f"Model server is not reachable: {exc}")
    return {"user_id": body.user_id, "session_id": session_id, "reply": out["reply"], "used": out["used"], "metrics": out["metrics"]}
@router.get("/memory/{user_id}")
def get_memory(user_id: str):
    session_id = latest_session_id(user_id)
    rows = list(get_messages().find({"user_id": user_id}).sort([("created_at", -1), ("_id", -1)]).limit(16))
    facts = list(get_episodes().find({"user_id": user_id}).sort([("created_at", -1), ("_id", -1)]).limit(20))
    session_doc = get_summaries().find_one({"user_id": user_id, "scope": "session", "session_id": session_id},
                                           sort=[("created_at", -1), ("_id", -1)]) if session_id else None
    lifetime_doc = get_summaries().find_one({"user_id": user_id, "scope": "user"}, sort=[("created_at", -1), ("_id", -1)])
    return {"user_id": user_id, "session_id": session_id,
            "recent_messages": [clean(r) for r in reversed(rows)],  # oldest first
            "session_summary": clean(session_doc) if session_doc else None,
            "lifetime_summary": clean(lifetime_doc) if lifetime_doc else None,
            "episodic_facts": [clean(f) for f in facts]}
@router.get("/aggregate/{user_id}")
def aggregate(user_id: str):
    pipeline = [{"$match": {"user_id": user_id}},
                {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}}, "count": {"$sum": 1}}},  # messages per day
                {"$sort": {"_id": 1}}]
    daily = [{"date": d["_id"], "count": d["count"]} for d in get_messages().aggregate(pipeline)]
    recent = list(get_summaries().find({"user_id": user_id}).sort([("created_at", -1), ("_id", -1)]).limit(5))
    return {"user_id": user_id, "daily_message_counts": daily, "recent_summaries": [clean(s) for s in recent]}
