# HW8 Part 1 FastAPI service on port 8619
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from kafka_rpc import KafkaRPC
from pydantic import BaseModel, Field
from settings import PORT_BASE, PREFIX, REQUEST_TOPIC, RESPONSE_TOPIC, SID4, STUDENT_NAME, banner, log

RPC = KafkaRPC()


class FixtureRequest(BaseModel):
    correlation_id: str | None = Field(default=None, max_length=100)  # sent by the client
    operation: str = Field(min_length=1)
    data: dict = Field(default_factory=dict)


@asynccontextmanager
async def lifespan(app):
    banner("Part 1 FastAPI service")
    await RPC.start()
    log("API", "SERVER_STARTED", url=f"http://127.0.0.1:{PORT_BASE}")
    print(f"FastAPI server started at http://127.0.0.1:{PORT_BASE}", flush=True)
    yield
    await RPC.stop()


APP = FastAPI(title=f"{PREFIX} Fixture service over Kafka - HW8", lifespan=lifespan)


@APP.get("/")
async def home():
    return {
        "service": "fixture request/response over Kafka",
        "student": STUDENT_NAME,
        "sid4": SID4,
        "request_topic": REQUEST_TOPIC,
        "response_topic": RESPONSE_TOPIC,
    }


@APP.post("/fixtures/kafka")
async def fixture_operation(body: FixtureRequest):
    cid = body.correlation_id
    if not cid:
        cid = str(uuid.uuid4())  # only if the client did not send one
        log("API", "CORRELATION_ID_CREATED_BY_API", cid)
    log("API", "HTTP_REQUEST_RECEIVED", cid, operation=body.operation, data=body.data)
    response = await RPC.request(cid, body.operation, body.data)
    log("API", "RETURNING_HTTP_RESPONSE", cid, success=response.get("success"), response=response)
    status = 504 if response.get("error") == "Timed out waiting" else 200
    return JSONResponse(status_code=status, content=response)
