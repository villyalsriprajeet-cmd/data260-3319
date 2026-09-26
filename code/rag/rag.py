# HW4 Part 4: grounded RAG over the Domain 7 corpus 
import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE" 
os.environ["OMP_NUM_THREADS"] = "1" 
os.environ["TOKENIZERS_PARALLELISM"] = "false"  
import csv
import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from sentence_transformers import SentenceTransformer  # load PyTorch before FAISS
import faiss
import requests
from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter
ROOT = Path(__file__).resolve().parents[2]  # repo root
CORPUS_DIR = ROOT / "data" / "corpus"  # the 5 documents from HW3
RAW_DIR = ROOT / "reports" / "hw04" / "raw"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
LLM_MODEL = "qwen2.5:3b"
OLLAMA_URL = "http://localhost:11434/api/chat"
CHUNK_SIZE, CHUNK_OVERLAP = 500, 50  # tokens per chunk and overlap
TOP_K = 3
MIN_SCORE = 0.35  # config C drops chunks below this cosine score
DUP_SIM = 0.95  # config C drops a chunk this similar to one it already kept
MAX_CONTEXT_CHARS = 6000  # config C token budget, roughly 1,500 tokens
REFUSAL = "I cannot answer this question from the provided documents"
CACHE_FILE = RAW_DIR / "rag_llm_cache.json"  # saved answers so a re run skips finished calls
QUESTIONS = [
    {"id": "Q1", "type": "answer in one chunk",
     "question": "Who won the Golden Boot in the 2023-24 Premier League, and how many goals did he score?",
     "sources": ["2023_24_premier_league.txt"], "all": ["Haaland", "27"], "any": [], "refuse": False},
    {"id": "Q2", "type": "answer needs two chunks",
     "question": "Which three clubs were relegated from the 2023-24 Premier League, and which club won the 2023-24 EFL Championship?",
     "sources": ["2023_24_premier_league.txt", "2023_24_efl_championship.txt"],
     "all": ["Luton", "Burnley", "Sheffield", "Leicester"], "any": [], "refuse": False},
    {"id": "Q3", "type": "similar information across documents",
     "question": "Which club were the defending champions at the start of the 2023-24 La Liga season?",
     "sources": ["2023_24_la_liga.txt"], "all": ["Barcelona"], "any": [], "refuse": False},
    {"id": "Q4", "type": "ambiguous",
     "question": "Who won the league title?",
     "sources": ["2023_24_premier_league.txt", "2023_24_la_liga.txt", "2023_24_efl_championship.txt",
                 "2024_major_league_soccer_season.txt", "2024_25_uefa_champions_league.txt"],
     "all": [], "any": ["Manchester City", "Real Madrid", "Leicester", "Inter Miami", "LA Galaxy", "Paris Saint-Germain"],
     "refuse": False},
    {"id": "Q5", "type": "answer not in the documents",
     "question": "Who won the 2025 MLS Cup?", "sources": [], "all": [], "any": [], "refuse": True},
    {"id": "Q6", "type": "unrelated",
     "question": "What is the capital of Australia?", "sources": [], "all": [], "any": [], "refuse": True},
]
SWEEP_QID, SWEEP_KS = "Q2", [1, 3, 5]  # context size sweep
SYSTEM_C = (
    "You answer questions using ONLY the numbered context passages.\n"
    "Rules:\n"
    "1. Use only facts stated in the context. Do not use outside knowledge.\n"
    "2. Cite the passage number for every fact, like [1] or [2].\n"
    "3. The competition and season in the question must match the context exactly.\n"
    f"4. If the context does not contain the answer, reply exactly: {REFUSAL}\n"
    "5. If the question is ambiguous, say which competition each answer refers to.\n"
    "6. Answer in at most three sentences."
)
def load_chunks():
    docs = [Document(text=p.read_text(encoding="utf-8"), metadata={"source": p.name})
            for p in sorted(CORPUS_DIR.glob("*.txt"))]
    nodes = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP).get_nodes_from_documents(docs)
    chunks, counters = [], {}
    for n in nodes:
        src = n.metadata["source"]
        counters[src] = counters.get(src, 0) + 1
        chunks.append({"chunk_id": f"{src.removesuffix('.txt')}#{counters[src]}", "source": src,
                       "text": n.get_content()})  # text, source name and chunk_id for every chunk
    return docs, chunks
def build_index(chunks, model):
    vecs = model.encode([c["text"] for c in chunks], batch_size=32, normalize_embeddings=True).astype("float32")
    index = faiss.IndexFlatIP(vecs.shape[1])  # inner product on unit vectors = cosine similarity
    index.add(vecs)
    return index, vecs
def retrieve(question, k, model, index, chunks, vecs):
    q = model.encode([question], normalize_embeddings=True).astype("float32")
    scores, ids = index.search(q, k)  # top-k nearest chunks
    return [{**chunks[i], "rank": r + 1, "score": float(s), "vec": vecs[i]}
            for r, (s, i) in enumerate(zip(scores[0], ids[0]))]
def format_hits(qid, question, k, hits):
    lines = [f"[{qid}] k={k} {question}"]
    for h in hits:
        preview = re.sub(r"\s+", " ", h["text"])[:150]
        lines.append(f"  #{h['rank']} score={h['score']:.4f} source={h['source']} chunk={h['chunk_id']} | {preview}")
    return "\n".join(lines)
def engineer_context(hits):
    kept, dropped = [], []
    for h in sorted(hits, key=lambda x: x["score"], reverse=True):  # best evidence first
        if h["score"] < MIN_SCORE:
            dropped.append((h["chunk_id"], "irrelevant"))
        elif any(float(h["vec"] @ k["vec"]) >= DUP_SIM for k in kept):
            dropped.append((h["chunk_id"], "duplicate"))
        elif sum(len(k["text"]) for k in kept) + len(h["text"]) > MAX_CONTEXT_CHARS:
            dropped.append((h["chunk_id"], "over budget"))
        else:
            kept.append(h)
    return kept, dropped
def build_messages(config, question, hits):
    if config == "A":  # no RAG baseline
        return [{"role": "user", "content": f"Answer in at most three sentences.\n\nQuestion: {question}"}]
    if config == "B":  # basic RAG: raw top-k chunks, no rules
        context = "\n\n".join(h["text"] for h in hits)
        return [{"role": "user", "content": f"Use the context to answer the question.\n\nContext:\n{context}\n\nQuestion: {question}"}]
    context = "\n\n".join(f"[{i}] (source: {h['source']}, chunk {h['chunk_id']})\n{h['text']}"
                          for i, h in enumerate(hits, 1))  # labelled, ordered survivors
    return [{"role": "system", "content": SYSTEM_C},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"}]
def ask_llm(messages, cache):
    key = hashlib.sha256(json.dumps([LLM_MODEL, messages]).encode()).hexdigest()
    if key in cache:
        return cache[key]["answer"], cache[key]["seconds"], True  # reuse a saved answer
    payload = {"model": LLM_MODEL, "messages": messages, "stream": False,
               "options": {"temperature": 0, "seed": 3319, "num_ctx": 4096, "num_predict": 200}}
    t0 = time.perf_counter()
    r = requests.post(OLLAMA_URL, json=payload, timeout=900)
    r.raise_for_status()
    answer = r.json()["message"]["content"].strip()
    seconds = round(time.perf_counter() - t0, 1)
    cache[key] = {"answer": answer, "seconds": seconds}
    CACHE_FILE.write_text(json.dumps(cache, indent=1))  # save after every call
    return answer, seconds, False
def run_config(config, q, hits, cache):
    if config == "C":
        kept, dropped = engineer_context(hits)  # filter, de duplicate and order
    else:
        kept, dropped = (hits if config == "B" else []), []
    if config == "C" and not kept:
        return {"answer": REFUSAL + ". (No chunk passed the relevance filter.)", "seconds": 0.0,
                "cached": False, "context": [], "dropped": dropped}
    answer, seconds, cached = ask_llm(build_messages(config, q["question"], kept), cache)
    return {"answer": answer, "seconds": seconds, "cached": cached, "context": kept, "dropped": dropped}
def has(text, words):
    return all(w.lower() in text.lower() for w in words)
def evaluate(q, config, res, hits):
    ans = res["answer"]
    refused = "cannot answer this question from the provided documents" in ans.lower()
    ctx = res["context"]
    ctx_text = " ".join(c["text"] for c in ctx)
    retrieved_text = " ".join(h["text"] for h in hits)
    if q["refuse"]:
        retrieval_ok = "n/a"
    elif q["all"]:
        retrieval_ok = has(retrieved_text, q["all"])  # the retrieved chunks hold every fact needed
    else:
        retrieval_ok = any(w.lower() in retrieved_text.lower() for w in q["any"])
    if q["refuse"]:
        answer_ok = refused
    elif q["all"]:
        answer_ok = has(ans, q["all"]) and not refused
    else:
        answer_ok = any(w.lower() in ans.lower() for w in q["any"]) and not refused
    cited = [int(n) for n in re.findall(r"\[(\d+)\]", ans)]
    if config == "A":
        grounded = "n/a"  # no context to be grounded in
    elif refused:
        grounded = True
    else:
        facts = [w for w in q["all"] + q["any"] if w.lower() in ans.lower()]
        source_text = " ".join(ctx[n - 1]["text"] for n in cited if 1 <= n <= len(ctx)) if config == "C" else ctx_text
        grounded = bool(facts) and all(f.lower() in source_text.lower() for f in facts)
    if config == "C":
        format_ok = refused if q["refuse"] else (bool(cited) and all(1 <= n <= len(ctx) for n in cited))
    else:
        format_ok = "n/a"
    return {"correct_retrieval": retrieval_ok, "correct_answer": answer_ok, "grounded": grounded,
            "refused_when_needed": refused if q["refuse"] else "n/a", "format_ok": format_ok}
def pct(values):
    vals = [v for v in values if v != "n/a"]
    return f"{sum(bool(v) for v in vals)}/{len(vals)}" if vals else "n/a"
def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    started = datetime.now().isoformat(timespec="seconds")
    print(f"[{started}] HW4 Part 4 RAG run, model={LLM_MODEL}, embed={EMBED_MODEL}")
    docs, chunks = load_chunks()
    print(f"corpus: {len(docs)} documents -> {len(chunks)} chunks (chunk_size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP})")
    model = SentenceTransformer(EMBED_MODEL)
    index, vecs = build_index(chunks, model)
    print(f"FAISS index: {index.ntotal} vectors, dim={vecs.shape[1]}")
    cache = json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else {}
    printouts, comparison, evals = [], [], []
    for q in QUESTIONS:
        hits = retrieve(q["question"], TOP_K, model, index, chunks, vecs)
        block = format_hits(q["id"], q["question"], TOP_K, hits)
        print("\n" + block)  # retrieval shown before any LLM call
        printouts.append(block)
        for config in ["A", "B", "C"]:
            res = run_config(config, q, hits, cache)
            ev = evaluate(q, config, res, hits)
            print(f"  ({config}) {res['seconds']}s{' cached' if res['cached'] else ''} -> {res['answer'][:300]}")
            if config == "C" and res["dropped"]:
                print(f"      dropped: {res['dropped']}")
            comparison.append({"qid": q["id"], "type": q["type"], "config": config, "k": TOP_K,
                               "context_chunks": ";".join(c["chunk_id"] for c in res["context"]),
                               "dropped": ";".join(f"{c}:{why}" for c, why in res["dropped"]),
                               "seconds": res["seconds"], "answer": res["answer"]})
            evals.append({"qid": q["id"], "config": config, **ev})
    sweep, sq = [], next(x for x in QUESTIONS if x["id"] == SWEEP_QID)
    print(f"\n=== top_k sweep on {SWEEP_QID} (config C) ===")
    for k in SWEEP_KS:
        hits = retrieve(sq["question"], k, model, index, chunks, vecs)
        block = format_hits(sq["id"], sq["question"], k, hits)
        print(block)
        printouts.append(block)
        res = run_config("C", sq, hits, cache)
        ev = evaluate(sq, "C", res, hits)
        print(f"  (C, k={k}) {res['seconds']}s -> {res['answer'][:300]}")
        sweep.append({"k": k, "retrieved": ";".join(h["chunk_id"] for h in hits),
                      "kept": ";".join(c["chunk_id"] for c in res["context"]),
                      "dropped": ";".join(f"{c}:{why}" for c, why in res["dropped"]),
                      "irrelevant_retrieved": sum(1 for h in hits if not any(w.lower() in h["text"].lower() for w in sq["all"])),  # chunks with none of the answer facts
                      "correct_answer": ev["correct_answer"], "grounded": ev["grounded"], "answer": res["answer"]})
    (RAW_DIR / "rag_retrievals.txt").write_text("\n\n".join(printouts) + "\n")
    for name, rows in [("rag_comparison.csv", comparison), ("rag_ksweep.csv", sweep), ("rag_eval.csv", evals)]:
        with open(RAW_DIR / name, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    lines = ["| Config | Accuracy (correct answers) | Faithfulness (grounded) | Format compliance | Robustness (Q5/Q6 refused) |",
             "|---|---|---|---|---|"]
    names = {"A": "A: No RAG", "B": "B: Basic RAG", "C": "C: Context-engineered RAG"}
    for config in ["A", "B", "C"]:
        rows = [e for e in evals if e["config"] == config]
        lines.append(f"| {names[config]} | {pct([e['correct_answer'] for e in rows])} | {pct([e['grounded'] for e in rows])} | "
                     f"{pct([e['format_ok'] for e in rows])} | {pct([e['refused_when_needed'] for e in rows])} |")
    summary = "\n".join(lines)
    (RAW_DIR / "rag_eval_summary.md").write_text(summary + "\n")
    print("\n=== evaluation summary ===\n" + summary)
    print(f"\n[{datetime.now().isoformat(timespec='seconds')}] wrote rag_retrievals.txt, rag_comparison.csv, "
          f"rag_ksweep.csv, rag_eval.csv, rag_eval_summary.md to reports/hw04/raw/")
if __name__ == "__main__":
    main()