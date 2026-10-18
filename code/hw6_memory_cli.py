# Chat with file memory in the prompt, plus /memory /compact /dream /help
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from model_client import ModelClient
from code import file_memory as fm
KEEP_RECENT = 4  # messages kept in full by /compact
DEMO_MESSAGES = [
    "Hi, I am Sri and I manage the Spartans.",
    "Our home games are at Riverside Park and I always want reminders 48 hours before kickoff.",
    "What should I check before sending the weekend fixture list?",
]
HELP = """Commands:
  /memory   show AGENT.md and MEMORY.md as the model sees them
  /compact  consolidate MEMORY.md and compress older chat messages (counts before and after)
  /dream    pull lasting facts out of the recent chat and add them to MEMORY.md
  /help     show this list
  /quit     leave"""
def make_client():
    return ModelClient(num_ctx=4096, num_predict=200, seed=3319)
def system_message(agent_path, memory_path):
    return {"role": "system", "content": fm.build_system_prompt(fm.load_agent(agent_path), fm.load_memory(memory_path))}
def show_memory(agent_path, memory_path):
    agent, mem = fm.load_agent(agent_path), fm.load_memory(memory_path)
    due, why = fm.needs_consolidation(mem)
    print(f"AGENT.md: {len(fm.content_lines(agent))} content lines")
    print(f"MEMORY.md: {len(fm.content_lines(mem))} content lines, last consolidated {fm.read_last_consolidated(mem)}")
    print(f"consolidation required: {due} ({why})")
    print("--- MEMORY.md ---")
    print(mem.rstrip())
def compact(history, client, memory_path):  # /compact: report counts before and after
    before_msgs, lines_before = len(history), len(fm.content_lines(fm.load_memory(memory_path)))
    _, lines_after, log = fm.run_consolidation(memory_path)
    if len(history) > KEEP_RECENT:
        old, recent = history[:-KEEP_RECENT], history[-KEEP_RECENT:]
        text = "\n".join(f"{m['role']}: {m['content']}" for m in old)
        ask = [{"role": "system", "content": "Summarize this chat in 2 short bullets starting with '- '."},
               {"role": "user", "content": text}]
        summary = client.complete(ask, json_mode=False)["text"].strip()
        history[:] = [{"role": "assistant", "content": "Summary of earlier chat:\n" + summary}] + recent
    print(f"messages: {before_msgs} -> {len(history)}")
    print(f"MEMORY.md content lines: {lines_before} -> {lines_after} ({len(log)} changes logged in {fm.LOG_PATH.name})")
KEY_HINTS = {"name": "the user's name", "role": "the user's job", "team": "the team's name",
             "home venue": "where home games are played", "away venue": "where away games are played",
             "rival": "the opposing team", "next game": "date and time of the next game",
             "training day": "the day the team trains", "reminders": "how long before games to send reminders",
             "availability": "days and times the user is free", "timezone": "the user's time zone",
             "contact": "how to contact the user", "summary style": "how summaries should look"}
def dream_prompt(keys):
    shown = ", ".join(f"{k} ({KEY_HINTS[k]})" if k in KEY_HINTS else k for k in keys)
    return ("Read the user's messages and list lasting facts they state about themselves, their team, venue, schedule or "
            f"preferences. Reuse one of these keys only when its meaning fits the fact: {shown}. Otherwise use a new key of "
            "one to three words. Copy each value from the user's own words. Reply with JSON only. Examples: "
            "'I can only help on Tuesdays' -> {\"facts\": [{\"key\": \"availability\", \"value\": \"Tuesdays only\"}]}; "
            "'Please remind me a day before each game' -> {\"facts\": [{\"key\": \"reminders\", \"value\": \"a day before each game\"}]}. "
            'Ignore questions and small talk. If nothing lasting was said, reply {"facts": []}.')
def dream(history, client, memory_path):  # /dream: add lasting facts to MEMORY.md
    mem = fm.load_memory(memory_path)
    users = [m["content"] for m in history[-10:] if m["role"] == "user"]
    said = "\n".join(t for t in users if not t.strip().endswith("?"))  # questions are not facts
    ask = [{"role": "system", "content": dream_prompt(fm.memory_keys(mem))}, {"role": "user", "content": said}]
    raw = client.complete(ask, json_mode=True)["text"]
    print("model reply:", raw.strip())
    new_text, added, notes = fm.add_facts(mem, fm.parse_dream(raw, said))
    Path(memory_path).write_text(new_text)
    for line in added + notes:
        print(" ", line)
    print(f"/dream added {len(added)} fact(s) to MEMORY.md")
def reply(history, client, user_text, agent_path, memory_path):  # system prompt rebuilt from the files each turn
    history.append({"role": "user", "content": user_text})
    messages = [system_message(agent_path, memory_path)] + history
    out = client.complete(messages, json_mode=False)
    history.append({"role": "assistant", "content": out["text"].strip()})
    return out["text"].strip(), out["input_tokens"]
def handle(line, history, client, agent_path, memory_path):  # route a command or a chat line
    if line == "/quit":
        return False
    if line == "/help":
        print(HELP)
    elif line == "/memory":
        show_memory(agent_path, memory_path)
    elif line == "/compact":
        compact(history, client, memory_path)
    elif line == "/dream":
        dream(history, client, memory_path)
    else:
        text, tokens = reply(history, client, line, agent_path, memory_path)
        print(f"assistant: {text}\n[prompt tokens: {tokens}, chat messages: {len(history)}]")
    return True
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="run a scripted session")
    ap.add_argument("--agent", default=str(fm.AGENT_PATH))
    ap.add_argument("--memory", default=str(fm.MEMORY_PATH))
    args = ap.parse_args()
    client, history = make_client(), []
    due, why = fm.needs_consolidation(fm.load_memory(args.memory))
    print(f"startup: consolidation required = {due} ({why})")
    script = ["/help", "/memory"] + DEMO_MESSAGES + ["/dream", "/compact", "/memory"] if args.demo else []
    while True:
        if args.demo:
            if not script:
                break
            line = script.pop(0)
            print(f"\nyou> {line}")
        else:
            try:
                line = input("you> ").strip()
            except EOFError:
                break
        if line and not handle(line, history, client, args.agent, args.memory):
            break
if __name__ == "__main__":
    main()
