# HW7 Part 6: six file tools confined to a sandbox directory, plus a pure-Python safety gate for bash
import difflib
import fnmatch
import re
import subprocess
from pathlib import Path

SAFE_PREFIXES = (
    "ls",
    "cat",
    "head",
    "tail",
    "wc",
    "grep",
    "echo",
    "pwd",
    "python3 --version",
    "git status",
    "git diff",
)
DENY_RULES = [  # (category, pattern) - checked on the whole command, every segment, regardless of SAFE_PREFIXES
    ("recursive deletion", r"\brm\b[^;&|]*\s(-[a-z]*r[a-z]*|--recursive)\b|\bfind\b[^;&|]*\s-delete\b|\brmtree\b"),
    ("privilege escalation", r"(^|[\s;&|(])(sudo|su|doas|pkexec)(\s|$)"),
    ("permission/ownership change", r"\b(chmod|chown|chgrp|setfacl|chattr)\b"),
    (
        "raw-device write",
        r"\bof=/dev/(?!null\b)|>\s*/dev/(?!null\b|stdout\b|stderr\b)\w+|\btee\b[^;&|]*\s/dev/(?!null\b)",
    ),
    ("filesystem creation", r"\b(mkfs(\.\w+)?|mke2fs|newfs|mkswap)\b|\bdiskutil\s+(erase|partition)"),
    ("redirection to a root path", r">>?\s*/(?!tmp/|dev/)|\btee\b(\s+-a)?\s+/(?!tmp/|dev/)"),
]
SEGMENT_SPLIT = re.compile(r"\s*(?:&&|\|\||;|\|)\s*")


class Sandbox:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if p != self.root and self.root not in p.parents:  # blocks ../ and absolute paths outside the sandbox
            raise PermissionError(f"path escapes the sandbox: {rel}")
        return p

    def read_file(self, rel: str, max_lines: int | None = None) -> dict:
        lines = self.path(rel).read_text(encoding="utf-8").splitlines()
        shown = lines if max_lines is None else lines[:max_lines]
        return {"path": rel, "lines": shown, "total_lines": len(lines), "truncated": len(shown) < len(lines)}

    def write_file(self, rel: str, content: str) -> dict:
        p = self.path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"path": rel, "bytes": len(content.encode("utf-8"))}

    def edit_file(self, rel: str, old: str, new: str) -> dict:
        p = self.path(rel)
        before = p.read_text(encoding="utf-8")
        if before.count(old) != 1:
            raise ValueError(f"old text must occur exactly once in {rel} (found {before.count(old)})")
        after = before.replace(old, new)
        p.write_text(after, encoding="utf-8")
        diff = difflib.unified_diff(before.splitlines(), after.splitlines(), f"a/{rel}", f"b/{rel}", lineterm="", n=0)
        return {"path": rel, "diff": "\n".join(list(diff)[:12])}  # short diff

    def glob_files(self, pattern: str) -> list[str]:
        return sorted(str(p.relative_to(self.root)) for p in self.root.rglob(pattern) if p.is_file())

    def search_in_files(self, text: str, file_pattern: str = "*") -> list[dict]:
        hits = []
        for rel in self.glob_files("*"):
            if not fnmatch.fnmatch(Path(rel).name, file_pattern):
                continue
            for n, line in enumerate(self.path(rel).read_text(encoding="utf-8").splitlines(), start=1):
                if text in line:
                    hits.append({"path": rel, "line": n, "text": line.strip()})
        return hits

    def bash(self, command: str, auto_approve: bool = False, timeout: int = 10) -> dict:
        gate = confirm_bash(command, auto_approve)
        if gate["decision"] != "allow":
            return {"ran": False, **gate}
        out = subprocess.run(command, shell=True, cwd=self.root, capture_output=True, text=True, timeout=timeout)
        return {
            "ran": True,
            **gate,
            "returncode": out.returncode,
            "stdout": out.stdout[-2000:],
            "stderr": out.stderr[-500:],
        }


def destructive_reasons(command: str) -> list[str]:
    cmd = " ".join(command.lower().split())
    return [cat for cat, pattern in DENY_RULES if re.search(pattern, cmd)]


def is_destructive(command: str) -> bool:
    return bool(destructive_reasons(command))


def starts_with_safe_prefix(segment: str) -> str | None:
    seg = " ".join(segment.split())
    return next((p for p in SAFE_PREFIXES if seg == p or seg.startswith(p + " ")), None)


def confirm_bash(command: str, auto_approve: bool = False) -> dict:
    if not command or not command.strip():
        return {"decision": "block", "reason": "empty command", "destructive": False}
    reasons = destructive_reasons(command)
    if reasons:  # deny-list wins over the allow-list: a safe first word does not make the command safe
        if auto_approve:
            return {
                "decision": "allow",
                "reason": f"destructive ({', '.join(reasons)}) but explicitly confirmed",
                "destructive": True,
            }
        lead = starts_with_safe_prefix(command)
        note = f" even though it starts with safe prefix '{lead}'" if lead else ""
        return {
            "decision": "block",
            "reason": f"destructive: {', '.join(reasons)}{note}; needs explicit confirmation",
            "destructive": True,
        }
    unsafe = [s for s in SEGMENT_SPLIT.split(command.strip()) if s and not starts_with_safe_prefix(s)]
    if not unsafe:
        return {"decision": "allow", "reason": "every part starts with a SAFE_PREFIXES entry", "destructive": False}
    if auto_approve:
        return {
            "decision": "allow",
            "reason": f"not allow-listed ({unsafe[0]!r}) but explicitly approved",
            "destructive": False,
        }
    return {
        "decision": "block",
        "reason": f"not in SAFE_PREFIXES: {unsafe[0]!r}; needs confirmation",
        "destructive": False,
    }


# First version of the gate, kept only so the test can show the false allows it produced.
def is_destructive_v1(command: str) -> bool:
    return any(s in command for s in ("rm -rf", "sudo ", "chmod ", "mkfs", "dd if="))


def confirm_bash_v1(command: str, auto_approve: bool = False) -> dict:
    if starts_with_safe_prefix(command):  # bug: the allow-list was checked before the deny-list
        return {"decision": "allow", "reason": "starts with a safe prefix"}
    if is_destructive_v1(command) and not auto_approve:
        return {"decision": "block", "reason": "destructive"}
    return {"decision": "allow" if auto_approve else "block", "reason": "not allow-listed"}
