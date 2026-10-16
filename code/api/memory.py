# Part 2 memory logic: short-term window, summaries, episodic facts, prompt assembly and one full chat turn
import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from model_client import ModelClient  # the HW1 model adapter
from . import config
from .embedder import embed
from .mongo_db import get_episodes, get_messages, get_summaries
PRIMER = ("You are the assistant for a community sports league fixtures app. Use the memory you are given to answer. "
          "Answer in at most two short sentences. If the memory does not contain the answer, say you do not know.")
EXTRACT_SYSTEM = ("Extract up to 3 short lasting facts about the user from their message, such as their name, team, venue or preferences. "
                  'Reply with JSON only, like {"facts":[{"fact":"The user supports the Spartans","importance":0.8}]}. '
                  "importance is 0 to 1, higher means more important to remember. Only use what the user literally said, never guess or infer. "
                  "Questions and small talk give an empty list: {\"facts\":[]}. Output the JSON and nothing else.")
SUMMARY_SYSTEM = ("Summarize the conversation as at most 6 short bullet points, one per line starting with '- '. "
                  "Keep names, teams, venues, dates and preferences. Merge the previous summary with the new messages.")
LIFETIME_SYSTEM = ("Condense these session summaries into one lifetime summary of at most 8 short bullet points, one per line starting with '- '. "
                   "Keep every lasting fact about the user and drop repeats.")
METRIC_FIELDS = ["timestamp", "user_id", "session_id", "turn", "short_term_n", "prompt_tokens", "completion_tokens",
                 "primer_tokens", "long_term_tokens", "short_term_tokens", "current_tokens", "episodic_tokens",
                 "extract_prompt_tokens", "extract_completion_tokens", "summary_prompt_tokens", "summary_completion_tokens",
                 "latency_ms", "reply_latency_ms", "token_method"]
_tokenizer = None  # loaded on first use
def now():
    return datetime.now(timezone.utc)
def call_model(messages, json_mode=False, num_predict=None):
    client = ModelClient(model=config.LLM_MODEL, base_url=config.OLLAMA_URL, temperature=0.0, num_ctx=config.LLM_NUM_CTX,
                         num_predict=num_predict or config.LLM_NUM_PREDICT, seed=config.SEED)  # temperature 0 and a fixed seed
    return client.complete(messages, json_mode=json_mode)
def token_method():
    return "qwen2.5 tokenizer" if _tokenizer else "chars/4 estimate"
def count_tokens(text):
    global _tokenizer
    if not text:
        return 0
    if _tokenizer is None:
        try:
            from transformers import AutoTokenizer
            _tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-3B-Instruct")  # same tokenizer family as qwen2.5:3b
        except Exception:
            _tokenizer = False  # not available, fall back to about 4 characters per token
    return len(_tokenizer.encode(text)) if _tokenizer else max(1, len(text) // 4)
def save_message(user_id, session_id, role, content):
    doc = {"user_id": user_id, "session_id": session_id, "role": role, "content": content, "created_at": now()}
    doc["_id"] = get_messages().insert_one(doc).inserted_id
    return doc
def short_term(user_id, session_id, n, before_id=None):
    if n <= 0:
        return []  # limit(0) would mean no limit in MongoDB
    query = {"user_id": user_id, "session_id": session_id}
    if before_id is not None:
        query["_id"] = {"$lt": before_id}  # only messages saved before the current one
    rows = list(get_messages().find(query).sort([("created_at", -1), ("_id", -1)]).limit(n))  # newest N
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]  # back to oldest first
def latest_summary(user_id, scope, session_id=None):
    query = {"user_id": user_id, "scope": scope}
    if scope == "session":
        query["session_id"] = session_id
    doc = get_summaries().find_one(query, sort=[("created_at", -1), ("_id", -1)])
    return doc["text"] if doc else None
def parse_facts(raw):
    try:
        data = json.loads(raw)
    except ValueError:
        match = re.search(r"\{.*\}", raw, re.S)  # the model sometimes wraps the JSON in extra text
        try:
            data = json.loads(match.group(0)) if match else {}
        except ValueError:
            data = {}
    items = data.get("facts", []) if isinstance(data, dict) else []
    if not items:  # broken JSON: salvage every complete fact/importance pair that can still be read
        items = [{"fact": f, "importance": i} for f, i in re.findall(r'"fact"\s*:\s*"([^"]+)"\s*,\s*"importance"\s*:\s*([0-9.]+)', raw)]
    facts = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, str):
            item = {"fact": item}  # a plain string counts as a fact with default importance
        if not isinstance(item, dict) or not str(item.get("fact", "")).strip():
            continue
        try:
            importance = min(1.0, max(0.0, float(item.get("importance", 0.5))))  # keep it between 0 and 1
        except (TypeError, ValueError):
            importance = 0.5
        facts.append({"fact": str(item["fact"]).strip()[:300], "importance": importance})
    return facts[:config.MAX_FACTS_PER_MESSAGE]
def extract_facts(message):
    result = call_model([{"role": "system", "content": EXTRACT_SYSTEM}, {"role": "user", "content": message}],
                        json_mode=True, num_predict=120)
    return parse_facts(result["text"]), result
def store_episodes(user_id, session_id, facts):
    known = {d["fact"].lower() for d in get_episodes().find({"user_id": user_id}, {"fact": 1})}
    rows = []
    for f in facts:
        if f["fact"].lower() in known:
            continue  # this fact is already stored
        known.add(f["fact"].lower())
        rows.append({"user_id": user_id, "session_id": session_id, "fact": f["fact"], "importance": f["importance"],
                     "embedding": embed(f["fact"]), "created_at": now()})  # embedding stored as an array of floats
    if rows:
        get_episodes().insert_many(rows)
    return rows
def retrieve_episodes(user_id, query_vec, k):
    docs = list(get_episodes().find({"user_id": user_id}))
    if not docs or k <= 0:
        return []
    matrix = np.array([d["embedding"] for d in docs], dtype=np.float32)
    q = np.array(query_vec, dtype=np.float32)
    scores = matrix @ q / (np.linalg.norm(matrix, axis=1) * np.linalg.norm(q) + 1e-9)  # cosine similarity
    return [{"fact": docs[i]["fact"], "importance": docs[i]["importance"], "score": round(float(scores[i]), 4),
             "session_id": docs[i]["session_id"]} for i in np.argsort(-scores)[:k]]  # top k
def build_prompt(session_summary, lifetime_summary, window, message, facts):
    memory = []
    if lifetime_summary:
        memory.append("Lifetime summary:\n" + lifetime_summary)
    if session_summary:
        memory.append("Session summary:\n" + session_summary)
    long_term = "\n\n".join(memory)
    system = PRIMER + ("\n\nLong-term memory:\n" + long_term if long_term else "")
    episodic = "\n".join(f"- {f['fact']}" for f in facts)
    current = message + ("\n\nRelevant remembered facts about the user:\n" + episodic if episodic else "")
    messages = [{"role": "system", "content": system}] + window + [{"role": "user", "content": current}]  # primer, summaries, window, message + facts
    parts = {"primer": PRIMER, "long_term": long_term, "short_term": "\n".join(m["content"] for m in window),
             "current": message, "episodic": episodic}
    return messages, parts
def summarize_session(user_id, session_id):
    last = get_summaries().find_one({"user_id": user_id, "scope": "session", "session_id": session_id},
                                    sort=[("created_at", -1), ("_id", -1)])
    query = {"user_id": user_id, "session_id": session_id}
    if last:
        query["created_at"] = {"$gt": last["created_at"]}  # only the messages since the last summary
    rows = list(get_messages().find(query).sort([("created_at", 1), ("_id", 1)]))
    text = "\n".join(f"{r['role']}: {r['content']}" for r in rows)
    prompt = f"Previous summary:\n{last['text'] if last else 'none'}\n\nNew messages:\n{text}\n\nWrite the updated summary."
    result = call_model([{"role": "system", "content": SUMMARY_SYSTEM}, {"role": "user", "content": prompt}], num_predict=200)
    doc = {"user_id": user_id, "session_id": session_id, "scope": "session", "text": result["text"].strip(), "created_at": now()}
    get_summaries().insert_one(doc)
    return result
def maybe_lifetime(user_id):
    sessions = get_summaries().find({"user_id": user_id, "scope": "session"})
    docs = list(sessions.sort([("created_at", -1), ("_id", -1)]))
    if not docs or len(docs) % config.LIFETIME_EVERY_SUMMARIES:
        return None  # only after every few session summaries
    recent = "\n\n".join(d["text"] for d in reversed(docs[:config.LIFETIME_EVERY_SUMMARIES]))
    prompt = f"Previous lifetime summary:\n{latest_summary(user_id, 'user') or 'none'}\n\nSession summaries:\n{recent}\n\nWrite the lifetime summary."
    result = call_model([{"role": "system", "content": LIFETIME_SYSTEM}, {"role": "user", "content": prompt}], num_predict=250)
    get_summaries().insert_one({"user_id": user_id, "session_id": None, "scope": "user", "text": result["text"].strip(),
                                "created_at": now()})  # session_id stays null for the lifetime summary
    return result
def log_metrics(metrics, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=METRIC_FIELDS, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        writer.writerow(metrics)
def chat_turn(user_id, session_id, message, short_term_n=None, summarize_every=None, top_k=None, log_path=config.METRICS_LOG):
    n = config.SHORT_TERM_N if short_term_n is None else short_term_n
    every = config.SUMMARIZE_EVERY_USER_MSGS if summarize_every is None else summarize_every
    k = config.EPISODIC_TOP_K if top_k is None else top_k
    started = time.perf_counter()
    saved = save_message(user_id, session_id, "user", message)  # 1. save the user message
    window = short_term(user_id, session_id, n, saved["_id"])  # 2. short term window
    session_summary = latest_summary(user_id, "session", session_id)  # 3. summaries
    lifetime_summary = latest_summary(user_id, "user")
    facts = retrieve_episodes(user_id, embed(message), k)  # 4. top-k episodic facts
    messages, parts = build_prompt(session_summary, lifetime_summary, window, message, facts)  # 5. prompt
    t0 = time.perf_counter()
    result = call_model(messages)  # 6. model call
    reply_ms = round((time.perf_counter() - t0) * 1000)
    reply = result["text"].strip() or "(empty reply)"
    save_message(user_id, session_id, "assistant", reply)  # 7. save the reply
    new_facts, extract = extract_facts(message)  # 8. episodic extraction
    saved_facts = store_episodes(user_id, session_id, new_facts)
    user_count = get_messages().count_documents({"user_id": user_id, "session_id": session_id, "role": "user"})
    summary = None
    if every > 0 and user_count % every == 0:  # 9. summary every M user messages
        summary = summarize_session(user_id, session_id)
        lifetime = maybe_lifetime(user_id)
        if lifetime:
            summary = {"input_tokens": summary["input_tokens"] + lifetime["input_tokens"],
                       "output_tokens": summary["output_tokens"] + lifetime["output_tokens"]}
    metrics = {"timestamp": now().isoformat(timespec="seconds"), "user_id": user_id, "session_id": session_id, "turn": user_count,
               "short_term_n": n, "prompt_tokens": result["input_tokens"], "completion_tokens": result["output_tokens"],
               "primer_tokens": count_tokens(parts["primer"]), "long_term_tokens": count_tokens(parts["long_term"]),
               "short_term_tokens": count_tokens(parts["short_term"]), "current_tokens": count_tokens(parts["current"]),
               "episodic_tokens": count_tokens(parts["episodic"]), "extract_prompt_tokens": extract["input_tokens"],
               "extract_completion_tokens": extract["output_tokens"],
               "summary_prompt_tokens": summary["input_tokens"] if summary else 0,
               "summary_completion_tokens": summary["output_tokens"] if summary else 0,
               "latency_ms": round((time.perf_counter() - started) * 1000), "reply_latency_ms": reply_ms,
               "token_method": token_method()}
    if log_path:
        log_metrics(metrics, log_path)
    used = {"short_term_count": len(window), "short_term": window, "long_term_summary": parts["long_term"] or None,
            "episodic_facts": facts, "new_facts_saved": [r["fact"] for r in saved_facts], "summary_created": summary is not None}
    return {"reply": reply, "used": used, "metrics": metrics}
