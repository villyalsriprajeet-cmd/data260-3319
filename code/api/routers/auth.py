# HW3 Part 1 auth routes (home, login, dashboard, logout)
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from ..store import templates, current_user, filter_fixtures, VALID_USERS
router = APIRouter()
@router.get("/")
def home(request: Request, q: str = ""):
    return templates.TemplateResponse(request, "home.html", {"user": current_user(request), "fixtures": filter_fixtures(q), "q": q})
@router.get("/login")
def login_page(request: Request, error: int = 0):
    if current_user(request):  # already logged in, skip the form
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"user": None, "error": bool(error)})
@router.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if VALID_USERS.get(username) == password:
        request.session["user"] = username  # start the session
        return RedirectResponse(url="/dashboard", status_code=303)
    return RedirectResponse(url="/login?error=1", status_code=303)  # wrong credentials
@router.get("/dashboard")
def dashboard(request: Request, q: str = ""):
    if not current_user(request):  # protected: must be logged in
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "dashboard.html", {"user": current_user(request), "fixtures": filter_fixtures(q), "q": q})
@router.get("/logout")
def logout(request: Request):
    request.session.clear()  # destroy the session
    return RedirectResponse(url="/", status_code=303)