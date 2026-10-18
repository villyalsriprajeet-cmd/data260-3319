# Check the code against the rules written in AGENT.md
import ast
import io
import re
import sys
import tokenize
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
CATEGORIES = ["Project description", "Technology stack", "Coding conventions", "Testing approach", "Prohibited actions"]
SECRET_WORDS = ("password", "secret", "token", "api_key")
RESULTS = []


def record(name, ok, detail=""):
    # store and print one pass/fail line
    RESULTS.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}".rstrip())


def check_agent_md(path):
    # at least 5 instructions and at least 3 of the 5 categories
    text = Path(path).read_text()
    found = [c for c in CATEGORIES if re.search(rf"^## {c}", text, re.M)]
    rules = [ln for ln in text.splitlines() if ln.startswith("- ")]
    record("AGENT.md has at least 3 categories", len(found) >= 3, f"({len(found)}: {', '.join(found)})")
    record("AGENT.md has at least 5 instructions", len(rules) >= 5, f"({len(rules)} bullets)")


def check_functions(tree, label):
    # snake_case names, no docstrings, under 40 lines, no eval/exec, no bare except
    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    bad_names = [f.name for f in funcs if not re.fullmatch(r"[a-z_][a-z0-9_]*", f.name)]
    record(f"{label}: function names are snake_case", not bad_names, str(bad_names or ""))
    docs = [f.name for f in funcs if ast.get_docstring(f)]
    record(f"{label}: no docstrings", not docs, str(docs or ""))
    long = [f.name for f in funcs if f.end_lineno - f.lineno + 1 >= 40]
    record(f"{label}: every function under 40 lines", not long, str(long or ""))
    calls = [n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    record(f"{label}: no eval or exec", not {"eval", "exec"} & set(calls))
    bare = [n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler) and n.type is None]
    record(f"{label}: no bare except", not bare)


def check_constants_and_secrets(tree, label):
    # module constants are UPPER_CASE; no secret-looking name gets a string literal
    names = [t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)]
    bad = [n for n in names if not n.isupper()]
    record(f"{label}: module constants are UPPER_CASE", not bad, str(bad or ""))
    leaks = [t.id for n in ast.walk(tree) if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
             and isinstance(n.value.value, str) and n.value.value for t in n.targets
             if isinstance(t, ast.Name) and any(w in t.id.lower() for w in SECRET_WORDS)]
    record(f"{label}: no hardcoded secrets", not leaks, str(leaks or ""))


def check_comments(source, label):
    # comments are single-line and under 80 characters
    comments = [t.string for t in tokenize.generate_tokens(io.StringIO(source).readline) if t.type == tokenize.COMMENT]
    long = [c for c in comments if len(c) >= 80]
    record(f"{label}: comments are one line under 80 characters", not long, f"({len(comments)} comments)")


def check_behaviour():
    # needs_consolidation must follow the 40-line and 24-hour rules
    import file_memory as fm
    now = datetime(2026, 10, 17, 12, 0, 0)
    fresh = (now - timedelta(hours=1)).isoformat()
    old = (now - timedelta(hours=25)).isoformat()
    body = "\n".join(f"- [2026-01-01] k{i}: v" for i in range(41))
    short = "\n".join(f"- [2026-01-01] k{i}: v" for i in range(5))
    cases = [(f"<!-- last_consolidated: {fresh} -->\n{short}", False), (f"<!-- last_consolidated: {old} -->\n{short}", True),
             (f"<!-- last_consolidated: {fresh} -->\n{body}", True), (short, True)]
    got = [fm.needs_consolidation(text, now)[0] for text, _ in cases]
    record("needs_consolidation: fresh and short -> no, old -> yes, 41 lines -> yes, no stamp -> yes",
           got == [want for _, want in cases], str(got))
    forty = "\n".join(f"- [2026-01-01] k{i}: v" for i in range(40))
    edge = fm.needs_consolidation(f"<!-- last_consolidated: {fresh} -->\n{forty}", now)[0]
    record("needs_consolidation: exactly 40 lines is not over the limit", edge is False)


def main():
    check_agent_md(REPO / "AGENT.md")
    for name in ("file_memory.py", "hw6_memory_cli.py"):
        source = (REPO / "code" / name).read_text()
        tree = ast.parse(source)
        check_functions(tree, name)
        check_constants_and_secrets(tree, name)
        check_comments(source, name)
    check_behaviour()
    print(f"{sum(RESULTS)}/{len(RESULTS)} checks passed")
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
