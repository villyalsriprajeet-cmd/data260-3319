# File memory: load AGENT.md and MEMORY.md, build the prompt, consolidate
import argparse
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AGENT_PATH = REPO / "AGENT.md"
MEMORY_PATH = REPO / "MEMORY.md"
LOG_PATH = REPO / "MEMORY_CONSOLIDATION_LOG.md"
MAX_LINES = 40  # consolidate when MEMORY.md has more content lines than this
MAX_AGE_HOURS = 24  # or when the last consolidation is older than this
DREAM_HEADING = "## Recent (from /dream)"
STAMP_RE = re.compile(r"last_consolidated:\s*(\S+)")
ENTRY_RE = re.compile(r"^- \[(\d{4}-\d{2}-\d{2})\] ([^:]+): (.+)$")
SUPERSEDES_RE = re.compile(r"^(.*?)(?: \((supersedes .*)\))?$")
HEDGES = ("maybe", "might", "unconfirmed", "tentative", "not sure", "rumour", "rumor", "possibly")


def load_text(path):
    # return the file text, or an empty string when the file is missing
    path = Path(path)
    return path.read_text() if path.exists() else ""


def load_agent(path=AGENT_PATH):
    return load_text(path)


def load_memory(path=MEMORY_PATH):
    return load_text(path)


def content_lines(text):
    # non-empty lines that are not HTML comments
    return [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("<!--")]


def plain_fact(line):
    # turn "- [date] key: value" into "key: value"
    match = ENTRY_RE.match(line)
    return f"{match.group(2)}: {match.group(3)}" if match else line.lstrip("# ").strip()


def build_system_prompt(agent_text, memory_text):
    # AGENT.md first, then the memory facts as plain lines
    facts = "\n".join(plain_fact(ln) for ln in content_lines(memory_text))
    note = ("Use these facts when they help. Answer in short plain sentences, not as a copy of this list. "
            "You cannot change files or settings, so never say you updated or saved anything.")
    return f"{agent_text.strip()}\n\n# Long-term memory (from MEMORY.md)\n{note}\n{facts}"


def read_last_consolidated(text):
    # parse the last_consolidated timestamp comment, or None when absent or invalid
    match = STAMP_RE.search(text)
    if not match:
        return None
    try:
        return datetime.fromisoformat(match.group(1).rstrip("-> "))
    except ValueError:
        return None


def needs_consolidation(text, now=None):
    # True when over 40 content lines or last consolidation over 24h ago
    now = now or datetime.now()
    count = len(content_lines(text))
    if count > MAX_LINES:
        return True, f"{count} content lines > {MAX_LINES}"
    stamp = read_last_consolidated(text)
    if stamp is None:
        return True, "no last_consolidated timestamp"
    if now - stamp > timedelta(hours=MAX_AGE_HOURS):
        return True, f"last consolidated {stamp.isoformat()} is over {MAX_AGE_HOURS}h old"
    return False, f"{count} content lines, consolidated {stamp.isoformat()}"


def normalise(value):
    # lower-case, no punctuation, single spaces, for comparing text
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", value.lower())).strip()


def parse_memory(text):
    # return the title and an ordered {heading: items} map
    title, sections, current = "# MEMORY.md", {"": []}, ""
    for ln in text.splitlines():
        if not ln.strip() or ln.strip().startswith("<!--"):
            continue
        if ln.startswith("# "):
            title = ln
        elif ln.startswith("## "):
            current = ln
            sections.setdefault(current, [])
        else:
            sections[current].append(parse_entry(ln))
    return title, sections


def parse_entry(line):
    # split one entry line into fields, or keep the raw line
    match = ENTRY_RE.match(line)
    if not match:
        return {"raw": line}
    value, history = SUPERSEDES_RE.match(match.group(3)).groups()
    return {"date": match.group(1), "key": match.group(2).strip(), "value": value, "history": history}


def clean_history(parts, winner_value):
    # drop repeated notes and notes that only restate the winning value
    kept = []
    for part in parts:
        if normalise(part.split(": ", 1)[-1]) != normalise(winner_value) and part not in kept:
            kept.append(part)
    return "; ".join(kept)


def resolve_group(group, log):
    # merge duplicates or resolve a contradiction for one key
    ranked = sorted(enumerate(group), key=lambda p: (p[1]["date"], p[0]))
    winner = dict(ranked[-1][1])
    key = winner["key"]
    values = {normalise(e["value"]) for e in group}
    notes = [p for _, e in ranked if e["history"] for p in e["history"].split("; ")]
    if len(values) == 1:
        winner["value"] = group[0]["value"]  # keep the first, cleanest wording
        if len(group) > 1:
            dates = ", ".join(e["date"] for e in group)
            log.append(f"MERGED duplicate | {key} | {len(group)} copies ({dates}) -> kept {winner['date']}")
        winner["history"] = clean_history(notes, winner["value"])
        return winner
    old = {}
    for _, e in ranked[:-1]:
        if normalise(e["value"]) != normalise(winner["value"]):
            old[normalise(e["value"])] = e
    shown = [f"supersedes {e['date']}: {e['value']}" for e in old.values()]
    winner["history"] = clean_history(notes + shown, winner["value"])
    log.append(f"CONTRADICTION | {key} | kept {winner['date']} '{winner['value']}' over " + "; ".join(f"{e['date']} '{e['value']}'" for e in old.values()))
    if any(h in winner["value"].lower() for h in HEDGES):
        log.append(f"REVIEW | {key} | newest value is hedged, so newest-wins may be WRONG; the older value may still be true")
    return winner


def format_entry(entry):
    if "raw" in entry:
        return entry["raw"]
    tail = f" ({entry['history']})" if entry["history"] else ""
    return f"- [{entry['date']}] {entry['key']}: {entry['value']}{tail}"


def consolidate(text, now=None):
    # merge duplicates, resolve contradictions newest-wins, log each change
    now = now or datetime.now()
    title, sections = parse_memory(text)
    groups, placed = {}, {heading: [] for heading in sections}
    for heading, items in sections.items():
        for item in items:
            gid = ("raw", item["raw"]) if "raw" in item else normalise(item["key"])
            if gid not in groups:
                groups[gid] = []
                placed[heading].append(gid)  # the entry stays in the section of its first copy
            groups[gid].append(item)
    out, log = [f"<!-- last_consolidated: {now.replace(microsecond=0).isoformat()} -->", title], []
    for heading, gids in placed.items():
        if heading and gids:
            out.append(heading)
        for gid in gids:
            grp = groups[gid]
            out.append(format_entry(grp[0] if "raw" in grp[0] else resolve_group(grp, log)))
    return "\n".join(out) + "\n", log


def write_log(log, before, after, path=LOG_PATH, now=None):
    # write the consolidation audit log as Markdown
    now = now or datetime.now()
    lines = [f"# Consolidation log ({now.replace(microsecond=0).isoformat()})", "",
             f"Content lines before: {before}. After: {after}.", ""]
    lines += [f"- {entry}" for entry in log] or ["- no changes"]
    Path(path).write_text("\n".join(lines) + "\n")


def run_consolidation(path=MEMORY_PATH, log_path=LOG_PATH):
    # consolidate the file in place; returns (before, after, log)
    text = load_memory(path)
    new_text, log = consolidate(text)
    before, after = len(content_lines(text)), len(content_lines(new_text))
    Path(path).write_text(new_text)
    write_log(log, before, after, log_path)
    return before, after, log


def memory_keys(text):
    # keys already stored, in order, so /dream can reuse them
    keys = []
    for items in parse_memory(text)[1].values():
        keys += [e["key"] for e in items if "key" in e and e["key"] not in keys]
    return keys


def parse_dream(raw, source=None):
    # read the model's JSON reply into (key, value) pairs, dropping junk
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    items = data.get("facts", []) if isinstance(data, dict) else data
    heard = set(normalise(source or "").split())
    pairs = []
    for item in items if isinstance(items, list) else []:
        key, value = str(item.get("key", "")).strip().lower(), str(item.get("value", "")).strip()
        grounded = source is None or set(normalise(value).split()) <= heard
        if key and value and ":" not in key and len(key.split()) <= 3 and "lower-case" not in key and grounded:
            pairs.append((key, value))
    return pairs[:5]


def add_facts(text, facts, today=None):
    # append new facts under the /dream heading, skipping exact repeats
    today = today or datetime.now().strftime("%Y-%m-%d")
    existing = {}
    for items in parse_memory(text)[1].values():
        for e in items:
            if "key" in e:
                existing.setdefault(normalise(e["key"]), set()).add(normalise(e["value"]))
    added, notes = [], []
    for key, value in facts:
        known = existing.get(normalise(key), set())
        if normalise(value) in known:
            notes.append(f"skipped (already stored): {key}: {value}")
            continue
        if known:
            notes.append(f"conflicts with an older '{key}', consolidation will resolve it")
        added.append(f"- [{today}] {key}: {value}")
        existing.setdefault(normalise(key), set()).add(normalise(value))
    if added and DREAM_HEADING not in text:
        text = text.rstrip("\n") + "\n" + DREAM_HEADING + "\n"
    if added:
        text = text.rstrip("\n") + "\n" + "\n".join(added) + "\n"
    return text, added, notes


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="show whether consolidation is required")
    ap.add_argument("--consolidate", action="store_true", help="consolidate MEMORY.md and write the log")
    args = ap.parse_args()
    mem = load_memory()
    print("needs_consolidation:", needs_consolidation(mem))
    if args.consolidate:
        b, a, lg = run_consolidation()
        print(f"content lines before: {b}, after: {a}")
        for item in lg:
            print(" ", item)
        print(f"log written to {LOG_PATH.name}")
