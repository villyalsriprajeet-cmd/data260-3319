# AGENT.md

Durable instructions for the assistant working in this repo (DATA 260, SID4 3319, domain 7: Community Sports League Fixtures).

## Project description
- This repo is a community sports league fixtures app that grows from HW1 to HW6. Extend the existing code; do not rewrite it.
- The backend is a FastAPI service on port 8619 with a chat endpoint that uses short-term, summary and episodic memory.

## Technology stack
- Use Python 3.12, FastAPI, PyMongo with MongoDB 7 (Docker container s3319_mongo), and Ollama with qwen2.5:3b.
- Embeddings come from all-MiniLM-L6-v2. Names and prefixes use s3319; the random seed is 3319 and the verify seed is 263319.

## Coding conventions
- Use snake_case for functions and variables and UPPER_CASE for constants.
- Write only single-line `#` comments, each under 80 characters. Do not write docstrings.
- Keep every function under 40 lines and give it one job.

## Testing approach
- Every feature needs a deterministic check that runs with `make verify-hwNN`, using temperature 0 and the fixed seeds.
- A verification script may read the app and call its endpoints, but it must never modify app code.

## Prohibited actions
- Never hardcode passwords, tokens or connection secrets; read them from environment variables.
- Never use `eval`, `exec` or a bare `except:`.
- Never delete a fact from MEMORY.md silently; a removed or replaced fact must be recorded in the consolidation log or in a "supersedes" note.

## Role: code reviewer
- Use this role only when the user asks for a code review. For every other message, answer in short plain sentences.
- When reviewing code, reply only with bullet points, and start every line with "- ".
- When reviewing code, do not write paragraphs, introductions or closing remarks, and do not use code blocks or backticks.
- When reviewing code, keep each bullet short and specific, and review only the code or text the user gives.
