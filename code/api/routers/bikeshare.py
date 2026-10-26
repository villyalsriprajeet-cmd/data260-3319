# HW7 Part 4: bike share advisor UI (GET /bikeshare) and run endpoint (POST /bikeshare/run)
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

PAGE = Path(__file__).resolve().parents[1] / "templates" / "bikeshare.html"
DEFAULT_URL = "https://capitalbikeshare.com/pricing"
router = APIRouter(prefix="/bikeshare", tags=["Bike-share advisor (HW7 Part 4)"])


@router.get("", response_class=HTMLResponse)
def page():
    return PAGE.read_text(encoding="utf-8").replace("{{DEFAULT_URL}}", DEFAULT_URL)


@router.post("/run")
def run(
    trips: UploadFile = File(...),
    url: str = Form(DEFAULT_URL),
    prompt_defense: bool = Form(True),
    tool_defense: bool = Form(True),
):
    from ...bikeshare.agent import run_bikeshare  # imported here so the API starts even without LangGraph

    if not (trips.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="upload a .csv file")
    scenario = re.sub(r"[^A-Za-z0-9_-]", "_", Path(trips.filename).stem)[:40] or "upload"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "uploaded.csv"
        path.write_bytes(trips.file.read())
        try:
            return run_bikeshare(path, url.strip(), scenario, prompt_defense=prompt_defense, tool_defense=tool_defense)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"could not read the CSV: {exc}")
