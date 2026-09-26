# Counts the SQL statements each request sends to MySQL (Part 3)
from contextvars import ContextVar
from sqlalchemy import event
from .database import engine
sql_counter = ContextVar("sql_counter", default=None)  # {"n": count} for the current request
@event.listens_for(engine, "before_cursor_execute")
def count_statement(conn, cursor, statement, parameters, context, executemany):
    box = sql_counter.get()
    if box is not None:
        box["n"] += 1  # one statement sent to the database