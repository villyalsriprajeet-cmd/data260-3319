# PyMongo connection, collection rules and indexes for the fixtures (Part 1) and memory (Part 2) collections
from pymongo import ASCENDING, MongoClient
from .config import (CATEGORY_VALUES, EPISODES_COLLECTION, FIXTURES_COLLECTION, MESSAGES_COLLECTION, MONGODB_DB,
                     MONGODB_URI, STATUS_VALUES, SUMMARIES_COLLECTION)
_client = None  # one shared client for the whole app
def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=3000)  # fail fast if Mongo is down
    return _client
def get_db():
    return get_client()[MONGODB_DB]
def get_fixtures():
    return get_db()[FIXTURES_COLLECTION]
def get_messages():
    return get_db()[MESSAGES_COLLECTION]
def get_summaries():
    return get_db()[SUMMARIES_COLLECTION]
def get_episodes():
    return get_db()[EPISODES_COLLECTION]
FIXTURES_VALIDATOR = {"$jsonSchema": {
    "bsonType": "object",
    "required": ["fixture_title", "status", "category", "kickoff_at", "created_at", "updated_at"],  # mandatory fields
    "properties": {
        "fixture_title": {"bsonType": "string", "minLength": 1, "maxLength": 100},  # required short text
        "description": {"bsonType": ["string", "null"]},  # optional text
        "status": {"enum": STATUS_VALUES},  # constrained field with a default set by the API
        "category": {"enum": CATEGORY_VALUES},  # constrained field with a fixed set
        "kickoff_at": {"bsonType": "date"},  # required date/time
        "created_at": {"bsonType": "date"},
        "updated_at": {"bsonType": "date"},
    }}}
MESSAGES_VALIDATOR = {"$jsonSchema": {
    "bsonType": "object",
    "required": ["user_id", "session_id", "role", "content", "created_at"],
    "properties": {
        "user_id": {"bsonType": "string"},
        "session_id": {"bsonType": "string"},
        "role": {"enum": ["user", "assistant"]},
        "content": {"bsonType": "string"},
        "created_at": {"bsonType": "date"},
    }}}
SUMMARIES_VALIDATOR = {"$jsonSchema": {
    "bsonType": "object",
    "required": ["user_id", "session_id", "scope", "text", "created_at"],
    "properties": {
        "user_id": {"bsonType": "string"},
        "session_id": {"bsonType": ["string", "null"]},  # null for the lifetime summary
        "scope": {"enum": ["session", "user"]},
        "text": {"bsonType": "string"},
        "created_at": {"bsonType": "date"},
    }}}
EPISODES_VALIDATOR = {"$jsonSchema": {
    "bsonType": "object",
    "required": ["user_id", "session_id", "fact", "importance", "embedding", "created_at"],
    "properties": {
        "user_id": {"bsonType": "string"},
        "session_id": {"bsonType": "string"},
        "fact": {"bsonType": "string", "minLength": 1, "maxLength": 300},
        "importance": {"bsonType": ["double", "int"], "minimum": 0, "maximum": 1},
        "embedding": {"bsonType": "array", "items": {"bsonType": "double"}},
        "created_at": {"bsonType": "date"},
    }}}
COLLECTIONS = {
    FIXTURES_COLLECTION: (FIXTURES_VALIDATOR, [[("kickoff_at", ASCENDING)]]),
    MESSAGES_COLLECTION: (MESSAGES_VALIDATOR, [[("user_id", ASCENDING), ("session_id", ASCENDING), ("created_at", ASCENDING)],
                                               [("user_id", ASCENDING), ("created_at", ASCENDING)]]),
    SUMMARIES_COLLECTION: (SUMMARIES_VALIDATOR, [[("user_id", ASCENDING), ("scope", ASCENDING), ("created_at", ASCENDING)]]),
    EPISODES_COLLECTION: (EPISODES_VALIDATOR, [[("user_id", ASCENDING), ("created_at", ASCENDING)]]),
}
def ensure_collections():
    db = get_db()
    existing = db.list_collection_names()
    for name, (validator, indexes) in COLLECTIONS.items():
        if name not in existing:
            db.create_collection(name, validator=validator)  # create with rules
        else:
            db.command("collMod", name, validator=validator)  # refresh the rules
        for keys in indexes:
            db[name].create_index(keys)  # speed up the lookups the memory code does
