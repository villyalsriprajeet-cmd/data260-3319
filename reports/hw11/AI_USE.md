# HW11 AI Use

## 1. What I used AI for and what I did myself
I used an AI assistant as a helper: i read the assignment and the kit, drafted
the two watch.py patches (per-ticker volatility command, Yahoo and data.sec.gov sources), the golden-set generator,
the verify script and the Muse prompts, and explained errors. I chose the watchlist and agreed the threshold rule
(about 2.5 x each stock's typical daily move) after looking at the vol data. Then drafted the fictional
fixtures and the 12 labels; I checked each case against policy.md and committed them before any agent run (c482760). I ran
everything on Muse myself (install, live run, schedule, both fixture runs, the restart in a new chat, the injection
and duplicate tests), took every screenshot, made all commits, and checked the numbers in METRICS.md against the Muse
outputs and the saved state.

## 2. One AI output that was wrong
The assistant's first Part 4 plan did not test what the assignment asks. It told me to ask "what were you working
on?" without making sure I opened a new chat, and it expected Muse to open the injection link through watch.py fetch
without asking for it. In the first attempt I asked the question in the same chat (thread 6e423d6a), so Muse answered
from chat history, and Muse refused the link without calling fetch, so the metrics showed
blocked_non_allowlisted_urls 0 even though nothing was opened.

## 3. How I found it
Checking the screenshots against the assignment text: every message of attempt 1 had the same thread URL, Muse's
answer began with "in this chat we've been doing...", and the metrics output said blocked_non_allowlisted_urls 0. The
assignment asks for a new chat and for the link to be "blocked by fetch".

## 4. What I changed and why it works now
I redid the whole fixture run from empty state: the crash in one chat, the question in a new side chat (thread
6d88ee9e, the URL is visible in the screenshot), and an explicit prompt to check the link only with watch.py fetch,
which returned blocked true. The redo gives blocked_non_allowlisted_urls 1, and its saved state (gold-run2) shows the
run_start, interrupted and resume records of run 20261119-181649-2556. Other mistakes fixed on the way: the first live
sources failed from the Muse computer (Stooq bot check, legacy EDGAR HTTP 400) and were replaced by the Yahoo chart
API and data.sec.gov; long terminal pastes of patches got corrupted, so files were created in the editor and checked
by fingerprint; and Muse once retyped an old run ID in a scan output, so every claim in the report comes from
watch.py status, trace or the database, not from the agent's wording.
