HW8 - Metrics

Domain 7 - Community sports league fixtures. SID4 3319, PORT_BASE 8619, PREFIX s3319, SEED 3319, VERIFY_SEED 263319, DOMAIN_ID 7. Everything ran on my MacBook Pro (Apple M2, 8 GB RAM, macOS) with Kafka 3.9.2 in Docker (one KRaft broker), aiokafka 0.12.0 and qwen2.5:3b through Ollama at temperature 0.

Part 1 - Request and response over Kafka

These come from code/homework_demo.py, run through FastAPI on port 8619.

    Check                                  Result
    CREATE_FIXTURE then GET_FIXTURE        round trip passed, same data back
    correlation_id kept end to end         yes, in both replies
    stages seen in the logs (each call)    10/10
    error cases with a clean reply         5/5 (unknown operation, missing venue, bad fixture_code, empty title, unknown fixture_id)

The API and the worker run in Docker and the demo client runs on the Mac, so some lines are a few ms apart across the two clocks. I sort ties by stage so the order in the sequence log is the real one.

Part 2 - Planner, Writer and Reviewer over Kafka

One question, correlation_id 3f2c3d1e-5ee8-4618-82f3-30596106ff1f, through s3319_inbox, s3319_tasks (2 partitions), s3319_drafts and s3319_final.

    Agent       Time      Tokens    Output
    Planner     22.2 s    217       3 step plan
    Writer      18.2 s    303       68 word draft
    Reviewer    16.4 s    421       approved, both checks true
    Total       60.7 s from QUESTION_SENT to FINAL_RECEIVED

Every agent commits its offset only after it has sent its output, and the same correlation_id shows up in all 14 lines of the journey.

Part 3 - Failure table

    Failure              Before the fix                                   After the fix
    Duplicate delivery   replay at tasks p1 offset 1, Writer called       replay at offset 2, Writer logged DUPLICATE_SKIPPED
                         the LLM again (303 tokens, 27.6 s), drafts       in 42 ms, no LLM call, drafts stayed at 2, final
                         went from 1 to 2                                 stayed at 1, lag 0
    Consumer killed      offset committed on receipt, kill -9 during      no commit before the work, kill -9 left lag 1, the
                         the work, lag 0, restart got nothing, Writer     restarted Writer got the same offset, logged
                         finished NEVER, 0 drafts (1 of 1 lost)           REDELIVERED and finished in 17.6 s (0 of 1 lost)
    Poison message       18 attempts in 64 s with no end, partition 0     3 attempts in 3.0 s (backoff 1 s, 2 s), moved to
                         lag 2, the good task behind it never ran         s3319_dead_letter, good task picked up 0.04 s later
    Ordering             no key: 0/4 fixtures in one partition,           key = fixture_code: 4/4 in one partition, 4/4 in
                         2/4 in order (FX-13355 and FX-30687 ran          order, Writer A took p0 (15 messages) and Writer B
                         as 1, 2, 4, 3, 5)                                took p1 (5 messages) in parallel

Run settings for the before runs: --no-idempotency, --commit-mode before, --no-dlq, and no key in ordering_test.py. The after runs use the default Writer. The ordering test uses 20 messages (4 fixtures x 5 updates) built from VERIFY_SEED 263319, two partitions and two Writers in the same group.

Fixes in short:
1. Idempotency: a SQLite store keeps the correlation_ids each agent finished. A replay is skipped but its offset is still committed.
2. Commit after processing: the offset is committed only after the output is sent, so a crash means a redelivery and not a loss.
3. Bounded retries: 3 attempts, then the message and its error go to s3319_dead_letter and the partition moves on.
4. Keys: related updates share the fixture_code key, so they land in one partition and one Writer reads them in order.

The dead letter entry has correlation_id null because the poison is not valid JSON. The key poison-demo and the source partition and offset (0, 2) identify it.

Comparison with HW2

In HW2 the Planner and Reviewer were nodes in one LangGraph StateGraph. A supervisor routed between them, the state was a dict in memory, and a turn ceiling stopped the loop. Moving the agents onto Kafka changed this.

Benefits:
1. Work survives a crash. Each handoff is a stored message with an offset, so when the Writer was killed in 3.2 the task was still in s3319_tasks and the next Writer finished it. In HW2 a crash lost the whole run because the state only lived in memory.
2. Agents scale and run on their own. With two partitions I ran two Writers in one group and they shared the work in parallel (3.4). Each agent is its own process, it can be restarted without stopping the others, and the topic plus correlation_id give a full trace of every hop.

New responsibilities:
1. Delivery rules are now my job. Kafka gives at least once delivery, so I had to add the idempotency store and commit only after processing (3.1 and 3.2). In HW2 a node ran once per call and none of this was needed.
2. Bad messages and order have to be handled on purpose. A poison message blocks its partition unless retries are bounded and there is a dead letter topic (3.3), and order is kept only inside one partition, so related messages need the same key (3.4). I also have to run the broker, create topics with the right partitions and watch consumer lag.

Notes

The Writer logs sometimes show "Heartbeat failed" or "coordinator dead" lines from aiokafka. They appeared right after a Writer was killed or a second Writer joined, while the group was rebalancing. No message was lost or repeated because of them. Raw files are in reports/hw08/raw/ and the logs and journeys are in reports/hw08/logs/.
