import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from model_client import ModelClient
REPO = Path(__file__).resolve().parent.parent
AGENT_MD = REPO / "AGENT.md"
def load_system_prompt():
    if AGENT_MD.exists():
        return AGENT_MD.read_text()
    return "You are a strict code-review assistant. Reply only with bullet points."
def print_stats(turn_count, cum_in, cum_out, history):
    serialized = json.dumps(history)
    print("\n/stats ")
    print(f"  Turn count                    : {turn_count}")
    print(f"  Cumulative input tokens       : {cum_in}")
    print(f"  Cumulative output tokens      : {cum_out}")
    print(f"  Cumulative total tokens       : {cum_in + cum_out}")
    print(f"  Serialized history length     : {len(serialized)} chars")
    print("------------------\n")
DEMO_TURNS = [
    "Review this: def add(a,b): return a+b",
    "Review this: x = [i for i in range(10) if i % 2 == 0]",
    "Review this: def get(d, k): return d[k]",
    "Review this: password = '12345'  # store user password",
    "Review this: for i in range(len(items)): print(items[i])",
]
def run_conversation(turns, interactive=False):
    client = ModelClient()
    system_prompt = load_system_prompt()
    history = [{"role": "system", "content": system_prompt}]
    turn_count = 0
    cum_in = 0
    cum_out = 0
    for user_text in turns:
        turn_count += 1
        print(f"\n=== Turn {turn_count} ===")
        print(f"User: {user_text}")
        history.append({"role": "user", "content": user_text})
        result = client.complete(history)
        reply = result["text"]
        history.append({"role": "assistant", "content": reply})
        cum_in += result["input_tokens"]
        cum_out += result["output_tokens"]
        print(f"Assistant:\n{reply}")
        print(f"\n[tokens] input: {result['input_tokens']}  "
              f"output: {result['output_tokens']}  total: {result['total_tokens']}")
        if turn_count in (3, 5):
            print_stats(turn_count, cum_in, cum_out, history)
    print("\nFINAL TOTALS ")
    print(f"  Total turns                   : {turn_count}")
    print(f"  Cumulative input tokens       : {cum_in}")
    print(f"  Cumulative output tokens      : {cum_out}")
    print(f"  Cumulative total tokens       : {cum_in + cum_out}")
def main():
    demo = "--demo" in sys.argv
    if demo:
        run_conversation(DEMO_TURNS)
    else:
        client = ModelClient()
        history = [{"role": "system", "content": load_system_prompt()}]
        turn_count = 0
        cum_in = 0
        cum_out = 0
        print("Interactive mode. Type a message, '/stats' for stats, '/quit' to exit.")
        while True:
            user_text = input("\nYou: ").strip()
            if user_text == "/quit":
                break
            if user_text == "/stats":
                print_stats(turn_count, cum_in, cum_out, history)
                continue
            if not user_text:
                continue
            turn_count += 1
            history.append({"role": "user", "content": user_text})
            result = client.complete(history)
            history.append({"role": "assistant", "content": result["text"]})
            cum_in += result["input_tokens"]
            cum_out += result["output_tokens"]
            print(f"Assistant:\n{result['text']}")
            print(f"\n[tokens] input: {result['input_tokens']}  "
                  f"output: {result['output_tokens']}  total: {result['total_tokens']}")
        print("\n FINAL TOTALS ")
        print(f"  Total turns                   : {turn_count}")
        print(f"  Cumulative input tokens       : {cum_in}")
        print(f"  Cumulative output tokens      : {cum_out}")
        print(f"  Cumulative total tokens       : {cum_in + cum_out}")
if __name__ == "__main__":
    main()