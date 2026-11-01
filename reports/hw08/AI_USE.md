# HW8 AI Use

## 1. What I used AI for and what I did myself
I used an AI assistant as a helper for this homework. I wrote first drafts of the Kafka worker, the FastAPI wrapper,
the three agents, the Part 3 test scripts and the verify script. I did the setup myself:
Docker and the Kafka container, the conda environment, Ollama and the topics. I ran every command on my own laptop,
started and killed the agents for the failure tests, took every screenshot, made all the commits and checked the
numbers in METRICS.md against the logs and the raw files.

## 2. One AI output that was wrong
For the consumer death test the AI told me to start the buggy Writer with a 25 second slow step and kill it during
that step. The window was too short to do by hand. The Planner took about 25 seconds first, and by the time I ran
kill -9 the slow step was already over and the Writer had called the LLM and finished. So that "before" run did
not show a lost message at all.

I also checked one result myself. My first keyed ordering run showed 4/4 in order, but the writers column said only
WRITER-A. Writer B had stopped, so one Writer read both partitions and the run did not test two consumers.

## 3. How I found it
After the kill I ran inspect_state.py and read_topic.py for that correlation_id. The Writer row had a finished time
and s3319_drafts had 1 draft, which means the task completed and nothing was lost. For the ordering run, I read the
summary table instead of only the 4/4 lines, and the Writer A terminal showed PARTITIONS_ASSIGNED [0,1].

## 4. What I changed and why it works now
I reran the test with --work-seconds 60 and killed the Writer as soon as WORKING_SLOW_STEP appeared, using pgrep so I
did not have to type the pid. This time the offset was already committed, the lag was 0, the restarted Writer got
nothing, the Writer never finished and there were 0 drafts, so the loss is real. The after run used the same 60 second
step and the task was redelivered and completed. For ordering, I started Writer B again, waited until each Writer had
one partition and reran the keyed test: 4/4 in one partition and 4/4 in order, with FX-13355 on Writer B and the other
three on Writer A.
