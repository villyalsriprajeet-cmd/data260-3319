# AI_USE — HW3

1.What I used an AI assistant for and what I did myself: I used an AI assistant to help set up the FastAPI auth app (Part 1) and the three-technique LlamaIndex script (Part 2), and to work through some setup errors. I picked the domain and corpus sources, wrote the five questions, committed them before running, and ran everything and took the screenshots myself.

2. **One AI output that was wrong/unsuitable:** The first version of my corpus downloader only pulled about 35 KB because the API it used dropped all the tables, which was under the 200 KB minimum. My first package install also broke on my Intel Mac because the numpy and torch versions clashed.

3. **How I detected the problem / verified the result:** I caught the corpus problem from the script's own "35.2 KB - under 200 KB" message, and the install problem from the import error in the terminal. For the questions, I made sure each expected answer in its file before committing questions.yaml.

4. **What I changed and why it works now:** I changed the downloader to grab the rendered page and keep the tables as text, which got me to 303 KB. After that everything ran and the model embedded at dim 384.