# HW5 AI Use

## 1. What I used AI for and what I did myself
I used AI as a helper in this homework. It helped me plan each part, explained MCP, retries and the agent loop, and helped me debug setup problems. I implemented the code and then ran and tested it on my own laptop. I ran every command myself, took every screenshot, checked the outputs against my own database, and made the final decisions. All numbers in this report come from my own runs.

## 2. One AI output that was wrong
The first version of meals_server.py did not start with mcp dev. The Inspector showed "Failed to spawn", because mcp dev installs the newest mcp package, and in that version FastMCP has a different name.

## 3. How I found it
I ran the command mcp dev uses in the background, uv run --with mcp mcp run code/mcp_servers/meals_server.py, on its own in the terminal, and it showed the real import error. I also checked the tickets_by_city numbers against my own MySQL query.

## 4. What I changed and why it works now
I changed the import so it works with both versions of the mcp package. After that, mcp dev connected straight away and all four tools worked in the Inspector.