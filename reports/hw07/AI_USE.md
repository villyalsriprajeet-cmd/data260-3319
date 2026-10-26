# HW7 AI Use

## 1. What I used AI for and what I did myself
I used an AI assistant as a helper for this homework. I wrote first drafts of the code and explained each
step. Did the setup myself: the MySQL migration, the passwords, Ollama and the conda environment. I ran every command
on my own laptop, did the lint demo and all the commits, took every screenshot and checked the results against the raw
files. Every number in the report comes from my own runs.

## 2. One AI output that was wrong
In Part 4 the bike-share agent gave a wrong answer. For the pay-per-use scenario it recommended "Buy Monthly Membership"
even though its own tool results said pay per ride was cheaper. An earlier run also wrote a
justification that called the $1 unlock fee "a 30-Day Membership for $1.00".

## 3. How I found it
The results page compares the agent's decision with the costs worked out by the tools, and it showed "differs from the
verified cost comparison". I then read the cost table and the timeline myself. The agent had made only two tool calls,
had not used the calculator for the totals, and the numbers in its text did not match any tool output.

## 4. What I changed and why it works now
I added a final decide step. After all the tool calls, the model sees every tool result before it decides. Every number in the justification must come from a tool
result, otherwise a template built from the checked numbers is shown instead. I reran both scenarios with the same code:
membership wins for the commuters and pay per ride wins for the occasional riders, and both match the cost comparison.

I also checked one of my own tests. In Part 2 the first task-B check rejected a correct answer because the model
paraphrased the fixture title. I changed the check to accept both team names from a fixture the search really returned,
and it still rejects made up fixtures.
