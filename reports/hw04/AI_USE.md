# AI_USE — HW4

1. **What I used an AI assistant for and what I did myself:** I used an AI assistant to explain each step and help write the auth API, the React pages, the N+1 measurement script, the index migration and the RAG script. I ran every command myself on my Mac, checked the results in the terminal, Postman, MySQL and the browser, took all the screenshots, and wrote up the results.

2. **One AI output that was wrong/unsuitable:** The first RAG script crashed with a "segmentation fault" on my Mac as soon as it built the FAISS index. Earlier, the suggested `pip install cryptography` also failed because it tried to build the newest version from source on my x86 conda env.

3. **How I detected the problem / verified the result:** The crash showed up in the terminal right after the embeddings loaded and before any question ran, so the problem was loading FAISS and PyTorch together, not my questions. For cryptography, the error said there was no wheel and OpenSSL was missing. After each fix I re-ran the step and checked the output (all 6 questions and the k-sweep finished and saved to reports/hw04/raw; `import pymysql` connected to MySQL).

4. **What I changed and why it works now:** I set `KMP_DUPLICATE_LIB_OK=TRUE` and `OMP_NUM_THREADS=1` and imported sentence-transformers before faiss, so the two libraries share one OpenMP runtime and stop crashing. For cryptography I used `pip install --only-binary=:all: cryptography`, which installed a ready-made wheel (48.0.1) instead of building from source.