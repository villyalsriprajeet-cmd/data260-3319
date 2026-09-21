# HW3 Part 2 - compare three LlamaIndex chunking techniques (retrieval only RAG).
import os, re, json, csv, time, datetime
import numpy as np
import yaml
from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.core.node_parser import TokenTextSplitter, SemanticSplitterNodeParser, SentenceWindowNodeParser
ROOT = os.getenv("RAG_ROOT", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CORPUS_DIR = os.path.join(ROOT, "data", "corpus")
QUESTIONS = os.path.join(ROOT, "reports", "hw03", "questions.yaml")
RAW_DIR = os.path.join(ROOT, "reports", "hw03", "raw")
MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K = 5
def make_embed_model():
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    return HuggingFaceEmbedding(model_name=MODEL)
def load_corpus():
    docs = []
    for fn in sorted(os.listdir(CORPUS_DIR)):
        if fn.endswith(".txt"):
            path = os.path.join(CORPUS_DIR, fn)
            docs.append(Document(text=open(path, encoding="utf-8").read(),
                                 metadata={"source": os.path.relpath(path, ROOT)}))
    return docs
def load_questions():
    with open(QUESTIONS) as f:
        return yaml.safe_load(f)
def cosine(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    return float(a @ b / ((np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9))
def build_parsers(embed):
    return {
        "token": TokenTextSplitter(chunk_size=256, chunk_overlap=32),
        "semantic": SemanticSplitterNodeParser(buffer_size=1, breakpoint_percentile_threshold=95, embed_model=embed),
        "sentence_window": SentenceWindowNodeParser.from_defaults(window_size=3),
    }
def main():
    print("Run started:", datetime.datetime.now().isoformat())
    os.makedirs(RAW_DIR, exist_ok=True)
    embed = make_embed_model()
    Settings.embed_model = embed
    docs = load_corpus()
    cfg = load_questions()
    k = int(cfg.get("k", TOP_K)); questions = cfg["questions"]
    parsers = build_parsers(embed)
    rows, tech_stats = [], {}
    for name, parser in parsers.items():
        print("\n" + "=" * 78)
        print(f"TECHNIQUE: {name}")
        print("=" * 78)
        nodes = parser.get_nodes_from_documents(docs)
        lens = [len(n.get_content()) for n in nodes]
        tech_stats[name] = {"num_chunks": len(nodes),
                            "avg_chunk_len_chars": round(sum(lens) / max(len(lens), 1), 1)}
        print(f"chunks={len(nodes)}  avg_chunk_len={tech_stats[name]['avg_chunk_len_chars']} chars")
        index = VectorStoreIndex(nodes)  # in memory SimpleVectorStore
        retriever = index.as_retriever(similarity_top_k=k)
        for q in questions:
            qid, question, expected = q["id"], q["question"], q.get("expected_source", "")
            qv = embed.get_query_embedding(question)
            t0 = time.perf_counter()
            hits = retriever.retrieve(question)
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            print(f"\n[{qid}] {question}")
            print(f"  query embedding dim={len(qv)}  first8={[round(x,4) for x in qv[:8]]}")
            print(f"  {'rank':<4} {'store':<9} {'cosine':<9} {'len':<6} {'source':<30} preview")
            doc_vecs = []
            for rank, h in enumerate(hits, 1):
                txt = h.node.get_content()
                dv = embed.get_text_embedding(txt); doc_vecs.append(dv)
                cs = round(cosine(qv, dv), 4)
                src = h.node.metadata.get("source", "")
                preview = re.sub(r"\s+", " ", txt)[:160]
                rows.append({"technique": name, "qid": qid, "question": question, "rank": rank,
                             "store_score": round(float(h.score or 0.0), 4), "cosine_sim": cs,
                             "chunk_len": len(txt), "source": src,
                             "in_expected_source": (src == expected), "latency_ms": latency_ms,
                             "preview": preview})
                print(f"  {rank:<4} {round(float(h.score or 0),4):<9} {cs:<9} {len(txt):<6} {os.path.basename(src):<30} {preview[:55]}")
            qvs, dvs = np.array([qv]), np.array(doc_vecs)
            print(f"  shapes: query={qvs.shape}  docs={dvs.shape}  latency={latency_ms} ms")
    with open(os.path.join(RAW_DIR, "retrieval_rows.jsonl"), "w") as f:
        for r in rows: f.write(json.dumps(r) + "\n")
    with open(os.path.join(RAW_DIR, "retrieval_rows.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with open(os.path.join(RAW_DIR, "technique_stats.json"), "w") as f:
        json.dump({"top_k": k, "techniques": tech_stats}, f, indent=2)
    print(f"\nWrote {len(rows)} rows to {os.path.relpath(RAW_DIR, ROOT)}/ (retrieval_rows.jsonl, .csv) + technique_stats.json")
    print("Run finished:", datetime.datetime.now().isoformat())
if __name__ == "__main__":
    main()