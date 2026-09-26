# HW4 - Community Sports League Fixtures API (Domain 7) for the React client, runs on port 8619
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers.auth import router as auth_router
from .routers.fixtures import router as fixtures_router
from .perf import sql_counter
PORT_BASE = 8619
app = FastAPI(title="Community Sports League Fixtures - HW4")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # the React dev server
    allow_credentials=True,  # allow the session cookie on cross origin calls
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.middleware("http")
async def add_sql_count(request, call_next):
    box = {"n": 0}
    sql_counter.set(box)  # fresh counter for this request
    response = await call_next(request)
    response.headers["X-SQL-Count"] = str(box["n"])  # statements this request ran
    return response
app.include_router(auth_router)  # POST /login
app.include_router(fixtures_router)  # CRUD on /fixtures
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT_BASE)