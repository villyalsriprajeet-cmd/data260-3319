# HW9 AI Use

## 1. What I used AI for and what I did myself
I used an AI assistant as a helper for this homework. I drafted the Redis view counter, the semantic cache and the
Q&A service, the threshold sweep and cost scripts, the stale answer demo, the Part 4 agents and runner, and the
verify script. I also suggested the 40 labeled cache cases and the Part 4 questions. I did the setup myself: the
Redis Stack container, the MySQL migration, Ollama, Kafka and the three HW8 agents. I ran every command on my own
laptop, chose which runs to keep, took every screenshot, made all the commits, and checked the numbers in METRICS.md
against the terminal output and the raw files.

## 2. One AI output that was wrong
The first Evaluator Agent graded answers wrongly in two directions. In my first Part 4 training run it marked TR04,
"FX-01002 is sold out as the tickets_available value is 0", as REVISE, although the answer is correct. It also
marked TR16, "Fixture FX-01114 has 37 more tickets than fixture FX-01115", as PASS, although FX-01114 has 136 and
FX-01115 has 173, so it has 37 fewer. On top of that, the first question set was too easy for qwen2.5:3b (15 of 16
right on the first try), so no failure repeated and no lesson could form.

## 3. How I found it
I read every answer in the training output next to the reference values printed by the reference export instead of
only looking at the PASS count. The sold out check had read the field name tickets_available as "tickets available",
which it treats as "not sold out", and the difference check only compared the number, not the direction. While
testing the fix we also found that the fixture codes were sorted, so "A minus B" could become "B minus A". Later, the
retrained run showed TR08 and TR12 repeating the same wrong answer after feedback, because the feedback was too
general for a model at temperature 0.

## 4. What I changed and why it works now
The evaluator now removes the field name before checking sold-out wording, checks both the number and the direction
of a difference (and which fixture the sentence is about), and keeps the fixture codes in question order. I re-graded
my real v1 answers with it: TR04 now passes, TR16 is caught, and the other answers kept their grades. The feedback
for a difference now names the exact mistake ("Your answer says FX-01114 has more tickets, but in the records it has
fewer") without giving the number, and after that TR08 and TR12 were fixed on the second attempt. I changed the
training, validation and test questions to harder kinds before validation or test had ever been run, so no test
result was used to change the system. Two of these bugs are now regression checks in make verify-hw09.
