# HW10 Part 1: Streamlit operations dashboard (Summary, Evaluation, Trace lookup) over the HW10 logs and results
# usage (repo root): streamlit run code/hw10/dashboard.py --server.port 8620
import json
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # streamlit runs this file directly, so add the repo root
if "code" in sys.modules and not hasattr(sys.modules["code"], "__path__"):
    del sys.modules["code"]  # drop the standard library module named code so the repo package loads

from code.hw9.fixture_cache import REDIS_HOST, REDIS_PORT
from code.hw9.semantic_cache import INDEX
from code.hw10.tracing import QUEUE_STAGES, SPANS_FILE, STAGE_ORDER, stage_rank, to_dt
from code.kafka_service.settings import PORT_BASE, PREFIX, SID4, STUDENT_NAME

import altair as alt
import pandas as pd
import redis
import streamlit as st

REPORTS = ROOT / "reports" / "hw10"
EVAL_FILE = REPORTS / "eval" / "eval_results.jsonl"
VALIDATION_JSON = REPORTS / "eval" / "judge_validation.json"
VALIDATION_CSV = REPORTS / "eval" / "judge_validation.csv"
TRACE_IDS = REPORTS / "traces" / "trace_ids.json"
LATENCY_SUMMARY = REPORTS / "latency" / "latency_summary.json"
LATENCY_MISSES = REPORTS / "latency" / "latency_misses.jsonl"
WINDOWS = {"All recorded requests": None, "Last 1 hour": 1, "Last 24 hours": 24, "Last 7 days": 24 * 7}
AGENT_STAGES = ["inbox", "planner", "tasks", "writer", "drafts", "reviewer", "final", "evaluation"]


def rel(path):
    return str(Path(path).relative_to(ROOT))


def mtime(path):
    return os.path.getmtime(path) if Path(path).exists() else 0.0


@st.cache_data(show_spinner=False)
def load_jsonl(path, changed):  # changed is the file mtime, so an edited file is read again
    rows = []
    if Path(path).exists():
        for line in Path(path).read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # skip a torn line
    return rows


@st.cache_data(show_spinner=False)
def load_json(path, changed):
    return json.loads(Path(path).read_text()) if Path(path).exists() else None


@st.cache_data(show_spinner=False)
def load_csv(path, changed):
    return pd.read_csv(path) if Path(path).exists() else None


@st.cache_resource
def redis_client():  # one connection pool reused across reruns and sessions
    return redis.Redis(
        host=REDIS_HOST, port=REDIS_PORT, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
    )


def spans():
    return load_jsonl(str(SPANS_FILE), mtime(SPANS_FILE))


def pct(values, q):
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return round(statistics.quantiles(values, n=100, method="inclusive")[q - 1], 1)  # same method as Part 4.3


def span_window(rows):
    if not rows:
        return "no data"
    first = min(r["start"] for r in rows)
    last = max(r["end"] for r in rows)
    return f"{first} to {last} (UTC)"


def ms(value):
    return "n/a" if value is None else f"{value:,.1f} ms"


def summary_page():
    st.title("Summary")
    choice = st.selectbox("Time window", list(WINDOWS), index=0)
    now = datetime.now(timezone.utc)
    requests = [s for s in spans() if s.get("stage") == "request"]
    if WINDOWS[choice]:
        cutoff = now - timedelta(hours=WINDOWS[choice])
        requests = [s for s in requests if to_dt(s["start"]) >= cutoff]
        bounds = f"{cutoff:%Y-%m-%dT%H:%M:%SZ} to {now:%Y-%m-%dT%H:%M:%SZ} (UTC)"
    else:
        bounds = "every request span in the file"
    st.caption(
        f"Data source: {rel(SPANS_FILE)}, one 'request' span per question written by code/hw10/traced_qa.py. "
        f"Window: {bounds}. Requests found in it: {span_window(requests)}."
    )
    if not requests:
        st.warning("No request spans in this window. Choose 'All recorded requests' or run a traced question.")
        return
    hits = [r for r in requests if r["attrs"].get("path") == "hit"]
    misses = [r for r in requests if r["attrs"].get("path") == "miss"]
    errors = [r for r in requests if r["status"] != "ok"]
    looked_up = len(hits) + len(misses)
    c = st.columns(5)
    c[0].metric("Requests", len(requests))
    c[1].metric("Cache hits", len(hits))
    c[2].metric("Cache misses", len(misses))
    c[3].metric("Cache hit rate", f"{100 * len(hits) / looked_up:.1f}%" if looked_up else "n/a")
    c[4].metric("Error rate", f"{100 * len(errors) / len(requests):.1f}%")
    st.caption(
        "Hit rate = hits / (hits + misses). Error rate = requests with status error / all requests. "
        "Part 3 case collection sent questions straight to Kafka, so it has no request span and is not counted."
    )

    st.subheader("End-to-end latency (successful requests)")
    miss_ms = [r["duration_ms"] for r in misses if r["status"] == "ok"]
    hit_ms = [r["duration_ms"] for r in hits if r["status"] == "ok"]
    c = st.columns(4)
    c[0].metric("Cache miss p50", ms(pct(miss_ms, 50)))
    c[1].metric("Cache miss p95", ms(pct(miss_ms, 95)))
    c[2].metric("Cache hit p50", ms(pct(hit_ms, 50)))
    c[3].metric("Cache hit p95", ms(pct(hit_ms, 95)))
    st.caption(
        f"Same window and source. Request span duration, from the start of the cache lookup to the answer. "
        f"n = {len(miss_ms)} misses and {len(hit_ms)} hits; failed requests are left out of latency. "
        "p50 and p95 use linear interpolation."
    )

    table = pd.DataFrame(
        [
            {
                "path": r["attrs"].get("path"),
                "status": r["status"],
                "duration_ms": r["duration_ms"],
            }
            for r in requests
        ]
    )
    by_path = table.groupby(["path", "status"]).agg(requests=("duration_ms", "size")).reset_index()
    left, right = st.columns(2)
    left.markdown("**Requests by path and status**")
    left.dataframe(by_path, hide_index=True, width="stretch")
    right.markdown("**Failed requests**")
    failed = [
        {"trace_id": r["trace_id"], "failing_stage": r["attrs"].get("failing_stage"), "error": r["error"]}
        for r in errors
    ]
    right.dataframe(pd.DataFrame(failed or [{"trace_id": "none"}]), hide_index=True, width="stretch")

    st.subheader("Most recent requests")
    recent = sorted(requests, key=lambda r: r["start"], reverse=True)[:10]
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "start": r["start"],
                    "trace_id": r["trace_id"],
                    "path": r["attrs"].get("path"),
                    "status": r["status"],
                    "duration_ms": r["duration_ms"],
                    "question": r["attrs"].get("query"),
                }
                for r in recent
            ]
        ),
        hide_index=True,
        width="stretch",
    )

    stage_latency()
    live_cache()


def stage_latency():
    st.subheader("Stage latency of 50 confirmed cache misses (Part 4.3)")
    summary = load_json(str(LATENCY_SUMMARY), mtime(LATENCY_SUMMARY))
    if not summary:
        st.info(f"{rel(LATENCY_SUMMARY)} not found. Run: python -m code.hw10.p4_latency analyze")
        return
    ids = {r["trace_id"] for r in load_jsonl(str(LATENCY_MISSES), mtime(LATENCY_MISSES))}
    measured = [s for s in spans() if s["trace_id"] in ids and s["stage"] == "request"]
    st.caption(
        f"Data source: {rel(LATENCY_SUMMARY)} (built from {rel(SPANS_FILE)} by code/hw10/p4_latency.py). "
        f"Window: the {summary['miss_requests']} miss requests, {span_window(measured)}. "
        "% of e2e = sum of the stage over all requests / sum of end-to-end over all requests."
    )
    rows = [
        {"stage": name, "p50 ms": v["p50_ms"], "p95 ms": v["p95_ms"], "% of e2e": v.get("share_pct")}
        for name, v in summary["stages"].items()
    ]
    left, right = st.columns([3, 2])
    left.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=35 * (len(rows) + 1) + 3)
    share = pd.DataFrame([r for r in rows if r["stage"] in ["cache_lookup", *AGENT_STAGES, "other"]])
    chart = (
        alt.Chart(share)
        .mark_bar()
        .encode(x=alt.X("% of e2e:Q"), y=alt.Y("stage:N", sort=[*STAGE_ORDER, "other"]), tooltip=["stage", "% of e2e"])
    )
    right.altair_chart(chart, width="stretch")
    hits = summary.get("cache_hits") or {}
    if hits.get("request"):
        h, lk = hits["request"], hits.get("cache_lookup") or {}
        c = st.columns(4)
        c[0].metric("Part 4.3 hit request p50", ms(h["p50_ms"]))
        c[1].metric("Part 4.3 hit request p95", ms(h["p95_ms"]))
        c[2].metric("Part 4.3 hit lookup p50", ms(lk.get("p50_ms")))
        c[3].metric("Part 4.3 hit lookup p95", ms(lk.get("p95_ms")))
        st.caption(f"Cache hits kept separate from the misses above: n = {h['n']} repeat questions served from Redis.")


def live_cache():
    st.subheader("Semantic cache right now")
    try:
        info = redis_client().ft(INDEX).info()
        st.metric("Cached answers in Redis", int(info["num_docs"]))
        st.caption(f"Data source: live Redis at {REDIS_HOST}:{REDIS_PORT}, index {INDEX}, read when the page loads.")
    except Exception as exc:  # Redis stopped: the file based metrics above still work
        st.info(f"Redis not reachable ({type(exc).__name__}), so the live cache count is skipped.")


def short_question(text):
    return str(text or "").split("\n\nFixture facts")[0]  # drop the MySQL facts added for the Writer


def eval_frame(rows):
    out = []
    for r in rows:
        fvd = r.get("final_vs_draft") or {}
        out.append(
            {
                "evaluated_at": r.get("evaluated_at"),
                "trace_id": r["trace_id"],
                "status": r["status"],
                "plan_quality": r["plan_quality"]["score"],
                "writer_helpfulness": r["writer_helpfulness"]["score"],
                "final_helpfulness": r["final_helpfulness"]["score"],
                "final_minus_draft": fvd.get("difference"),
                "draft_changed": fvd.get("draft_changed"),
                "question": short_question((r.get("inputs") or {}).get("question")),
                "error": r.get("error"),
            }
        )
    return pd.DataFrame(out)


def evaluation_page():
    st.title("Evaluation")
    rows = load_jsonl(str(EVAL_FILE), mtime(EVAL_FILE))
    st.subheader("Part 2: pipeline evaluation by stage")
    if not rows:
        st.info(f"{rel(EVAL_FILE)} is empty. Start the evaluator and run a traced question.")
    else:
        latest_only = st.toggle("Latest evaluation per trace only", value=True)
        if latest_only:
            rows = list({r["trace_id"]: r for r in rows}.values())  # a later rescore replaces the earlier one
        st.caption(
            f"Data source: {rel(EVAL_FILE)}, written by code/hw10/evaluator.py (GEval, 1 to 5 scale, local judge "
            f"{rows[-1].get('judge', {}).get('judge_model', 'n/a')}). Window: evaluated "
            f"{min(r['evaluated_at'] for r in rows)} to {max(r['evaluated_at'] for r in rows)} (UTC)."
        )
        df = eval_frame(rows)
        ok = df[df["status"] == "ok"]
        c = st.columns(5)
        c[0].metric("Evaluated requests", len(df))
        c[1].metric("Planner: plan quality", f"{ok['plan_quality'].mean():.2f}" if len(ok) else "n/a")
        c[2].metric("Writer: draft helpfulness", f"{ok['writer_helpfulness'].mean():.2f}" if len(ok) else "n/a")
        c[3].metric("Reviewer: final helpfulness", f"{ok['final_helpfulness'].mean():.2f}" if len(ok) else "n/a")
        c[4].metric("Mean final minus draft", f"{ok['final_minus_draft'].mean():+.2f}" if len(ok) else "n/a")
        st.caption(f"Means over the {len(ok)} evaluations with status ok; {len(df) - len(ok)} had a judge error.")
        st.markdown("**Scores by case**")
        st.dataframe(df, hide_index=True, width="stretch")
        detail(rows)
        interpretation(ok)
    validation()


def detail(rows):
    pick = st.selectbox("Show the inputs and judge reasons for one trace", [r["trace_id"] for r in reversed(rows)])
    r = next(x for x in rows if x["trace_id"] == pick)
    inputs = r.get("inputs") or {}
    with st.expander("Plan, draft, final answer and reasons", expanded=False):
        st.markdown(f"**Question:** {short_question(inputs.get('question'))}")
        st.markdown("**Plan:**\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(inputs.get("plan") or [], 1)))
        st.markdown(f"**Draft:** {inputs.get('draft')}")
        st.markdown(f"**Final answer:** {inputs.get('final_answer')}")
        for key in ("plan_quality", "writer_helpfulness", "final_helpfulness"):
            s = r[key]
            st.markdown(f"**{key}** = {s['score']}: {s['reason'] or s['error']}")
        st.markdown(f"**Final vs draft:** {(r.get('final_vs_draft') or {}).get('interpretation')}")


def interpretation(ok):
    st.markdown("**What the scores suggest about coordination**")
    if ok.empty:
        st.write("No successful evaluations yet.")
        return
    changed = int(ok["draft_changed"].fillna(False).astype(bool).sum())
    diff = ok["final_minus_draft"].dropna()
    up, same, down = int((diff > 0).sum()), int((diff == 0).sum()), int((diff < 0).sum())
    if up > same + down:
        verdict = "The Reviewer adds value: most final answers score higher than the draft."
    elif down > up:
        verdict = "The Reviewer more often hurts than helps: final answers score lower than drafts more often."
    else:
        verdict = "The Reviewer mostly keeps the draft's quality: the final usually scores the same as the draft."
    st.write(
        f"Planner plans average {ok['plan_quality'].mean():.2f}, Writer drafts {ok['writer_helpfulness'].mean():.2f} "
        f"and Reviewer final answers {ok['final_helpfulness'].mean():.2f}. The Reviewer changed the draft text in "
        f"{changed} of {len(ok)} requests, and the judge rated the final answer higher than the draft in {up}, the "
        f"same in {same} and lower in {down}. {verdict} These are judge scores: Part 3 below shows how far they "
        "agree with human labels, so read them as a screening signal, not proof of quality."
    )


def validation():
    st.subheader("Part 3: judge validation against human labels")
    summary = load_json(str(VALIDATION_JSON), mtime(VALIDATION_JSON))
    cases = load_csv(str(VALIDATION_CSV), mtime(VALIDATION_CSV))
    if not summary or cases is None:
        st.info(f"{rel(VALIDATION_JSON)} not found. Run: python -m code.hw10.p3_judge report")
        return
    st.caption(
        f"Data source: {rel(VALIDATION_JSON)} and {rel(VALIDATION_CSV)} from code/hw10/p3_judge.py. "
        f"{summary['cases']} frozen Writer drafts (sha256 {summary['cases_sha256'][:12]}), judged {summary['runs']} "
        f"times at temperature {summary['judge'].get('temperature')}, seed {summary['judge'].get('seed')}, "
        f"created {summary['created_at']} (UTC)."
    )
    med, rep = summary["agreement_median"], summary["repeatability"]
    c = st.columns(4)
    c[0].metric("Spearman (median of runs)", med["spearman"])
    c[1].metric("Mean absolute difference", med["mean_abs_diff"])
    c[2].metric("Exact agreement", f"{100 * med['exact_agreement']:.0f}%")
    c[3].metric("Within 1 point", f"{100 * med['within_1_agreement']:.0f}%")
    c = st.columns(3)
    c[0].metric("Cases whose score changed across runs", f"{rep['cases_with_any_change']} of {summary['cases']}")
    c[1].metric("Mean change", rep["mean_change"])
    c[2].metric("Max change", rep["max_change"])
    by_run = pd.DataFrame([{"run": k, **v} for k, v in summary["agreement_by_run"].items()])
    st.markdown("**Agreement by run**")
    st.dataframe(by_run, hide_index=True, width="stretch")
    st.markdown("**Raw per-case data**")
    st.dataframe(cases, hide_index=True, width="stretch")


def kind(stage):
    if stage == "request":
        return "whole request"
    return "queue wait" if stage in QUEUE_STAGES else "work"


def path_banner(by_stage):
    req, lookup = by_stage.get("request"), by_stage.get("cache_lookup")
    info = (lookup or {}).get("attrs", {})
    path = (req or {}).get("attrs", {}).get("path") or info.get("result")
    sim = f"similarity {info.get('similarity')} vs threshold {info.get('threshold')}"
    if req and req["status"] != "ok":
        stage = req["attrs"].get("failing_stage")
        st.error(f"FAILED request on the cache-miss path. Failing stage: {stage}. Error: {req['error']}")
    elif path == "hit":
        st.success(f"CACHE HIT path: answered from the Redis semantic cache ({sim}). Kafka agents were skipped.")
        st.caption(f"Matched cached question: {info.get('matched_query')}")
    elif path == "miss":
        st.info(f"CACHE MISS path: no cached answer close enough ({sim}), so the question went through Kafka.")
    else:
        st.warning(
            "No request span: this trace was sent straight to Kafka (Part 3 case collection), so no cache lookup."
        )
    return path


def trace_page():
    st.title("Trace lookup")
    saved = load_json(str(TRACE_IDS), mtime(TRACE_IDS)) or {}
    options = ["type a trace_id below"] + [f"{label}: {v['trace_id']}" for label, v in saved.items()]

    def use_saved():
        if ": " in st.session_state.saved_pick:
            st.session_state.trace_input = st.session_state.saved_pick.split(": ", 1)[1]

    st.selectbox(f"Saved traces from Part 4.2 ({rel(TRACE_IDS)})", options, key="saved_pick", on_change=use_saved)
    tid = st.text_input("trace_id (the HW8 correlation_id)", key="trace_input").strip()
    if not tid:
        st.caption(f"Data source: {rel(SPANS_FILE)}. Pick a saved trace or paste a trace_id.")
        return
    found = sorted([s for s in spans() if s.get("trace_id") == tid], key=lambda s: (stage_rank(s["stage"]), s["start"]))
    if not found:
        st.error(f"No spans for {tid} in {rel(SPANS_FILE)}.")
        return
    by_stage = {s["stage"]: s for s in found}
    path = path_banner(by_stage)
    st.caption(f"Data source: {rel(SPANS_FILE)}. {len(found)} spans, {span_window(found)}.")
    table = pd.DataFrame(
        [
            {
                "order": stage_rank(s["stage"]),
                "stage": s["stage"],
                "kind": kind(s["stage"]),
                "service": s.get("service"),
                "start": s["start"],
                "end": s["end"],
                "duration_ms": s["duration_ms"],
                "status": s["status"],
                "error": s.get("error") or "",
            }
            for s in found
        ]
    )
    styled = table.style.format({"duration_ms": "{:,.1f}"}).apply(
        lambda row: ["background-color: rgba(228, 87, 86, 0.35)" if row["status"] != "ok" else "" for _ in row], axis=1
    )
    st.dataframe(styled, hide_index=True, width="stretch")
    expected = {"hit": ["request", "cache_lookup"], "miss": ["request", "cache_lookup", *AGENT_STAGES]}.get(path, [])
    missing = [s for s in expected if s not in by_stage]
    if path == "hit":
        st.caption("Agent stages (inbox to evaluation) are not expected on a cache hit.")
    elif missing:
        st.warning(f"Stages not reached: {', '.join(missing)}")
    if "request" in by_stage:
        parts = sum(s["duration_ms"] for s in found if s["stage"] != "request")
        st.caption(f"Request {by_stage['request']['duration_ms']:,.1f} ms; sum of the stage spans {parts:,.1f} ms.")
    timeline = table[table["stage"] != "request"].assign(start=lambda d: pd.to_datetime(d["start"]))
    timeline = timeline.assign(end=pd.to_datetime(timeline["end"]))
    chart = (
        alt.Chart(timeline)
        .mark_bar()
        .encode(
            x=alt.X("start:T", title="time (UTC)"),
            x2="end:T",
            y=alt.Y("stage:N", sort=STAGE_ORDER),
            color=alt.Color("status:N", scale=alt.Scale(domain=["ok", "error"], range=["#4c78a8", "#e45756"])),
            tooltip=["stage", "start", "end", "duration_ms", "status", "error"],
        )
    )
    st.altair_chart(chart, width="stretch")


st.set_page_config(page_title=f"{PREFIX} HW10 dashboard", layout="wide")
st.sidebar.markdown(f"**{STUDENT_NAME}**  \nSID4 {SID4}, prefix {PREFIX}, port {PORT_BASE + 1}")
st.sidebar.caption("Domain 7: community sports league fixtures. Reads the HW10 files under reports/hw10.")
if st.sidebar.button("Reload data"):
    st.cache_data.clear()  # read the files again; the Redis connection stays cached
nav = st.navigation(
    [
        st.Page(summary_page, title="Summary", default=True),
        st.Page(evaluation_page, title="Evaluation"),
        st.Page(trace_page, title="Trace lookup"),
    ]
)
nav.run()
