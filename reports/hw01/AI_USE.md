# AI Use Disclosure

1. What I used an AI assistant for and what I did myself

I used AI mostly to help me plan things out, keep track of what was left, and write up the report. The actual running and checking was done by me I ran each part myself, checked my values, and took all the screenshots.

2. One AI-produced output that was wrong or unsuitable

In one of my early Part 2 runs, the tags came out messy. Instead of a clean "spartans vs bulldogs", they had brackets and quotes stuck on them like "['spartans vs bulldogs']".

3. How I detected or verified the problem

I was reading through the JSON in the terminal and noticed the tags weren't plain text and they were wrapped in brackets, which would've caused issues later on.

4. What I changed and why it works now

I added a small step that cleans those brackets and quotes off each tag. After that they came out clean every time, and I checked by running it again.