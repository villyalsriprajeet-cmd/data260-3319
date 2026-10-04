# HW5 Part 2B: "league" MCP server over s3319_rel with 3 tools (search, detail, aggregate), run over STDIO; Part 3 adds retries
import logging
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse
try:
    from mcp.server.fastmcp import FastMCP  
except ImportError:
    from mcp.server.mcpserver import MCPServer as FastMCP 
from envelope import fail, ok
from faults import VERIFY_SEED, FaultInjector
from retry import RetryExhausted, RetryPolicy, TransientError, retry_call
# Constants
ENV_FILE = Path(__file__).resolve().parents[1] / "api" / ".env"  # same DATABASE_URL as the FastAPI app
CODE_PATTERN = re.compile(r"^FX-\d{5}$")  # fixture codes look like FX-00001
DB_TIMEOUT = 5  # seconds each attempt may wait for MySQL (connect and read)
RETRY_POLICY = RetryPolicy(max_attempts=3, base_delay=0.1, max_delay=1.0)  
NO_RETRY_CODES = {1044, 1045, 1049}  # access denied / unknown database: retrying cannot help
# Logging goes to stderr because stdout carries the JSON-RPC messages
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("league")
# Initialize the FastMCP server
mcp = FastMCP("league")
def read_database_url() -> str:
    """Take DATABASE_URL from the environment, else from code/api/.env."""
    url = os.getenv("DATABASE_URL")
    if not url and ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("DATABASE_URL="):
                url = line.split("=", 1)[1].strip()
    if not url:
        raise RuntimeError(f"DATABASE_URL not set and not found in {ENV_FILE}")
    return url
class MySQLStore:
    """Read-only access to fixtures and teams in s3319_rel."""
    def __init__(self, url: str):
        parts = urlparse(url)  # mysql+pymysql://user:password@host:port/db
        self.config = {"host": parts.hostname or "localhost", "port": parts.port or 3306,
                       "user": unquote(parts.username or ""), "password": unquote(parts.password or ""),
                       "database": parts.path.lstrip("/")}
        self.fault = None  # optional FaultInjector used for the Part 3 tests
    def query(self, sql: str, params: tuple) -> list[dict]:
        if self.fault:
            self.fault()  # may raise TransientError on purpose
        import pymysql  # imported here so the server still starts and lists tools without it
        conn = pymysql.connect(**self.config, connect_timeout=DB_TIMEOUT, read_timeout=DB_TIMEOUT,
                               cursorclass=pymysql.cursors.DictCursor)
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)  # %s placeholders, so user input is never pasted into the SQL
                return list(cur.fetchall())
        finally:
            conn.close()
    def search_fixtures(self, text: str, limit: int) -> list[dict]:
        like = f"%{text}%"
        return self.query(
            "SELECT f.fixture_code, f.fixture_title, f.venue, f.tickets_available, t.name AS home_team "
            "FROM fixtures f JOIN teams t ON t.id = f.home_team_id "
            "WHERE f.fixture_title LIKE %s OR f.venue LIKE %s ORDER BY f.id LIMIT %s", (like, like, limit))
    def get_fixture(self, code: str) -> dict | None:
        rows = self.query(
            "SELECT f.id, f.fixture_code, f.fixture_title, f.venue, f.tickets_available, f.created_at, "
            "t.id AS team_id, t.name AS team_name, t.city AS team_city, t.contact_email AS team_email "
            "FROM fixtures f JOIN teams t ON t.id = f.home_team_id WHERE f.fixture_code = %s", (code,))
        return rows[0] if rows else None
    def tickets_by_city(self, top_n: int) -> list[dict]:
        return self.query(
            "SELECT t.city, COUNT(*) AS fixtures, SUM(f.tickets_available) AS total_tickets, "
            "ROUND(AVG(f.tickets_available), 1) AS avg_tickets "
            "FROM fixtures f JOIN teams t ON t.id = f.home_team_id "
            "GROUP BY t.city ORDER BY total_tickets DESC, t.city LIMIT %s", (top_n,))
_store = None
def get_store():
    """Create the store on first use so a missing DB shows up as an envelope error, not a crash."""
    global _store
    if _store is None:
        _store = MySQLStore(read_database_url())
        rate = float(os.getenv("LEAGUE_FAULT_RATE", "0"))  # optional failure rate for testing in Inspector
        if rate > 0:
            _store.fault = FaultInjector(rate, int(os.getenv("VERIFY_SEED", VERIFY_SEED)))
    return _store
def is_retryable(exc: Exception) -> bool:
    """Retry lost connections and timeouts, not mistakes that would fail again."""
    if isinstance(exc, TransientError):
        return True
    if type(exc).__name__ in ("OperationalError", "InterfaceError"):  # pymysql connection problems
        return not (exc.args and exc.args[0] in NO_RETRY_CODES)
    return False
def run_query(action) -> dict:
    """Run one store call with retries and wrap any database problem in the envelope."""
    try:
        data, _ = retry_call(lambda: action(get_store()), RETRY_POLICY, is_retryable)
        return ok(data)
    except RetryExhausted as exc:
        return fail("UNAVAILABLE", f"database still failing after {exc.attempts} attempts: {exc.last_error}")
    except ModuleNotFoundError:
        logger.error("pymysql is not installed")
        return fail("DB_ERROR", "pymysql is not installed; start with: mcp dev league_server.py --with pymysql")
    except Exception as exc:
        logger.error("database error: %s", exc)
        return fail("DB_ERROR", f"database request failed: {exc}")
def to_json(row: dict) -> dict:
    """Make MySQL values JSON friendly (datetime and Decimal become plain values)."""
    out = {}
    for key, value in row.items():
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        elif type(value).__name__ == "Decimal":
            value = int(value) if value == int(value) else float(value)  # SUM gives Decimal, keep whole numbers as int
        out[key] = value
    return out
@mcp.tool()
async def search_fixtures(query: str, limit: int = 10) -> dict:
    """Search fixtures whose title or venue contains the text.

    Args:
        query: Text to look for, e.g. "Hawks" or "Field" (at least 2 characters)
        limit: Maximum number of fixtures to return (1-50)
    """
    text = query.strip()
    if len(text) < 2:
        return fail("INVALID_INPUT", "query must be at least 2 characters")
    if not 1 <= limit <= 50:
        return fail("INVALID_INPUT", f"limit must be between 1 and 50, got {limit}")
    logger.info("search_fixtures query=%r limit=%d", text, limit)
    result = run_query(lambda s: [to_json(r) for r in s.search_fixtures(text, limit)])
    if result["ok"]:
        result["data"] = {"count": len(result["data"]), "results": result["data"]}
    return result
@mcp.tool()
async def fixture_details(fixture_code: str) -> dict:
    """Look up one fixture by its code, with its home team.

    Args:
        fixture_code: Fixture code in the form FX-00001
    """
    code = fixture_code.strip().upper()
    if not CODE_PATTERN.match(code):
        return fail("INVALID_INPUT", f"fixture_code must look like FX-00001, got '{fixture_code}'")
    logger.info("fixture_details code=%s", code)
    result = run_query(lambda s: s.get_fixture(code))
    if result["ok"] and result["data"] is None:
        return fail("NOT_FOUND", f"no fixture with code {code}")
    if result["ok"]:
        result["data"] = to_json(result["data"])
    return result
@mcp.tool()
async def tickets_by_city(top_n: int = 5) -> dict:
    """Aggregate: fixtures and tickets available per home-team city, highest total first.

    Args:
        top_n: How many cities to return (1-20)
    """
    if not 1 <= top_n <= 20:
        return fail("INVALID_INPUT", f"top_n must be between 1 and 20, got {top_n}")
    logger.info("tickets_by_city top_n=%d", top_n)
    return run_query(lambda s: [to_json(r) for r in s.tickets_by_city(top_n)])
def main() -> None:
    mcp.run(transport="stdio") 
if __name__ == "__main__":
    main()