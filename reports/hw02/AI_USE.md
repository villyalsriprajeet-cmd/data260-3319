# AI Use Disclosure

What I used an AI assistant for and what I did myself

I used AI to help me plan out each part, talk through the LangGraph and Pydantic bits since they were new to me. The running and checking was all me I ran the FastAPI server, ran Ollama, did all the experiment runs on my laptop, and took the screenshots.

One AI-produced output that was wrong or unsuitable

An early version of the FastAPI home page crashed with a "TypeError: unhashable type: 'dict'" error. The template line was written the old way with the request inside the dictionary.

How I detected or verified the problem

I ran the server and hit the page, and the terminal showed the traceback pointing right at the TemplateResponse line.

What I changed and why it works now

I moved the request to be the first argument, so TemplateResponse(request, "home.html", {...}). That's what the newer version expects, and the page loaded fine after that.