# HW7 - League Fixtures API (Domain 7): JWT + roles on MySQL fixtures/teams, MongoDB API from HW6, port 8619
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError, WriteError

from .mongo_db import ensure_collections
from .perf import sql_counter
from .routers.auth import router as auth_router
from .routers.chat import router as chat_router
from .routers.docs import router as docs_router
from .routers.fixtures import router as fixtures_router
from .routers.teams import router as teams_router

PORT_BASE = 8619


@asynccontextmanager
async def lifespan(app):
    try:
        ensure_collections()  # create the Mongo collections and rules on startup
    except PyMongoError as exc:
        print(f"WARNING: MongoDB not ready: {exc}")
    yield


app = FastAPI(title="Community Sports League Fixtures - HW7", lifespan=lifespan)
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
    sql_counter.set(box)
    response = await call_next(request)
    response.headers["X-SQL-Count"] = str(box["n"])  # statements this request ran
    return response


app.include_router(auth_router)  # HW7: POST /auth/login, GET /auth/me (JWT)
app.include_router(fixtures_router)  # CRUD on /fixtures
app.include_router(teams_router)  # CRUD on /teams and /teams/{id}/fixtures
app.include_router(docs_router)  # HW6 Part 1: CRUD on /api/fixtures (MongoDB)
app.include_router(chat_router)  # HW6 Part 2: /api/chat, /api/memory, /api/aggregate


@app.exception_handler(WriteError)
async def mongo_write_error(request, exc):
    code = 422 if exc.code == 121 else 500  # 121 = the collection validator rejected the document
    return JSONResponse(status_code=code, content={"detail": f"Database rejected the write: {exc}"})


@app.exception_handler(ServerSelectionTimeoutError)
async def mongo_down(request, exc):
    return JSONResponse(status_code=503, content={"detail": "MongoDB is not reachable"})


@app.exception_handler(PyMongoError)
async def mongo_error(request, exc):
    return JSONResponse(status_code=500, content={"detail": "Database error"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT_BASE)
