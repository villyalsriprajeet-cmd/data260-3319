# Shared {ok, data, error} response envelope for the domain MCP tools (reused by execute_tool in Part 4)
from typing import Any
def ok(data: Any) -> dict:
    """Success: data holds the result and error is null."""
    return {"ok": True, "data": data, "error": None}
def fail(code: str, message: str) -> dict:
    """Failure: data is null and error says what went wrong."""
    return {"ok": False, "data": None, "error": {"code": code, "message": message}}