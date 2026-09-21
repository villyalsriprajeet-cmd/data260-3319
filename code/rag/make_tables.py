# HW3 Part 2 - recompute the METRICS comparison table from reports/hw03/raw/.
import os, json, statistics
ROOT = os.getenv("RAG_ROOT", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
RAW = os.path.join(ROOT, "reports", "hw03", "raw")
OUT = os.path.join(ROOT, "reports", "hw03", "METRICS.md")
def main():
    rows = [json.loads(l) for l in open(os.path.join(RAW, "retrieval_rows.jsonl"))]
    stats = json.load(open(os.path.join(RAW, "technique_stats.json")))
    k, tech_stats = stats["top_k"], stats["techniques"]
    order = ["token", "semantic", "sentence_window"]
    header = (f"| Technique | Chunks | Avg chunk length (chars) | Top-1 cosine | "
              f"Mean@{k} cosine | Recall@{k} | Mean retrieval latency (ms) |")
    sep = "|---|---|---|---|---|---|---|"
    body = []
    for t in order:
        tr = [r for r in rows if r["technique"] == t]
        qids = sorted(set(r["qid"] for r in tr))
        top1, meank, recall, lat = [], [], [], []
        for qid in qids:
            qr = [r for r in tr if r["qid"] == qid]
            coss = [r["cosine_sim"] for r in qr]
            top1.append(max(coss)); meank.append(sum(coss) / len(coss))
            recall.append(1.0 if any(r["in_expected_source"] for r in qr) else 0.0)
            lat.append(qr[0]["latency_ms"])
        body.append(f"| {t} | {tech_stats[t]['num_chunks']} | {tech_stats[t]['avg_chunk_len_chars']} | "
                    f"{statistics.mean(top1):.4f} | {statistics.mean(meank):.4f} | "
                    f"{statistics.mean(recall):.2f} | {statistics.mean(lat):.2f} |")
    table = "\n".join([header, sep] + body)
    print(table)
    md = ("# METRICS — HW3 Part 2 (Retrieval-only RAG)\n\n"
          "## Retrieval quality comparison\n\n" + table + "\n\n"
          "## Confidently-scored wrong retrieval\n\n_(fill in: one high-score hit that does NOT contain the answer, and why the embedding thought it similar)_\n\n"
          "## Observations\n\n_(1-2 paragraphs)_\n\n"
          "## Conclusion\n\n_(2-5 sentences: best technique for this corpus and why)_\n\n"
          "## AI_USE\n\n1. What I used an AI assistant for and what I did myself:\n2. One AI output that was wrong/unsuitable, or one thing I verified:\n3. How I detected the problem / verified the result:\n4. What I changed and why it works now:\n")
    open(OUT, "w").write(md)
    print("\nWrote", os.path.relpath(OUT, ROOT))
if __name__ == "__main__":
    main()