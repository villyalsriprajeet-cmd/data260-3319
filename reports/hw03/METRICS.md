# METRICS — HW3 Part 2 (Retrieval only RAG)

Domain 7 (community sports league fixtures). I used the all-MiniLM-L6-v2 embedding model (384-dim) with k = 5.

## Retrieval quality

| Technique | Chunks | Avg chunk length (chars) | Top-1 cosine | Mean@5 cosine | Recall@5 | Mean latency (ms) |
|---|---|---|---|---|---|---|
| token | 499 | 700.3 | 0.6642 | 0.5945 | 1.00 | 39.99 |
| semantic | 167 | 1821.3 | 0.5838 | 0.5151 | 1.00 | 47.81 |
| sentence_window | 3202 | 95.0 | 0.6491 | 0.5153 | 1.00 | 147.70 |

Recall@5 is at the document level (did the right source file show up in the top 5). All three got 1.00, so the real difference is in the cosine scores and the speed.

## A confident but wrong hit

On q3 (who won the 2023-24 EFL Championship), token chunking put a chunk at rank 1 with a high score of 0.594, but that chunk was just a long list of past seasons with no answer in it, and its actual cosine was only 0.21. I think it scored high because it's full of the league name and lots of season numbers, so it looks a lot like the question even though the answer isn't there.

## Observations

Token chunking worked best for me. Its approx 700 character chunks are big enough to hold an answer with some context but still stay focused, so it got the best cosine scores and was also the fastest. Semantic chunking made a few very large chunks, which seemed to bury the answer sentence inside a lot of other text and pulled the scores down. Sentence window split everything into single sentences, so a matching sentence can score well, but most chunks are tiny fragments like headings or citations, and searching that many vectors made it clearly the slowest. One thing I noticed across all three is that the Wikipedia text has citation clutter that keeps showing up as confident but useless hits.

## Conclusion

For this corpus I'd go with token chunking. It had the best top 1 and mean cosine, full recall, and the lowest latency, and its medium sized chunks kept enough context without drowning the answer. Semantic chunks were too big and sentence-window chunks were too small and too slow.

## AI_USE

1. I used an AI assistant to help set up the FastAPI auth app and the three-technique LlamaIndex script, and to work through some setup errors. I picked the domain and sources, wrote the five questions, committed them before running, and ran everything myself.
2. The first version of my corpus downloader only pulled about 35 KB because the API it used dropped all the tables, which was under the 200 KB minimum.
3. I caught the corpus problem from the script's own "35.2 KB — under 200 KB" message. For the questions.
4. I changed the downloader to grab the rendered page and keep the tables as text, which got me to 303 KB.