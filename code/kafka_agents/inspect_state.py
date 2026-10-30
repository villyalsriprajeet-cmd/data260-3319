# HW8 Part 3: what each agent started and finished (idempotency store)
# usage: python inspect_state.py [--cid ID]
import argparse
import sqlite3

from common import STATE_DB, show_banner

QUERY = (
    "SELECT s.agent, s.cid, s.at, d.at FROM started s LEFT JOIN done d ON s.agent = d.agent AND s.cid = d.cid "
    "WHERE (? IS NULL OR s.cid = ?) ORDER BY s.at"
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cid")
    args = parser.parse_args()
    show_banner("inspect_state (idempotency store)")
    rows = sqlite3.connect(STATE_DB).execute(QUERY, (args.cid, args.cid)).fetchall() if STATE_DB.exists() else []
    for agent, cid, started, done in rows:
        print(f"{agent:<9} {cid}  started={started}  finished={done or 'NEVER (lost or still running)'}")
    print(f"\n{len(rows)} row(s)")
