# Shared state so main.py and routers/auth.py don't have to import each other
import os
from pathlib import Path
from fastapi import Request
from fastapi.templating import Jinja2Templates
# Point Jinja at the templates folder
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
# Demo login 
VALID_USERS = {os.getenv("AUTH_USER", "admin"): os.getenv("AUTH_PASS", "s3319")}
# In-memory fixtures carried over from HW2
fixtures = [
    {"id": 1, "fixtureTitle": "Spartans vs Bulldogs - Matchweek 5", "venue": "Spartan Soccer Complex", "status": "Scheduled"},
    {"id": 2, "fixtureTitle": "Lions vs Tigers - Matchweek 6", "venue": "City Arena", "status": "Scheduled"},
]
next_id = 3
def get_next_id():
    global next_id
    nid = next_id
    next_id += 1
    return nid
def current_user(request: Request):
    return request.session.get("user")  # username in session, or None
def filter_fixtures(q: str):
    query = q.strip().lower()
    if not query:
        return fixtures
    return [f for f in fixtures if query in f["fixtureTitle"].lower() or query in f["venue"].lower()]