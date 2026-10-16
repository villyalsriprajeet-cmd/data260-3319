# Local sentence embeddings, unit length so cosine similarity is a dot product
import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")  
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
from .config import EMBED_MODEL
_model = None  # loaded on first use, then reused
def embed(text: str) -> list[float]:
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(EMBED_MODEL)
    return [float(x) for x in _model.encode([text], normalize_embeddings=True)[0]]  # plain floats for MongoDB
