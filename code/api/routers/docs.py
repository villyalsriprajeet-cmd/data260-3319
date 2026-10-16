# Part 1 CRUD routes for the MongoDB fixtures collection 
from datetime import datetime, timezone
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Query
from pymongo import ReturnDocument
from ..doc_schemas import FixtureDocCreate, FixtureDocOut, FixtureDocUpdate
from ..mongo_db import get_fixtures
router = APIRouter(prefix="/api/fixtures", tags=["Fixtures (MongoDB)"])
def to_object_id(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid id format: {value}")  
def serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))  
    return doc
@router.post("", response_model=FixtureDocOut, status_code=201)
def create_fixture(payload: FixtureDocCreate):
    now = datetime.now(timezone.utc)
    doc = {**payload.model_dump(), "created_at": now, "updated_at": now}  # timestamps set by the server
    doc["_id"] = get_fixtures().insert_one(doc).inserted_id
    return serialize(doc)
@router.get("", response_model=list[FixtureDocOut])
def list_fixtures(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
    cursor = get_fixtures().find().sort("created_at", -1).skip(skip).limit(limit)  # newest first
    return [serialize(d) for d in cursor]
@router.get("/{fixture_id}", response_model=FixtureDocOut)
def get_fixture(fixture_id: str):
    doc = get_fixtures().find_one({"_id": to_object_id(fixture_id)})
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Fixture {fixture_id} not found")
    return serialize(doc)
@router.put("/{fixture_id}", response_model=FixtureDocOut)
def update_fixture(fixture_id: str, payload: FixtureDocUpdate):
    oid = to_object_id(fixture_id)
    changes = payload.model_dump(exclude_unset=True)  # only the fields that were sent
    if not changes:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    changes["updated_at"] = datetime.now(timezone.utc)
    doc = get_fixtures().find_one_and_update({"_id": oid}, {"$set": changes}, return_document=ReturnDocument.AFTER)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Fixture {fixture_id} not found")
    return serialize(doc)
@router.delete("/{fixture_id}")
def delete_fixture(fixture_id: str):
    if get_fixtures().delete_one({"_id": to_object_id(fixture_id)}).deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"Fixture {fixture_id} not found")
    return {"message": "Fixture deleted", "id": fixture_id}