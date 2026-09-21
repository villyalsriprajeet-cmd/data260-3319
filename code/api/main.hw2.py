from pathlib import Path
from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
PORT_BASE = 8619
app = FastAPI(title="Community Sports League Fixtures - HW2")
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# In-memory data store
fixtures = [
    {"id": 1, "fixtureTitle": "Spartans vs Bulldogs - Matchweek 5",
     "venue": "Spartan Soccer Complex", "status": "Scheduled"},
    {"id": 2, "fixtureTitle": "Lions vs Tigers - Matchweek 6",
     "venue": "City Arena", "status": "Scheduled"},
]
next_id = 3
def get_next_id():
    global next_id
    nid = next_id
    next_id += 1
    return nid


# HOME VIEW (also handles search)
@app.get("/")
def home(request: Request, q: str = ""):
    query = q.strip().lower()
    if query:
        visible = [
            f for f in fixtures
            if query in f["fixtureTitle"].lower() or query in f["venue"].lower()
        ]
    else:
        visible = fixtures

    return templates.TemplateResponse(
        request,
        "home.html",
        {"fixtures": visible, "q": q},
    )


# 1. ADD A RECORD
@app.post("/add")
def add_fixture(fixtureTitle: str = Form(...), venue: str = Form(...)):
    fixtures.append({
        "id": get_next_id(),
        "fixtureTitle": fixtureTitle,
        "venue": venue,
        "status": "Scheduled",
    })
    return RedirectResponse(url="/", status_code=303)


# 2. UPDATE RECORD WITH ID 1
@app.post("/update/1")
def update_fixture_1(fixtureTitle: str = Form(...), venue: str = Form(...)):
    for f in fixtures:
        if f["id"] == 1:
            f["fixtureTitle"] = fixtureTitle
            f["venue"] = venue
            break
    return RedirectResponse(url="/", status_code=303)


# 3. DELETE THE RECORD WITH THE HIGHEST ID
@app.post("/delete-highest")
def delete_highest():
    if fixtures:
        highest = max(fixtures, key=lambda f: f["id"])
        fixtures.remove(highest)
    return RedirectResponse(url="/", status_code=303)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT_BASE)