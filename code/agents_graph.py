# HW2 Part 3 - Stateful agent graph 
import json
import re
import sys
import time
from pathlib import Path
from typing import TypedDict, Dict, Any, List, Iterable, Tuple
from langgraph.graph import StateGraph, START, END
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.model_client import ModelClient
TURN_CEILING = 6
# Parsing helpers 
STOP = {
    "the", "and", "for", "that", "with", "this", "from", "into", "than", "your",
    "you", "are", "was", "were", "have", "has", "had", "use", "used", "using",
    "about", "how", "can", "will", "more", "less", "very", "over", "under",
    "their", "there", "then", "our", "out", "on", "in", "of", "to", "by",
    "a", "an", "is", "it", "as", "at", "its", "who", "one", "they", "after",
    "before", "while", "following", "another",
}
def strip_code_and_md(s: str) -> str:
    s = str(s)
    s = re.sub(r"```[a-zA-Z]*", " ", s)
    s = s.replace("```", " ").replace("`", " ")
    return " ".join(s.split())
def extract_json_block(text: str) -> str:
    text = str(text).strip()
    start = text.find("{")
    if start == -1:
        return json.dumps({"message": strip_code_and_md(text)})
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return json.dumps({"message": strip_code_and_md(text)})
def tokens(txt: str) -> List[str]:
    return re.findall(r"[a-z][a-z\-]+", str(txt).lower())
def ngrams(words: List[str], n: int) -> Iterable[Tuple[str, ...]]:
    for i in range(max(0, len(words) - n + 1)):
        yield tuple(words[i:i + n])
def phrase_candidates(title: str, content: str, maxn: int = 12) -> List[str]:
    words = tokens(f"{title} {content}")
    counts: Dict[str, int] = {}
    def consider(pw: Tuple[str, ...]):
        if all(w in STOP for w in pw):
            return
        if pw[0] in STOP or pw[-1] in STOP:
            return
        phrase = " ".join(pw)
        counts[phrase] = counts.get(phrase, 0) + 1
    for n in (3, 2):
        for g in ngrams(words, n):
            consider(g)
    for w in words:
        if w not in STOP and len(w) > 3:
            counts[w] = counts.get(w, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (kv[1], len(kv[0])), reverse=True)
    return [phrase for phrase, _ in ranked[:maxn]]
def _clip_words(text: str, limit: int) -> str:
    words = strip_code_and_md(text).split()
    if len(words) > limit:
        words = words[:limit]
    out = " ".join(words).rstrip(" .")
    return out + "." if out else out
def coerce_reply(raw_obj: Any, title: str, content: str, strict: bool) -> Dict[str, Any]:
    if not isinstance(raw_obj, dict):
        raw_obj = {"message": str(raw_obj)}
    data = raw_obj.get("data")
    if not isinstance(data, dict):
        data = {}
    tags = data.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    clean_tags: List[str] = []
    for t in tags:
        t = strip_code_and_md(str(t)).lower().strip().strip("[]'\" ")
        if t and t not in clean_tags:
            clean_tags.append(t)
    if len(clean_tags) < 3:
        for cand in phrase_candidates(title, content):
            if cand not in clean_tags:
                clean_tags.append(cand)
            if len(clean_tags) == 3:
                break
    clean_tags = clean_tags[:3]
    summary = _clip_words(str(data.get("summary", "")), 25)
    if not summary:
        summary = _clip_words(f"{title}. {content}", 25)
    message = strip_code_and_md(str(raw_obj.get("message", "")))
    if not message:
        message = "Tags and summary prepared."
    message = _clip_words(message, 60)
    issues = data.get("issues", [])
    if not isinstance(issues, list):
        issues = []
    if strict:
        multiword = sum(1 for t in clean_tags if " " in t)
        if multiword < 2:
            issues = list(issues) + ["fewer than two multi-word tags"]
    return {
        "thought": strip_code_and_md(str(raw_obj.get("thought", ""))),
        "message": message,
        "data": {"tags": clean_tags, "summary": summary, "issues": issues},
    }
def parse_and_coerce(text: str, title: str, content: str, strict: bool) -> Dict[str, Any]:
    try:
        obj = json.loads(extract_json_block(text))
    except Exception:
        obj = {"message": strip_code_and_md(text)}
    return coerce_reply(obj, title, content, strict)

# AgentState: the shared memory for every node
class AgentState(TypedDict):
    title: str
    content: str
    email: str
    strict: bool
    task: str
    llm: Any
    planner_proposal: Dict[str, Any]
    reviewer_feedback: Dict[str, Any]
    turn_count: int
# Agent nodes (Planner and Reviewer)
# Each node takes the state, calls the LLM through ModelClient, and returns
# a dict with only the keys of AgentState it wants to update.
PLANNER_SYSTEM = (
    "You label sports fixtures. Read the title and content and propose exactly "
    "3 distinct, specific tags (prefer two-word phrases taken from the text) "
    "plus a one-sentence summary of 25 words or fewer. Base everything on the "
    "given text only. Reply with ONE JSON object only, no code fences: "
    'keys are "thought", "message", and "data" where data has "tags" (array of '
    '3 strings), "summary" (string), and "issues" (array).'
)
REVIEWER_SYSTEM = (
    "You check the Planner's work. Make sure there are exactly 3 specific tags "
    "drawn from the text, the summary is one sentence of 25 words or fewer, and "
    "there is no code or markdown. Put any problems in data.issues; if it is all "
    "fine return data.issues as an empty list. Reply with ONE JSON object only, "
    'no code fences: keys "thought", "message", and "data" with "tags", '
    '"summary", and "issues".'
)
def _call_llm(state: AgentState, system_prompt: str, extra_context: str = "") -> Dict[str, Any]:
    llm: ModelClient = state["llm"]
    user = (
        f"Task:\n{state['task']}\n\n"
        f"{extra_context}\n"
        "Reply with ONE JSON object only."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user},
    ]
    result = llm.complete(messages)
    return parse_and_coerce(
        result["text"], state["title"], state["content"], state["strict"]
    )
def planner_node(state: AgentState) -> Dict[str, Any]:
    print("NODE: Planner")
    proposal = _call_llm(state, PLANNER_SYSTEM)
    return {"planner_proposal": proposal}
def reviewer_node(state: AgentState) -> Dict[str, Any]:
    print("NODE: Reviewer")
    proposal = state.get("planner_proposal", {})
    context = "The Planner proposed:\n" + json.dumps(proposal.get("data", {}), indent=2)
    feedback = _call_llm(state, REVIEWER_SYSTEM, extra_context=context)
    # feedback["data"]["issues"] = ["forced issue for loop demo"]
    return {"reviewer_feedback": feedback}

# Supervisor node and router logic
def supervisor_node(state: AgentState) -> Dict[str, Any]:
    print("NODE: Supervisor")
    return {"turn_count": state.get("turn_count", 0) + 1}
def router_logic(state: AgentState) -> str:
    if not state.get("planner_proposal"):
        return "planner"
    feedback = state.get("reviewer_feedback") or {}
    issues = feedback.get("data", {}).get("issues", [])
    if not feedback:
        return "reviewer"
    if issues and state.get("turn_count", 0) < TURN_CEILING:
        return "planner"
    return END
# Build the graph: here the supervisor routes to planner/reviewer, both loop back to supervisor, ends via router
def build_graph():
    graph = StateGraph(AgentState)
# register the three nodes
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("planner", planner_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_edge(START, "supervisor") # always start at the supervisor
# supervisor uses router_logic to pick planner, reviewer, or END
    graph.add_conditional_edges(
        "supervisor",
        router_logic,
        {"planner": "planner", "reviewer": "reviewer", END: END},
    )
# both workers hand control back to the supervisor (this creates the loop)
    graph.add_edge("planner", "supervisor")
    graph.add_edge("reviewer", "supervisor")
    return graph.compile()
# Build the initial state and run the graph with .stream(), printing each node's output
def run_once(title, content, email="student@sjsu.edu", strict=False,
             model="qwen2.5:3b", base_url="http://localhost:11434", temperature=0.0):
    task = (
        f'Fixture title: "{title}". '
        f'Fixture details: "{content}". '
        "Produce exactly 3 topical tags and a one-sentence summary (<=25 words), "
        "in your own words, based only on this fixture."
    )
    initial_state = {
        "title": title,
        "content": content,
        "email": email,
        "strict": strict,
        "task": task,
        "llm": ModelClient(model=model, base_url=base_url, temperature=temperature),
        "planner_proposal": {},
        "reviewer_feedback": {},
        "turn_count": 0,
    }
    app = build_graph()
    final_state = None
# stream through the graph so we see the output from each step
    for step in app.stream(initial_state):
        for node_name, node_output in step.items():
            print(f"[{node_name}] -> {json.dumps(node_output)[:300]}")
        final_state = step
    return final_state
def main():
    title = "San Jose State Spartans vs Fresno State Bulldogs - Mountain West Soccer Fixture"
    content = (
        "The San Jose State Spartans host the Fresno State Bulldogs in a Mountain West "
        "Conference men's soccer match this Saturday at the Spartan Soccer Complex on "
        "South Campus. Kickoff is scheduled for 7 PM. The match was moved from its "
        "original Friday slot following a scheduling conflict with another campus event."
    )
    t0 = time.time()
    result = run_once(title, content)
    dt = int((time.time() - t0) * 1000)
    print(f"\nDone in {dt} ms ")
    print(json.dumps(result, indent=2))
if __name__ == "__main__":
    main()