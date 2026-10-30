# HW8 Part 1: validate and run CREATE_FIXTURE and GET_FIXTURE
import re
import uuid

from settings import PREFIX, RESPONSE_TOPIC

CODE_PATTERN = re.compile(r"^FX-\d{5}$")  # same code format as HW5
REQUIRED_FIELDS = ("fixture_title", "fixture_code", "venue", "tickets_available", "home_team_id")


def text_error(data, name, max_len):
    value = data.get(name)
    if not isinstance(value, str) or not value.strip():
        return f"{name} is required and must be a non-empty string"
    if len(value.strip()) > max_len:
        return f"{name} must be at most {max_len} characters"
    return None


def int_error(data, name, minimum):
    value = data.get(name)
    if isinstance(value, bool) or not isinstance(value, int):  # True/False also count as int
        return f"{name} is required and must be an integer"
    if value < minimum:
        return f"{name} must be >= {minimum}"
    return None


def validate_fixture(data):
    missing = [f for f in REQUIRED_FIELDS if f not in data or data[f] is None]
    if missing:
        return f"Missing required field(s): {', '.join(missing)}"
    unknown = sorted(set(data) - set(REQUIRED_FIELDS))
    if unknown:
        return f"Unknown field(s): {', '.join(unknown)}"
    error = text_error(data, "fixture_title", 200) or text_error(data, "venue", 200)
    if error:
        return error
    if not isinstance(data["fixture_code"], str) or not CODE_PATTERN.match(data["fixture_code"].strip()):
        return "fixture_code must look like FX-12345"
    return int_error(data, "tickets_available", 0) or int_error(data, "home_team_id", 1)


def create_fixture(data, fixtures):
    error = validate_fixture(data)
    if error:
        return {"success": False, "error": error}
    code = data["fixture_code"].strip()
    if any(f["fixture_code"] == code for f in fixtures.values()):
        return {"success": False, "error": f"fixture_code {code} already exists"}
    fixture_id = str(uuid.uuid4())  # id made by the worker
    fixtures[fixture_id] = {
        "fixture_id": fixture_id,
        "fixture_title": data["fixture_title"].strip(),
        "fixture_code": code,
        "venue": data["venue"].strip(),
        "tickets_available": data["tickets_available"],
        "home_team_id": data["home_team_id"],
    }
    return {"success": True, "fixture_id": fixture_id, "message": "Fixture created"}


def get_fixture(data, fixtures):
    fixture_id = data.get("fixture_id")
    if not isinstance(fixture_id, str) or not fixture_id.strip():
        return {"success": False, "error": "fixture_id is required"}
    if fixture_id not in fixtures:
        return {"success": False, "error": "Fixture not found"}
    return {"success": True, "fixture": dict(fixtures[fixture_id])}


def envelope_error(message):
    if not isinstance(message, dict):
        return "Request must be a JSON object"
    missing = [k for k in ("correlation_id", "reply_to", "operation", "data") if not message.get(k)]
    if missing and missing != ["data"]:
        return f"Missing required field(s): {', '.join(missing)}"
    if not str(message["reply_to"]).startswith(f"{PREFIX}_"):
        return f"reply_to must be a {PREFIX}_ topic"
    if not isinstance(message.get("data"), dict):
        return "data must be a JSON object"
    return None


def reply_topic(message):
    reply_to = message.get("reply_to") if isinstance(message, dict) else None
    ok = isinstance(reply_to, str) and reply_to.startswith(f"{PREFIX}_")
    return reply_to if ok else RESPONSE_TOPIC  # only reply on our own topics


def process_request(message, fixtures):
    cid = message.get("correlation_id") if isinstance(message, dict) else None
    operation = message.get("operation") if isinstance(message, dict) else None
    error = envelope_error(message)
    if error:
        result = {"success": False, "error": error}
    elif operation == "CREATE_FIXTURE":
        result = create_fixture(message["data"], fixtures)
    elif operation == "GET_FIXTURE":
        result = get_fixture(message["data"], fixtures)
    else:
        result = {"success": False, "error": "Unknown operation"}
    return {"correlation_id": cid, "operation": operation, **result}  # same correlation_id goes back
