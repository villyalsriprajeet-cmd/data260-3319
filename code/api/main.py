# HW3 - Community Sports League Fixtures (Domain 7), runs on port 8619
import os
from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from .store import fixtures, get_next_id, current_user
from .routers.auth import router as auth_router

PORT_BASE = 8619  
SECRET_KEY = os.getenv("SECRET_KEY", "hw3-dev-only-secret-s3319")
SESSION_MAX_AGE = int(os.getenv("SESSION_MAX_AGE", "900"))  # idle timeout in seconds
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "1") not in ("0", "false", "False")  # Secure attribute
app = FastAPI(title="Community Sports League Fixtures - HW3")
# Signed session cookie: HttpOnly and Secure and SameSite
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="fixtures_session",
    max_age=SESSION_MAX_AGE,
    same_site="lax",
    https_only=COOKIE_SECURE,
)
app.include_router(auth_router)  # home, login, dashboard, logout
@app.post("/add")
def add_fixture(request: Request, fixtureTitle: str = Form(...), venue: str = Form(...)):
    if not current_user(request):  # only logged in users can change data
        return RedirectResponse(url="/login", status_code=303)
    fixtures.append({"id": get_next_id(), "fixtureTitle": fixtureTitle, "venue": venue, "status": "Scheduled"})
    return RedirectResponse(url="/dashboard", status_code=303)
@app.post("/update/1")
def update_fixture_1(request: Request, fixtureTitle: str = Form(...), venue: str = Form(...)):
    if not current_user(request):
        return RedirectResponse(url="/login", status_code=303)
    for f in fixtures:
        if f["id"] == 1:
            f["fixtureTitle"] = fixtureTitle
            f["venue"] = venue
            break
    return RedirectResponse(url="/dashboard", status_code=303)
@app.post("/delete-highest")
def delete_highest(request: Request):
    if not current_user(request):
        return RedirectResponse(url="/login", status_code=303)
    if fixtures:
        fixtures.remove(max(fixtures, key=lambda f: f["id"]))
    return RedirectResponse(url="/dashboard", status_code=303)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT_BASE)