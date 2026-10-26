# HW7 Part 6: one combined run - (a) glob - search - read integration test, (b) 10-command safety-gate test
# usage: python code/hw7_part6_test.py
import csv
import json
import tempfile
from datetime import datetime
from pathlib import Path

from hw7_file_tools import SAFE_PREFIXES, Sandbox, confirm_bash, confirm_bash_v1, is_destructive, is_destructive_v1

RAW = Path(__file__).resolve().parents[1] / "reports" / "hw07" / "raw"
FILES = {
    "app/main.py": "def main():\n    print('league fixtures app')\n\n\nif __name__ == '__main__':\n    main()\n",
    "app/utils.py": "def add(a, b):\n    return a + b\n",
    "app/config.py": "PORT = 8619\nDEBUG = True  # turn off before release\nLOG_LEVEL = 'info'\n",
}
GATE_CASES = [  # (command, expected decision)
    ("ls -la", "allow"),
    ("cat app/config.py", "allow"),
    ("grep -n DEBUG app/config.py", "allow"),
    ("python3 --version", "allow"),
    ("echo hello > notes.txt", "allow"),
    ("rm -r -f build/", "block"),
    ("echo ok && sudo mkfs.ext4 /dev/sdb1", "block"),
    ("ls && chown -R nobody ~", "block"),
    ("cat disk.img > /dev/disk2", "block"),
    ("echo hacked > /etc/hosts", "block"),
]


def integration(box: Sandbox) -> None:
    print("(a) Integration test: glob -> search -> read")
    for rel, text in FILES.items():
        box.write_file(rel, text)
    print(f"  write_file x3 -> {', '.join(FILES)}")
    print("  instruction: 'Find the Python file that contains DEBUG and show its contents'")
    files = box.glob_files("*.py")
    print(f"  1. glob_files('*.py') -> {files}")
    hits = box.search_in_files("DEBUG", file_pattern="*.py")
    print(f"  2. search_in_files('DEBUG', file_pattern='*.py') -> {[(h['path'], h['line']) for h in hits]}")
    target = hits[0]["path"]
    page = box.read_file(target, max_lines=10)
    print(f"  3. read_file('{target}', max_lines=10) -> {page['total_lines']} lines:")
    for n, line in enumerate(page["lines"], start=1):
        print(f"       {n}: {line}")
    short = box.read_file("app/main.py", max_lines=2)
    print(f"  read_file('app/main.py', max_lines=2) -> {short['lines']} (truncated={short['truncated']})")
    diff = box.edit_file(target, "DEBUG = True", "DEBUG = False")["diff"]
    print("  edit_file(config.py, 'DEBUG = True' -> 'DEBUG = False') diff:")
    print("\n".join(f"       {d}" for d in diff.splitlines()))
    out = box.bash("grep -n DEBUG app/config.py")
    print(f"  bash('grep -n DEBUG app/config.py') -> {out['decision']}, stdout: {out['stdout'].strip()}")
    try:
        box.read_file("../../etc/passwd")
    except PermissionError as exc:
        print(f"  read_file('../../etc/passwd') -> PermissionError: {exc}")


def gate_test() -> list[dict]:
    print(f"\n(b) Safety-gate test (SAFE_PREFIXES = {', '.join(SAFE_PREFIXES)})")
    rows = []
    for cmd, expected in GATE_CASES:
        v1, v2 = confirm_bash_v1(cmd), confirm_bash(cmd)
        rows.append(
            {
                "command": cmd,
                "expected": expected,
                "v1_is_destructive": is_destructive_v1(cmd),
                "v1_decision": v1["decision"],
                "is_destructive": is_destructive(cmd),
                "decision": v2["decision"],
                "reason": v2["reason"],
                "correct": v2["decision"] == expected,
                "v1_false_allow": expected == "block" and v1["decision"] == "allow",
            }
        )
    print("  First version of the gate (allow-list checked before deny-list, literal 'rm -rf' match):")
    for r in rows:
        flag = "  <-- FALSE ALLOW" if r["v1_false_allow"] else ""
        print(f"    {r['v1_decision']:<6} is_destructive={r['v1_is_destructive']!s:<5} {r['command']}{flag}")
    print(
        f"  -> {sum(r['v1_false_allow'] for r in rows)} false allows. Fix: run the deny-list first on the whole "
        "command and every chained part, match split flags (rm -r -f), cover all six categories."
    )
    print("\n  Final gate:")
    for r in rows:
        print(f"    {r['decision']:<6} is_destructive={r['is_destructive']!s:<5} {r['command']:<38} {r['reason']}")
    confirmed = confirm_bash("rm -r -f build/", auto_approve=True)
    print(f"\n  confirm_bash('rm -r -f build/', auto_approve=True) -> {confirmed['decision']}: {confirmed['reason']}")
    passed = sum(r["correct"] for r in rows)
    allowed = sum(r["decision"] == "allow" for r in rows)
    print(
        f"  Result: {passed}/10 correct ({allowed} allowed, {10 - allowed} blocked), "
        f"false allows: {sum(r['expected'] == 'block' and r['decision'] == 'allow' for r in rows)}"
    )
    return rows


def main() -> None:
    print(f"=== HW7 Part 6 file tools + safety gate | {datetime.now():%Y-%m-%d %H:%M:%S} ===")
    with tempfile.TemporaryDirectory(prefix="s3319_sandbox_") as tmp:
        box = Sandbox(Path(tmp))
        print(f"sandbox: {box.root}\n")
        integration(box)
        rows = gate_test()
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "p6_gate_results.json").write_text(json.dumps(rows, indent=2) + "\n")
    with open(RAW / "p6_gate_results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Raw results: {RAW / 'p6_gate_results.csv'}")


if __name__ == "__main__":
    main()
