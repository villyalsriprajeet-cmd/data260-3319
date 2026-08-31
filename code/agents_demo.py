import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import List, Dict, Any, Iterable, Tuple
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
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
    s = s.replace("```", " ")
    s = s.replace("`", " ")
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
    def consider(phrase_words: Tuple[str, ...]):
        if all(w in STOP for w in phrase_words):
            return
        if phrase_words[0] in STOP or phrase_words[-1] in STOP:
            return
        phrase = " ".join(phrase_words)
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
        t = strip_code_and_md(str(t)).lower().strip()
        t = t.strip("[]'\" ")
        if t and t not in clean_tags:
            clean_tags.append(t)
    if len(clean_tags) < 3:
        for cand in phrase_candidates(title, content):
            if cand not in clean_tags:
                clean_tags.append(cand)
            if len(clean_tags) == 3:
                break
    clean_tags = clean_tags[:3]
    summary = data.get("summary", "")
    summary = _clip_words(str(summary), 25)
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
@dataclass
class SimpleAgent:
    name: str
    system: str
    model: Any
    def respond(
        self,
        conversation: List[Dict[str, str]],
        task: str,
        title: str,
        content: str,
        strict: bool,
    ) -> Dict[str, Any]:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.system),
            ("human",
             "Task:\n{task}\n\nConversation so far:\n{history}\n\n"
             "Reply with ONE JSON object only - no code fences, no text around it. "
             "Keys: thought (string), message (non-empty, <=60 words, no code), "
             "data.tags (array of exactly 3 topical tags), "
             "data.summary (<=25 words, ends with a period), "
             "data.issues (array)."),
        ])
        history = "\n".join(f'{m["role"]}: {m["content"]}' for m in conversation) or "(empty)"
        chain = prompt | self.model | StrOutputParser()
        raw = chain.invoke({"task": task, "history": history})
        return parse_and_coerce(raw, title, content, strict)
def make_llm(temperature: float, model: str = None, base_url: str = None):
    return ChatOllama(
        model=model or os.environ.get("HW1_MODEL", "qwen2.5:3b"),
        temperature=temperature,
        base_url=base_url or os.environ.get("OLLAMA_URL", "http://localhost:11434"),
        num_ctx=512,
        num_predict=256,
        format="json",
    )
def build_agents(llm):
    planner = SimpleAgent(
        name="Planner",
        system=(
            "You label sports fixtures. Read the title and content and propose exactly "
            "3 distinct, specific tags (prefer two-word phrases taken from the text) "
            "plus a one-sentence summary. Base everything on the given text only."
        ),
        model=llm,
    )
    reviewer = SimpleAgent(
        name="Reviewer",
        system=(
            "You check the Planner's work. Make sure the 3 tags are specific and drawn "
            "from the text, the summary is one sentence of 25 words or fewer, and there "
            "is no code or markdown. List any problems in data.issues, otherwise return "
            "the cleaned-up tags and summary."
        ),
        model=llm,
    )
    finalizer = SimpleAgent(
        name="Finalizer",
        system=(
            "You produce the final answer using the Reviewer's feedback. Output exactly "
            "3 tags in data.tags and the final summary in data.summary, and set "
            "data.issues to an empty list."
        ),
        model=llm,
    )
    return planner, reviewer, finalizer
def run_pipeline(title, content, planner, reviewer, finalizer, strict=False, email="student@sjsu.edu"):
    task = (
        f'Fixture title: "{title}". '
        f'Fixture details: "{content}". '
        "Produce exactly 3 topical tags and a one-sentence summary (<=25 words), "
        "in your own words, based only on this fixture."
    )
    transcript = []
    planned = planner.respond(transcript, task, title, content, strict)
    transcript.append({"role": "Planner", "content": planned.get("message", "")})
    reviewed = reviewer.respond(transcript, task, title, content, strict)
    transcript.append({"role": "Reviewer", "content": reviewed.get("message", "")})
    final = finalizer.respond(transcript, task, title, content, strict)
    return {"planner": planned, "reviewer": reviewed, "final": final, "transcript": transcript}
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", default="San Jose State Spartans vs Fresno State Bulldogs - Mountain West Soccer Fixture")
    ap.add_argument("--content", default=(
        "The San Jose State Spartans host the Fresno State Bulldogs in a Mountain West "
        "Conference men's soccer match this Saturday at the Spartan Soccer Complex on "
        "South Campus. Kickoff is scheduled for 7 PM. The Spartans enter the fixture "
        "unbeaten in their last four home games and sit near the top of the conference "
        "table, while the Bulldogs arrive after a hard-fought road win midweek. The "
        "referee assignment has been confirmed and gates open one hour before kickoff. "
        "The match was moved from its original Friday slot following a scheduling "
        "conflict with another campus event."
    ))
    ap.add_argument("--email", default="student@sjsu.edu")
    ap.add_argument("--model", default=os.environ.get("HW1_MODEL", "qwen2.5:3b"))
    ap.add_argument("--base_url", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    try:
        llm = make_llm(args.temperature, args.model, args.base_url)
    except Exception:
        print(
            "Could not start ChatOllama. Is `ollama serve` running and the model pulled?\n"
            "Try: ollama serve   (and)   ollama pull qwen2.5:3b",
            file=sys.stderr,
        )
        raise
    planner, reviewer, finalizer = build_agents(llm)
    task = (
        f'Fixture title: "{args.title}". '
        f'Fixture details: "{args.content}". '
        "Produce exactly 3 topical tags and a one-sentence summary (<=25 words), "
        "in your own words, based only on this fixture."
    )
    transcript: List[Dict[str, str]] = []
    t0 = time.time()
    planned = planner.respond(transcript, task, args.title, args.content, args.strict)
    t1 = time.time()
    transcript.append({"role": "Planner", "content": planned.get("message", "")})
    print(f"\n--- Planner ({int((t1 - t0) * 1000)} ms) ---\n{json.dumps(planned, indent=2)}")
    t0 = time.time()
    reviewed = reviewer.respond(transcript, task, args.title, args.content, args.strict)
    t1 = time.time()
    transcript.append({"role": "Reviewer", "content": reviewed.get("message", "")})
    print(f"\n--- Reviewer ({int((t1 - t0) * 1000)} ms) ---\n{json.dumps(reviewed, indent=2)}")
    final = finalizer.respond(transcript, task, args.title, args.content, args.strict)
    print(f"\n=== Finalized Output ===\n{json.dumps(final, indent=2)}")
    package = {
        "title": args.title,
        "email": args.email,
        "content": args.content,
        "agents": {"transcript": transcript, "final": final.get("data", {})},
        "submissionDate": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    print(f"\n=== Publish Package ===\n{json.dumps(package, indent=2)}")
if __name__ == "__main__":
    main()