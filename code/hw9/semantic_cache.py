# HW9 Part 2: semantic response cache, query embeddings in a Redis vector index compared by cosine similarity
import hashlib
import os
import time

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from code.hw9.fixture_cache import make_redis
from code.kafka_service.settings import PREFIX

import numpy as np
from redis.commands.search.field import NumericField, TagField, TextField, VectorField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.query import Query
from redis.exceptions import ResponseError

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"  # same embedder as HW4 and HW6
DIM = 384
INDEX = f"{PREFIX}:idx:qa"  # vector index over every hash whose key starts with DOC_PREFIX
DOC_PREFIX = f"{PREFIX}:qa:"
DEFAULT_THRESHOLD = 0.85
RETURN_FIELDS = ["query", "answer", "data_version", "fixture_codes", "created_at", "correlation_id", "dist"]
_model = None


def embed(text):
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(EMBED_MODEL)
    return _model.encode([text], normalize_embeddings=True)[0].astype(np.float32)  # unit length, 384 floats


def normalize(query):
    return " ".join(query.strip().split())  # trim and collapse spaces, nothing else


class SemanticCache:
    def __init__(self, redis_client=None, threshold=DEFAULT_THRESHOLD, embed_fn=embed):
        self.r = redis_client or make_redis()
        self.threshold = threshold
        self.embed_fn = embed_fn
        self.ensure_index()

    def ensure_index(self):
        try:
            self.r.ft(INDEX).info()
            return  # already there
        except ResponseError:
            pass
        schema = (
            TextField("query"),
            TagField("fixture_codes"),
            TagField("data_version"),
            NumericField("created_at"),
            VectorField("embedding", "FLAT", {"TYPE": "FLOAT32", "DIM": DIM, "DISTANCE_METRIC": "COSINE"}),
        )
        definition = IndexDefinition(prefix=[DOC_PREFIX], index_type=IndexType.HASH)
        self.r.ft(INDEX).create_index(schema, definition=definition)

    def key_for(self, query):
        return DOC_PREFIX + hashlib.sha1(normalize(query).lower().encode()).hexdigest()[:16]

    def nearest(self, vector):
        q = Query("*=>[KNN 1 @embedding $vec AS dist]").sort_by("dist").return_fields(*RETURN_FIELDS).dialect(2)
        res = self.r.ft(INDEX).search(q, query_params={"vec": vector.astype(np.float32).tobytes()})
        if not res.docs:
            return None  # empty cache
        doc = res.docs[0]
        entry = {name: getattr(doc, name, "") for name in RETURN_FIELDS if name != "dist"}
        entry["key"] = doc.id
        entry["similarity"] = 1.0 - float(doc.dist)  # Redis returns cosine distance = 1 - cosine similarity
        return entry

    def lookup(self, query, vector=None):
        vector = self.embed_fn(normalize(query)) if vector is None else vector
        best = self.nearest(vector)
        hit = best is not None and best["similarity"] >= self.threshold
        return hit, best, vector

    def store(self, query, vector, answer, data_version, fixture_codes, **extra):
        key = self.key_for(query)
        mapping = {
            "query": normalize(query),
            "answer": answer,
            "embedding": vector.astype(np.float32).tobytes(),
            "data_version": data_version,
            "fixture_codes": ",".join(fixture_codes),
            "created_at": time.time(),
            **{k: str(v) for k, v in extra.items()},
        }
        self.r.hset(key, mapping=mapping)
        return key

    def delete(self, key):
        return self.r.delete(key)

    def entries(self):
        return sorted(self.r.scan_iter(f"{DOC_PREFIX}*", count=1000))

    def clear(self):
        keys = self.entries()
        if keys:
            self.r.delete(*keys)
        return len(keys)
