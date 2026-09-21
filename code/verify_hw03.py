# HW3 self check reports/hw03/verification.json 
import os, json, glob, subprocess, datetime
import yaml
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # code/.. -> repo root
REP = os.path.join(ROOT, "reports", "hw03")
CORPUS = os.path.join(ROOT, "data", "corpus")
SID4 = 3319
CONFIG = {"SID4": SID4, "PORT_BASE": 8000 + SID4 % 900, "PREFIX": "s%d" % SID4,
          "SEED": SID4, "VERIFY_SEED": 260000 + SID4, "DOMAIN_ID": SID4 % 8}
checks = []
def check(name, ok, detail=""):
    checks.append({"check": name, "passed": bool(ok), "detail": detail})
def exists(rel):
    return os.path.exists(os.path.join(ROOT, rel))
# Part 1 files
for f in ["code/api/main.py", "code/api/store.py", "code/api/routers/auth.py",
          "code/api/templates/base.html", "code/api/templates/home.html",
          "code/api/templates/login.html", "code/api/templates/dashboard.html"]:
    check("part1 file: " + f, exists(f))
# Part 2 files
for f in ["code/rag/build_corpus.py", "code/rag/rag_compare.py", "code/rag/make_tables.py"]:
    check("part2 file: " + f, exists(f))
# corpus >= 200 KB
txts = glob.glob(os.path.join(CORPUS, "*.txt"))
total = sum(os.path.getsize(p) for p in txts)
check("corpus >= 200 KB", total >= 200 * 1024, f"{len(txts)} files, {total} bytes")
check("CORPUS_MANIFEST.json exists", exists("reports/hw03/CORPUS_MANIFEST.json"))
check("SOURCES.md exists", exists("reports/hw03/SOURCES.md"))
# questions.yaml: >= 5 questions, >= 2 single-source
nq = nss = 0
qpath = os.path.join(REP, "questions.yaml")
if os.path.exists(qpath):
    qs = (yaml.safe_load(open(qpath)) or {}).get("questions", [])
    nq = len(qs); nss = sum(1 for q in qs if q.get("single_source"))
check("questions.yaml >= 5 questions", nq >= 5, f"{nq} questions")
check("questions.yaml >= 2 single-source", nss >= 2, f"{nss} single-source")
# raw outputs + all three techniques
check("raw/retrieval_rows.jsonl exists", exists("reports/hw03/raw/retrieval_rows.jsonl"))
check("raw/technique_stats.json exists", exists("reports/hw03/raw/technique_stats.json"))
try:
    ts = json.load(open(os.path.join(REP, "raw", "technique_stats.json")))["techniques"]
    check("all three techniques present", set(ts) >= {"token", "semantic", "sentence_window"}, ",".join(ts))
except Exception as e:
    check("all three techniques present", False, str(e))
check("METRICS.md exists", exists("reports/hw03/METRICS.md"))
try:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
except Exception:
    commit = "unknown"

all_passed = all(c["passed"] for c in checks)
out = {"hw": "hw3", "generated": datetime.datetime.now().isoformat(), "commit_hash": commit,
       "config": CONFIG, "embed_model": "sentence-transformers/all-MiniLM-L6-v2",
       "all_passed": all_passed, "checks": checks}
os.makedirs(REP, exist_ok=True)
json.dump(out, open(os.path.join(REP, "verification.json"), "w"), indent=2)
for c in checks:
    print(("PASS" if c["passed"] else "FAIL"), "-", c["check"], (f"({c['detail']})" if c["detail"] else ""))
print("\n" + ("ALL PASSED" if all_passed else "SOME CHECKS FAILED"))
print("Wrote", os.path.relpath(os.path.join(REP, "verification.json"), ROOT))