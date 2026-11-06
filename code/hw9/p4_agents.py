# HW9 Part 4: Answering Agent, Evaluator Agent and lesson memory for fixture questions
# The Answering Agent reads fixture rows from MySQL s3319_rel and calls qwen2.5:3b through src/model_client.py.
# The Evaluator Agent grades every answer against reports/hw09/part4/reference_fixtures.json (ground truth).
import asyncio
import json
import re
import time
from code.hw9.qa_service import CODE_RE, FACTS_SQL, facts_text, fixture_codes
from code.kafka_service.settings import SEED, now_utc
from datetime import date
from pathlib import Path

from src.model_client import ModelClient

ROOT = Path(__file__).resolve().parents[2]
PART4 = ROOT / "reports" / "hw09" / "part4"
REFERENCE_FILE = PART4 / "reference_fixtures.json"
LESSONS_FILE = PART4 / "lessons.json"  # lessons kept after validation (4.3)
CANDIDATES_FILE = PART4 / "lessons_candidates.json"  # every lesson made from the training data (4.2)
MAX_ATTEMPTS = 2
MIN_REPEATS = 2  # a failure pattern becomes a lesson once it has been seen this many times
TITLE_RE = re.compile(r"^(?P<home>.+?) vs (?P<away>.+?) - Matchweek (?P<week>\d+)$")
UNSUPPORTED = {  # asked for, but not stored in s3319_rel
    "kickoff time": r"kick ?off|kick-off|start time|what time",
    "referee": r"referee",
    "attendance": r"attendance|how many (people|fans|spectators)",
    "weather": r"weather",
    "final score": r"score|result",
}
FIELDS = [  # (field, keywords) checked in this order on the lower-case question
    ("city", r"\bcity\b"),
    ("away_team", r"away team|away side|visiting team|visitors"),
    ("home_team", r"home team|home side"),
    ("venue", r"venue|\bwhere\b|stadium|ground|played at"),
    ("matchweek", r"matchweek|which week|what week"),
    ("title", r"\btitle\b|\bcalled\b"),
    ("tickets", r"tickets"),
]
FIELD_NAMES = {
    "city": "home team's city",
    "away_team": "away team",
    "home_team": "home team",
    "venue": "venue",
    "matchweek": "matchweek",
    "title": "title",
    "tickets": "number of tickets left",
}
REFUSAL = re.compile(
    r"not (available|provided|included|listed|given|known|specified|stated|recorded|found|in the)|"
    r"no (information|data|record|details|fixture|such|mention)|(does|do|is|are)( not|n t) "
    r"(include|exist|have|contain|mention|available|provided|listed|included|specified)|"
    r"cannot (find|determine|tell|say|be determined|provide)|can t (find|determine|tell|provide)|"
    r"could( not|n t) find|unknown|unable to|not able to"
)
PATTERNS = {  # failure pattern -> (description, correction, question tags it applies to)
    "omits_requested_field": (
        "The answer leaves out part of a question that asks for more than one fact.",
        "When a question asks for several facts, answer every part; check each requested fact before finishing.",
        ["multi"],
    ),
    "wrong_away_team": (
        "The answer names the wrong team as the away team.",
        "Fixture titles are written 'Home Team vs Away Team - Matchweek N'; the away team is the team after 'vs'.",
        ["away_team"],
    ),
    "unclear_sold_out": (
        "The answer does not say clearly whether the fixture is sold out.",
        "Answer sold-out questions with a clear yes or no: a fixture is sold out only when tickets_available is 0.",
        ["sold_out"],
    ),
    "invented_unknown_fixture": (
        "The answer gives details for a fixture code that is not in the league records.",
        "If the records say a fixture code does not exist, say the fixture was not found and give no details.",
        ["unknown_fixture"],
    ),
    "invented_unsupported_field": (
        "The answer guesses a fact that the fixture records do not contain.",
        "The records only have title, venue, tickets_available and home team; for anything else "
        "(kickoff time, referee, attendance, weather, score) say it is not available.",
        ["unsupported"],
    ),
    "wrong_difference": (
        "The answer gives the wrong difference between two ticket counts, or says more instead of fewer.",
        "For 'how many more tickets does A have than B', compute A minus B; if the result is negative, "
        "say A has that many fewer tickets than B.",
        ["difference"],
    ),
    "wrong_total": (
        "The answer gives the wrong total of two ticket counts.",
        "For 'in total' questions, add the tickets_available of both fixtures digit by digit and give the sum.",
        ["total"],
    ),
    "wrong_week_gap": (
        "The answer gives the wrong number of matchweeks between two fixtures.",
        "For 'how many matchweeks apart' questions, take the number after 'Matchweek' in each title and "
        "subtract the smaller from the larger.",
        ["week_gap"],
    ),
}
for _f, _name in FIELD_NAMES.items():
    if _f != "away_team":
        PATTERNS[f"wrong_{_f}"] = (
            f"The answer gives the wrong {_name}.",
            f"Copy the {_name} exactly as it appears in the fixture record."
            + (" The matchweek is the number after 'Matchweek' in the title." if _f == "matchweek" else ""),
            [_f],
        )


def norm(text):
    return " " + re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip() + " "


def numbers(text):
    return {int(n) for n in re.findall(r"(?<![\w-])\d+(?![\w])", re.sub(r"FX-\d{5}", " ", str(text), flags=re.I))}


def load_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else default


def load_reference():
    data = load_json(REFERENCE_FILE)
    return {f["fixture_code"]: f for f in data["fixtures"]}, set(data["not_in_league"])


def analyze(question, fixtures):
    """What the question asks: kind, requested fields and fixture codes (used by both agents)."""
    q = question.lower()
    codes = list(dict.fromkeys(c.upper() for c in CODE_RE.findall(question)))  # keep question order (A minus B)
    unknown = [c for c in codes if c not in fixtures]
    unsupported = [name for name, rx in UNSUPPORTED.items() if re.search(rx, q)]
    if unknown:
        kind, fields = "unknown_fixture", []
    elif unsupported:
        kind, fields = "unsupported", unsupported
    elif "how many more tickets" in q and len(codes) == 2:
        kind, fields = "difference", ["tickets"]
    elif "in total" in q and len(codes) == 2:
        kind, fields = "total", ["tickets"]
    elif "matchweeks apart" in q and len(codes) == 2:
        kind, fields = "week_gap", ["matchweek"]
    elif "sold out" in q:
        kind, fields = "sold_out", ["tickets"]
    else:
        fields, rest = [], q
        for field, rx in FIELDS:
            if re.search(rx, rest):
                fields.append(field)
                if field == "city":
                    rest = re.sub(r"home team", " ", rest)  # 'city of the home team' asks only for the city
        kind = "multi" if len(fields) > 1 else (fields[0] if fields else "other")
    return {"kind": kind, "fields": fields, "codes": codes, "unknown": unknown, "tags": {kind, *fields}}


class AnsweringAgent:
    SYSTEM = (
        "You are the Answering Agent of a community sports league fixtures assistant. "
        "Answer the question using only the fixture records you are given. Answer in one or two sentences. "
        'Reply with ONE JSON object only: {"answer": "your answer"}'
    )
    FAULT = "For this first draft, answer only the first thing the question asks and leave out everything else."

    def __init__(self, engine):
        self.engine = engine
        self.client = ModelClient(model="qwen2.5:3b", temperature=0.0, num_ctx=2048, num_predict=200, seed=SEED)

    def records(self, question):
        codes = fixture_codes(question)
        if not codes:
            return "No fixture code was given, so no fixture records apply."
        with self.engine.connect() as conn:
            rows = [dict(r._mapping) for r in conn.execute(FACTS_SQL, {"codes": codes})]
        return facts_text(codes, rows).strip()

    def answer(self, question, lessons=(), previous=None, feedback=None, inject_fault=False):
        system = self.SYSTEM
        if lessons:
            system += "\n\nLessons learned from earlier mistakes (follow them):\n" + "\n".join(
                f"- {lsn['correction']}" for lsn in lessons
            )
        if inject_fault:
            system += "\n\n" + self.FAULT  # controlled test case: a deliberately incomplete first answer
        user = f"Question: {question}\n\n{self.records(question)}"
        if previous is not None:
            user += f"\n\nYour previous answer: {previous}\nEvaluator feedback: {feedback}\nWrite a corrected answer."
        result = self.client.complete([{"role": "system", "content": system}, {"role": "user", "content": user}])
        try:
            text = json.loads(result["text"]).get("answer", "")
        except (json.JSONDecodeError, AttributeError):
            text = result["text"]
        return str(text).strip(), result["total_tokens"]


class EvaluatorAgent:
    def __init__(self, fixtures):
        self.fixtures = fixtures

    def expected(self, field, code):
        f = self.fixtures[code]
        return {
            "city": f["home_city"],
            "away_team": f["away_team"],
            "home_team": f["home_team"],
            "venue": f["venue"],
            "matchweek": f["matchweek"],
            "title": f["fixture_title"],
            "tickets": f["tickets_available"],
        }[field]

    def field_ok(self, field, code, answer):
        value = self.expected(field, code)
        if field in ("tickets", "matchweek"):
            return int(value) in numbers(answer)
        if field == "title":
            f = self.fixtures[code]
            return all(norm(p).strip() in norm(answer) for p in (f["home_team"], f["away_team"])) and int(
                f["matchweek"]
            ) in numbers(answer)
        return norm(value) in norm(answer)

    def evaluate(self, question, answer):
        info = analyze(question, self.fixtures)
        kind, codes, t = info["kind"], info["codes"], norm(answer)
        checked, problems = {}, []  # problems: (pattern, explanation, feedback)
        if kind == "unknown_fixture":
            checked = {c: "not in the league records" for c in info["unknown"]}
            if not REFUSAL.search(t):
                problems.append(
                    (
                        "invented_unknown_fixture",
                        f"{', '.join(info['unknown'])} is not in the reference data, but the answer does not say so.",
                        f"{', '.join(info['unknown'])} does not exist; say it was not found and give no details.",
                    )
                )
        elif kind == "unsupported":
            checked = {f: "not stored for any fixture" for f in info["fields"]}
            guessed = re.search(r"\b\d{1,2}(:\d{2})? ?(am|pm)\b|\b\d{1,2}:\d{2}\b", answer.lower())
            if not REFUSAL.search(t) or guessed:
                problems.append(
                    (
                        "invented_unsupported_field",
                        f"The reference data has no {', '.join(info['fields'])}, but the answer gives one.",
                        f"The records do not contain the {', '.join(info['fields'])}; say it is not available.",
                    )
                )
        elif kind == "difference":
            a, b = (int(self.fixtures[c]["tickets_available"]) for c in codes)
            d = a - b  # "how many more does the first have than the second"
            checked = {codes[0]: a, codes[1]: b, "first_minus_second": d}
            low = answer.lower()
            pos_a, pos_b = low.find(codes[0].lower()), low.find(codes[1].lower())
            subject_is_b = pos_b != -1 and (pos_a == -1 or pos_b < pos_a)  # which fixture the sentence is about
            claim = -1 if (re.search(r"fewer|\bless\b|lower|negative", low) or f"-{abs(d)}" in low) else 1
            claim = -claim if subject_is_b else claim  # 'B has N more' means A has N fewer
            direction_ok = d == 0 or (claim > 0) == (d > 0)
            if abs(d) not in numbers(answer) or not direction_ok:
                problems.append(
                    (
                        "wrong_difference",
                        f"{codes[0]} has {a} and {codes[1]} has {b} tickets; the answer has the wrong number or "
                        "says more/fewer the wrong way round.",
                        "Compute first minus second from the records; if the first fixture has fewer tickets, "
                        "say it has that many fewer.",
                    )
                )
        elif kind == "total":
            a, b = (int(self.fixtures[c]["tickets_available"]) for c in codes)
            checked = {codes[0]: a, codes[1]: b, "total": a + b}
            if a + b not in numbers(answer):
                problems.append(
                    (
                        "wrong_total",
                        "The total of the two ticket counts is missing or wrong.",
                        "Add the tickets_available of both fixtures from the records and give the sum.",
                    )
                )
        elif kind == "week_gap":
            a, b = (int(self.fixtures[c]["matchweek"]) for c in codes)
            checked = {codes[0]: a, codes[1]: b, "gap": abs(a - b)}
            if abs(a - b) not in numbers(answer):
                problems.append(
                    (
                        "wrong_week_gap",
                        "The number of matchweeks between the two fixtures is missing or wrong.",
                        "Read both matchweek numbers from the titles and subtract the smaller from the larger.",
                    )
                )
        elif kind == "sold_out":
            tickets = int(self.fixtures[codes[0]]["tickets_available"])
            checked = {"tickets_available": tickets, "sold_out": tickets == 0}
            ts = norm(re.sub(r"tickets_available", "count", answer, flags=re.I))  # the field name is not a claim
            zero = re.search(r" (0|zero|no) tickets ", ts)
            still = re.search(
                r"not sold out|n t sold out| [1-9]\d* (tickets )?(are )?(still )?(left|available|remaining)", ts
            )
            ok = (zero or ("sold out" in ts and not still)) if tickets == 0 else (still and not zero)
            if not ok:
                problems.append(
                    (
                        "unclear_sold_out",
                        f"{codes[0]} has {tickets} tickets left, so it is {'' if tickets == 0 else 'not '}sold out; "
                        "the answer does not say this clearly.",
                        "Say yes or no: a fixture is sold out only when tickets_available is 0.",
                    )
                )
        elif kind in FIELD_NAMES or kind == "multi":
            code = codes[0]
            for field in info["fields"]:
                checked[field] = self.expected(field, code)
                if not self.field_ok(field, code, answer):
                    if kind == "multi":
                        pattern = "omits_requested_field"
                        why = f"The answer does not give the correct {FIELD_NAMES[field]} that was asked for."
                        tip = f"Also give the {FIELD_NAMES[field]} of {code}; it is in the fixture record."
                    elif field == "away_team":
                        pattern = "wrong_away_team"
                        why = "The away team is wrong or missing."
                        tip = "In the title 'Home vs Away - Matchweek N' the away team is the team after 'vs'."
                    else:
                        pattern = f"wrong_{field}"
                        why = f"The {FIELD_NAMES[field]} does not match the reference for {code}."
                        tip = f"Re-read the {FIELD_NAMES[field]} in the fixture record for {code} and copy it exactly."
                    problems.append((pattern, why, tip))
        if problems:
            return {
                "result": "REVISE",
                "explanation": " ".join(p[1] for p in problems),
                "feedback": " ".join(p[2] for p in problems),
                "failure_patterns": [p[0] for p in problems],
                "checked": checked,
                "kind": kind,
            }
        return {
            "result": "PASS",
            "explanation": f"All requested facts match the reference ({kind}).",
            "feedback": None,
            "failure_patterns": [],
            "checked": checked,
            "kind": kind,
        }


class LessonStore:
    def __init__(self, path=None, lessons=None, learn=False):
        self.path = Path(path) if path else None  # None = in memory only (validation trials)
        self.lessons = lessons if lessons is not None else load_json(self.path, [])
        self.learn = learn
        self.seen = {}  # failure pattern -> question ids where it happened

    def save(self):
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.lessons, indent=2) + "\n")

    def relevant(self, info):
        found = [lsn for lsn in self.lessons if info["tags"] & set(lsn["applies_to"])]
        for lsn in found:
            lsn["use_count"] += 1
        if found:
            self.save()
        return found

    def record_failure(self, pattern, qid):
        """Count a failure pattern; make it a lesson once it repeats MIN_REPEATS times."""
        self.seen.setdefault(pattern, []).append(qid)
        exists = any(lsn["failure_pattern"] == PATTERNS[pattern][0] for lsn in self.lessons)
        if not self.learn or exists or len(self.seen[pattern]) < MIN_REPEATS:
            return None
        description, correction, applies = PATTERNS[pattern]
        lesson = {
            "lesson_id": f"lesson_{len(self.lessons) + 1:03d}",
            "failure_pattern": description,
            "correction": correction,
            "created_at": date.today().isoformat(),
            "use_count": 0,
            "pattern_key": pattern,
            "applies_to": applies,
            "seen_in": list(self.seen[pattern]),
        }
        self.lessons.append(lesson)
        self.save()
        return lesson


async def solve(qid, question, answerer, evaluator, store=None, repair=True, inject_fault=False, log=print):
    """Answer -> evaluate -> (revise -> evaluate). At most MAX_ATTEMPTS answers, then stop."""
    info = analyze(question, evaluator.fixtures)
    lessons = store.relevant(info) if store else []
    if lessons:
        names = ", ".join("{} (use_count {})".format(x["lesson_id"], x["use_count"]) for x in lessons)
        log(f"  [{qid}] lessons loaded: {names}")
    start, attempts, previous, feedback, tokens = time.perf_counter(), [], None, None, 0
    for n in range(1, (MAX_ATTEMPTS if repair else 1) + 1):
        fault = inject_fault and n == 1
        text, used = await asyncio.to_thread(answerer.answer, question, lessons, previous, feedback, fault)
        tokens += used
        verdict = evaluator.evaluate(question, text)
        attempts.append({"attempt": n, "answer": text, "controlled_fault": fault, **verdict})
        log(f"  [{qid}] attempt {n}{' (controlled fault)' if fault else ''}: {verdict['result']}  {text}")
        if verdict["result"] == "REVISE":
            log(f"  [{qid}]   evaluator: {verdict['explanation']}  feedback: {verdict['feedback']}")
            if store and n == 1:
                for pattern in verdict["failure_patterns"]:
                    lesson = store.record_failure(pattern, qid)
                    if lesson:
                        log(f"  [{qid}]   LESSON_CREATED {lesson['lesson_id']}: {lesson['failure_pattern']}")
        if verdict["result"] == "PASS" or not repair:
            break
        previous, feedback = text, verdict["feedback"]
    return {
        "id": qid,
        "question": question,
        "kind": info["kind"],
        "lessons_used": [x["lesson_id"] for x in lessons],
        "attempts": attempts,
        "n_attempts": len(attempts),
        "first_result": attempts[0]["result"],
        "final_result": attempts[-1]["result"],
        "final_answer": attempts[-1]["answer"],
        "latency_s": round(time.perf_counter() - start, 2),
        "tokens": tokens,
        "finished_at": now_utc(),
    }
