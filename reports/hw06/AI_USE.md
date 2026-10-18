# HW6 AI Use

## 1. What I used AI for and what I did myself
I used AI as an assistant for this homework. It wrote the first drafts of the Mongo routes, the chat memory, the sweep script, the file memory module and the report text, and it walked me through each step. I set up MongoDB, Ollama and the environment on my laptop, ran every command myself, took all the screenshots, and checked the results against Compass and the raw files. Every number in the report comes from my own runs.

## 2. One AI output that was wrong
The first fact-e\ xtraction prompt for the memory did not work well with qwen2.5:3b. In my first N=4 run it found nothing in four of the six messages that plant a fact, and the session summary was cut off, so the Sunday 2 PM change was lost. The score for that run was 4.2, and the next game question got 1 out of 5.

## 3. How I found it
The score looked too low, so I printed the stored facts and summaries for that run. The planted messages had empty results and one summary stopped in the middle of a bullet. I kept the files from that first run so the difference can be seen.

## 4. What I changed and why it works now
I added three short examples to the extraction prompt, made the summaries stricter and longer, and added a warm up call before timing. A separate check then found all six planted facts and nothing in the filler messages. I reran all four settings and used the new results.

In Part 4 the same checking found more. The AGENT.md checker failed 2 of 20 checks because of long comments, and I shortened them. The first /dream runs saved an invented key and a question as a fact, so I added key hints, a rule that values must come from the user's own words, and a rule that questions are skipped. The consolidation also resolved the home venue contradiction the wrong way, which I describe in Part 4 of the report instead of hiding it.
