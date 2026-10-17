# HW6 Part 3 runner: same 30-message conversation for N=4, 12, 30 and an eviction policy, then the 5 probes
import argparse
import csv
import json
import re
import statistics
import time
from pathlib import Path
import yaml
from code.api import memory
from code.api.embedder import embed
from code.api.mongo_db import get_episodes, get_messages, get_summaries
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "reports" / "hw06" / "raw"
TURNS_CSV = RAW / "sweep_turns.csv"
PROBES = yaml.safe_load(open(ROOT / "reports" / "hw06" / "memory_probes.yaml"))["probes"]
SETTINGS = {"n4": (4, None), "n12": (12, None), "n30": (30, None), "evict": (12, "evict_assistant")}  # label: (window size, policy)
FILLER = ["How many points does a win give in most leagues?", "What does the Postponed status mean for a fixture?",
          "Can a fixture be both Live and Completed?", "What is the difference between a League and a Cup fixture?",
          "How long is a typical youth soccer match?", "What should I check before marking a fixture as Completed?",
          "How do tie-breakers usually work in a league table?", "Is a Friendly counted in the standings?",
          "What is a good way to name tournament rounds?", "How many substitutes are usually allowed?",
          "What does extra time mean in a cup match?", "Why might a fixture be postponed?",
          "How early should teams arrive before kickoff?", "What is a walkover?",
          "How are home and away fixtures usually decided?", "What is a bye in a tournament?",
          "How should results be recorded after a match?", "What is goal difference?",
          "How do I report a rule dispute?", "What does a clean sheet mean?",
          "How many teams usually play in a small community league?", "What is a rescheduled fixture?",
          "How long before a match can a fixture be postponed?", "Thanks, that is all for today."]
PLANTED = {1: "Hi, my name is Sri and I manage the Spartans.", 2: "Our home games are at Riverside Park Field 3.",
           5: "We usually kick off on Saturdays at 9 AM.", 12: "Please remind me about fixtures by email, never by text.",
           19: "Our biggest rival is the Hawks.", 26: "Update: our next game has been moved to Sunday at 2 PM."}
def conversation():
    filler = iter(FILLER)
    return [PLANTED.get(i) or next(filler) for i in range(1, 31)]  # 30 user messages, facts planted at fixed positions
def score(answer, probe):
    text = answer.lower()
    hit = lambda w: re.search(r"\b" + re.escape(str(w).lower()) + r"\b", text) is not None
    groups = probe["must_include"]
    matched = sum(any(hit(w) for w in g) for g in groups)
    value = 1 if matched == 0 else 1 + round(4 * matched / len(groups))
    if any(hit(w) for w in probe.get("must_not") or []):
        value = min(value, 2)
    return value, matched
def clear_user(user_id):
    for col in (get_messages(), get_summaries(), get_episodes()):
        col.delete_many({"user_id": user_id})
def ask_probe(user_id, session_id, question, n, policy):
    window = memory.short_term(user_id, session_id, n)  # same prompt assembly as a chat turn, but nothing is saved
    if policy == "evict_assistant":
        window = memory.compress_window(window)
    facts = memory.retrieve_episodes(user_id, embed(question), memory.config.EPISODIC_TOP_K)
    messages, parts = memory.build_prompt(memory.latest_summary(user_id, "session", session_id), memory.latest_summary(user_id, "user"), window, question, facts)
    t0 = time.perf_counter()
    result = memory.call_model(messages)
    return {"answer": result["text"].strip(), "prompt_tokens": result["input_tokens"], "latency_ms": round((time.perf_counter() - t0) * 1000),
            "own_prompt_tokens": sum(memory.count_tokens(v) for v in parts.values()), "facts_retrieved": [f["fact"] for f in facts]}
def run_setting(label, results):
    n, policy = SETTINGS[label]
    user_id, session_id = f"sweep-{label}", f"sweep-{label}-session"
    clear_user(user_id)
    memory.call_model([{"role": "user", "content": "Say hi."}], num_predict=5)  # load the model, embedder and tokenizer before timing starts
    embed("warm up")
    memory.count_tokens("warm up")
    for i, text in enumerate(conversation(), 1):
        out = memory.chat_turn(user_id, session_id, text, short_term_n=n, log_path=TURNS_CSV, policy=policy)
        print(f"[{label}] turn {i}/30 | prompt {out['metrics']['prompt_tokens']} tok | {out['metrics']['latency_ms']} ms | facts +{len(out['used']['new_facts_saved'])}", flush=True)
    probes = []
    for p in PROBES:
        r = ask_probe(user_id, session_id, p["question"], n, policy)
        r["score"], r["matched"] = score(r["answer"], p)
        r["id"], r["question"], r["expected"] = p["id"], p["question"], p["expected"]
        probes.append(r)
        print(f"[{label}] {p['id']} score {r['score']} | {r['answer']}", flush=True)
    results[label] = {"short_term_n": n, "policy": policy, "probes": probes, "mean_probe_quality": round(statistics.mean(r["score"] for r in probes), 2)}
    json.dump(results, open(RAW / "probe_results.json", "w"), indent=2)
def summarize(results):
    rows = list(csv.DictReader(open(TURNS_CSV)))
    summary = {}
    for label in SETTINGS:
        if label not in results:
            continue
        mine = [r for r in rows if r["user_id"] == f"sweep-{label}"][-30:]  # the latest complete run of this setting
        num = lambda key: [float(r[key]) for r in mine]
        own = [sum(float(r[k]) for k in ("primer_tokens", "long_term_tokens", "short_term_tokens", "current_tokens", "episodic_tokens")) for r in mine]
        extra_in = statistics.mean(num("extract_prompt_tokens")) + statistics.mean(num("summary_prompt_tokens"))
        extra_out = statistics.mean(num("extract_completion_tokens")) + statistics.mean(num("summary_completion_tokens"))
        s = {"mean_prompt_tokens_model": round(statistics.mean(num("prompt_tokens")), 1), "mean_prompt_tokens_own_count": round(statistics.mean(own), 1),
             "mean_completion_tokens": round(statistics.mean(num("completion_tokens")), 1), "mean_latency_ms": round(statistics.mean(num("latency_ms"))),
             "mean_reply_latency_ms": round(statistics.mean(num("reply_latency_ms"))), "maintenance_in_tokens_per_turn": round(extra_in, 1),
             "maintenance_out_tokens_per_turn": round(extra_out, 1), "mean_probe_quality": results[label]["mean_probe_quality"]}
        total_in = s["mean_prompt_tokens_model"] + extra_in
        total_out = s["mean_completion_tokens"] + extra_out
        s["cost_10000_convs_usd"] = round(10000 * 30 * (total_in * 1.0 + total_out * 5.0) / 1e6, 2)  # $1 per M input, $5 per M output
        s["cost_chat_only_usd"] = round(10000 * 30 * (s["mean_prompt_tokens_model"] * 1.0 + s["mean_completion_tokens"] * 5.0) / 1e6, 2)
        summary[label] = s
    json.dump(summary, open(RAW / "sweep_summary.json", "w"), indent=2)
    print("\n| setting | mean prompt tokens/turn (model) | (own count) | mean latency ms | probe quality 1-5 | cost 10k convs (chat only) | cost (with memory upkeep) |")
    print("|---|---|---|---|---|---|---|")
    for label, s in summary.items():
        print(f"| {label} | {s['mean_prompt_tokens_model']} | {s['mean_prompt_tokens_own_count']} | {s['mean_latency_ms']} | {s['mean_probe_quality']} | ${s['cost_chat_only_usd']} | ${s['cost_10000_convs_usd']} |")
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", choices=list(SETTINGS), help="run only these settings")
    ap.add_argument("--force", action="store_true", help="rerun settings that already have results")
    args = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / "probe_results.json"
    results = json.load(open(path)) if path.exists() else {}
    for label in args.only or list(SETTINGS):
        if label in results and not args.force:
            print(f"[{label}] already done, skipping (use --force to rerun)")
            continue
        run_setting(label, results)
    summarize(results)
