data260-3319

DATA-260 homework 1

HW1 - Community Sports League Fixtures

A small web app for submitting football league fixtures (match title, venue, submitter email, match details, status, and terms agreement). Built with plain HTML, CSS, and JavaScript, then packaged with Docker and deployed to AWS ECS. The repo also has the Part 2 agents, the Part 3 non-determinism experiment, and the Part 4 token-accounting client.

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