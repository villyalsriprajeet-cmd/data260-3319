data260-3319

DATA-260 homework 1

HW1 - Community Sports League Fixtures

A small web app for submitting football league fixtures (match title, venue, submitter email, match details, status, and terms agreement). Built with plain HTML, CSS, and JavaScript, then packaged with Docker and deployed to AWS ECS. The repo also has the Part 2 agents, the Part 3 non determinism experiment, and the Part 4 token accounting client.

Configuration

- SID4: 3319
- PORT_BASE: 8619
- PREFIX: s3319
- DOMAIN_ID: 7 (Community sports league fixtures)

Files

- code/web_application/ - the Part 1 web app (index.html, style.css, script.js)
- code/agents_demo.py - the Part 2 agents (Planner, Reviewer, Finalizer)
- code/nondeterminism_run.py - the Part 3 experiment that runs the pipeline 40 times
- code/hw1_client.py - the Part 4 token-accounting demo
- code/verify_hw01.py - a small self-check script
- code/Dockerfile - builds the container image
- src/model_client.py - the reusable model adapter all model calls go through
- reports/hw01/ - the report, METRICS.md, RUN_LOG.txt, AI_USE.md, verification.json, DOMAIN_SCHEMA.md, cases/, and raw/
- AGENT.md - the system prompt for the code-review agent

Setup

Create the environment and install what's needed:

    conda create -n data260 python=3.12 -y
    conda activate data260
    pip install langchain langchain-core langchain-ollama

Install Ollama, start it, and pull the model:

    ollama serve
    ollama pull qwen2.5:3b

Note: the assignment suggested qwen3:8b, but my laptop (8 GB, CPU only) couldn't run an 8B model, so I used the smaller qwen2.5:3b, which the assignment allows.

How to run

Part 1 - the web app (build and run with Docker, then open http://localhost:8619):

    cd code
    docker build -t fixtures-app .
    docker run -p 8619:80 fixtures-app

Part 2 - the agents:

    python code/agents_demo.py

Part 3 - the non-determinism experiment (runs 40 times, takes a while):

    python code/nondeterminism_run.py

Part 4 - the token-accounting demo:

    python code/hw1_client.py --demo

Self-check:

    python code/verify_hw01.py

For all the Python parts, make sure the data260 environment is active and Ollama is running with qwen2.5:3b pulled.

Part 4 - short answers

Why is the conversation context resent every turn?
The model doesn't remember anything between calls, so it only sees what I send in that one request. I send the whole history each time so it knows what was already said.

How is a system prompt different from a user message?
The system prompt sets the rules for the whole conversation and stays at the top the entire time. A user message is just one request. One decides how the model behaves overall, the other is what it's answering that turn.

Why do input tokens grow over a conversation?
Because the full history gets resent each turn, every new turn includes everything before it plus the new message. In my run the input tokens went 106, 171, 211, 271, 312.

What eventually limits that growth?
The model's context window - the most tokens it can take at once. Once the history gets close to that, older turns have to be trimmed or summarized, otherwise it gets cut off.
HW6 - MongoDB, chat memory, memory cost and file memory

This extends the same repo. Same configuration as above (SID4 3319, PORT_BASE 8619, PREFIX s3319, SEED 3319, VERIFY_SEED 263319, DOMAIN_ID 7). Model: qwen2.5:3b through Ollama. MongoDB 7.0 runs in Docker (container s3319_mongo, database s3319_doc).

Files

- code/api/ - MongoDB fixtures CRUD (/api/fixtures) and the chat with memory (POST /api/chat, GET /api/memory/{user_id}, GET /api/aggregate/{user_id})
- code/hw6_chat_demo.py - the scripted chat demo
- code/hw6_sweep.py - the Part 3 sweep (N=4, 12, 30 and the eviction policy)
- code/file_memory.py - loads AGENT.md and MEMORY.md, builds the system prompt, checks and runs consolidation
- code/hw6_memory_cli.py - the /memory, /compact, /dream and /help commands
- code/check_agent_rules.py - checks code against the rules in AGENT.md
- code/verify_hw06.py - the self-check script (make verify-hw06)
- AGENT.md, MEMORY.md, MEMORY_CONSOLIDATION_LOG.md - durable instructions, durable facts, and the consolidation audit
- reports/hw06/ - report.pdf, METRICS.md, RUN_LOG.txt, AI_USE.md, verification.json, memory_probes.yaml, and raw/

How to run

Start MongoDB and Ollama, then the backend:

    docker start s3319_mongo
    ollama serve
    python -m uvicorn code.api.main:app --port 8619

Part 3 - the memory sweep (takes a while):

    python -m code.hw6_sweep

Part 4 - the file memory chat and its demo:

    python -m code.hw6_memory_cli
    python -m code.hw6_memory_cli --demo

Self-check:

    make verify-hw06

Make sure the data260 environment is active, Docker is running, and Ollama has qwen2.5:3b pulled.
HW7 - JWT roles, agent loop, Reflexion, bike-share ReAct agent, prompt injection, file tools

Same configuration (SID4 3319, PORT_BASE 8619, PREFIX s3319, SEED 3319, VERIFY_SEED 263319, DOMAIN_ID 7). Model qwen2.5:3b through Ollama, MySQL s3319_rel.

Files

- code/api/ - JWT login (POST /auth/login, GET /auth/me), reader/writer/moderator roles on /fixtures and /teams, the bike-share page (GET /bikeshare)
- code/api/sql/004_hw07_jwt_roles.sql and code/api/seed_hw07_users.py - username and role columns, three role accounts with hashed passwords
- pyproject.toml, .pre-commit-config.yaml - Ruff and the pre-commit hook
- code/hw7_agent.py, code/hw7_tasks.py, code/hw7_reliability.py - Part 2 agent loop, tasks A/B/C/ERR, 21-attempt reliability run
- code/hw7_reflexion.py, code/hw7_reflexion_selftest.py - Part 3 bounded Reflexion and its offline self-test
- code/bikeshare/ - Part 4 tools (csv_sql, policy_retriever, calculator), LangGraph agent, data prep, Part 5 injection_eval
- code/hw7_file_tools.py, code/hw7_part6_test.py - Part 6 file tools, SAFE_PREFIXES, confirm_bash, is_destructive
- code/verify_hw07.py - self-check (make verify-hw07)
- reports/hw07/ - report, METRICS.md, RUN_LOG.txt, AI_USE.md, THREAT_MODEL.md, verification.json, cases/ and raw/

How to run

    mysql -u root -p < code/api/sql/004_hw07_jwt_roles.sql      # once
    python -m code.api.seed_hw07_users
    python -m uvicorn code.api.main:app --port 8619
    bash code/hw7_auth_demo.sh all                                # Part 1
    python code/hw7_agent.py A                                    # Part 2 (also B, C, ERR)
    python code/hw7_reliability.py
    python code/hw7_reflexion.py compare                          # Part 3
    python -m code.bikeshare.prepare_data                         # Part 4 data, then open http://localhost:8619/bikeshare
    python -m code.bikeshare.injection_eval all all               # Part 5
    python code/hw7_part6_test.py                                 # Part 6
    make verify-hw07

code/api/.env needs DATABASE_URL, JWT_SECRET, JWT_EXPIRE_MINUTES and READER_PASSWORD / WRITER_PASSWORD / MODERATOR_PASSWORD.

HW8 - Kafka request/response service, three agents over Kafka, failure tests

Same configuration (SID4 3319, PORT_BASE 8619, PREFIX s3319, SEED 3319, VERIFY_SEED 263319, DOMAIN_ID 7). Kafka 3.9.2 in Docker (one KRaft broker), aiokafka 0.12.0, qwen2.5:3b through Ollama.

Files

- docker-compose.yml - Kafka, the fixture worker and the FastAPI service (port 8619)
- code/kafka_service/ - Part 1 settings, fixture_store (CREATE_FIXTURE / GET_FIXTURE), worker.py, kafka_rpc.py, api.py, Dockerfile
- code/homework_demo.py - Part 1 demo, CREATE then GET through FastAPI and Kafka with the full log sequence
- code/kafka_agents/ - Part 2 planner.py, writer.py, reviewer.py, send_question.py, journey.py, shared common.py and runtime.py
- code/kafka_agents/ - Part 3 replay_message.py, send_poison.py, ordering_test.py, read_topic.py, inspect_state.py
- code/verify_hw08.py - self-check (make verify-hw08)
- reports/hw08/ - report, METRICS.md, RUN_LOG.txt, AI_USE.md, verification.json and raw/

Topics: s3319_fixture_requests, s3319_fixture_responses (Part 1), s3319_inbox, s3319_tasks (2 partitions), s3319_drafts, s3319_final (Part 2), s3319_dead_letter (Part 3).

How to run

    pip install -r code/api/requirements.txt                      # includes aiokafka==0.12.0
    docker compose up -d --build                                  # Kafka, worker, API; creates the Part 1 topics
    python code/homework_demo.py                                  # Part 1
    for t in inbox:1 tasks:2 drafts:1 final:1 dead_letter:1; do docker exec s3319_kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --if-not-exists --topic s3319_${t%%:*} --partitions ${t##*:} --replication-factor 1; done
    cd code/kafka_agents
    python planner.py                                             # Part 2, one terminal each
    python writer.py
    python reviewer.py
    python send_question.py
    python journey.py CORRELATION_ID
    python replay_message.py --cid CORRELATION_ID                 # Part 3 duplicate (writer.py --no-idempotency for before)
    python writer.py --commit-mode before --work-seconds 60       # Part 3 consumer death, kill -9 during the slow step
    python send_poison.py                                         # Part 3 poison (writer.py --no-dlq for before)
    python writer.py --instance A                                 # Part 3 ordering, with writer.py --instance B
    python ordering_test.py nokey
    python ordering_test.py keyed
    cd ../..
    make verify-hw08

The idempotency store is code/kafka_agents/state/agents_state.db and the agent log is reports/hw08/logs/agents.log; both stay out of git.

HW9 - Redis view counter, semantic cache, threshold economics, self-improving agents

Same configuration (SID4 3319, PORT_BASE 8619, PREFIX s3319, SEED 3319, VERIFY_SEED 263319, DOMAIN_ID 7). Redis Stack 7.4.0-v8 in Docker (s3319_redis, vector search), MySQL s3319_rel, Kafka 3.9.2 and the HW8 agents, qwen2.5:3b through Ollama, all-MiniLM-L6-v2 embeddings. Every Redis key starts with s3319:.

Files

- docker-compose.yml - adds the redis service (s3319_redis, port 6379)
- code/api/sql/005_hw09_views.sql - fixtures.views column
- code/hw9/check_setup.py - Step 0 check of Redis, MySQL, Ollama, Kafka and the embedder
- code/hw9/fixture_cache.py, p1_counter_test.py - Part 1 increment_fixture_views (INCR, MySQL sync every 10 views)
- code/hw9/semantic_cache.py, qa_service.py, p2_run.py - Part 2 semantic cache (Redis vector index s3319:idx:qa, cosine) in front of the HW8 Planner, Writer and Reviewer
- reports/hw09/cache_cases.yaml, code/hw9/p3_cases.py - Part 3.1 labeled cases (committed before the sweep)
- code/hw9/p3_sweep.py, p3_analysis.py, p3_stale.py - Part 3.2 to 3.5 sweep, false hit, cost model, stale answer and data-version invalidation
- code/hw9/p4_agents.py, p4_run.py - Part 4 Answering Agent, Evaluator Agent, lessons, validation and the four variants
- reports/hw09/part4/ - reference_fixtures.json, training_data.json, validation_data.json, test_data.json, lessons.json, lessons_candidates.json, validation_report.json, results_test.json and runs/
- code/verify_hw09.py - self-check (make verify-hw09), code/hw9/build_run_log.py builds RUN_LOG.txt, code/hw9/restore_cache.py puts the 10 saved seed answers back into Redis
- reports/hw09/ - report, METRICS.md, RUN_LOG.txt, AI_USE.md, verification.json and raw/

How to run

    docker compose up -d                                          # Redis Stack, Kafka, worker, API
    mysql -u root -p < code/api/sql/005_hw09_views.sql            # once
    python -m code.hw9.check_setup
    python -m code.hw9.p1_counter_test                            # Part 1
    cd code/kafka_agents && python planner.py                     # Parts 2 and 3: one terminal each
    python writer.py
    python reviewer.py
    cd ../..
    python -m code.hw9.p2_run --probe                             # Part 2, similarities only
    python -m code.hw9.p2_run --reset                             # Part 2, 12 queries through the cache and agents
    python -m code.hw9.p3_cases                                   # Part 3.1
    python -m code.hw9.p3_sweep seed                              # Part 3.2
    python -m code.hw9.p3_sweep sweep
    python -m code.hw9.p3_analysis false-hit --case D01           # Part 3.3
    python -m code.hw9.p3_analysis cost --miss-cost 1 --false-hit-cost 20   # Part 3.4
    python -m code.hw9.p3_stale                                   # Part 3.5
    python -m code.hw9.p4_run reference                           # Part 4 (no Kafka needed)
    python -m code.hw9.p4_run demo-repair
    python -m code.hw9.p4_run train
    python -m code.hw9.p4_run validate
    python -m code.hw9.p4_run test
    python -m code.hw9.restore_cache                              # only if Redis lost the cache
    make verify-hw09
    python -m code.hw9.build_run_log

Add -W ignore::FutureWarning to hide one huggingface warning.
