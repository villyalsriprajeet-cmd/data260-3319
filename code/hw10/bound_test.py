# HW10 Part 2.1: show the evaluator is bounded (malformed messages, judge down, judge that never answers)
# usage (repo root): python -m code.hw10.bound_test malformed
#                    python -m code.hw10.bound_test judge-down --cid ID
#                    python -m code.hw10.bound_test judge-hang --cid ID
import argparse
import asyncio
import socket
import threading
import time
from code.hw10.evaluator import evaluate_one
from code.hw10.judge import LocalJudge
from code.kafka_agents import common as k
from code.kafka_service.settings import banner

HANG_TIMEOUT = 5.0  # seconds per judge call in the hang test


async def send_malformed():
    producer = await k.make_producer()
    for value in (b"this is not json", b'{"status": "approved", "answer": "no correlation_id here"}'):
        meta = await producer.send_and_wait(k.FINAL, value)
        print(f"sent to {meta.topic} offset {meta.offset}: {value.decode()}")
    await producer.stop()
    print("check the evaluator terminal: two MALFORMED_SKIPPED lines, and it keeps running")


def silent_judge():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    held = []

    def accept_forever():
        while True:
            conn, _ = server.accept()
            held.append(conn)  # accept the call, never answer

    threading.Thread(target=accept_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.getsockname()[1]}"


async def judge_test(cid, url, timeout):
    print(f"judge at {url}, {timeout} s per call")
    t0 = time.perf_counter()
    result = await evaluate_one(cid, LocalJudge(base_url=url, timeout=timeout))
    if result:
        print(f"\nfinished in {time.perf_counter() - t0:.2f} s with status={result['status']} (no hang)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["malformed", "judge-down", "judge-hang"])
    parser.add_argument("--cid", help="a correlation_id that already has a plan, draft and final")
    args = parser.parse_args()
    banner(f"HW10 Part 2.1 bounded evaluator test: {args.mode}")
    if args.mode == "malformed":
        asyncio.run(send_malformed())
    elif args.mode == "judge-down":
        asyncio.run(judge_test(args.cid, "http://127.0.0.1:9", 120.0))  # nothing listens on port 9
    else:
        asyncio.run(judge_test(args.cid, silent_judge(), HANG_TIMEOUT))
